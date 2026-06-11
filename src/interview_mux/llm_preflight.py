"""Deterministic pre-flight checks before flagship OpenAI LLM stage calls."""

from __future__ import annotations

from typing import Any

from interview_mux.artifact_completeness import artifact_status, compute_gaps
from interview_mux.gates import check_transcript_review_pending
from interview_mux.llm_flow_hardening import ANALYSIS_READY_ARTIFACT_PATHS
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS, validate_artifact_write
from interview_mux.run_context import RunContext

_MIN_TRANSCRIPT_CHARS = 80

_FLOW_UPSTREAM_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "topic_coverage_audit": (
        "segments/manifest.json",
        "understanding/content_brief.json",
        "understanding/analysis_state.json",
    ),
    "narrative_arc_plan": ("flow_1_master/coverage_audit.json",),
    "full_master_ranking": ("flow_1_master/narrative_plan.json",),
    "highlight_selection": (
        "segments/manifest.json",
        "understanding/content_brief.json",
    ),
    "transitions": ("flow_1_master/selection.json",),
    "podcast_sfx_brief": ("flow_1_master/selection.json",),
    "sound_design_plan_flow1": ("understanding/sound_design_plan.json",),
    "sound_design_plan_flow2": ("understanding/sound_design_plan.json",),
    "sfx_brief": ("flow_2_highlights/selection.json",),
    "podcast_show_description": ("flow_1_master/selection.json",),
    "edl_narrative_audit": ("flow_1_master/edl.json",),
}


def run_preflight(stage_key: str, ctx: RunContext) -> list[str]:
    """Return human-readable preflight errors (empty list = pass)."""
    checker = _PREFLIGHT_CHECKERS.get(stage_key)
    if checker is None:
        upstream = _FLOW_UPSTREAM_ARTIFACTS.get(stage_key)
        if upstream:
            return _check_upstream_artifacts(ctx, upstream)
        return []
    return checker(ctx)


def _check_upstream_artifacts(ctx: RunContext, paths: tuple[str, ...]) -> list[str]:
    errors: list[str] = []
    for rel in paths:
        if not ctx.artifact_exists(rel):
            errors.append(f"Missing upstream artifact: {rel}")
            continue
        if artifact_status(rel, ctx) != "complete":
            errors.append(f"Upstream artifact incomplete: {rel}")
    return errors


def _preflight_speaker_roles(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    if not ctx.artifact_exists("transcript/full.json"):
        return ["transcript/full.json missing"]
    doc = ctx.read_json("transcript/full.json")
    text = ""
    if isinstance(doc, dict):
        text = str(doc.get("text") or "")
        if not text and doc.get("items"):
            text = " ".join(
                str(it.get("text", "")) for it in doc["items"] if isinstance(it, dict)
            )
    if len(text.strip()) < 10:
        errors.append("transcript/full.json is empty or too short")
    if check_transcript_review_pending(ctx):
        errors.append("Transcript review (G0) incomplete")
    return errors


def _preflight_content_context(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    if not ctx.artifact_exists("transcript/full.json"):
        return ["transcript/full.json missing"]
    doc = ctx.read_json("transcript/full.json")
    text = str(doc.get("text") or "") if isinstance(doc, dict) else str(doc or "")
    if len(text.strip()) < _MIN_TRANSCRIPT_CHARS:
        errors.append(f"transcript shorter than {_MIN_TRANSCRIPT_CHARS} characters")
    if check_transcript_review_pending(ctx):
        errors.append("Transcript review (G0) incomplete")
    return errors


def _preflight_boundary_detection(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    if not ctx.artifact_exists("understanding/speakers.json"):
        return ["understanding/speakers.json missing"]
    doc = ctx.read_json("understanding/speakers.json")
    schema_errors = validate_artifact_write("understanding/speakers.json", doc)
    if schema_errors:
        errors.append(f"speakers.json schema: {schema_errors[0]}")
    speakers = doc.get("speakers") or []
    if not speakers:
        errors.append("speakers.json has no speakers")
        return errors
    roles = {str(sp.get("role", "")).strip().lower() for sp in speakers if isinstance(sp, dict)}
    if "interviewer" not in roles:
        errors.append("speakers.json missing interviewer role")
    return errors


def _preflight_segment_classification(ctx: RunContext) -> list[str]:
    if not ctx.artifact_exists("segments/boundaries.json"):
        return ["segments/boundaries.json missing"]
    doc = ctx.read_json("segments/boundaries.json")
    boundaries = doc.get("boundaries") if isinstance(doc, dict) else None
    if not boundaries:
        return ["segments/boundaries.json has no boundaries"]
    return []


def _preflight_content_brief_reanchor(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    if not ctx.artifact_exists("understanding/content_brief.json"):
        errors.append("understanding/content_brief.json missing")
    else:
        brief = ctx.read_json("understanding/content_brief.json")
        gaps = compute_gaps("understanding/content_brief.json", brief)
        if gaps:
            errors.append(f"content_brief gaps: {gaps[0].path}")
        elif isinstance(brief, dict):
            if not str(brief.get("thesis", "")).strip():
                errors.append("content_brief missing thesis")
            if not (brief.get("topics") or []):
                errors.append("content_brief missing topics")
    if not ctx.artifact_exists("segments/manifest.json"):
        errors.append("segments/manifest.json missing")
    return errors


def _preflight_missing_framing(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    if not ctx.artifact_exists("understanding/content_brief.json"):
        errors.append("understanding/content_brief.json missing")
    if not ctx.artifact_exists("segments/manifest.json"):
        errors.append("segments/manifest.json missing")
    else:
        manifest = ctx.read_json("segments/manifest.json")
        segs = manifest.get("segments") or [] if isinstance(manifest, dict) else []
        if not segs:
            errors.append("segments/manifest.json has no segments")
    return errors


def _preflight_optimal_questions(ctx: RunContext) -> list[str]:
    if not ctx.artifact_exists("understanding/gap_evaluations.json"):
        return ["understanding/gap_evaluations.json missing"]
    return []


def _preflight_pre_flow1(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    for rel in ANALYSIS_READY_ARTIFACT_PATHS:
        if artifact_status(rel, ctx) != "complete":
            errors.append(f"{rel} is not complete")
    for stage_key, rel in STAGE_ARTIFACT_DISK_PATHS.items():
        if stage_key in (
            "speaker_roles",
            "content_context",
            "boundary_detection",
            "segment_classification",
            "content_brief_reanchor",
            "missing_framing",
            "optimal_questions",
        ):
            if artifact_status(rel, ctx) != "complete":
                errors.append(f"Critical analysis artifact {rel} incomplete")
    return errors


_PREFLIGHT_CHECKERS: dict[str, Any] = {
    "speaker_roles": _preflight_speaker_roles,
    "content_context": _preflight_content_context,
    "boundary_detection": _preflight_boundary_detection,
    "segment_classification": _preflight_segment_classification,
    "content_brief_reanchor": _preflight_content_brief_reanchor,
    "missing_framing": _preflight_missing_framing,
    "optimal_questions": _preflight_optimal_questions,
    "topic_coverage_audit": _preflight_pre_flow1,
}
