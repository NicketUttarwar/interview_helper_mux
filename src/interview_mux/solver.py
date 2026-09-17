"""Deterministic admissible-set solver (plan §2.1, §6.1) — observing, not deciding.

A turn budget is the symptom of *LLM owns control flow*. This module is the
replacement: a pure function from on-disk state to "which stages are runnable right
now". Control flow becomes a function of state rather than of model output, so there
is nothing to bound.

**Nothing here decides a run today**, and the two switches are deliberately asymmetric:

* ``shadow_logging_enabled()`` — **default ON**. The walk reports every stage-selection
  decision to ``observe_walk_choice`` and the comparison is appended to
  ``operator/solver_decision.jsonl``. Observe and record; it cannot select.
* ``solver_authoritative()`` — **default OFF, and it should stay off.** This is the one
  flag that lets the solver choose. ``authoritative_sequence`` is built and tested
  (``tests/test_solver_authoritative.py``) so promotion is one flag rather than a
  rewrite, but flipping it is **not recommended yet**: only the ``prepare`` contract
  group is strict, 39 of 72 stages declare no hard inputs and therefore defer, and no
  real run has yet produced shadow evidence. The bar is *zero non-deferred
  disagreements across a real run* plus the downstream contract groups reaching strict.

``tests/test_solver_inert.py`` pins what remains true with authority off: the walk's
chosen stage sequence is identical whether the shadow hook is armed, silenced or
outright broken.

Admissibility (plan §2.1, with the §8.1-§8.3 terms the rule was missing)::

    admissible(stage, posture) ⟺
          tier(stage) ∈ PIPELINE_TIERS                    # §8.4 — 72, not 90
      ∧   not done(stage)                                 # §8.5 — marker ∧ outputs
      ∧   gate_clear(stage, posture)                      # §8.1 / §8.2
      ∧   ∀ hard input d where when(d) holds :
              committed(d.path) ∧ sufficient(d)           # §8.6 — committed, not staged
      ∧   ∀ output o : write_permitted(stage, o.path)      # §4.2
      ∧   lease permits acting                            # §8.3
      ∧   evaluate_dispatch(...) allows it                # observing only — see below

The last two terms are the two places where "inadmissible" and "must not be offered"
come apart, so both are qualified where they are applied:

* The **door** term is dropped while the solver is authoritative. A door refusal has
  side effects the walk owns — the defect ledger row and the ship-severance halt — and
  those only run on a stage the walk is actually handed (``evaluate_stage`` step 8).
* The **lease** is a run-level condition. It empties the set per stage so the halt panel
  has something to render, but ``authoritative_sequence`` reports it as a *pause*, never
  as the §2.1 structural halt (``Decision.halt_kind``).

**Partial contract truth is a first-class answer.** Contract population is still in
flight (45/90 hollow at plan time), so a check the contract cannot answer yields
``unknown`` — recorded on the verdict, never converted into an exclusion. A hollow
contract can therefore never make a stage look blocked; it only makes the verdict
non-``confident``, i.e. "defer to the walk". Only a *positive* blocker excludes.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from interview_mux.run_context import RunContext
from interview_mux.stage_contract import PIPELINE_TIERS

SOLVER_DECISION_REL = "operator/solver_decision.jsonl"

# Cap the JSONL so a long full-auto run cannot grow it without bound.
MAX_DECISION_ROWS = 400

Posture = Literal["manual", "partially-accelerated", "full-auto"]

MANUAL: Posture = "manual"
PARTIAL: Posture = "partially-accelerated"
FULL_AUTO: Posture = "full-auto"
POSTURES: tuple[Posture, ...] = (MANUAL, PARTIAL, FULL_AUTO)

# Shadow verdicts (§6.2). `DEFER` is a third value on purpose: while 39 of the 72
# stages declare no hard inputs, folding "the solver declines to have an opinion" into
# "the solver disagrees" would make the disagreement count meaningless — and the
# promotion gate is *zero non-deferred disagreements*, so the two must stay apart.
AGREE = "agree"
DISAGREE = "disagree"
DEFER = "defer"
SHADOW_VERDICTS: tuple[str, ...] = (AGREE, DISAGREE, DEFER)

# Why the sequence stopped. The distinction is operator-facing: a structural halt says
# "this run cannot proceed until state changes", a lease pause says "another session is
# driving this run right now" and resolves itself on the next tick. Presenting the second
# as the first sends an operator hunting for a blocker that was never there.
HALT_STRUCTURAL = "structural_halt"
PAUSE_LEASE = "lease_pause"
LEASE_REASON = "lease_held_by_gui"

# --- gate ids (§8.1). These are the ids `automation_run.PARTIAL_*_GATES`,
# `phases.PHASES[*]["gate"]` and `dispatch_door.GATE_STAGES` all speak. ---
G0 = "transcript_review"
G_FRAMING = "gap_framing"
G1 = "g1_vo_pickup"
G_PRECLEAN = "source_preclean"
G_PUBLISH = "g_publish"
SOLVER_GATES: tuple[str, ...] = (G0, G_FRAMING, G1, G_PRECLEAN, G_PUBLISH)

# G0 exempts only the four stages that produce the transcript it protects — the same
# set `pipeline.py` exempts from `require_transcript_review_clear`.
G0_EXEMPT_STAGES: frozenset[str] = frozenset(
    {"audio_preclean", "ingest", "transcribe", "transcript_review_build"}
)
# G-Framing gates the gap-VO consent stages (`pipeline.py` →
# `require_gap_framing_decision_clear`). `optimal_questions` is retired.
G_FRAMING_STAGES: frozenset[str] = frozenset({"missing_framing", "gap_framing_compose"})
G_PUBLISH_STAGES: frozenset[str] = frozenset({"podcast_publish"})


# ---------------------------------------------------------------------------
# switches
# ---------------------------------------------------------------------------

def _env_on(name: str, *, default: bool = False) -> bool:
    raw = str(os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def solver_authoritative() -> bool:
    """The one-line promotion switch (§7). Default OFF, and it must stay OFF.

    This is the *only* flag that gives the solver any say in what runs. Shadow mode
    below is armed by default, but shadow observes and records; it cannot select.
    """
    return _env_on("MUX_SOLVER_AUTHORITATIVE", default=False)


def shadow_logging_enabled() -> bool:
    """Armed by DEFAULT (§6.2), because unarmed telemetry never gets turned on in time.

    Agreement data from a real campaign run is the only evidence that could ever
    justify promotion, so the default has to collect it without anyone remembering to.
    Three properties make defaulting this on safe, and all three are pinned by tests:
    the hook cannot raise into the walk, it cannot influence stage selection while
    ``solver_authoritative()`` is False, and it writes one operator-tier log line via
    the ownership matrix or not at all. Set ``MUX_SOLVER_SHADOW=0`` to silence it.
    """
    return _env_on("MUX_SOLVER_SHADOW", default=True)


# ---------------------------------------------------------------------------
# verdicts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StageVerdict:
    """Why one stage is or is not runnable right now.

    ``reasons`` are *positive blockers*; ``unknowns`` are checks the on-disk truth
    could not answer (hollow contract, advisory gate, absent producer table). A
    verdict is ``admissible`` when ``reasons`` is empty — an ``unknown`` never
    excludes, it only clears ``confident``.
    """

    stage: str
    admissible: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)
    unknowns: tuple[str, ...] = field(default_factory=tuple)
    detail: dict[str, Any] = field(default_factory=dict)
    tier: str = ""
    phase: str = ""
    seed_index: int = -1

    @property
    def reason(self) -> str:
        """The single most specific exclusion reason, for a one-line halt panel."""
        return self.reasons[0] if self.reasons else ""

    @property
    def confident(self) -> bool:
        return not self.unknowns

    @property
    def deferred(self) -> bool:
        """Admissible but not provable from contracts — the walk stays in charge."""
        return self.admissible and bool(self.unknowns)

    def as_row(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "stage": self.stage,
            "admissible": self.admissible,
            "tier": self.tier,
            "phase": self.phase,
            "seed_index": self.seed_index,
            "confident": self.confident,
        }
        if self.reasons:
            row["reason"] = self.reason
            row["reasons"] = list(self.reasons)
        if self.unknowns:
            row["unknowns"] = list(self.unknowns)
        if self.detail:
            row["detail"] = self.detail
        return row


@dataclass(frozen=True)
class Decision:
    """One solver evaluation: the admissible set, the pick, and every exclusion."""

    posture: Posture
    admissible: tuple[str, ...]
    would_choose: str | None
    verdicts: tuple[StageVerdict, ...]
    lease_ok: bool
    seed_first_incomplete: str | None = None
    at: str = ""

    @property
    def halted(self) -> bool:
        """The admissible set is empty. Consult ``halt_kind`` for *why* before saying so."""
        return not self.admissible

    @property
    def paused(self) -> bool:
        """Empty because another session holds the run — waiting, not stuck."""
        return self.halted and not self.lease_ok

    @property
    def halt_kind(self) -> str:
        """``""`` | ``lease_pause`` | ``structural_halt``."""
        if not self.halted:
            return ""
        return PAUSE_LEASE if not self.lease_ok else HALT_STRUCTURAL

    @property
    def confident_admissible(self) -> tuple[str, ...]:
        return tuple(v.stage for v in self.verdicts if v.admissible and v.confident)

    @property
    def would_choose_confident(self) -> str | None:
        """The pick the solver can actually justify from contracts. None ⇒ defer."""
        confident = self.confident_admissible
        return confident[0] if confident else None

    @property
    def deferred(self) -> tuple[str, ...]:
        return tuple(v.stage for v in self.verdicts if v.deferred)

    def verdict_for(self, stage: str) -> StageVerdict | None:
        for v in self.verdicts:
            if v.stage == stage:
                return v
        return None

    def exclusions(self) -> dict[str, str]:
        """``{stage: most specific reason}`` — the "why is nothing runnable" payload."""
        return {v.stage: v.reason for v in self.verdicts if not v.admissible}

    def as_row(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "posture": self.posture,
            "lease_ok": self.lease_ok,
            "kind": "decision",
            "admissible": list(self.admissible),
            "would_choose": self.would_choose,
            "would_choose_confident": self.would_choose_confident,
            "deferred": list(self.deferred),
            "seed_first_incomplete": self.seed_first_incomplete,
            "halted": self.halted,
            "halt_kind": self.halt_kind,
            "paused": self.paused,
            "excluded": [v.as_row() for v in self.verdicts if not v.admissible],
            "admissible_detail": [v.as_row() for v in self.verdicts if v.admissible],
        }


# ---------------------------------------------------------------------------
# posture + seed order
# ---------------------------------------------------------------------------

def _run_meta(ctx: RunContext) -> dict[str, Any]:
    try:
        if not ctx.artifact_exists("run_meta.json"):
            return {}
        meta = ctx.read_json("run_meta.json")
        return meta if isinstance(meta, dict) else {}
    except Exception:
        return {}


def posture_for_meta(meta: dict[str, Any] | None) -> Posture:
    from interview_mux.automation_run import is_full_auto_run, is_partially_accelerated_run

    if is_partially_accelerated_run(meta):
        return PARTIAL
    if is_full_auto_run(meta):
        return FULL_AUTO
    return MANUAL


def posture_for(ctx: RunContext) -> Posture:
    """`automation_run` is the SSOT (§8.2) — never re-derive posture from env here."""
    return posture_for_meta(_run_meta(ctx))


def seed_order() -> tuple[str, ...]:
    from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

    return tuple(ANALYSIS_ORDER) + tuple(DELIVERY_ORDER)


def dispatchable_stages() -> tuple[str, ...]:
    """The 72 pipeline-tier stages in seed order (§8.4 — not the 90 contract files)."""
    from interview_mux.stage_contract import load_contract

    out: list[str] = []
    for sid in seed_order():
        contract = load_contract(sid)
        if contract is None or str(contract.tier) in PIPELINE_TIERS:
            out.append(sid)
    return tuple(out)


def _phase_of(stage: str) -> str:
    try:
        from interview_mux.v2.phases import phase_for_stage

        phase = phase_for_stage(stage) or {}
        return str(phase.get("id") or "")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# §8.5 done() / §8.6 committed()
# ---------------------------------------------------------------------------

def stage_done(ctx: RunContext, stage: str) -> bool:
    """``is_done ∧ stage_outputs_present`` — a hollow marker is not done (§8.5)."""
    if not ctx.is_done(stage):
        return False
    try:
        from interview_mux.homunculus.agenda import stage_outputs_present

        return bool(stage_outputs_present(ctx, stage))
    except Exception:
        # Cannot prove the outputs landed: treat the marker as hollow rather than
        # trusting it. Over-offering a done stage is caught by the dispatch door;
        # under-offering an undone one strands the run.
        return False


def committed(ctx: RunContext, rel: str) -> bool:
    """True only for artifacts promoted out of staging (§8.6).

    A peer stage's ``.pending_writes`` copy must never satisfy a hard input: the
    consumer would derive from work that may never commit.
    """
    from interview_mux.write_staging import uncommitted_pending_reason

    final = ctx.final_path(*rel.split("/"))
    if "*" in rel:
        try:
            return any(p.is_file() for p in ctx.final_path().glob(rel))
        except Exception:
            return False
    if final.is_dir():
        try:
            return any(p.is_file() for p in final.rglob("*"))
        except Exception:
            return False
    if not final.is_file():
        return False
    try:
        return uncommitted_pending_reason(ctx, rel) is None
    except Exception:
        return True


def _min_chars_ok(ctx: RunContext, rel: str, min_chars: int | None) -> bool | None:
    if not min_chars:
        return None
    try:
        return ctx.final_path(*rel.split("/")).stat().st_size >= int(min_chars)
    except OSError:
        return False


def input_satisfied(
    ctx: RunContext,
    rel: str,
    *,
    consumer_stage: str,
    min_chars: int | None = None,
) -> tuple[bool, str]:
    """``(ok, reason)`` for one hard input — existence is not sufficiency.

    The trap this closes: a hollow artifact that exists on disk. Sufficiency comes
    from ``artifact_completeness.artifact_status_for_stage``, which routes through the
    sufficiency engine and the per-artifact gap rules, so a schema-valid but empty
    ``master/selection.json`` reads ``partial``, not satisfied.
    """
    if not committed(ctx, rel):
        final = ctx.final_path(*rel.split("/"))
        if final.exists():
            return False, f"hard_input_uncommitted:{rel}"
        return False, f"hard_input_missing:{rel}"
    sized = _min_chars_ok(ctx, rel, min_chars)
    if sized is False:
        return False, f"hard_input_below_min_chars:{rel}"
    from interview_mux.artifact_completeness import artifact_status_for_stage

    try:
        status = artifact_status_for_stage(rel, ctx, consumer_stage)
    except Exception:
        # An unreadable status is not evidence of a blocker; existence stands.
        return True, ""
    if status == "complete":
        return True, ""
    return False, f"hard_input_{'missing' if status == 'pending' else 'insufficient'}:{rel}"


# ---------------------------------------------------------------------------
# §8.1 / §8.2 gates × posture
# ---------------------------------------------------------------------------

def gate_open(ctx: RunContext, gate_id: str) -> bool | None:
    """Is this operator gate open? ``None`` when the answer is indeterminate."""
    try:
        if gate_id == G0:
            from interview_mux.gates import check_transcript_review_pending

            return bool(check_transcript_review_pending(ctx))
        if gate_id == G_FRAMING:
            from interview_mux.gap_vo_gates import check_gap_framing_decision_pending

            return bool(check_gap_framing_decision_pending(ctx))
        if gate_id == G1:
            from interview_mux.gates import check_g1_vo

            return bool(check_g1_vo(ctx))
        if gate_id == G_PUBLISH:
            from interview_mux.gates import check_g_publish_pending

            return bool(check_g_publish_pending(ctx))
        if gate_id == G_PRECLEAN:
            return _preclean_auto_enabled(ctx)
    except Exception:
        return None
    return None


def _preclean_auto_enabled(ctx: RunContext) -> bool:
    """True when pre-clean looks enabled without an operator decision behind it.

    The Preclean checkpoint is *never auto-run* (operator-gates.md). The stage itself
    self-skips when no scope is selected, so the thing to refuse is not the dispatch —
    it is running DeepFilterNet off an enable no operator ever made.
    """
    preclean = _run_meta(ctx).get("audio_preclean")
    if not isinstance(preclean, dict) or not preclean.get("enabled"):
        return False
    decided = preclean.get("decisions")
    if isinstance(decided, list) and decided:
        return False
    return not preclean.get("requested_at")


def gates_blocking(stage: str) -> tuple[str, ...]:
    """Which gates gate this stage, ignoring whether they are currently open."""
    out: list[str] = []
    if stage == "audio_preclean":
        out.append(G_PRECLEAN)
    if stage not in G0_EXEMPT_STAGES:
        out.append(G0)
    if stage in G_FRAMING_STAGES:
        out.append(G_FRAMING)
    if stage in G_PUBLISH_STAGES:
        out.append(G_PUBLISH)
    from interview_mux.v2.config import DELIVERY_ORDER

    if stage in DELIVERY_ORDER:
        out.append(G1)
    return tuple(out)


def gate_enforcement(gate_id: str, posture: Posture) -> str:
    """``block`` | ``may_pause`` | ``auto_accept`` for this gate under this posture.

    Partial-auto is the subtle one and `automation_run` is its SSOT (§8.2):
    ``PARTIAL_MUST_ACT_GATES`` block, ``PARTIAL_MAY_PAUSE_GATES`` may pause. A solver
    that ignores posture auto-advances ``transcript_review`` in partial mode and
    silently destroys the G0 contract.
    """
    from interview_mux.automation_run import PARTIAL_MAY_PAUSE_GATES, PARTIAL_MUST_ACT_GATES

    # Never auto-run, in any posture — this one is not an automation decision.
    if gate_id == G_PRECLEAN:
        return "block"
    if posture == MANUAL:
        return "block"
    if posture == PARTIAL:
        if gate_id in PARTIAL_MUST_ACT_GATES:
            return "block"
        if gate_id in PARTIAL_MAY_PAUSE_GATES:
            return "may_pause"
        return "auto_accept"
    return "auto_accept"


def _gate_verdict(
    ctx: RunContext, stage: str, posture: Posture
) -> tuple[list[str], list[str], dict[str, Any]]:
    reasons: list[str] = []
    unknowns: list[str] = []
    detail: dict[str, Any] = {}
    for gate_id in gates_blocking(stage):
        is_open = gate_open(ctx, gate_id)
        if is_open is None:
            unknowns.append(f"gate_indeterminate:{gate_id}")
            continue
        if not is_open:
            continue
        detail.setdefault("open_gates", []).append(gate_id)
        mode = gate_enforcement(gate_id, posture)
        if mode == "block":
            reasons.append(f"gate_open:{gate_id}")
        elif mode == "may_pause":
            # MAY_PAUSE is not guaranteed every run, so it cannot be a blocker
            # without halting healthy partial runs (D1: unknown favours progress).
            unknowns.append(f"gate_may_pause:{gate_id}")
        else:
            unknowns.append(f"gate_auto_accept_pending:{gate_id}")
    # G1 is configuration-optional: `pipeline.py` only calls `require_g1_clear` when
    # `v2_g1_optional()` is false, so an open G1 is advisory under the default.
    from interview_mux.v2.config import v2_g1_optional

    if v2_g1_optional():
        blocked = f"gate_open:{G1}"
        if blocked in reasons:
            reasons.remove(blocked)
            unknowns.append(f"gate_optional_by_config:{G1}")
    return reasons, unknowns, detail


# ---------------------------------------------------------------------------
# §8.3 lease + audio serialization
# ---------------------------------------------------------------------------

def lease_permits_acting(ctx: RunContext) -> bool:
    """Read-only mirror of ``driver_may_walk`` — the solver never *takes* the lease.

    ``automation_run.driver_may_walk`` writes the lease as a side effect, so calling
    it from a decision function would make the pure half impure and would race an
    operator clicking Continue. The rule from §8.3 is: the solver decides, and only a
    dispatcher may take the lease.

    A fresh GUI lease is the whole answer: ``driver_may_walk`` refuses on it whether
    or not the job has started, because the GUI is about to walk either way.
    """
    from interview_mux.automation_run import gui_holds_fresh_lease

    try:
        return not gui_holds_fresh_lease(ctx)
    except Exception:
        return True


def _audio_inflight(ctx: RunContext) -> str:
    """Stage id of a running AUDIO_MUTATING job, per the GUI job doc. '' when idle."""
    from interview_mux.homunculus.budget import AUDIO_MUTATING

    try:
        from interview_mux.write_staging import read_gui_job

        job = read_gui_job(ctx) or {}
    except Exception:
        return ""
    if str(job.get("status") or "").lower() not in {"running", "starting"}:
        return ""
    sid = str(job.get("stage") or job.get("stage_id") or "")
    return sid if sid in AUDIO_MUTATING else ""


# ---------------------------------------------------------------------------
# the rule
# ---------------------------------------------------------------------------

def evaluate_stage(
    ctx: RunContext,
    stage: str,
    *,
    posture: Posture | None = None,
    lease_ok: bool | None = None,
    include_door: bool | None = None,
) -> StageVerdict:
    """Pure decision for one stage. Reads disk; writes nothing.

    ``include_door`` defaults to *observing*, i.e. ``not solver_authoritative()`` — see
    step 8 for why the door term has to come out once the solver picks.
    """
    from interview_mux.artifact_ownership import write_permitted
    from interview_mux.stage_contract import (
        evaluate_when,
        is_path_spec,
        load_contract,
    )

    sid = str(stage or "").strip()
    order = seed_order()
    seed_index = order.index(sid) if sid in order else -1
    contract = load_contract(sid)
    tier = str(contract.tier) if contract is not None else ""
    reasons: list[str] = []
    unknowns: list[str] = []
    detail: dict[str, Any] = {}

    def _verdict() -> StageVerdict:
        return StageVerdict(
            stage=sid,
            admissible=not reasons,
            reasons=tuple(reasons),
            unknowns=tuple(unknowns),
            detail=detail,
            tier=tier,
            phase=_phase_of(sid),
            seed_index=seed_index,
        )

    # 1. tier — only pipeline-tier contracts are dispatchable (§8.4).
    if contract is None:
        unknowns.append("contract_absent")
        if seed_index < 0:
            reasons.append("not_a_pipeline_stage")
            return _verdict()
    elif tier not in PIPELINE_TIERS:
        reasons.append(f"tier_not_dispatchable:{tier}")
        return _verdict()

    # 2. done — marker plus real outputs (§8.5).
    if stage_done(ctx, sid):
        reasons.append("already_done")
        return _verdict()
    if ctx.is_done(sid):
        detail["hollow_done_marker"] = True

    # 3. gates × posture (§8.1 / §8.2).
    resolved_posture = posture or posture_for(ctx)
    gate_reasons, gate_unknowns, gate_detail = _gate_verdict(ctx, sid, resolved_posture)
    reasons.extend(gate_reasons)
    unknowns.extend(gate_unknowns)
    detail.update(gate_detail)

    # 4. hard inputs — committed and sufficient (§2.1, §8.6).
    declared_hard = 0
    if contract is not None:
        for dep in contract.inputs:
            if not dep.path or not dep.hard:
                continue
            try:
                if not evaluate_when(dep.when, ctx):
                    continue
            except Exception:
                unknowns.append(f"when_indeterminate:{dep.path}")
                continue
            if is_path_spec(dep.path):
                unknowns.append(f"input_is_path_spec:{dep.path}")
                continue
            declared_hard += 1
            ok, why = input_satisfied(
                ctx, dep.path, consumer_stage=sid, min_chars=dep.min_chars
            )
            if not ok:
                reasons.append(why)
                if dep.producer:
                    detail.setdefault("producers", {})[dep.path] = dep.producer
                else:
                    unknowns.append(f"producer_undeclared:{dep.path}")
    detail["declared_hard_inputs"] = declared_hard
    if declared_hard == 0:
        # A hollow contract must never make a stage look blocked. "Nothing declared"
        # is *unknown*, not "no prerequisites" — the walk keeps deciding this one.
        unknowns.append("hard_inputs_undeclared")

    # 5. outputs writable (§4.2). Statically decidable with ctx=None, but the run's
    #    epoch matters for seat/freeze rows, so pass ctx.
    declared_outputs = 0
    if contract is not None:
        for out in contract.outputs:
            if not out.path or is_path_spec(out.path):
                continue
            declared_outputs += 1
            try:
                ok, why = write_permitted(ctx, out.path, sid)
            except Exception:
                unknowns.append(f"ownership_indeterminate:{out.path}")
                continue
            if not ok:
                reasons.append(f"output_write_denied:{out.path}:{why}")
    detail["declared_outputs"] = declared_outputs
    if declared_outputs == 0:
        unknowns.append("outputs_undeclared")

    # 6. the lease (§8.3) — a run-level condition, reported per stage so the halt
    #    panel never shows an empty set with no explanation.
    if lease_ok is None:
        lease_ok = lease_permits_acting(ctx)
    if not lease_ok:
        reasons.append("lease_held_by_gui")

    # 7. audio serialization (§8.3) — two MLX/ffmpeg jobs must not contend.
    from interview_mux.homunculus.budget import AUDIO_MUTATING

    if sid in AUDIO_MUTATING:
        detail["audio_mutating"] = True
        inflight = _audio_inflight(ctx)
        if inflight and inflight != sid:
            reasons.append(f"audio_serialize_inflight:{inflight}")

    # 8. the dispatch door. Composed with, never re-implemented — caps, no-delta and
    #    the attempt memo all stay its business either way. What changes is *who* acts
    #    on a refusal:
    #
    #    Observing: a stage the door would refuse is not admissible, which keeps the
    #    shadow scan honest — the solver must not report `solver_prefers:X` for an X the
    #    walk's own door would have turned away.
    #
    #    Authoritative: the term comes out. A door refusal is not inert — the walk
    #    answers it by writing a defect ledger row (`refuse_dispatch`) and then asking
    #    `unreachable_halt` whether the ship path is severed. Both only run on a stage
    #    the walk is handed, so excluding door-refused stages here would silently delete
    #    the defect row and make `ShipUnreachable` unreachable. Deferring cannot re-open
    #    the re-dispatch loop the door exists to stop: `authoritative_sequence` offers
    #    each stage at most once, and the walk still runs the door before dispatching.
    if include_door is None:
        include_door = not solver_authoritative()
    if not include_door:
        detail["door_deferred_to_walk"] = True
        return _verdict()
    from interview_mux.dispatch_door import evaluate_dispatch

    try:
        verdict = evaluate_dispatch(ctx, sid, source="solver", layer="walk")
    except Exception:
        unknowns.append("door_indeterminate")
        verdict = None
    if verdict is not None and verdict.refused:
        reasons.append(f"door_refused:{verdict.reason}")
        detail["door_detail"] = dict(verdict.detail or {})

    return _verdict()


def admissible_set(
    ctx: RunContext,
    *,
    posture: Posture | None = None,
    stages: tuple[str, ...] | None = None,
    include_door: bool | None = None,
) -> Decision:
    """Evaluate every dispatchable stage. Pure: no ctx mutation, no LLM, no network."""
    resolved_posture = posture or posture_for(ctx)
    lease_ok = lease_permits_acting(ctx)
    candidates = tuple(stages) if stages is not None else dispatchable_stages()
    verdicts = tuple(
        evaluate_stage(
            ctx,
            sid,
            posture=resolved_posture,
            lease_ok=lease_ok,
            include_door=include_door,
        )
        for sid in candidates
    )
    admissible = tuple(v.stage for v in verdicts if v.admissible)
    return Decision(
        posture=resolved_posture,
        admissible=admissible,
        would_choose=admissible[0] if admissible else None,
        verdicts=verdicts,
        lease_ok=lease_ok,
        seed_first_incomplete=_seed_first_incomplete(ctx),
        at=_utcnow(),
    )


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _seed_first_incomplete(ctx: RunContext) -> str | None:
    """Lowest seed-order stage that is not done — context for shadow comparison."""
    for sid in dispatchable_stages():
        if not stage_done(ctx, sid):
            return sid
    return None


def next_stage(ctx: RunContext, posture: Posture | None = None) -> Decision:
    """The §6.1 entry point: ``Decision(stage | halt(blockers))``. Never dispatches.

    Decision and dispatch stay separate functions (§8.3) so this half is pure and
    unit-testable, and so no caller can accidentally act on it.
    """
    return admissible_set(ctx, posture=posture)


def halt_payload(decision: Decision) -> dict[str, Any]:
    """"Why is nothing runnable" (§10.2) — the unmet dep and who would satisfy it.

    ``blockers`` is capped for the panel, so the aggregates are computed over all of
    them: ``reason_families`` is the histogram a halt line can be read from, and
    ``hard_input_blockers`` isolates the failure mode a promoted solver introduces —
    one over-declared ``inputs.hard`` entry retires its stage permanently, where the
    unpromoted walk would attempt it and let the pre-stage checks decide. Each entry
    carries the artifact, its declared producer and how many hard inputs the contract
    declares, which is what tells a wrong declaration apart from a real missing input.
    """
    blockers: list[dict[str, Any]] = []
    families: dict[str, int] = {}
    hard_input_blockers: list[dict[str, Any]] = []
    for verdict in decision.verdicts:
        if verdict.admissible or verdict.seed_index < 0:
            continue
        detail = verdict.detail or {}
        producers = detail.get("producers") or {}
        blockers.append(
            {
                "stage": verdict.stage,
                "phase": verdict.phase,
                "reason": verdict.reason,
                "reasons": list(verdict.reasons),
                "producers": producers,
                "confident": verdict.confident,
                "unknowns": list(verdict.unknowns),
                "seed_index": verdict.seed_index,
            }
        )
        for reason in verdict.reasons:
            family = reason.split(":", 1)[0]
            families[family] = families.get(family, 0) + 1
            if not family.startswith("hard_input_"):
                continue
            artifact = reason.split(":", 1)[1] if ":" in reason else ""
            hard_input_blockers.append(
                {
                    "stage": verdict.stage,
                    "artifact": artifact,
                    "blocker": family,
                    "producer": producers.get(artifact) or "",
                    "declared_hard_inputs": detail.get("declared_hard_inputs"),
                }
            )
    return {
        "halted": decision.halted,
        "kind": decision.halt_kind,
        "paused": decision.paused,
        "reason_code": LEASE_REASON if decision.paused else "",
        "posture": decision.posture,
        "lease_ok": decision.lease_ok,
        "seed_first_incomplete": decision.seed_first_incomplete,
        "blockers": blockers[:24],
        "blocked_total": len(blockers),
        "reason_families": dict(sorted(families.items(), key=lambda kv: (-kv[1], kv[0]))),
        "hard_input_blockers": hard_input_blockers[:24],
    }


# ---------------------------------------------------------------------------
# §10.2 observability
# ---------------------------------------------------------------------------

def decision_log_writable(ctx: RunContext) -> tuple[bool, str]:
    """Ask the ownership matrix, never assume. ``(ok, reason)``.

    ``operator/solver_decision.jsonl`` now has its own ``ops`` ALLOW row in
    `artifact_ownership.py`, so this resolves to a registered owner rather than the
    blanket ``operational_unregistered`` answer the matrix gives any other ``operator/``
    path. ``decision_log_registered`` asserts that row is still there; this predicate
    remains what gates the write, so if the catalog ever tightens the writer goes quiet
    instead of writing illegally.
    """
    try:
        from interview_mux.artifact_ownership import write_permitted

        return write_permitted(ctx, SOLVER_DECISION_REL, "ops", role="ops")
    except Exception as exc:  # noqa: BLE001
        return False, f"ownership_unavailable:{exc}"


def decision_log_registered() -> bool:
    """True once ``operator/solver_decision.jsonl`` has its own catalog ALLOW row."""
    try:
        from interview_mux.artifact_ownership import owners_of

        return bool(owners_of(SOLVER_DECISION_REL))
    except Exception:
        return False


def _decision_path(ctx: RunContext) -> Path:
    return Path(ctx.run_dir) / SOLVER_DECISION_REL


def _append_row(ctx: RunContext, row: dict[str, Any]) -> bool:
    """Append one JSONL row if the matrix permits it. Never raises."""
    ok, reason = decision_log_writable(ctx)
    if not ok:
        try:
            ctx.log(
                f"solver decision not logged: {SOLVER_DECISION_REL} is not writable "
                f"per the ownership matrix ({reason})",
                level="debug",
            )
        except Exception:
            pass
        return False
    try:
        dest = _decision_path(ctx)
        dest.parent.mkdir(parents=True, exist_ok=True)
        rows = _read_rows(dest)
        rows.append(row)
        with dest.open("w", encoding="utf-8") as fh:
            for kept in rows[-MAX_DECISION_ROWS:]:
                fh.write(json.dumps(kept, sort_keys=True, default=str) + "\n")
    except Exception:
        return False
    return True


def log_decision(ctx: RunContext, decision: Decision) -> bool:
    """Append one row. Returns False (no write, no raise) when unowned or unwritable."""
    return _append_row(ctx, decision.as_row())


def _read_rows(dest: Path) -> list[dict[str, Any]]:
    if not dest.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in dest.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    except OSError:
        return []
    return rows


def read_decisions(ctx: RunContext, *, limit: int = 25) -> list[dict[str, Any]]:
    """Most recent rows last — the API/GUI read path for the halt panel."""
    rows = _read_rows(_decision_path(ctx))
    return rows[-max(1, int(limit)):]


def decision_view(ctx: RunContext, *, limit: int = 25) -> dict[str, Any]:
    """API payload: the persisted rows plus a live evaluation of current state."""
    live = admissible_set(ctx)
    return {
        "artifact": SOLVER_DECISION_REL,
        "authoritative": solver_authoritative(),
        "shadow_logging": shadow_logging_enabled(),
        "writable": decision_log_writable(ctx)[0],
        "ownership_row_registered": decision_log_registered(),
        "rows": read_decisions(ctx, limit=limit),
        "live": live.as_row(),
        "halt": halt_payload(live),
        "shadow": shadow_summary(ctx),
    }


def shadow_observe(ctx: RunContext, *, posture: Posture | None = None) -> Decision:
    """Evaluate and (when shadow logging is on) persist one decision row."""
    decision = admissible_set(ctx, posture=posture)
    if shadow_logging_enabled():
        log_decision(ctx, decision)
    return decision


# ---------------------------------------------------------------------------
# §6.2 shadow mode — log walk-vs-solver disagreement until it is zero
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ShadowComparison:
    """What the walk chose, what the solver would have chosen, and whether they agree.

    ``verdict`` is one of ``agree`` / ``disagree`` / ``defer``. A ``defer`` is the
    solver correctly declining to have an opinion — its contract does not yet say
    enough — and is deliberately not a disagreement.
    """

    chosen: str
    solver_choice: str | None
    verdict: str
    reason: str = ""
    candidates: int = 0
    source: str = ""
    at: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def agrees(self) -> bool:
        return self.verdict == AGREE

    @property
    def disagrees(self) -> bool:
        return self.verdict == DISAGREE

    def as_row(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "kind": "shadow",
            "at": self.at,
            "source": self.source,
            "walk_chose": self.chosen,
            "solver_would_choose": self.solver_choice,
            "verdict": self.verdict,
            "candidates": self.candidates,
        }
        if self.reason:
            row["reason"] = self.reason
        if self.detail:
            row["detail"] = self.detail
        return row


def compare_walk_choice(
    ctx: RunContext,
    chosen: str,
    candidates: tuple[str, ...] | list[str] = (),
    *,
    source: str = "walk",
    posture: Posture | None = None,
) -> ShadowComparison:
    """Classify the walk's pick against the solver's — the one comparison rule.

    Shadow mode is armed on every real run, so a full 72-stage ``admissible_set`` per
    stage-selection decision is not affordable. Only two questions actually decide the
    verdict, and both short-circuit:

    * Is ``chosen`` itself admissible, and confidently so? One ``evaluate_stage``.
    * If it is, would the solver have justified an *earlier* candidate instead? Scan
      the candidates the walk passed over, stopping at the first confidently
      admissible one.

    In the common case — the walk takes its first live candidate — that is one
    evaluation, and the earlier candidates it did skip are almost all ``already_done``,
    which ``evaluate_stage`` answers and returns on before touching a contract. Posture
    and the lease are resolved once and reused, so the scan costs a contract read and a
    handful of ``stat`` calls per candidate rather than a fresh run-meta parse.

    The candidate set is the walk's own, and that is what makes the count fair: the
    walk cannot choose a stage its own filters removed, so letting the solver choose
    from a wider set would manufacture disagreements that mean nothing.
    """
    sid = str(chosen or "").strip()
    scope = tuple(str(s) for s in candidates if str(s))
    resolved = posture or posture_for(ctx)
    lease_ok = lease_permits_acting(ctx)

    def _out(kind: str, pick: str | None, reason: str = "", **detail: Any) -> ShadowComparison:
        return ShadowComparison(
            chosen=sid,
            solver_choice=pick,
            verdict=kind,
            reason=reason,
            candidates=len(scope),
            source=source,
            at=_utcnow(),
            detail={k: v for k, v in detail.items() if v},
        )

    verdict = evaluate_stage(ctx, sid, posture=resolved, lease_ok=lease_ok)
    if verdict.reason.startswith(("not_a_pipeline_stage", "tier_not_dispatchable")):
        # Gate pseudo-stages and non-pipeline ids are not the solver's business. Read
        # off the verdict rather than scanning all 72 contracts for a membership test.
        return _out(DEFER, None, "chosen_not_dispatchable")
    if not verdict.admissible:
        # The valuable class: the walk ran a stage the solver *proved* is blocked.
        # Either the contract is wrong or the walk has a rule not yet declarative.
        return _out(DISAGREE, None, verdict.reason, reasons=list(verdict.reasons))
    if verdict.deferred:
        return _out(
            DEFER, sid, f"verdict_deferred:{verdict.unknowns[0]}", unknowns=list(verdict.unknowns)
        )
    for earlier in scope:
        if earlier == sid:
            break
        other = evaluate_stage(ctx, earlier, posture=resolved, lease_ok=lease_ok)
        if other.admissible and other.confident:
            return _out(DISAGREE, earlier, f"solver_prefers:{earlier}")
    return _out(AGREE, sid)


def observe_walk_choice(
    ctx: RunContext,
    chosen: str,
    *,
    candidates: tuple[str, ...] | list[str] | None = None,
    source: str = "walk",
    posture: Posture | None = None,
) -> ShadowComparison | None:
    """The walk's shadow hook. Never raises, never changes what the walk does.

    Armed by default (see ``shadow_logging_enabled``), so this wrapper is the thing
    that makes the default safe: it returns ``None`` on *any* failure rather than
    letting a solver bug reach the walk, and the walk discards the return value.
    """
    if not shadow_logging_enabled():
        return None
    try:
        comparison = compare_walk_choice(
            ctx, chosen, candidates or (), source=source, posture=posture
        )
    except Exception:
        try:
            ctx.log("solver shadow hook failed — walk unaffected", level="debug")
        except Exception:
            pass
        return None
    try:
        log_shadow(ctx, comparison)
    except Exception:
        pass
    return comparison


def log_shadow(ctx: RunContext, comparison: ShadowComparison) -> bool:
    """Append a shadow row to the same artifact the decisions use."""
    return _append_row(ctx, comparison.as_row())


def shadow_summary(ctx: RunContext) -> dict[str, Any]:
    """"Is it zero yet?" without parsing the log by hand.

    ``zero`` is the promotion gate from §6.2, and it is keyed on ``disagree`` alone:
    deferrals are expected to stay non-zero until the contract groups are strict.
    """
    rows = [r for r in _read_rows(_decision_path(ctx)) if r.get("kind") == "shadow"]
    counts = {AGREE: 0, DISAGREE: 0, DEFER: 0}
    reasons: dict[str, int] = {}
    disagreements: list[dict[str, Any]] = []
    for row in rows:
        verdict = str(row.get("verdict") or "")
        if verdict in counts:
            counts[verdict] += 1
        if verdict != DISAGREE:
            continue
        reason = str(row.get("reason") or "unknown")
        family = reason.split(":", 1)[0]
        reasons[family] = reasons.get(family, 0) + 1
        disagreements.append(
            {
                "walk_chose": row.get("walk_chose"),
                "solver_would_choose": row.get("solver_would_choose"),
                "reason": reason,
            }
        )
    total = sum(counts.values())
    decided = counts[AGREE] + counts[DISAGREE]
    return {
        "observations": total,
        "agree": counts[AGREE],
        "disagree": counts[DISAGREE],
        "defer": counts[DEFER],
        "zero": counts[DISAGREE] == 0,
        "agreement_rate": (counts[AGREE] / decided) if decided else None,
        "disagreement_families": dict(sorted(reasons.items())),
        "disagreements": disagreements[-24:],
    }


# ---------------------------------------------------------------------------
# §7 promotion — authoritative selection, behind the switch, default OFF
# ---------------------------------------------------------------------------

def authoritative_sequence(
    ctx: RunContext,
    candidates: tuple[str, ...] | list[str],
    *,
    source: str = "walk",
    posture: Posture | None = None,
) -> Any:
    """Yield the walk's stage order from the solver instead of from seed order.

    Only reached when ``solver_authoritative()``. Three rules:

    1. A **confidently admissible** stage is the solver's call — lowest seed index.
    2. A stage the solver marks **deferred** is the *walk's* call, so seed order
       decides it. This is what keeps promotion safe while 39 of 72 contracts still
       declare no hard inputs.
    3. An **empty** admissible set ends the sequence — that is the structural halt
       from §2.1, and every remaining stage's exclusion reason is logged for it.

    A GUI lease is checked first and separately. It is the one run-level condition that
    empties the set for reasons that have nothing to do with the pipeline's state, so it
    ends the sequence as a *pause* — and short-circuiting it also spares a full sweep of
    per-stage evaluations that could only ever answer ``lease_held_by_gui``.

    Termination is structural: a stage is only ever yielded once, so the loop is
    bounded by ``len(candidates)`` regardless of what the stages do.
    """
    pending = [s for s in dict.fromkeys(str(s) for s in candidates) if s]
    offered: set[str] = set()
    while True:
        remaining = tuple(s for s in pending if s not in offered)
        if not remaining:
            return
        if not lease_permits_acting(ctx):
            _log_authoritative_pause(ctx, remaining, source=source, posture=posture)
            return
        try:
            decision = admissible_set(ctx, posture=posture, stages=remaining)
        except Exception:
            # A generator raises lazily, i.e. inside the walk's own loop, so this is
            # the only place that can keep a solver bug from breaking a promoted run.
            # Hand the rest back to seed order and say so.
            try:
                ctx.log(
                    "solver authoritative evaluation failed — falling back to seed order",
                    level="error",
                )
            except Exception:
                pass
            yield from remaining
            return
        pick = decision.would_choose_confident
        basis = "solver"
        if pick is None:
            pick = decision.deferred[0] if decision.deferred else None
            basis = "deferred_to_walk"
        if pick is None:
            _log_authoritative_halt(ctx, decision, source=source)
            return
        offered.add(pick)
        try:
            ctx.log(
                f"solver authoritative: {pick} ({basis})",
                level="info",
                stage=pick,
            )
        except Exception:
            pass
        if shadow_logging_enabled():
            log_decision(ctx, decision)
        yield pick


def _log_authoritative_halt(ctx: RunContext, decision: Decision, *, source: str) -> None:
    """The §2.1 structural halt: nothing is runnable until on-disk state changes.

    The reason histogram goes in the line itself, not only the detail, because the
    diagnosis this halt most needs to support — a stage retired by an ``inputs.hard``
    entry it should never have declared — reads as a ``hard_input_*`` family against a
    stage whose producer already ran, and that has to be visible from the log alone.
    """
    payload = halt_payload(decision)
    families = payload.get("reason_families") or {}
    summary = ", ".join(f"{k}×{v}" for k, v in list(families.items())[:6])
    try:
        ctx.log(
            "solver authoritative: structural halt — admissible set is empty, nothing "
            f"runnable ({payload.get('blocked_total', 0)} blocked stage(s)"
            f"{'; ' + summary if summary else ''})",
            level="warning",
            detail={"source": source, **payload},
        )
    except Exception:
        pass
    if shadow_logging_enabled():
        log_decision(ctx, decision)


def _log_authoritative_pause(
    ctx: RunContext,
    remaining: tuple[str, ...],
    *,
    source: str,
    posture: Posture | None = None,
) -> None:
    """A GUI lease pauses the sequence. It is *not* the structural halt.

    ``lease_held_by_gui`` is a run-level condition that ``evaluate_stage`` reports per
    stage, so on its own it empties the admissible set and is indistinguishable from
    "this run cannot proceed". The two need opposite operator responses — wait for the
    other session, versus go and unblock a producer — so the pause gets its own line,
    its own reason code and its own ``halt_kind`` on the persisted row.
    """
    try:
        resolved_posture = posture or posture_for(ctx)
    except Exception:
        resolved_posture = MANUAL
    decision = Decision(
        posture=resolved_posture,
        admissible=(),
        would_choose=None,
        verdicts=(),
        lease_ok=False,
        at=_utcnow(),
    )
    try:
        ctx.log(
            "solver authoritative: paused — the GUI holds a fresh lease, so this run is "
            f"another session's to walk ({len(remaining)} stage(s) waiting, none blocked)",
            level="info",
            detail={
                "source": source,
                "kind": PAUSE_LEASE,
                "reason_code": LEASE_REASON,
                "lease_ok": False,
                "waiting": list(remaining[:24]),
                "waiting_total": len(remaining),
            },
        )
    except Exception:
        pass
    if shadow_logging_enabled():
        log_decision(ctx, decision)


__all__ = [
    "AGREE",
    "DEFER",
    "DISAGREE",
    "FULL_AUTO",
    "HALT_STRUCTURAL",
    "LEASE_REASON",
    "MANUAL",
    "PAUSE_LEASE",
    "PARTIAL",
    "POSTURES",
    "SHADOW_VERDICTS",
    "SOLVER_DECISION_REL",
    "SOLVER_GATES",
    "Decision",
    "ShadowComparison",
    "StageVerdict",
    "admissible_set",
    "authoritative_sequence",
    "compare_walk_choice",
    "committed",
    "decision_log_registered",
    "decision_log_writable",
    "decision_view",
    "dispatchable_stages",
    "evaluate_stage",
    "gate_enforcement",
    "gate_open",
    "gates_blocking",
    "halt_payload",
    "input_satisfied",
    "lease_permits_acting",
    "log_decision",
    "log_shadow",
    "next_stage",
    "observe_walk_choice",
    "posture_for",
    "posture_for_meta",
    "read_decisions",
    "seed_order",
    "shadow_logging_enabled",
    "shadow_observe",
    "shadow_summary",
    "solver_authoritative",
    "stage_done",
]
