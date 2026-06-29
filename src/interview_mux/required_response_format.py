"""Centralized required response format blocks for system prompts and volley final turns."""

from __future__ import annotations

import json
from typing import Any, Literal

from interview_mux.null_field_policy import critical_fields_for_stage, nullable_fields_for_stage
from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS

Variant = Literal["full", "compact"]

ENVELOPE_SKELETON: dict[str, Any] = {
    "status": "complete",
    "artifacts": {},
    "memory_updates": {},
    "needs": [],
    "follow_up_investigations": [],
    "confidence": 0.0,
    "reasoning_summary": "2-5 sentences for the next stage",
}

ARBITER_SKELETON: dict[str, Any] = {
    "verdict": "accept",
    "confidence": 0.0,
    "gaps": [],
    "shard_plan": [],
    "suggested_investigation": None,
    "reasoning_summary": "",
}

# Compact artifact top-level shapes per stage (inside envelope.artifacts).
ARTIFACT_SKELETONS: dict[str, dict[str, Any]] = {
    "speaker_roles": {
        "speakers": [
            {
                "speaker_id": "spk_0",
                "role": "interviewer",
                "label": "Host",
                "confidence": 0.9,
            }
        ]
    },
    "content_context": {
        "thesis": "one sentence (critical)",
        "topics": [{"name": "string", "summary": "string", "approx_time_range": "optional|null"}],
        "key_claims": [],
        "audience": None,
        "emotional_beats": None,
        "jargon_glossary": None,
    },
    "content_brief_reanchor": {
        "thesis": "string",
        "topics": [{"name": "string", "segment_ids": ["seg_001"]}],
        "topic_relationships": None,
    },
    "boundary_detection": {"boundaries": [{"segment_id": "seg_001", "start_ms": 0, "end_ms": 1000}]},
    "segment_classification": {
        "segments": [{"segment_id": "seg_001", "type": "answer", "topic_tags": None}]
    },
    "missing_framing": {"evaluations": [{"segment_id": "seg_001", "gap_type": "missing_definition"}]},
    "optimal_questions": {"gaps": [{"segment_id": "seg_001", "vo_line": "short question"}]},
    "topic_coverage_audit": {"coverage_score": 0.85, "gaps": None},
    "narrative_arc_plan": {"chapters": [{"title": "string", "segment_ids": []}]},
    "full_master_ranking": {"ordered_segment_ids": ["seg_001"]},
    "highlight_selection": {"highlights": [{"segment_id": "seg_001", "reason": "string"}]},
    "transitions": {"transitions": [{"after_segment_id": "seg_001", "text": "short bridge"}]},
    "podcast_show_description": {"description": "string", "subtitle": None},
}

STAGE_LINT_HINTS: dict[str, str] = {
    "content_context": (
        "Every topic and key_claim needs segment_ids or approx_time_range unless nullable null."
    ),
    "content_brief_reanchor": "Every topic needs segment_ids (critical).",
    "speaker_roles": "Every speaker needs role interviewer|interviewee|unknown (critical).",
    "boundary_detection": "Every boundary needs start_ms/end_ms tied to transcript.",
    "segment_classification": (
        "Return one row per required_segment_id in classification_obligation; vary types beyond interviewee_answer."
    ),
}

PROFILE_NOTES: dict[str, str] = {
    "shard": "Return one complete envelope for this evidence slice only.",
    "collate": "Merge shard outputs losslessly into one envelope; dedupe topics/claims by name.",
    "full": "Return one complete envelope for the full stage.",
}


def build_envelope_skeleton() -> dict[str, Any]:
    return dict(ENVELOPE_SKELETON)


def build_artifact_skeleton(stage_key: str) -> dict[str, Any]:
    if stage_key in ARTIFACT_SKELETONS:
        return json.loads(json.dumps(ARTIFACT_SKELETONS[stage_key]))
    return {"stage_output": "per stage prompt schema"}


def _null_rules_block(stage_key: str, *, variant: Variant) -> str:
    critical = sorted(critical_fields_for_stage(stage_key))
    nullable = sorted(nullable_fields_for_stage(stage_key))
    if not critical and not nullable:
        return ""
    lines = ["### JSON null rules"]
    if critical:
        label = ", ".join(critical[:8 if variant == "compact" else 16])
        lines.append(f"- Critical (never null): {label}")
    if nullable:
        label = ", ".join(nullable[:6 if variant == "compact" else 14])
        lines.append(f"- Nullable (use JSON null when unavailable): {label}")
    lines.append("- Use JSON null, not empty strings or invented placeholders.")
    return "\n".join(lines)


def build_required_response_block(
    stage_key: str,
    *,
    variant: Variant = "full",
    profile: str = "full",
    task_kind: str = "primary",
    gap_fill_context: dict[str, Any] | None = None,
) -> str:
    """Markdown section for system prompt or final volley turn."""
    if task_kind == "arbiter":
        skel = json.dumps(ARBITER_SKELETON, indent=2 if variant == "full" else None)
        return (
            "## Required response format\n"
            "Reply with one JSON object only (arbiter verdict).\n"
            f"```json\n{skel}\n```"
        )

    lines = ["## Required response format"]
    lines.append(
        "Reply with **one JSON object** — the analysis **envelope** root "
        "(status, artifacts, memory_updates, needs, follow_up_investigations, "
        "confidence, reasoning_summary). Never return only the inner artifact."
    )

    if gap_fill_context and gap_fill_context.get("gaps"):
        gaps = gap_fill_context.get("gaps") or []
        lines.append(
            f"Patch-only mode: fill gaps {gaps[:8]} only; "
            f"skip {gap_fill_context.get('skip_fields', [])[:8]}."
        )

    env = build_envelope_skeleton()
    art = build_artifact_skeleton(stage_key)
    env["artifacts"] = art

    if variant == "compact":
        compact_env = {
            "status": "complete",
            "artifacts": art,
            "memory_updates": {},
            "needs": [],
            "reasoning_summary": "...",
        }
        skel_text = json.dumps(compact_env, separators=(",", ":"))
        if len(skel_text) > 600:
            skel_text = json.dumps({"status": "complete", "artifacts": {k: art[k] for k in list(art)[:4]}}, separators=(",", ":"))
    else:
        skel_text = json.dumps(env, indent=2)

    lines.append(f"```json\n{skel_text}\n```")

    null_block = _null_rules_block(stage_key, variant=variant)
    if null_block:
        lines.append(null_block)

    prof_note = PROFILE_NOTES.get(profile) or PROFILE_NOTES.get("full", "")
    if prof_note and profile != "full":
        lines.append(f"Profile ({profile}): {prof_note}")

    lint = STAGE_LINT_HINTS.get(stage_key)
    if lint and variant == "full":
        lines.append(f"Lint: {lint}")

    if stage_key in STAGE_ARTIFACT_SCHEMAS and variant == "full":
        lines.append(f"Schema: artifacts → {STAGE_ARTIFACT_SCHEMAS[stage_key]}")

    return "\n\n".join(lines)


def volley_format_footer(
    stage_key: str,
    *,
    profile: str = "full",
    task_kind: str = "primary",
    gap_fill_context: dict[str, Any] | None = None,
) -> str:
    """Compact block appended to final volley user turn."""
    block = build_required_response_block(
        stage_key,
        variant="compact",
        profile=profile,
        task_kind=task_kind,
        gap_fill_context=gap_fill_context,
    )
    return (
        f"{block}\n\n"
        "Reply with the JSON envelope only. No markdown fences. "
        "No prose outside the JSON object.\n"
        "Use JSON null (literal null, not the string \"NULL\") "
        "when a nullable field has no supportable value."
    )
