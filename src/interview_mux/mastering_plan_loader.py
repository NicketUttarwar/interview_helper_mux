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
        "gap_framing_recompose",
        "selection_framing_apply",
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

    status = plan.get("plan_status") or "complete"
    if status not in ("complete", "degraded", "forced_sparse", "absent_legacy"):
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


def write_plan(ctx: RunContext, plan: dict[str, Any]) -> None:
    ctx.write_json(PLAN_REL, plan)
    _record_degradation(ctx, plan)


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
    plan_ids = plan.get("ordered_segment_ids")
    if consumers_bind_enabled() and isinstance(plan_ids, list) and plan_ids:
        return [str(x) for x in plan_ids]
    if nle_ordered:
        return list(nle_ordered)
    if selection_ordered:
        return list(selection_ordered)
    return []
