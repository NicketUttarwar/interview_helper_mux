"""Centralized required response format blocks for system prompts and volley final turns."""

from __future__ import annotations

import copy
import json
from typing import Any, Literal

from interview_mux.envelope_min_example import build_envelope_min_example
from interview_mux.null_field_policy import critical_fields_for_stage, nullable_fields_for_stage
from interview_mux.openai_structured_output import min_example_for_arbiter, min_example_for_stage
from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS

Variant = Literal["full", "compact"]

STAGE_LINT_HINTS: dict[str, str] = {
    "content_context": (
        "Pre-segmentation: set non-null approx_time_range (mm:ss-mm:ss) on every topic and "
        "key_claim. Use JSON null for segment_ids/evidence_segment_ids — never leave empty "
        "[] arrays without a time range (lint fail)."
    ),
    "content_brief_reanchor": "Every topic needs segment_ids (critical).",
    "speaker_roles": (
        "Every speaker needs role interviewer|interviewee|moderator|panelist|co_host|off_mic|unknown (critical). "
        "Panel format needs 2+ content roles. Emit conversation_profile + gap_sensitivity."
    ),
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


def build_envelope_skeleton(*, include_optional_arrays: bool = True) -> dict[str, Any]:
    """Typed envelope min-example — every top-level field has a sample value."""
    return build_envelope_min_example(include_optional_arrays=include_optional_arrays)


def build_artifact_skeleton(stage_key: str) -> dict[str, Any]:
    parent = stage_key.split("__", 1)[0] if "__" in stage_key else stage_key
    if parent in STAGE_ARTIFACT_SCHEMAS or stage_key in STAGE_ARTIFACT_SCHEMAS:
        sk = parent if parent in STAGE_ARTIFACT_SCHEMAS else stage_key
        env = min_example_for_stage(sk)
        art = env.get("artifacts")
        if isinstance(art, dict):
            return art
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
    lines.append(
        "- Optional arrays (`needs`, `follow_up_investigations`) may be `[]` when none apply; "
        "the skeleton shows one sample row per field for shape only."
    )
    return "\n".join(lines)


def _envelope_example_for_stage(stage_key: str, *, variant: Variant) -> dict[str, Any]:
    art = build_artifact_skeleton(stage_key)
    env = build_envelope_min_example(artifacts=art, include_optional_arrays=True)
    if variant == "compact":
        # Keep typed samples but drop verbose memory append rows for token budget.
        mem = env.get("memory_updates")
        if isinstance(mem, dict):
            compact_mem = {k: mem[k] for k in list(mem.keys())[:3]}
            env = {**env, "memory_updates": compact_mem}
    return env


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
        skel = json.dumps(min_example_for_arbiter(), indent=2 if variant == "full" else None)
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

    example_env = _envelope_example_for_stage(stage_key, variant=variant)
    if variant == "compact":
        skel_text = json.dumps(example_env, separators=(",", ":"))
        if len(skel_text) > 900:
            trimmed = copy.deepcopy(example_env)
            art = trimmed.get("artifacts")
            if isinstance(art, dict) and len(art) > 4:
                trimmed["artifacts"] = {k: art[k] for k in list(art)[:4]}
            skel_text = json.dumps(trimmed, separators=(",", ":"))
    else:
        skel_text = json.dumps(example_env, indent=2)

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
        "when a nullable field has no supportable value.\n"
        "Use `[]` for `needs` and `follow_up_investigations` when none apply."
    )
