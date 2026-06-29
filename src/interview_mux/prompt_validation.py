"""Validate LLM stage artifacts against JSON Schema (docs/cross-cutting/json-schemas/artifacts/)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from interview_mux.config import repo_root

# stage_key -> artifact schema filename (under artifacts/)
STAGE_ARTIFACT_SCHEMAS: dict[str, str] = {
    "speaker_roles": "speakers_artifact.schema.json",
    "content_context": "content_brief_artifact.schema.json",
    "content_brief_reanchor": "content_brief_artifact.schema.json",
    "boundary_detection": "boundaries_artifact.schema.json",
    "segment_classification": "manifest_artifact.schema.json",
    "sound_design_palettes": "sound_design_palettes_artifact.schema.json",
    "missing_framing": "gap_evaluations_artifact.schema.json",
    "optimal_questions": "gap_report.schema.json",
    "topic_coverage_audit": "coverage_audit_artifact.schema.json",
    "narrative_arc_plan": "narrative_plan_artifact.schema.json",
    "full_master_ranking": "master_selection_artifact.schema.json",
    "edl_narrative_audit": "edl_narrative_audit_artifact.schema.json",
    "highlight_selection": "highlights_artifact.schema.json",
    "transitions": "transitions_artifact.schema.json",
    "podcast_sfx_brief": "podcast_sfx_artifact.schema.json",
    "sound_design_plan_flow1": "sound_design_plan_flow1_artifact.schema.json",
    "sound_design_plan_flow2": "sound_design_plan_flow2_artifact.schema.json",
    "sfx_prompt_craft": "sfx_prompts_artifact.schema.json",
    "sfx_prompt_refine": "sfx_prompts_artifact.schema.json",
    "sfx_brief": "sfx_montage_artifact.schema.json",
    "podcast_show_description": "show_description_artifact.schema.json",
}

# stage_key -> on-disk relative path (under run dir)
STAGE_ARTIFACT_DISK_PATHS: dict[str, str] = {
    "speaker_roles": "understanding/speakers.json",
    "content_context": "understanding/content_brief.json",
    "content_brief_reanchor": "understanding/content_brief.json",
    "boundary_detection": "segments/boundaries.json",
    "segment_classification": "segments/manifest.json",
    "sound_design_palettes": "understanding/sound_design_plan.json",
    "missing_framing": "understanding/gap_evaluations.json",
    "optimal_questions": "understanding/gap_report.json",
    "topic_coverage_audit": "flow_1_master/coverage_audit.json",
    "narrative_arc_plan": "flow_1_master/narrative_plan.json",
    "full_master_ranking": "flow_1_master/selection.json",
    "edl_narrative_audit": "flow_1_master/edl_narrative_audit.json",
    "highlight_selection": "flow_2_highlights/selection.json",
    "transitions": "flow_1_master/transitions.json",
    "podcast_sfx_brief": "flow_1_master/podcast_sfx_brief.json",
    "sound_design_plan_flow1": "understanding/sound_design_plan.json",
    "sound_design_plan_flow2": "understanding/sound_design_plan.json",
    "sfx_prompt_craft": "sound_design/sfx_prompts.json",
    "sfx_brief": "flow_2_highlights/sfx_brief.json",
    "podcast_show_description": "flow_3_description/show_description.json",
}


def _schemas_dir() -> Path:
    return repo_root() / "docs" / "cross-cutting" / "json-schemas" / "artifacts"


def _json_schemas_root() -> Path:
    return repo_root() / "docs" / "cross-cutting" / "json-schemas"


@lru_cache(maxsize=8)
def _load_root_schema(filename: str) -> dict[str, Any] | None:
    path = _json_schemas_root() / filename
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=32)
def _load_schema(filename: str) -> dict[str, Any] | None:
    path = _schemas_dir() / filename
    if not path.is_file():
        # gap_report lives one level up
        alt = repo_root() / "docs" / "cross-cutting" / "json-schemas" / filename
        if alt.is_file():
            return json.loads(alt.read_text(encoding="utf-8"))
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=4)
def _load_envelope_schema() -> dict[str, Any] | None:
    return _load_root_schema("analysis_envelope.schema.json")


def validate_envelope(envelope: dict[str, Any]) -> list[str]:
    """Validate analysis envelope shape before arbiter (BUILD-084)."""
    schema = _load_envelope_schema()
    if not schema:
        return []
    return [f"envelope.{e}" for e in _validate_dict(envelope, schema)]


def validate_investigation_queue(queue: dict[str, Any]) -> list[str]:
    return _validate_dict(queue, _load_root_schema("investigation_queue.schema.json"))


def validate_nle_edits(data: dict[str, Any]) -> list[str]:
    return _validate_dict(data, _load_root_schema("nle_edits.schema.json"))


def validate_stage_artifacts(stage_key: str, artifacts: dict[str, Any]) -> list[str]:
    """Return human-readable validation errors (empty if OK or no schema)."""
    filename = STAGE_ARTIFACT_SCHEMAS.get(stage_key)
    if not filename or not artifacts:
        return []
    schema = _load_schema(filename)
    if not schema:
        return []
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for err in sorted(validator.iter_errors(artifacts), key=lambda e: list(e.path)):
        loc = ".".join(str(p) for p in err.path) or "(root)"
        errors.append(f"{loc}: {err.message}")
    return errors[:12]


def format_validation_feedback(
    errors: list[str],
    *,
    stage_key: str | None = None,
    envelope_errors: list[str] | None = None,
) -> str:
    from interview_mux.required_response_format import build_envelope_skeleton, build_required_response_block

    lines = ["## Schema validation failed", "Fix the response to satisfy validation. Errors:"]
    env_errs = envelope_errors or [e for e in errors if e.startswith("envelope.")]
    art_errs = [e for e in errors if not e.startswith("envelope.")]
    if env_errs:
        lines.append("\n### Envelope")
        lines.extend(f"- {e}" for e in env_errs)
        skel = json.dumps(build_envelope_skeleton(), indent=2)
        lines.append(f"\nEnvelope skeleton:\n```json\n{skel}\n```")
    if art_errs:
        lines.append("\n### Artifacts")
        lines.extend(f"- {e}" for e in art_errs)
    if stage_key:
        lines.append(
            f"\n{build_required_response_block(stage_key, variant='compact')}"
        )
    return "\n".join(lines)


def _validate_dict(data: dict[str, Any], schema: dict[str, Any] | None) -> list[str]:
    if not schema:
        return []
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        loc = ".".join(str(p) for p in err.path) or "(root)"
        errors.append(f"{loc}: {err.message}")
    return errors[:12]


def validate_sound_design_plan(plan: dict[str, Any]) -> list[str]:
    """Validate `understanding/sound_design_plan.json` against sound_design_plan.schema.json."""
    return _validate_dict(plan, _load_root_schema("sound_design_plan.schema.json"))


def validate_master_selection(selection: dict[str, Any]) -> list[str]:
    """Validate `flow_1_master/selection.json` against master_selection_artifact.schema.json."""
    return _validate_dict(selection, _load_schema("master_selection_artifact.schema.json"))


def validate_edl_narrative_audit(audit: dict[str, Any]) -> list[str]:
    """Validate `flow_1_master/edl_narrative_audit.json`."""
    return _validate_dict(audit, _load_schema("edl_narrative_audit_artifact.schema.json"))


def validate_edl_flow1(edl: dict[str, Any]) -> list[str]:
    """Validate `flow_1_master/edl.json` against artifacts/edl_flow1.schema.json."""
    return _validate_dict(edl, _load_schema("edl_flow1.schema.json"))


def validate_source_acoustic_profile(profile: dict[str, Any]) -> list[str]:
    """Validate `understanding/source_acoustic_profile.json`."""
    return _validate_dict(profile, _load_root_schema("source_acoustic_profile.schema.json"))


def validate_interview_spine(doc: dict[str, Any]) -> list[str]:
    """Validate `understanding/interview_spine.json`."""
    return _validate_dict(doc, _load_root_schema("interview_spine.schema.json"))


def validate_coherence_report(doc: dict[str, Any]) -> list[str]:
    """Validate `understanding/coherence_report.json`."""
    return _validate_dict(doc, _load_root_schema("coherence_report.schema.json"))


def validate_analysis_state(state: dict[str, Any]) -> list[str]:
    """Validate `understanding/analysis_state.json`."""
    return _validate_dict(state, _load_root_schema("analysis_state.schema.json"))


def validate_run_meta(meta: dict[str, Any]) -> list[str]:
    """Validate `run_meta.json`."""
    return _validate_dict(meta, _load_root_schema("run_meta.schema.json"))


def validate_transcript_corrections(data: dict[str, Any]) -> list[str]:
    """Validate `transcript/corrections.json`."""
    return _validate_dict(data, _load_root_schema("transcript_corrections.schema.json"))


def validate_ingest_checksums(data: dict[str, Any]) -> list[str]:
    """Validate `ingest/checksums.json`."""
    return _validate_dict(data, _load_root_schema("ingest_checksums.schema.json"))


def validate_transcript_review_queue(data: dict[str, Any]) -> list[str]:
    """Validate `transcript/review_queue.json`."""
    return _validate_dict(data, _load_root_schema("transcript_review.schema.json"))


def validate_disfluencies(data: dict[str, Any]) -> list[str]:
    """Validate `transcript/disfluencies.json`."""
    return _validate_dict(data, _load_root_schema("disfluencies.schema.json"))


def _validate_by_artifact_schema(filename: str, data: dict[str, Any]) -> list[str]:
    return _validate_dict(data, _load_schema(filename))


def validate_content_brief(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("content_brief_artifact.schema.json", data)


def validate_speakers(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("speakers_artifact.schema.json", data)


def validate_boundaries(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("boundaries_artifact.schema.json", data)


def validate_manifest(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("manifest_artifact.schema.json", data)


def validate_gap_evaluations(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("gap_evaluations_artifact.schema.json", data)


def validate_gap_report(data: dict[str, Any]) -> list[str]:
    return _validate_dict(data, _load_root_schema("gap_report.schema.json"))


def validate_coverage_audit(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("coverage_audit_artifact.schema.json", data)


def validate_narrative_plan(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("narrative_plan_artifact.schema.json", data)


def validate_transitions(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("transitions_artifact.schema.json", data)


def validate_podcast_sfx_brief(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("podcast_sfx_artifact.schema.json", data)


def validate_highlights_selection(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("highlights_artifact.schema.json", data)


def validate_sfx_montage_brief(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("sfx_montage_artifact.schema.json", data)


def validate_show_description(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("show_description_artifact.schema.json", data)


def validate_sfx_prompts(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("sfx_prompts_artifact.schema.json", data)


def validate_sonic_context(data: dict[str, Any]) -> list[str]:
    """Validate `understanding/sonic_context.json`."""
    return _validate_dict(data, _load_root_schema("sonic_context.schema.json"))


def validate_mmaudio_qa(data: dict[str, Any]) -> list[str]:
    """Validate `sound_design/mmaudio_qa.json`."""
    return _validate_by_artifact_schema("mmaudio_qa.schema.json", data)


def validate_placement_adjustments(data: dict[str, Any]) -> list[str]:
    """Validate `sound_design/placement_adjustments.json`."""
    return _validate_dict(data, _load_root_schema("placement_adjustments.schema.json"))


def validate_context_index(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("context_index.schema.json", data)


# Relative artifact paths validated on write (RunContext.write_json and GUI PUT).
ARTIFACT_WRITE_VALIDATORS: dict[str, Any] = {
    "run_meta.json": validate_run_meta,
    "flow_1_master/edl.json": validate_edl_flow1,
    "flow_1_master/edl_narrative_audit.json": validate_edl_narrative_audit,
    "flow_1_master/selection.json": validate_master_selection,
    "flow_1_master/coverage_audit.json": validate_coverage_audit,
    "flow_1_master/narrative_plan.json": validate_narrative_plan,
    "flow_1_master/transitions.json": validate_transitions,
    "flow_1_master/podcast_sfx_brief.json": validate_podcast_sfx_brief,
    "flow_2_highlights/selection.json": validate_highlights_selection,
    "flow_2_highlights/sfx_brief.json": validate_sfx_montage_brief,
    "flow_3_description/show_description.json": validate_show_description,
    "understanding/source_acoustic_profile.json": validate_source_acoustic_profile,
    "understanding/interview_spine.json": validate_interview_spine,
    "understanding/coherence_report.json": validate_coherence_report,
    "understanding/sonic_context.json": validate_sonic_context,
    "understanding/analysis_state.json": validate_analysis_state,
    "understanding/sound_design_plan.json": validate_sound_design_plan,
    "understanding/content_brief.json": validate_content_brief,
    "understanding/speakers.json": validate_speakers,
    "understanding/gap_evaluations.json": validate_gap_evaluations,
    "understanding/gap_report.json": validate_gap_report,
    "segments/boundaries.json": validate_boundaries,
    "segments/manifest.json": validate_manifest,
    "sound_design/sfx_prompts.json": validate_sfx_prompts,
    "sound_design/mmaudio_qa.json": validate_mmaudio_qa,
    "sound_design/placement_adjustments.json": validate_placement_adjustments,
    "ingest/checksums.json": validate_ingest_checksums,
    "transcript/corrections.json": validate_transcript_corrections,
    "transcript/review_queue.json": validate_transcript_review_queue,
    "transcript/disfluencies.json": validate_disfluencies,
    "segments/nle_edits.json": validate_nle_edits,
    "understanding/investigation_queue.json": validate_investigation_queue,
    "understanding/context_index.json": validate_context_index,
}


def validate_artifact_write(rel_path: str, data: dict[str, Any]) -> list[str]:
    """Return schema errors for known on-disk artifacts (empty if path has no validator)."""
    validator = ARTIFACT_WRITE_VALIDATORS.get(rel_path)
    if not validator:
        return []
    return validator(data)
