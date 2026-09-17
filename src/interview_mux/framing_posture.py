"""Early framing posture advisory — homunculus 0.1.0+ only."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from interview_mux.config import merged_config
from interview_mux.gap_fill_eligibility import assess_gap_fill_eligibility, silent_skip_allowed
from interview_mux.homunculus.runtime import has_homunculus_features
from interview_mux.run_context import RunContext

FRAMING_POSTURE_DECISION_REL = "understanding/framing_posture_decision.json"

RecommendedFraming = Literal["yes", "no", "sparse"]
PostureHint = Literal["framing_full", "framing_sparse", "native_only"]
DecidedBy = Literal[
    "llm_advisory",
    "deterministic_monologue",
    "homunculus_skip",
    "feature_disabled",
]


def framing_posture_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis = (cfg or merged_config()).get("analysis") or {}
    defaults = {
        "enabled": True,
        "llm_tier": "flagship",
        "host_enforce": True,
    }
    raw = analysis.get("framing_posture")
    if isinstance(raw, dict):
        return {**defaults, **raw}
    return defaults


def framing_posture_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(framing_posture_cfg(cfg).get("enabled", True))


def _compute_volley_stats(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return {"segment_count": 0}
    manifest = ctx.read_json("segments/manifest.json")
    rows = [
        s for s in ((manifest or {}).get("segments") or []) if isinstance(s, dict)
    ]
    if not rows:
        return {"segment_count": 0}

    speaker_changes = 0
    prev_speaker: str | None = None
    durations: list[float] = []
    by_type: dict[str, int] = {}

    for row in rows:
        speaker = str(row.get("speaker_id") or "")
        if prev_speaker and speaker and speaker != prev_speaker:
            speaker_changes += 1
        if speaker:
            prev_speaker = speaker

        seg_type = str(row.get("segment_type") or row.get("type") or "unknown")
        by_type[seg_type] = by_type.get(seg_type, 0) + 1

        start = float(row.get("start_ms") or 0)
        end = float(row.get("end_ms") or start)
        durations.append(max(0.0, end - start))

    segment_count = len(rows)
    avg_duration = round(sum(durations) / max(1, len(durations)), 1)
    change_rate = round(speaker_changes / max(1, segment_count - 1), 4)

    return {
        "segment_count": segment_count,
        "speaker_change_count": speaker_changes,
        "speaker_change_rate": change_rate,
        "segment_type_counts": by_type,
        "avg_segment_duration_ms": avg_duration,
        "interviewer_question_segments": by_type.get("interviewer_question", 0),
        "interviewee_answer_segments": by_type.get("interviewee_answer", 0),
    }


def _exclusion_ratio_hints(ctx: RunContext) -> dict[str, Any]:
    manifest_count = 0
    if ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")
        manifest_count = len((manifest or {}).get("segments") or [])

    ideal_cut_segments = 0
    if ctx.artifact_exists("understanding/ideal_cuts_materialized.json"):
        cuts = ctx.read_json("understanding/ideal_cuts_materialized.json")
        for row in (cuts or {}).get("cuts") or []:
            if isinstance(row, dict) and row.get("segment_id"):
                ideal_cut_segments += 1

    hints: dict[str, Any] = {
        "manifest_segment_count": manifest_count,
        "ideal_cut_segment_count": ideal_cut_segments,
    }
    if manifest_count:
        hints["ideal_cut_coverage_ratio"] = round(
            ideal_cut_segments / max(manifest_count, 1), 4
        )
        hints["max_exclusion_ratio_hint"] = float(
            ((merged_config().get("analysis") or {}).get("gap_framing") or {}).get(
                "max_exclusion_ratio", 0.15
            )
        )
    return hints


def build_framing_posture_input(ctx: RunContext) -> dict[str, Any]:
    """Pack topology, brief, volley stats, and early comprehension signals."""
    from interview_mux.conversation_context import attach_conversation_context
    from interview_mux.interview_spine.compact import attach_spine_to_payload
    from interview_mux.source_topology import attach_adaptation_to_payload

    payload: dict[str, Any] = {
        "content_brief": ctx.read_json("understanding/content_brief.json"),
        "volley_stats": _compute_volley_stats(ctx),
        "exclusion_ratio_hints": _exclusion_ratio_hints(ctx),
    }
    if ctx.artifact_exists("understanding/speakers.json"):
        payload["speakers"] = ctx.read_json("understanding/speakers.json")

    payload = attach_adaptation_to_payload(ctx, payload)
    payload = attach_conversation_context(ctx, payload, "framing_posture_decide")
    attach_spine_to_payload(ctx, payload, "framing_posture_decide")

    eligibility = assess_gap_fill_eligibility(ctx)
    payload["gap_fill_eligibility"] = {
        "eligible": eligibility.eligible,
        "reason": eligibility.reason,
        "signals": dict(eligibility.signals or {}),
    }

    try:
        from interview_mux.llm_specialists import load_comprehension_risks

        risks = load_comprehension_risks(ctx, "missing_framing")
        if risks:
            payload["comprehension_risks"] = risks[:24]
    except Exception:
        pass

    return payload


def _normalize_decision(decision: dict[str, Any], *, decided_by: DecidedBy) -> dict[str, Any]:
    out = dict(decision or {})
    out.setdefault("recommended_framing", "yes")
    out.setdefault("posture_hint", "framing_full")
    out.setdefault("rationale_plain", "")
    out.setdefault("reason_codes", [])
    out["decided_by"] = decided_by
    out["advisory_only"] = decided_by == "llm_advisory"
    out["decided_at"] = datetime.now(timezone.utc).isoformat()
    return out


def build_monologue_decision(ctx: RunContext) -> dict[str, Any]:
    decision = assess_gap_fill_eligibility(ctx)
    return _normalize_decision(
        {
            "recommended_framing": "no",
            "posture_hint": "native_only",
            "rationale_plain": decision.reason,
            "reason_codes": ["deterministic_monologue"],
            "signals_summary": dict(decision.signals or {}),
        },
        decided_by="deterministic_monologue",
    )


def build_allow_stub_decision(*, decided_by: DecidedBy) -> dict[str, Any]:
    """Schema-complete stub so seed/delivery can proceed without the advisory LLM.

    Does not skip gap fill (HU-2 3A). G-Framing still runs as a normal gate.
    """
    if decided_by == "feature_disabled":
        rationale = (
            "Framing posture advisory is disabled. G-Framing still runs as a normal gate."
        )
        codes = ["feature_disabled"]
    else:
        rationale = (
            "Framing posture advisory skipped for this brain. "
            "G-Framing still runs as a normal gate."
        )
        codes = ["homunculus_skip"]
    return _normalize_decision(
        {
            "recommended_framing": "yes",
            "posture_hint": "framing_full",
            "rationale_plain": rationale,
            "reason_codes": codes,
        },
        decided_by=decided_by,
    )


def persist_framing_decision(ctx: RunContext, decision: dict[str, Any]) -> None:
    from interview_mux.artifact_writes import write_validated_artifact

    decided_by = str(decision.get("decided_by") or "llm_advisory")
    doc = _normalize_decision(decision, decided_by=decided_by)  # type: ignore[arg-type]
    write_validated_artifact(
        ctx,
        FRAMING_POSTURE_DECISION_REL,
        doc,
        stage_key="framing_posture_decide",
    )


def apply_host_gate(ctx: RunContext) -> None:
    """Enforce deterministic native_only — never LLM advisory alone (2M)."""
    if not framing_posture_cfg().get("host_enforce", True):
        return
    if not ctx.artifact_exists(FRAMING_POSTURE_DECISION_REL):
        return

    doc = ctx.read_json(FRAMING_POSTURE_DECISION_REL)
    if not isinstance(doc, dict):
        return

    decided_by = str(doc.get("decided_by") or "")
    posture = str(doc.get("posture_hint") or "")
    if posture != "native_only":
        return
    if decided_by not in {"deterministic_monologue", "operator_g_framing", "forced_skip"}:
        return

    from interview_mux.stages.gaps import ensure_gap_fill_skipped

    reason = str(doc.get("rationale_plain") or "native_only posture")
    signals = doc.get("signals_summary") if isinstance(doc.get("signals_summary"), dict) else {}
    ensure_gap_fill_skipped(ctx, reason=reason, signals=dict(signals))


def should_run_framing_posture_llm(ctx: RunContext) -> bool:
    """Skip LLM for true monologue; homunculus-only guard is applied by the stage runner."""
    if not has_homunculus_features(ctx):
        return False
    if not framing_posture_enabled():
        return False
    decision = assess_gap_fill_eligibility(ctx)
    if not decision.eligible and silent_skip_allowed(decision):
        return False
    return True


__all__ = [
    "FRAMING_POSTURE_DECISION_REL",
    "apply_host_gate",
    "build_allow_stub_decision",
    "build_framing_posture_input",
    "build_monologue_decision",
    "framing_posture_cfg",
    "framing_posture_enabled",
    "persist_framing_decision",
    "should_run_framing_posture_llm",
]
