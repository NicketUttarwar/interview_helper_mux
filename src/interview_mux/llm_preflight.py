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


def _preflight_sound_design_palettes(ctx: RunContext) -> list[str]:
    errors = _check_upstream_artifacts(ctx, ("understanding/content_brief.json", "segments/manifest.json"))
    if ctx.artifact_exists("understanding/content_brief.json"):
        brief = ctx.read_json("understanding/content_brief.json")
        if not str((brief or {}).get("thesis", "")).strip():
            errors.append("content_brief missing thesis before palettes")
    return errors


def _preflight_sound_design_plan_flow1(ctx: RunContext) -> list[str]:
    errors = _check_upstream_artifacts(
        ctx,
        (
            "understanding/sound_design_plan.json",
            "flow_1_master/selection.json",
            "flow_1_master/narrative_plan.json",
        ),
    )
    if ctx.artifact_exists("understanding/sound_design_plan.json"):
        sdp = ctx.read_json("understanding/sound_design_plan.json")
        if not (sdp.get("palettes") or []):
            errors.append("SDP palettes empty before flow1 plan")
        if not str((sdp.get("coherence") or {}).get("sonic_identity", "")).strip():
            errors.append("SDP coherence.sonic_identity missing")
    return errors


def _preflight_sound_design_plan_flow2(ctx: RunContext) -> list[str]:
    return _check_upstream_artifacts(
        ctx,
        ("understanding/sound_design_plan.json", "flow_2_highlights/selection.json"),
    )


def _preflight_sfx_prompt_craft(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        return ["understanding/sound_design_plan.json missing"]
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    assets = sdp.get("assets") or []
    if not assets:
        errors.append("SDP assets[] empty before prompt craft")
    from interview_mux.config import merged_config

    mcfg = merged_config().get("mmaudio") or {}
    min_s = float(mcfg.get("min_duration_sec", 3.0))
    max_s = float(mcfg.get("max_duration_sec", 8.0))
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        role = str(asset.get("role") or "")
        if not role:
            errors.append(f"SDP asset {asset.get('asset_id')} missing role before craft")
        dur = asset.get("duration_seconds")
        if dur is not None:
            d = float(dur)
            if d < min_s - 0.5 or d > max_s + 0.5:
                errors.append(
                    f"SDP asset {asset.get('asset_id')} duration {d}s outside MMAudio plan band"
                )
    return errors


def _preflight_edl_narrative_audit(ctx: RunContext) -> list[str]:
    return _check_upstream_artifacts(
        ctx,
        (
            "flow_1_master/selection.json",
            "flow_1_master/narrative_plan.json",
            "flow_1_master/coverage_audit.json",
        ),
    )


def _preflight_podcast_show_description(ctx: RunContext) -> list[str]:
    from interview_mux.gates import get_selected_flow

    flow = get_selected_flow(ctx)
    if flow == "flow3":
        return _check_upstream_artifacts(
            ctx,
            (
                "understanding/content_brief.json",
                "understanding/speakers.json",
                "segments/manifest.json",
            ),
        )
    return _check_upstream_artifacts(ctx, ("flow_1_master/selection.json",))


def _preflight_narrative_arc_plan(ctx: RunContext) -> list[str]:
    return _check_upstream_artifacts(ctx, ("flow_1_master/coverage_audit.json",))


def _preflight_full_master_ranking(ctx: RunContext) -> list[str]:
    return _check_upstream_artifacts(
        ctx,
        ("flow_1_master/narrative_plan.json", "flow_1_master/coverage_audit.json"),
    )


def _preflight_highlight_selection(ctx: RunContext) -> list[str]:
    return _check_upstream_artifacts(
        ctx,
        ("segments/manifest.json", "understanding/content_brief.json", "understanding/gap_report.json"),
    )


def _preflight_transitions(ctx: RunContext) -> list[str]:
    return _check_upstream_artifacts(ctx, ("flow_1_master/selection.json",))


def _preflight_topic_coverage(ctx: RunContext) -> list[str]:
    return _preflight_pre_flow1(ctx)


def _preflight_sfx_prompt_refine(ctx: RunContext) -> list[str]:
    errors = _preflight_sfx_prompt_craft(ctx)
    if not ctx.artifact_exists("sound_design/sfx_prompts.json"):
        errors.append("sound_design/sfx_prompts.json missing before refine")
    return errors


_PREFLIGHT_CHECKERS: dict[str, Any] = {
    "speaker_roles": _preflight_speaker_roles,
    "content_context": _preflight_content_context,
    "boundary_detection": _preflight_boundary_detection,
    "segment_classification": _preflight_segment_classification,
    "content_brief_reanchor": _preflight_content_brief_reanchor,
    "missing_framing": _preflight_missing_framing,
    "optimal_questions": _preflight_optimal_questions,
    "sound_design_palettes": _preflight_sound_design_palettes,
    "topic_coverage_audit": _preflight_topic_coverage,
    "narrative_arc_plan": _preflight_narrative_arc_plan,
    "full_master_ranking": _preflight_full_master_ranking,
    "highlight_selection": _preflight_highlight_selection,
    "transitions": _preflight_transitions,
    "sound_design_plan_flow1": _preflight_sound_design_plan_flow1,
    "sound_design_plan_flow2": _preflight_sound_design_plan_flow2,
    "sfx_prompt_craft": _preflight_sfx_prompt_craft,
    "sfx_prompt_refine": _preflight_sfx_prompt_refine,
    "edl_narrative_audit": _preflight_edl_narrative_audit,
    "podcast_show_description": _preflight_podcast_show_description,
}
