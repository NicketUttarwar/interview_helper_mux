"""Validate-or-degrade loader for mastering_plan + conflict precedence.

Canon: docs/cross-cutting/narrative-mode-and-montage.md
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from interview_mux.narrative_mode import demote_hybrid, hybrid_acceptance
from interview_mux.run_context import RunContext

PLAN_REL = "mastering/mastering_plan.json"
PlanStatus = Literal["complete", "degraded", "forced_sparse", "absent_legacy"]


def plan_is_authoritative(plan: dict[str, Any] | None) -> bool:
    """HM-3: consumers may bind only when ``plan_status`` is complete."""
    return isinstance(plan, dict) and str(plan.get("plan_status") or "") == "complete"

REBUILD_SCOPES: dict[str, tuple[str, ...]] = {
    "plan_only": (
        "mastering_research_rollup",
        "mastering_shape_agenda",
        "mastering_shape_candidates",
        "mastering_plan_synthesize",
        "mastering_plan_confirm",
    ),
    "plan_gap": (
        "mastering_research_rollup",
        "mastering_shape_agenda",
        "mastering_shape_candidates",
        "mastering_plan_synthesize",
        "missing_framing",
        "mastering_plan_confirm",
        "gap_framing_compose",
        "gap_framing_recompose",
    ),
    "plan_gap_rank_edl": (
        "mastering_research_rollup",
        "mastering_shape_agenda",
        "mastering_shape_candidates",
        "mastering_plan_synthesize",
        "missing_framing",
        "mastering_plan_confirm",
        "gap_framing_compose",
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "air_script_compose",
        "nugget_corpus_mine",
        "information_package_plan",
        "nugget_layup_compose",
        "gap_framing_recompose",
        "selection_framing_apply",
        "air_script_seams",
        "transitions",
        "edl",
        "assembly_preview",
        "mix",
        "master_finalize",
    ),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def evidence_packet_hash(packet: dict[str, Any] | None) -> str:
    payload = packet if isinstance(packet, dict) else {}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]


def forced_sparse_plan(*, reason: str, evidence_hash: str = "") -> dict[str, Any]:
    from interview_mux.information_packages import default_episode_close

    return {
        "version": 1,
        "pass": "confirmed",
        "plan_status": "forced_sparse",
        "narrative_mode": "sparse_source",
        "montage_grammar": [],
        "provisional_mode": "sparse_source",
        "confirmed_mode": "sparse_source",
        "cold_open": {
            "kind": "none",
            "rationale": reason,
            "evidence_refs": [],
            "confidence": 0.3,
        },
        "information_packages": [],
        "episode_close": default_episode_close(),
        "decisions": [],
        "bespoke_rationale": f"Forced sparse: {reason}",
        "listener_outcome": {
            "finishability": "prefer_tape",
            "recommendability": "honest_sparse",
            "rationale": reason,
        },
        "invariants": {
            "never_invent_unspoken_dialogue": True,
            "prefer_pickup_voice": True,
            "pickup_voice_only": False,
        },
        "degradation_reasons": [reason],
        "evidence_packet_hash": evidence_hash,
        "generated_at": _now(),
    }


def absent_legacy_stub(*, reason: str) -> dict[str, Any]:
    p = forced_sparse_plan(reason=reason)
    p["plan_status"] = "absent_legacy"
    p["pass"] = "provisional"
    p["bespoke_rationale"] = f"Legacy path: {reason}"
    return p


def _basic_valid(plan: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(plan, dict):
        return False, "not_object"
    if plan.get("version") != 1:
        return False, "bad_version"
    mode = plan.get("narrative_mode")
    if not isinstance(mode, str) or not mode:
        return False, "missing_narrative_mode"
    if "cold_open" not in plan:
        return False, "missing_cold_open"
    return True, "ok"


def load_plan_raw(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(PLAN_REL):
        return None
    try:
        doc = ctx.read_json(PLAN_REL)
    except Exception:
        return None
    return doc if isinstance(doc, dict) else None


def validate_or_degrade(
    ctx: RunContext,
    *,
    expected_hash: str | None = None,
    prefer_pass: str | None = None,
) -> dict[str, Any]:
    """Load plan or return forced_sparse / absent_legacy. Never raises for corrupt disk."""
    raw = None
    try:
        if ctx.artifact_exists(PLAN_REL):
            raw = ctx.read_json(PLAN_REL)
    except Exception:
        plan = forced_sparse_plan(reason="corrupt_plan_on_disk")
        _record_degradation(ctx, plan)
        return plan

    if not isinstance(raw, dict):
        plan = absent_legacy_stub(reason="plan_missing")
        _record_degradation(ctx, plan)
        return plan

    ok, why = _basic_valid(raw)
    if not ok:
        plan = forced_sparse_plan(reason=f"schema_invalid:{why}")
        _record_degradation(ctx, plan)
        return plan

    plan = dict(raw)
    if expected_hash and plan.get("evidence_packet_hash") and plan["evidence_packet_hash"] != expected_hash:
        plan = forced_sparse_plan(reason="stale_invalidated", evidence_hash=expected_hash)
        _record_degradation(ctx, plan)
        return plan

    if prefer_pass and plan.get("pass") and plan.get("pass") != prefer_pass:
        reasons = list(plan.get("degradation_reasons") or [])
        if "unexpected_pass" not in reasons:
            reasons.append("unexpected_pass")
        plan["degradation_reasons"] = reasons

    accepted, _hy_why = hybrid_acceptance(plan)
    if not accepted:
        plan = demote_hybrid(plan)

    status = plan.get("plan_status")
    if not status:
        # A-03: missing plan_status must not default to authoritative complete.
        plan["plan_status"] = "degraded"
        reasons = list(plan.get("degradation_reasons") or [])
        if "missing_plan_status" not in reasons:
            reasons.append("missing_plan_status")
        plan["degradation_reasons"] = reasons
    elif status not in ("complete", "degraded", "forced_sparse", "absent_legacy"):
        plan["plan_status"] = "degraded"
        reasons = list(plan.get("degradation_reasons") or [])
        reasons.append("unknown_plan_status")
        plan["degradation_reasons"] = reasons

    return plan


def best_available_mode(plan: dict[str, Any]) -> str:
    return str(
        plan.get("confirmed_mode")
        or plan.get("narrative_mode")
        or plan.get("provisional_mode")
        or "sparse_source"
    )


def write_plan(
    ctx: RunContext,
    plan: dict[str, Any],
    *,
    seat_reason: str = "",
) -> None:
    from interview_mux.information_packages import ensure_episode_close_on_plan

    plan = ensure_episode_close_on_plan(plan)
    if "information_packages" not in plan:
        plan["information_packages"] = []
    # A′′ Global Freeze: preserve prior vo_seats when freeze is active and the
    # caller did not name an End-A / one-shot reason (seat-truth artifact).
    plan = _preserve_frozen_vo_seats(ctx, plan, seat_reason=seat_reason)
    ctx.write_json(PLAN_REL, plan)
    _record_degradation(ctx, plan)


def _vo_seats_blob(plan: dict[str, Any] | None) -> dict[str, Any]:
    script = (plan or {}).get("air_script") if isinstance(plan, dict) else None
    seats = (script or {}).get("vo_seats") if isinstance(script, dict) else None
    return dict(seats) if isinstance(seats, dict) else {}


def _preserve_frozen_vo_seats(
    ctx: RunContext,
    plan: dict[str, Any],
    *,
    seat_reason: str = "",
) -> dict[str, Any]:
    try:
        from interview_mux.seat_authority import (
            freeze_active,
            hard_freeze_action_permitted,
            read_seat_freeze,
        )

        if not freeze_active(ctx):
            return plan
        fr = read_seat_freeze(ctx)
        if isinstance(fr, dict) and fr.get("one_shot_rewrite"):
            return plan
        if hard_freeze_action_permitted(str(seat_reason or "").strip(), ctx):
            return plan
    except Exception:
        return plan
    try:
        prior = load_plan_raw(ctx)
    except Exception:
        prior = None
    if not isinstance(prior, dict):
        return plan
    prior_seats = _vo_seats_blob(prior)
    new_seats = _vo_seats_blob(plan)
    if prior_seats == new_seats:
        return plan
    out = dict(plan)
    script = dict(out.get("air_script") or {}) if isinstance(out.get("air_script"), dict) else {}
    script["vo_seats"] = prior_seats
    out["air_script"] = script
    try:
        ctx.log(
            "seat_freeze: preserved mastering_plan vo_seats "
            f"(not End-A; reason={seat_reason or 'empty'})",
            level="warning",
            stage=str(seat_reason or "") or None,
        )
    except Exception:
        pass
    return out


def _record_degradation(ctx: RunContext, plan: dict[str, Any]) -> None:
    meta: dict[str, Any]
    if ctx.artifact_exists("run_meta.json"):
        doc = ctx.read_json("run_meta.json")
        meta = doc if isinstance(doc, dict) else {}
    else:
        meta = {}
    meta["mastering_degradation"] = {
        "plan_status": plan.get("plan_status"),
        "narrative_mode": plan.get("narrative_mode"),
        "pass": plan.get("pass"),
        "degradation_reasons": list(plan.get("degradation_reasons") or []),
        "updated_at": _now(),
    }
    ctx.write_json("run_meta.json", meta)


def consumers_bind_enabled(cfg: dict[str, Any] | None = None) -> bool:
    from interview_mux.config import merged_config

    root = cfg if isinstance(cfg, dict) else merged_config()
    shape = ((root.get("mastering") or {}).get("shape") or {}).get("soft_gate") or {}
    if not isinstance(shape, dict):
        return False
    if shape.get("consumers_bind") is True:
        return True
    return str(shape.get("mode") or "advisory") in ("bind", "authoritative")


def soft_gate_enabled(cfg: dict[str, Any] | None = None) -> bool:
    from interview_mux.config import merged_config

    root = cfg if isinstance(cfg, dict) else merged_config()
    shape = ((root.get("mastering") or {}).get("shape") or {}).get("soft_gate") or {}
    if not isinstance(shape, dict):
        return True
    return shape.get("enable", True) is not False


def research_llm_enabled(cfg: dict[str, Any] | None = None) -> bool:
    """A-03: mastering.research.llm.enabled — wire prompts when true."""
    from interview_mux.config import merged_config

    root = cfg if isinstance(cfg, dict) else merged_config()
    research = (root.get("mastering") or {}).get("research") or {}
    llm = research.get("llm") if isinstance(research, dict) else None
    if not isinstance(llm, dict):
        return False
    return llm.get("enabled") is True


def shape_llm_enabled(cfg: dict[str, Any] | None = None) -> bool:
    """A-03: mastering.shape.llm.enabled — authoritative complete requires LLM acceptance."""
    from interview_mux.config import merged_config

    root = cfg if isinstance(cfg, dict) else merged_config()
    shape = (root.get("mastering") or {}).get("shape") or {}
    llm = shape.get("llm") if isinstance(shape, dict) else None
    if not isinstance(llm, dict):
        return False
    return llm.get("enabled") is True


def soft_gate_may_claim_complete(cfg: dict[str, Any] | None = None) -> bool:
    """A-03 / MPS-B1: soft_gate/heuristic is never authoritative — always False.

    Decoupled from research.llm / shape.llm: plan authority is Shape-LLM-only
    via claim_plan_complete(source=\"llm\"). Research flag only gates routing.
    Do not flip this to True under defaults — consumers_bind stays advisory.
    """
    _ = cfg  # reserved for future policy; soft-gate never claims complete
    return False


def claim_plan_complete(
    *,
    source: Literal["llm", "soft_gate"],
    cfg: dict[str, Any] | None = None,
) -> PlanStatus:
    """Authoritative complete only from LLM when shape.llm enabled.

    MPS-B1 / A-03: ``source=\"soft_gate\"`` is always ``degraded`` (never complete).
    """
    if source == "llm":
        return "complete" if shape_llm_enabled(cfg) else "degraded"
    if source == "soft_gate":
        return "degraded"
    return "degraded"


def clear_rebuild_scope(ctx: RunContext, scope: str) -> list[str]:
    """Clear .stage_done markers for a rebuild scope. Returns cleared stage ids."""
    stages = REBUILD_SCOPES.get(scope) or ()
    cleared: list[str] = []
    for stage in stages:
        marker = f".stage_done/{stage}"
        path = ctx.path(marker)
        if path.exists():
            try:
                path.unlink()
                cleared.append(stage)
            except OSError:
                pass
    return cleared


def precedence_ordered_segment_ids(
    *,
    plan: dict[str, Any],
    nle_ordered: list[str] | None,
    selection_ordered: list[str] | None,
) -> list[str]:
    from interview_mux.air_script import (
        load_air_script,
        omitted_segment_ids,
        ordered_ids_from_air_script,
    )

    omitted = omitted_segment_ids(plan)
    script = load_air_script(plan) or {}
    has_real_air = bool(isinstance(script, dict) and (script.get("beats") or []))
    # ordered_ids_from_air_script falls back to plan.ordered_segment_ids — only
    # honor that when the plan is authoritative or a real air_script exists.
    air_ids = ordered_ids_from_air_script(plan)
    if air_ids and (plan_is_authoritative(plan) or has_real_air):
        if nle_ordered:
            nle = [str(x) for x in nle_ordered if x and x not in omitted]
            kept_air = set(air_ids)
            nle_in = [s for s in nle if s in kept_air]
            if nle_in:
                tail = [s for s in air_ids if s not in set(nle_in)]
                return nle_in + tail
        return list(air_ids)
    plan_ids = plan.get("ordered_segment_ids")
    if (
        consumers_bind_enabled()
        and plan_is_authoritative(plan)
        and isinstance(plan_ids, list)
        and plan_ids
    ):
        return [str(x) for x in plan_ids]
    if nle_ordered:
        return list(nle_ordered)
    if selection_ordered:
        return list(selection_ordered)
    return []
