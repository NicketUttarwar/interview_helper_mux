"""Validate LLM stage artifacts against JSON Schema (docs/cross-cutting/json-schemas/artifacts/)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from interview_mux.config import repo_root
from interview_mux.schema_nullability import with_nullable_optional_leaves

# stage_key -> artifact schema filename (under artifacts/)
STAGE_ARTIFACT_SCHEMAS: dict[str, str] = {
    "speaker_roles": "speakers_artifact.schema.json",
    "content_context": "content_brief_artifact.schema.json",
    "talking_points_compose": "talking_points_artifact.schema.json",
    "ideal_cuts_propose": "ideal_cuts_artifact.schema.json",
    "content_brief_reanchor": "content_brief_artifact.schema.json",
    "boundary_detection": "boundaries_artifact.schema.json",
    "boundary_topic_resplit": "boundaries_artifact.schema.json",
    "segment_classification": "manifest_artifact.schema.json",
    "sound_design_palettes": "sound_design_palettes_artifact.schema.json",
    "missing_framing": "gap_evaluations_artifact.schema.json",
    "gap_framing_compose": "gap_report.schema.json",
    "optimal_questions": "gap_report.schema.json",
    "topic_coverage_audit": "coverage_audit_artifact.schema.json",
    "narrative_arc_plan": "narrative_plan_artifact.schema.json",
    "full_master_ranking": "master_selection_artifact.schema.json",
    "connector_seam_adjudicate": "connector_seam_adjudicate.schema.json",
    "island_cluster_structure_adjudicate": "island_cluster_structure_adjudicate.schema.json",
    "nugget_corpus_mine": "nugget_corpus_artifact.schema.json",
    "nugget_layup_compose": "nugget_layup_plan_artifact.schema.json",
    "air_script_compose": "mastering_plan.schema.json",
    "air_script_seams": "mastering_plan.schema.json",
    "edl_narrative_audit": "edl_narrative_audit_artifact.schema.json",
    "transitions": "transitions_artifact.schema.json",
    "synthetic_framing_plan": "synthetic_framing_plan.schema.json",
    "podcast_sfx_brief": "podcast_sfx_artifact.schema.json",
    "sound_design_plan": "sound_design_plan_artifact.schema.json",
    "music_palette_compose": "music_palette_compose_artifact.schema.json",
    "sfx_prompt_craft": "sfx_prompts_artifact.schema.json",
    "sfx_prompt_refine": "sfx_prompts_artifact.schema.json",
    "mmaudio_sfx": "mmaudio_qa.schema.json",
    "sfx_brief": "sfx_montage_artifact.schema.json",
    "junction_feel_audit": "junction_feel_audit.schema.json",
    "junction_thought_complete": "junction_thought_complete.schema.json",
    "master_transcript_build": "master_transcript.schema.json",
}

# stage_key -> on-disk relative path (under run dir)
# LLM envelope artifacts are a subset merged into a larger on-disk document via stage persist_fn.
STAGE_MERGE_DISK_PERSIST: frozenset[str] = frozenset(
    {
        "sound_design_palettes",
        "sound_design_plan",
        "sfx_prompt_refine",
    }
)

# Keys that must not be passed through merge persist (normalization / envelope pollution).
PERSIST_ARTIFACT_JUNK_KEYS: frozenset[str] = frozenset(
    {"_meta", "envelope", "follow_up_investigations"}
)

STAGE_ARTIFACT_DISK_PATHS: dict[str, str] = {
    "speaker_roles": "understanding/speakers.json",
    "content_context": "understanding/content_brief.json",
    "talking_points_compose": "understanding/talking_points.json",
    "ideal_cuts_propose": "understanding/ideal_cuts.json",
    "ideal_cuts_materialize": "understanding/ideal_cuts_materialized.json",
    "content_brief_reanchor": "understanding/content_brief.json",
    "boundary_detection": "segments/boundaries.json",
    "boundary_topic_resplit": "segments/boundaries.json",
    "segment_classification": "segments/manifest.json",
    "sound_design_palettes": "understanding/sound_design_plan.json",
    "missing_framing": "understanding/gap_evaluations.json",
    "gap_framing_compose": "understanding/gap_report.json",
    "optimal_questions": "understanding/gap_report.json",
    "topic_coverage_audit": "master/coverage_audit.json",
    "narrative_arc_plan": "master/narrative_plan.json",
    "chapter_close_hitch": "mastering/chapter_close_hitch.json",
    "full_master_ranking": "master/selection.json",
    "connector_seam_adjudicate": "analysis/connector_seam_verdicts.json",
    "island_cluster_structure_adjudicate": "analysis/island_cluster_structure_verdicts.json",
    "low_conf_island_scan": "analysis/low_conf_islands.json",
    "connector_fuse_pass": "analysis/connector_fuse_audit.json",
    "connector_fuse_pass_pre_ranking": "analysis/connector_fuse_rounds.json",
    "nugget_corpus_mine": "understanding/nugget_corpus.json",
    "nugget_layup_compose": "understanding/nugget_layup_plan.json",
    "edl_narrative_audit": "master/edl_narrative_audit.json",
    "edl": "master/edl.json",
    "air_script_compose": "mastering/mastering_plan.json",
    "air_script_seams": "mastering/mastering_plan.json",
    "transitions": "master/transitions.json",
    "synthetic_framing_plan": "understanding/synthetic_framing_plan.json",
    "podcast_sfx_brief": "master/podcast_sfx_brief.json",
    "sound_design_plan": "understanding/sound_design_plan.json",
    "music_palette_compose": "sound_design/music_palette_compose.json",
    "sfx_prompt_craft": "sound_design/sfx_prompts.json",
    "sfx_prompt_refine": "sound_design/sfx_prompts.json",
    "mmaudio_sfx": "sound_design/mmaudio_qa.json",
    "junction_feel_audit": "master/junction_feel_audit.json",
    "junction_thought_complete": "master/junction_thought_complete.json",
    "master_transcript_build": "master/transcript.json",
    "mastering_research_routing": "mastering/research/routing.json",
    "mastering_research_waves": "mastering/research/waves.json",
    "mastering_research_rollup": "mastering/research/rollup.json",
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

# Models often emit informal status tokens; coerce before schema validation.
_ENVELOPE_STATUS_ALIASES = {
    "ok": "complete",
    "okay": "complete",
    "success": "complete",
    "succeeded": "complete",
    "done": "complete",
    "finished": "complete",
    "pass": "complete",
    "passed": "complete",
    "error": "blocked",
    "failed": "blocked",
    "fail": "blocked",
    "failure": "blocked",
}


def coerce_envelope_status(envelope: dict[str, Any]) -> dict[str, Any]:
    """Normalize informal envelope.status values to the schema enum (in place)."""
    if not isinstance(envelope, dict):
        return envelope
    raw = str(envelope.get("status") or "").strip().lower()
    if not raw:
        return envelope
    mapped = _ENVELOPE_STATUS_ALIASES.get(raw)
    if mapped:
        envelope["status"] = mapped
    elif raw in {"complete", "partial", "needs_input", "blocked"}:
        envelope["status"] = raw
    return envelope


def coerce_envelope_needs(envelope: dict[str, Any]) -> dict[str, Any]:
    """Drop/normalize null need fields so OA envelope verification accepts LLM nulls."""
    if not isinstance(envelope, dict):
        return envelope
    needs = envelope.get("needs")
    if not isinstance(needs, list):
        return envelope
    cleaned: list[Any] = []
    for item in needs:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        if row.get("stage") is None:
            row["stage"] = ""
        if row.get("blocking") is None:
            row["blocking"] = False
        if row.get("params") is None:
            row["params"] = {}
        cleaned.append(row)
    envelope["needs"] = cleaned
    return envelope


def validate_envelope(envelope: dict[str, Any]) -> list[str]:
    """Validate analysis envelope shape before arbiter (BUILD-084)."""
    schema = _load_envelope_schema()
    if not schema:
        return []
    if isinstance(envelope, dict):
        coerce_envelope_status(envelope)
        coerce_envelope_needs(envelope)
    return [f"envelope.{e}" for e in _validate_dict(envelope, schema)]

def validate_investigation_queue(queue: dict[str, Any]) -> list[str]:
    return _validate_dict(queue, _load_root_schema("investigation_queue.schema.json"))

def validate_nle_edits(data: dict[str, Any]) -> list[str]:
    return _validate_dict(data, _load_root_schema("nle_edits.schema.json"))

def stage_uses_merge_disk_persist(stage_key: str) -> bool:
    """True when stage persist_fn merges envelope artifacts into a larger disk artifact."""
    return stage_key in STAGE_MERGE_DISK_PERSIST


def clean_stage_artifacts_for_persist(stage_key: str, artifacts: dict[str, Any]) -> dict[str, Any]:
    """Drop envelope pollution before merge persist or stage-schema validation."""
    _ = stage_key
    return {k: v for k, v in artifacts.items() if k not in PERSIST_ARTIFACT_JUNK_KEYS}


def validate_stage_artifacts(stage_key: str, artifacts: dict[str, Any]) -> list[str]:
    """Return human-readable validation errors (empty if OK or no schema)."""
    filename = STAGE_ARTIFACT_SCHEMAS.get(stage_key)
    if not filename or not artifacts:
        return []
    schema = _load_schema(filename)
    if not schema:
        return []
    schema = with_nullable_optional_leaves(schema)
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
    """Validate `master/selection.json` against master_selection_artifact.schema.json."""
    return _validate_dict(selection, _load_schema("master_selection_artifact.schema.json"))

def validate_edl_narrative_audit(audit: dict[str, Any]) -> list[str]:
    """Validate `master/edl_narrative_audit.json`."""
    return _validate_dict(audit, _load_schema("edl_narrative_audit_artifact.schema.json"))

def validate_edl(edl: dict[str, Any]) -> list[str]:
    """Validate `master/edl.json` against artifacts/edl.schema.json."""
    return _validate_dict(edl, _load_schema("edl.schema.json"))


def validate_synthesis_report(report: dict[str, Any]) -> list[str]:
    """Validate VO synthesis provenance and stale-audio hashes."""
    return _validate_dict(report, _load_root_schema("synthesis_report.schema.json"))

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
    schema = _load_schema(filename)
    if schema:
        schema = with_nullable_optional_leaves(schema)
    return _validate_dict(data, schema)

def validate_content_brief(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("content_brief_artifact.schema.json", data)

def validate_speakers(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("speakers_artifact.schema.json", data)

def validate_boundaries(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("boundaries_artifact.schema.json", data)


def validate_boundary_review_queue(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("boundary_review_queue.schema.json", data)


def validate_manifest(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("manifest_artifact.schema.json", data)

def validate_gap_evaluations(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("gap_evaluations_artifact.schema.json", data)

def validate_gap_report(data: dict[str, Any]) -> list[str]:
    return _validate_dict(data, _load_root_schema("gap_report.schema.json"))

def validate_nugget_corpus(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("nugget_corpus_artifact.schema.json", data)


def validate_nugget_layup_plan(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("nugget_layup_plan_artifact.schema.json", data)


def validate_omit_ledger(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("omit_ledger.schema.json", data)


def validate_master_transcript(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("master_transcript.schema.json", data)


def validate_asset_transcript(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("asset_transcript.schema.json", data)

def validate_coverage_audit(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("coverage_audit_artifact.schema.json", data)

def validate_narrative_plan(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("narrative_plan_artifact.schema.json", data)

def validate_transitions(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("transitions_artifact.schema.json", data)

def validate_podcast_sfx_brief(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("podcast_sfx_artifact.schema.json", data)

def validate_sfx_montage_brief(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("sfx_montage_artifact.schema.json", data)

def validate_show_description(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("show_description_artifact.schema.json", data)

def validate_sfx_prompts(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("sfx_prompts_artifact.schema.json", data)

def validate_sonic_context(data: dict[str, Any]) -> list[str]:
    """Validate `understanding/sonic_context.json`."""
    return _validate_dict(data, _load_root_schema("sonic_context.schema.json"))

def validate_delivery_brief(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("delivery_brief.schema.json", data)


def validate_soundscape_policy(data: dict[str, Any]) -> list[str]:
    """Validate `understanding/soundscape_policy.json` (root schema, not artifacts/)."""
    return _validate_dict(data, _load_root_schema("soundscape_policy.schema.json"))


def validate_episode_structure(data: dict[str, Any]) -> list[str]:
    """Validate `understanding/episode_structure.json` (root schema, not STAGE_ARTIFACT_SCHEMAS)."""
    return _validate_dict(data, _load_root_schema("episode_structure.schema.json"))


def validate_source_readiness(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("source_readiness.schema.json", data)


def validate_mmaudio_qa(data: dict[str, Any]) -> list[str]:
    """Validate `sound_design/mmaudio_qa.json`."""
    return _validate_by_artifact_schema("mmaudio_qa.schema.json", data)


def validate_musicgen_candidates(data: dict[str, Any]) -> list[str]:
    """Validate `sound_design/musicgen_candidates.json`."""
    return _validate_by_artifact_schema("musicgen_candidates.schema.json", data)


def validate_underbed_ab_qc(data: dict[str, Any]) -> list[str]:
    """Validate `master/underbed_ab_qc.json`."""
    return _validate_by_artifact_schema("underbed_ab_qc.schema.json", data)


def validate_placement_adjustments(data: dict[str, Any]) -> list[str]:
    """Validate `sound_design/placement_adjustments.json`."""
    return _validate_dict(data, _load_root_schema("placement_adjustments.schema.json"))

def validate_context_index(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("context_index.schema.json", data)


def validate_refinement_agenda(data: dict[str, Any]) -> list[str]:
    """Validate `understanding/refinement_agenda.json` (L0)."""
    return _validate_by_artifact_schema("refinement_agenda.schema.json", data)

def validate_refinement_ledger(data: dict[str, Any]) -> list[str]:
    """Validate `understanding/refinement_ledger.json` (CFI call ledger)."""
    return _validate_by_artifact_schema("refinement_ledger.schema.json", data)

def validate_refinement_plan(data: dict[str, Any]) -> list[str]:
    """Validate `understanding/refinement_plan.json` (L1 gate decisions)."""
    return _validate_by_artifact_schema("refinement_plan.schema.json", data)

def validate_junction_snip_qa(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("junction_snip_qa.schema.json", data)


def validate_chapter_close_hitch(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("chapter_close_hitch.schema.json", data)


def validate_media_ip_cta(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("media_ip_cta.schema.json", data)


def validate_junction_feel_audit(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("junction_feel_audit.schema.json", data)


def validate_junction_thought_complete(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("junction_thought_complete.schema.json", data)


def validate_seam_autopsy(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("seam_autopsy.schema.json", data)


def validate_failure_review(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("failure_review.schema.json", data)


def validate_remediation_plan(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("remediation_plan.schema.json", data)


def validate_remediation_run_log(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("remediation_run_log.schema.json", data)


def validate_post_master_quality(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("post_master_quality.schema.json", data)


def validate_listener_scorecard(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("listener_scorecard.schema.json", data)


def validate_synthetic_context_packet(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("synthetic_context_packet.schema.json", data)


def validate_render_ledger(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("render_ledger.schema.json", data)


def validate_synthetic_framing_plan(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("synthetic_framing_plan.schema.json", data)


def validate_talking_points(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("talking_points_artifact.schema.json", data)


def validate_ideal_cuts(data: dict[str, Any]) -> list[str]:
    return _validate_by_artifact_schema("ideal_cuts_artifact.schema.json", data)


# Relative artifact paths validated on write (RunContext.write_json and GUI PUT).
ARTIFACT_WRITE_VALIDATORS: dict[str, Any] = {
    "run_meta.json": validate_run_meta,
    "master/edl.json": validate_edl,
    "master/transcript.json": validate_master_transcript,
    "vo_pickup/synthesis_report.json": validate_synthesis_report,
    "master/junction_snip_qa.json": validate_junction_snip_qa,
    "mastering/chapter_close_hitch.json": validate_chapter_close_hitch,
    "mastering/media_ip_cta.json": validate_media_ip_cta,
    "master/junction_feel_audit.json": validate_junction_feel_audit,
    "master/junction_thought_complete.json": validate_junction_thought_complete,
    "master/seam_autopsy.json": validate_seam_autopsy,
    "master/failure_review.json": validate_failure_review,
    "master/remediation_plan.json": validate_remediation_plan,
    "master/remediation_run_log.json": validate_remediation_run_log,
    "master/post_master_quality.json": validate_post_master_quality,
    "master/listener_scorecard.json": validate_listener_scorecard,
    "master/render_ledger.json": validate_render_ledger,
    "master/edl_narrative_audit.json": validate_edl_narrative_audit,
    "master/selection.json": validate_master_selection,
    "master/coverage_audit.json": validate_coverage_audit,
    "master/narrative_plan.json": validate_narrative_plan,
    "master/transitions.json": validate_transitions,
    "master/podcast_sfx_brief.json": validate_podcast_sfx_brief,
    "show_notes/show_description.json": validate_show_description,
    "understanding/source_acoustic_profile.json": validate_source_acoustic_profile,
    "understanding/interview_spine.json": validate_interview_spine,
    "understanding/coherence_report.json": validate_coherence_report,
    "understanding/sonic_context.json": validate_sonic_context,
    "understanding/analysis_state.json": validate_analysis_state,
    "understanding/sound_design_plan.json": validate_sound_design_plan,
    "understanding/content_brief.json": validate_content_brief,
    "understanding/talking_points.json": validate_talking_points,
    "understanding/ideal_cuts.json": validate_ideal_cuts,
    "understanding/speakers.json": validate_speakers,
    "understanding/gap_evaluations.json": validate_gap_evaluations,
    "understanding/gap_report.json": validate_gap_report,
    "understanding/nugget_corpus.json": validate_nugget_corpus,
    "understanding/nugget_layup_plan.json": validate_nugget_layup_plan,
    "understanding/omit_ledger.json": validate_omit_ledger,
    "understanding/delivery_brief.json": validate_delivery_brief,
    "understanding/soundscape_policy.json": validate_soundscape_policy,
    "understanding/episode_structure.json": validate_episode_structure,
    "understanding/source_readiness.json": validate_source_readiness,
    "segments/boundaries.json": validate_boundaries,
    "segments/boundary_review_queue.json": validate_boundary_review_queue,
    "segments/manifest.json": validate_manifest,
    "sound_design/sfx_prompts.json": validate_sfx_prompts,
    "sound_design/mmaudio_qa.json": validate_mmaudio_qa,
    "sound_design/musicgen_candidates.json": validate_musicgen_candidates,
    "sound_design/placement_adjustments.json": validate_placement_adjustments,
    "master/underbed_ab_qc.json": validate_underbed_ab_qc,
    "ingest/checksums.json": validate_ingest_checksums,
    "transcript/corrections.json": validate_transcript_corrections,
    "transcript/review_queue.json": validate_transcript_review_queue,
    "transcript/disfluencies.json": validate_disfluencies,
    "segments/nle_edits.json": validate_nle_edits,
    "understanding/investigation_queue.json": validate_investigation_queue,
    "understanding/context_index.json": validate_context_index,
    "understanding/refinement_agenda.json": validate_refinement_agenda,
    "understanding/refinement_ledger.json": validate_refinement_ledger,
    "understanding/refinement_plan.json": validate_refinement_plan,
    "understanding/synthetic_context_packet.json": validate_synthetic_context_packet,
    "understanding/synthetic_framing_plan.json": validate_synthetic_framing_plan,
}

def validate_artifact_write(rel_path: str, data: dict[str, Any]) -> list[str]:
    """Return schema errors for known on-disk artifacts (empty if path has no validator)."""
    validator = ARTIFACT_WRITE_VALIDATORS.get(rel_path)
    if validator:
        return validator(data)
    if (
        rel_path.startswith("transcripts/")
        and rel_path.endswith(".json")
        and rel_path.count("/") == 2
        and not rel_path.endswith("/index.json")
    ):
        return validate_asset_transcript(data)
    return []
