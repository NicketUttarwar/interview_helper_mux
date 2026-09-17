"""Hard execution limits for homunculus brains. Conductor cannot raise these."""

from __future__ import annotations

from typing import Any, NamedTuple

from interview_mux.config import merged_config
from interview_mux.homunculus.ledger import count_identity, count_problem, read_ledger
from interview_mux.run_context import RunContext
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

MAX_INVOKES_PER_IDENTITY = 3
MAX_PROBLEM_ANALYSES = 1
MAX_COMPLETE_MASTERS = 3
MAX_MIX_CYCLES = 3

AUDIO_MUTATING = frozenset(
    {
        "mix",
        "master_finalize",
        "audio_preclean",
        "transcribe",
        "mmaudio_sfx",
        "music_palette_compose",
        "run_musicgen",
        "run_mmaudio",
        "run_chatterbox",
        "run_s2s",
        "run_deepfilter",
        "ears_stt_window",
        "ears_s2s_window",
    }
)

# Budget exemptions used to early-return out of check_dispatch for the whole run,
# voiding every cap (exec_11871: mix reached 28 against max_mix_cycles=3). They are
# now named identity sets with a bounded grace, and a pipeline stage dispatch of an
# AUDIO_MUTATING stage can never be exempted.
CTA_COVER_EXEMPT_IDENTITIES = frozenset({"run_chatterbox", "run_s2s"})
EXEMPTION_GRACE = 3
_MAX_EXEMPT_PLAN_STAGES = 12


class BudgetExemption(NamedTuple):
    name: str
    identity: str
    grace: int


def _cfg() -> dict[str, Any]:
    hom = ((merged_config().get("mastering") or {}).get("homunculus") or {})
    limits = hom.get("limits") if isinstance(hom.get("limits"), dict) else {}
    return limits


def _policy_remediation_identities(ctx: RunContext) -> frozenset[str]:
    """Stages an active repair plan explicitly names — the narrowed exemption set.

    A publishability repair plan contributes only its pinned producer (``from_stage``),
    never its ``invalidate_set``: that set is the whole downstream tail, so honouring
    it would put the run back where exec_11871 was — every cap void for hours.
    """
    named: set[str] = set()
    try:
        from interview_mux.execution_contract import read_active_vo_repair_plan
        from interview_mux.remediation_framework import read_active_remediation_plan

        plan = read_active_remediation_plan(ctx) or read_active_vo_repair_plan(ctx)
    except Exception:
        plan = None
    if isinstance(plan, dict):
        for key in ("allowed_rerun_stages", "invalidate_set"):
            listed = [s for s in (plan.get(key) or []) if isinstance(s, str) and s]
            # A plan that names a tail-sized set is not a narrow exemption.
            if listed and len(listed) <= _MAX_EXEMPT_PLAN_STAGES:
                named.update(listed)
        for key in ("consumer_stage", "resume_stage"):
            sid = str(plan.get(key) or "").strip()
            if sid:
                named.add(sid)
    try:
        from interview_mux.publishability_boundary import read_active_repair_plan

        repair = read_active_repair_plan(ctx)
    except Exception:
        repair = None
    if isinstance(repair, dict):
        pin = str(repair.get("from_stage") or "").strip()
        if pin:
            named.add(pin)
    return frozenset(named)


def exemption_for(
    ctx: RunContext,
    identity: str,
    kind: str = "",
) -> BudgetExemption | None:
    """Named, bounded budget exemption for this identity — or None.

    An exemption may only raise a cap by ``EXEMPTION_GRACE``; it never voids one.
    Pipeline stage dispatches (``kind='stage'``) of AUDIO_MUTATING stages are never
    exempt: remastering audio is exactly what the caps exist to bound.
    """
    if kind == "stage" and identity in AUDIO_MUTATING:
        return None
    if identity in CTA_COVER_EXEMPT_IDENTITIES:
        try:
            from interview_mux.media_ip_cta import cta_cover_budget_exempt

            if cta_cover_budget_exempt(ctx):
                return BudgetExemption("cta_cover_regenerate", identity, EXEMPTION_GRACE)
        except Exception:
            pass
    if identity in AUDIO_MUTATING:
        return None
    if identity in _policy_remediation_identities(ctx):
        return BudgetExemption("policy_remediation_plan", identity, EXEMPTION_GRACE)
    return None


def _log_exemption(ctx: RunContext, exemption: BudgetExemption, *, used: int, cap: int) -> None:
    """Every exemption taken is logged and ledgered — they were invisible before."""
    try:
        ctx.log(
            f"budget exemption {exemption.name} for {exemption.identity} "
            f"({used}/{cap} +{exemption.grace} grace)",
            level="warning",
            stage=exemption.identity,
        )
    except Exception:
        pass
    try:
        from interview_mux.homunculus.ledger import append_ledger

        append_ledger(
            ctx,
            {
                "kind": "budget_exemption",
                "identity": "budget_exemption",
                "stage": exemption.identity,
                "exemption": exemption.name,
                "used": int(used),
                "cap": int(cap),
                "grace": int(exemption.grace),
            },
        )
    except Exception:
        pass


def count_attempts(ctx: RunContext, identity: str) -> int:
    """Dispatch attempts for this identity — every opened stage/host row.

    ``count_identity`` deliberately returns 0 while a stage is not done so failures
    and recycles do not burn the cap. That is why the driver walk could dispatch
    ``mix`` 28 times against ``max_mix_cycles: 3``: junction unmarks ``.stage_done/mix``
    between iterations, so the count was always 0. The walk door counts attempts.
    """
    return sum(
        1
        for row in read_ledger(ctx)
        if row.get("identity") == identity
        and row.get("kind") in {"stage", "host"}
        and row.get("status") in (None, "started")
    )


def attempt_cap(identity: str) -> tuple[int, str]:
    """(cap, reason) for a stage dispatch of ``identity`` on the walk door."""
    limits = _cfg()
    if identity in {"mix", "master_finalize"}:
        return int(limits.get("max_mix_cycles") or MAX_MIX_CYCLES), "max_mix_cycles"
    if identity == "complete_master":
        return int(limits.get("max_complete_masters") or MAX_COMPLETE_MASTERS), "max_complete_masters"
    return (
        int(limits.get("max_invokes_per_identity") or MAX_INVOKES_PER_IDENTITY),
        "max_invokes_per_identity",
    )


def dispatch_cap_refusal(
    ctx: RunContext,
    identity: str,
    *,
    kind: str = "stage",
) -> tuple[str, dict[str, Any]] | None:
    """Non-raising cap evaluation for the driver/operator walk door.

    Returns ``(reason, counts)`` when the cap is spent, else None. D1: a spent cap
    must route to the defect ledger and reachability, never strand the run with a
    ``LimitExhausted`` traceback out of the middle of a walk.
    """
    cap, reason = attempt_cap(identity)
    used = count_attempts(ctx, identity)
    if used < cap:
        return None
    exemption = exemption_for(ctx, identity, kind)
    if exemption is not None:
        _log_exemption(ctx, exemption, used=used, cap=cap)
        if used < cap + exemption.grace:
            return None
        return reason, {
            "used": used,
            "cap": cap,
            "exemption": exemption.name,
            "grace": exemption.grace,
            "exhausted_with_grace": True,
        }
    return reason, {"used": used, "cap": cap}


class LimitExhausted(RuntimeError):
    """Hard cap hit — dispatch refused."""

    def __init__(self, identity: str, reason: str, counts: dict[str, Any]) -> None:
        self.identity = identity
        self.reason = reason
        self.counts = counts
        super().__init__(f"limit_exhausted:{identity}:{reason}")


def max_conductor_turns() -> int:
    limits = _cfg()
    if "max_conductor_turns" in limits:
        return int(limits["max_conductor_turns"])
    return 3 * (len(ANALYSIS_ORDER) + len(DELIVERY_ORDER))


def _identity_cap(identity: str, kind: str = "") -> int:
    """Per-tool invoke cap. Conductor turns use max_conductor_turns, not the stage cap."""
    if identity == "conductor_turn" or kind == "conductor_turn":
        return max_conductor_turns()
    if identity == "timeline_optimizer_propose":
        return int(_cfg().get("max_timeline_optimizer_invokes") or 12)
    return int(_cfg().get("max_invokes_per_identity") or MAX_INVOKES_PER_IDENTITY)


def remaining(ctx: RunContext, identity: str) -> int:
    used = count_identity(ctx, identity)
    cap = _identity_cap(identity)
    return max(0, cap - used)


def mark_identity_exhausted(ctx: RunContext, identity: str) -> None:
    cache = getattr(ctx, "_budget_exhausted_identities", None)
    if cache is None:
        cache = set()
        setattr(ctx, "_budget_exhausted_identities", cache)
    cache.add(identity)


def identity_exhausted(ctx: RunContext, identity: str) -> bool:
    cache = getattr(ctx, "_budget_exhausted_identities", None)
    if isinstance(cache, set) and identity in cache:
        return True
    return remaining(ctx, identity) <= 0


def remaining_conductor_turns(ctx: RunContext) -> int:
    return remaining(ctx, "conductor_turn")


def check_dispatch(
    ctx: RunContext,
    *,
    identity: str,
    kind: str,
    packet_hash: str | None = None,
    problem_id: str | None = None,
) -> None:
    """Refuse before side effects. Ledger is the source of counts."""
    from interview_mux.chapter_close_hitch import hitch_budget_identity, junction_snip_budget_identity

    identity = junction_snip_budget_identity(ctx, hitch_budget_identity(ctx, identity))
    limits = _cfg()
    cap = _identity_cap(identity, kind)
    used = count_identity(ctx, identity)
    exemption = exemption_for(ctx, identity, kind)
    if exemption is not None and used >= cap:
        _log_exemption(ctx, exemption, used=used, cap=cap)
        if used < cap + exemption.grace:
            return
    if used >= cap:
        reason = (
            "max_conductor_turns"
            if identity == "conductor_turn" or kind == "conductor_turn"
            else "max_invokes_per_identity"
        )
        mark_identity_exhausted(ctx, identity)
        _halt(ctx, identity, reason, {"used": used, "cap": cap})
    if packet_hash:
        from interview_mux.homunculus.ledger import has_packet_hash

        if has_packet_hash(ctx, identity, packet_hash):
            _halt(ctx, identity, "identical_packed_call", {"packet_hash": packet_hash})
    if kind == "analyze_issue" and problem_id:
        analyses = count_problem(ctx, problem_id)
        once = int(limits.get("max_problem_analyses_per_issue") or MAX_PROBLEM_ANALYSES)
        if analyses >= once:
            _halt(
                ctx,
                identity,
                "max_problem_analyses_per_issue",
                {"problem_id": problem_id, "used": analyses, "cap": once},
            )
    if identity in {"mix", "master_finalize"}:
        mix_cap = int(limits.get("max_mix_cycles") or MAX_MIX_CYCLES)
        if used >= mix_cap:
            _halt(ctx, identity, "max_mix_cycles", {"used": used, "cap": mix_cap})
    if identity == "complete_master":
        master_cap = int(limits.get("max_complete_masters") or MAX_COMPLETE_MASTERS)
        if used >= master_cap:
            _halt(ctx, identity, "max_complete_masters", {"used": used, "cap": master_cap})


def check_audio_serialize(ctx: RunContext, identity: str, inflight: set[str]) -> None:
    if identity not in AUDIO_MUTATING:
        return
    busy = inflight & AUDIO_MUTATING
    if busy:
        _halt(
            ctx,
            identity,
            "audio_serialize",
            {"inflight": sorted(busy), "requested": identity},
        )


def _halt(ctx: RunContext, identity: str, reason: str, counts: dict[str, Any]) -> None:
    payload = {
        "identity": identity,
        "reason": reason,
        "counts": counts,
        "homunculus_version": (ctx.read_json("run_meta.json") or {}).get(
            "homunculus_version"
        ),
    }
    try:
        ctx.write_json("mastering/homunculus/limit_exhausted.json", payload)
    except Exception:
        pass
    try:
        from interview_mux.homunculus.issues import emit_issue

        emit_issue(
            ctx,
            kind="limit_exhausted",
            source="budget",
            implicated=[identity],
            evidence={"reason": reason, "counts": counts},
        )
    except Exception:
        pass
    raise LimitExhausted(identity, reason, counts)


def snapshot(ctx: RunContext) -> dict[str, Any]:
    ledger = read_ledger(ctx)
    identities: dict[str, int] = {}
    for row in ledger:
        ident = str(row.get("identity") or "")
        if ident:
            identities[ident] = identities.get(ident, 0) + 1
    cap = int(_cfg().get("max_invokes_per_identity") or MAX_INVOKES_PER_IDENTITY)
    turn_cap = max_conductor_turns()
    remaining_map: dict[str, int] = {}
    for k, v in identities.items():
        ident_cap = turn_cap if k == "conductor_turn" else cap
        remaining_map[k] = max(0, ident_cap - v)
    return {
        "max_invokes_per_identity": cap,
        "max_conductor_turns": turn_cap,
        "identities": identities,
        "remaining": remaining_map,
    }
