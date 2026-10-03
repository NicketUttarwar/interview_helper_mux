"""One dispatch door for the driver walk (plan §5.3) — caps, no-delta, attempt memo.

The conductor path honoured ``check_dispatch`` (``audio_probe_build`` halted at 3/3
with ``limit_exhausted.json``); the driver walk did not bite, because
``count_identity`` returns 0 while a stage is not done and ``junction_snip_qa``
unmarks ``.stage_done/mix`` between iterations. So ``mix`` reached 28 dispatches
against ``max_mix_cycles: 3``. This module is the missing door.

Per **D1** a refusal is not an error: it records a defect and the walk advances
while ``master.wav`` is reachable. Nothing here raises.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from interview_mux.run_context import RunContext

# Gate pseudo-stages are operator business, never the door's: G0 / G1 / G-Publish
# and the partial-auto pause gates must reach their existing handlers untouched in
# all three postures. Gate ids that are *also* pipeline stages (``missing_framing``)
# are deliberately absent — the gate is enforced by the walk's own break, and
# missing_framing is one of the M2 thrash stages the door exists to bound.
GATE_STAGES: frozenset[str] = frozenset(
    {
        "transcript_review",
        "g1_vo_pickup",
        "g_publish",
        "gap_framing",
        "stage_reuse",
        "write_approval",
        "vo_ingest",
    }
)


@dataclass(frozen=True)
class DispatchVerdict:
    allowed: bool
    reason: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def refused(self) -> bool:
        return not self.allowed


ALLOWED = DispatchVerdict(True)


def door_enabled() -> bool:
    raw = str(os.environ.get("MUX_DISPATCH_DOOR") or "").strip().lower()
    if not raw:
        return True
    return raw in {"1", "true", "yes", "on"}


def door_applies(ctx: RunContext, *, layer: str = "dispatch") -> bool:
    """The door governs driver-issued dispatches only.

    A human clicking Re-run in the GUI is a decision, not thrash; the existing
    ``check_dispatch`` caps still cover that path. The door binds the automation
    driver (full-auto / partially-accelerated) and the seed walk.
    """
    if not door_enabled():
        return False
    if getattr(ctx, "_homunculus_seed_walk", False):
        return True
    try:
        from interview_mux.automation_run import (
            automation_driver_env_enabled,
            automation_driver_run,
        )

        if automation_driver_env_enabled():
            return True
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        return bool(automation_driver_run(meta if isinstance(meta, dict) else {}))
    except Exception:
        return False


_PREREQ_ATTR = "_seed_prereq_demanded"


def seed_prereq_demanded(ctx: RunContext) -> str:
    """The prerequisite the walk is running on the seed order's demand, if any."""
    return str(getattr(ctx, _PREREQ_ATTR, "") or "")


class demand_seed_prereq:
    """Context manager: mark ``stage`` as demanded by the seed order while it runs."""

    def __init__(self, ctx: RunContext, stage: str) -> None:
        self.ctx = ctx
        self.stage = str(stage or "")
        self.prev = ""

    def __enter__(self) -> "demand_seed_prereq":
        self.prev = seed_prereq_demanded(self.ctx)
        try:
            setattr(self.ctx, _PREREQ_ATTR, self.stage)
        except Exception:
            pass
        return self

    def __exit__(self, *exc: Any) -> None:
        try:
            if self.prev:
                setattr(self.ctx, _PREREQ_ATTR, self.prev)
            elif hasattr(self.ctx, _PREREQ_ATTR):
                delattr(self.ctx, _PREREQ_ATTR)
        except Exception:
            pass


def evaluate_dispatch(
    ctx: RunContext,
    stage: str,
    *,
    source: str = "driver",
    layer: str = "dispatch",
) -> DispatchVerdict:
    """Decide whether this dispatch may proceed.

    Side effect (once per RunContext): reclaim attempt budget when the product
    fingerprint flips so Partial / full-auto resume after a real code patch is not
    stranded behind pre-fix ``max_invokes`` / attempt_memo (DP-BUD1 A).

    ``layer="walk"`` additionally consults the attempt memo, because "do not
    re-offer" is a property of the walk, not of an explicit re-dispatch.
    """
    sid = str(stage or "").strip()
    if not sid:
        return ALLOWED
    if sid in GATE_STAGES:
        return ALLOWED
    if not door_applies(ctx, layer=layer):
        return ALLOWED

    if not getattr(ctx, "_budget_product_reclaim_checked", False):
        try:
            from interview_mux.identical_failures import reclaim_budget_on_product_flip

            reclaim_budget_on_product_flip(ctx)
        except Exception:
            pass
        try:
            setattr(ctx, "_budget_product_reclaim_checked", True)
        except Exception:
            pass

    from interview_mux.homunculus.budget import dispatch_cap_refusal

    try:
        cap_hit = dispatch_cap_refusal(ctx, sid, kind="stage")
    except Exception:
        cap_hit = None
    if cap_hit:
        reason, detail = cap_hit
        return DispatchVerdict(False, reason, detail)

    from interview_mux.dispatch_delta import memo_skip, no_delta_refusal

    # A stage the seed-order gate has just named as an incomplete prerequisite
    # is run, not re-argued (ISSUES 127). "Inputs unchanged since the last
    # success" and "already offered at this state" both assume the last result
    # stands; the gate has ruled that it does not, and refusing here left the
    # consumer blocked on a prerequisite the door would not let run. The caps
    # above still apply, and the walk asks once per prerequisite.
    if seed_prereq_demanded(ctx) == sid:
        return ALLOWED

    try:
        delta_hit = no_delta_refusal(ctx, sid)
    except Exception:
        delta_hit = None
    if delta_hit:
        reason, detail = delta_hit
        return DispatchVerdict(False, reason, detail)

    if layer == "walk":
        try:
            memo_hit = memo_skip(ctx, sid)
        except Exception:
            memo_hit = None
        if memo_hit:
            reason, detail = memo_hit
            return DispatchVerdict(False, reason, detail)
    return ALLOWED


def refuse_dispatch(
    ctx: RunContext,
    stage: str,
    verdict: DispatchVerdict,
    *,
    source: str = "driver",
) -> dict[str, Any]:
    """Route a refusal to the defect ledger + reachability. Never raises."""
    from interview_mux.defect_ledger import record_defect
    from interview_mux.dispatch_delta import record_attempt
    from interview_mux.ship_reachability import ship_reachable

    detail = dict(verdict.detail or {})
    artifact = ""
    try:
        from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

        artifact = str(STAGE_ARTIFACT_DISK_PATHS.get(stage) or "")
    except Exception:
        artifact = ""
    # A no-delta refusal cannot degrade the ship bar: the guard only fires when the
    # previous run of this stage succeeded and its outputs are still on disk, so the
    # artifact the dispatch would produce already exists. A cap or memo refusal means
    # the stage did not produce, which is a real ship-bar risk on the critical path.
    ship_bar = False if verdict.reason == "no_delta" else None
    defect = record_defect(
        ctx,
        stage=stage,
        blocker=verdict.reason,
        artifact=artifact,
        ship_bar=ship_bar,
        detail={**detail, "source": source},
    )
    try:
        record_attempt(ctx, stage, outcome="refused", source=source)
    except Exception:
        pass
    try:
        from interview_mux.homunculus.ledger import append_ledger

        append_ledger(
            ctx,
            {
                "kind": "stage",
                "identity": stage,
                "status": "refused",
                "source": source,
                "refusal": verdict.reason,
                "detail": detail,
            },
        )
    except Exception:
        pass
    # DP-BUD1 A: runner must not emit hollow "Finished" when outputs are still missing.
    try:
        refuses = getattr(ctx, "_dispatch_refuses", None)
        if not isinstance(refuses, list):
            refuses = []
            setattr(ctx, "_dispatch_refuses", refuses)
        refuses.append(
            {
                "stage": str(stage or ""),
                "reason": str(verdict.reason or ""),
                "source": str(source or ""),
            }
        )
    except Exception:
        pass
    reach = ship_reachable(ctx)
    # FLOW-critical with missing primary: pin resume — never leapfrog (NAP exec_13174).
    pin_instead = False
    try:
        from interview_mux.llm_flow_hardening import FLOW_CRITICAL_LLM_STAGES
        from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
        from interview_mux.homunculus.agenda import stage_outputs_present

        if str(stage or "") in FLOW_CRITICAL_LLM_STAGES:
            rel = STAGE_ARTIFACT_DISK_PATHS.get(str(stage or ""))
            missing_primary = bool(rel) and not ctx.artifact_exists(rel)
            if missing_primary or not stage_outputs_present(ctx, str(stage or "")):
                pin_instead = True
    except Exception:
        pin_instead = False
    try:
        if pin_instead:
            ctx.log(
                f"dispatch refused {stage}: {verdict.reason} — pinning resume "
                f"(FLOW-critical primary missing; ship reachable={reach.reachable})",
                level="warning",
                stage=stage,
            )
        else:
            ctx.log(
                f"dispatch refused {stage}: {verdict.reason} — advancing "
                f"(ship reachable={reach.reachable} certain={reach.certain})",
                level="warning",
                stage=stage,
            )
    except Exception:
        pass
    out = {
        "refused": True,
        "reason": verdict.reason,
        "defect_id": defect.get("defect_id"),
        "reachability": reach.as_row(),
    }
    if pin_instead:
        out["pin_resume"] = str(stage or "")
        out["no_advance"] = True
    return out


def note_dispatch_outcome(
    ctx: RunContext,
    stage: str,
    *,
    outcome: str,
    source: str = "driver",
) -> None:
    """Record a dispatch outcome for the delta guard / memo. Never raises."""
    if not door_applies(ctx):
        return
    try:
        from interview_mux.dispatch_delta import record_attempt

        record_attempt(ctx, stage, outcome=outcome, source=source)
    except Exception:
        return
    if outcome != "done":
        return
    try:
        from interview_mux.defect_ledger import resolve_stage_defects

        resolve_stage_defects(ctx, stage, reason="stage_completed")
    except Exception:
        pass
