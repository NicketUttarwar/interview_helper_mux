"""Pipeline execution order must match GUI stage metadata (web/stages.py)."""

from __future__ import annotations

from pathlib import Path

import interview_mux.pipeline as pipeline
from interview_mux.web.stages import EXECUTABLE_ORDER

TESTS_DIR = Path(__file__).parent

# Each pipeline stage must be covered by at least one listed test module.
STAGE_TEST_COVERAGE: dict[str, list[str]] = {
    "audio_preclean": ["test_audio_preclean.py", "test_pipeline.py"],
    "ingest": ["test_ingest_preclean.py", "test_assets_audio.py", "test_pipeline.py"],
    "transcribe": ["test_stage_reuse_api.py", "test_api_providers.py", "test_pipeline.py"],
    "transcript_review_build": ["test_transcript_review.py", "test_pipeline.py"],
    "disfluency_extract": ["test_disfluency.py", "test_disfluency_end_to_end.py", "test_pipeline.py"],
    "source_acoustic_profile": ["test_source_acoustic_profile.py", "test_recompute_acoustic_profile.py", "test_pipeline.py"],
    "speaker_roles": ["test_prompt_validation.py", "test_pipeline.py"],
    "content_context": ["test_prompt_validation.py", "test_value_analysis_auto_extract.py", "test_pipeline.py"],
    "content_brief_reanchor": ["test_content_brief_reanchor.py", "test_pipeline.py"],
    "boundary_detection": ["test_prompt_validation.py", "test_llm_harness_084.py", "test_pipeline.py"],
    "segment_classification": ["test_prompt_validation.py", "test_llm_harness_084.py", "test_pipeline.py"],
    "sound_design_palettes": ["test_sound_design_stages.py", "test_pipeline.py"],
    "missing_framing": ["test_llm_runner_structured.py", "test_prompt_validation.py", "test_pipeline.py"],
    "optimal_questions": ["test_gates.py", "test_prompt_validation.py", "test_pipeline.py"],
    "topic_coverage_audit": ["test_analysis_orchestrator.py", "test_pipeline.py"],
    "narrative_arc_plan": ["test_pipeline.py"],
    "full_master_ranking": ["test_llm_specialists.py", "test_nle_state.py", "test_pipeline.py"],
    "transitions": ["test_pipeline.py"],
    "sound_design_plan_flow1": ["test_sound_design_stages.py", "test_sound_design_plan_build060.py", "test_pipeline.py"],
    "sound_design_vo_finalize": ["test_mix_acoustic_profile.py", "test_pipeline.py"],
    "edl_narrative_audit": ["test_edl_narrative_qc.py", "test_pipeline.py"],
    "edl_flow1": ["test_assembly_flow1.py", "test_disfluency_end_to_end.py", "test_edl_qc.py", "test_pipeline.py"],
    "assembly_preview": ["test_assembly_flow1.py", "test_disfluency_mix.py", "test_sound_design_crossfade.py", "test_pipeline.py"],
    "elevenlabs_prompt_craft": ["test_sound_design_stages.py", "test_g1_5_prompt_review.py", "test_pipeline.py"],
    "elevenlabs_sfx_flow1": ["test_sfx_elevenlabs.py", "test_elevenlabs_music.py", "test_pipeline.py"],
    "mix_flow1": ["test_mix_engine.py", "test_disfluency_mix.py", "test_mix_completeness.py", "test_pipeline.py"],
    "master_flow1": ["test_mastering.py", "test_master_qc.py", "test_pipeline.py"],
    "highlight_selection": ["test_selection_flow2_sap.py", "test_pipeline.py"],
    "sound_design_plan_flow2": ["test_sound_design_stages.py", "test_pipeline.py"],
    "elevenlabs_sfx_flow2": ["test_sfx_elevenlabs.py", "test_pipeline.py"],
    "mix_flow2": ["test_mix_engine.py", "test_pipeline.py"],
    "master_flow2": ["test_mastering.py", "test_master_qc.py", "test_pipeline.py"],
    "podcast_show_description": ["test_show_description_qc.py", "test_prompt_validation.py", "test_pipeline.py"],
    "export_show_description": ["test_show_description_qc.py", "test_pipeline.py"],
}


def test_executable_order_matches_pipeline() -> None:
    pairs = [
        ("analysis", pipeline.ANALYSIS_ORDER),
        ("flow1", pipeline.FLOW1_ORDER),
        ("flow2", pipeline.FLOW2_ORDER),
        ("flow3", pipeline.FLOW3_ORDER),
    ]
    for name, pipe_order in pairs:
        web_order = EXECUTABLE_ORDER[name]
        assert list(pipe_order) == list(web_order), (
            f"{name}: pipeline vs GUI mismatch {set(pipe_order) ^ set(web_order)}"
        )


def test_stage_by_id_covers_pipeline_stages() -> None:
    from interview_mux.web.stages import STAGE_BY_ID

    for order in (
        pipeline.ANALYSIS_ORDER,
        pipeline.FLOW1_ORDER,
        pipeline.FLOW2_ORDER,
        pipeline.FLOW3_ORDER,
    ):
        for stage_id in order:
            assert stage_id in STAGE_BY_ID, f"missing GUI metadata for {stage_id}"


def test_each_pipeline_stage_has_test_coverage() -> None:
    all_stages = (
        list(pipeline.ANALYSIS_ORDER)
        + list(pipeline.FLOW1_ORDER)
        + list(pipeline.FLOW2_ORDER)
        + list(pipeline.FLOW3_ORDER)
    )
    missing_registry = [s for s in all_stages if s not in STAGE_TEST_COVERAGE]
    assert not missing_registry, f"Add STAGE_TEST_COVERAGE entries for: {missing_registry}"

    for stage_id in all_stages:
        modules = STAGE_TEST_COVERAGE[stage_id]
        existing = [m for m in modules if (TESTS_DIR / m).is_file()]
        assert existing, f"{stage_id}: no test modules found among {modules}"
        if "test_pipeline.py" in modules:
            continue
        mentioned = any(
            stage_id in (TESTS_DIR / mod).read_text(encoding="utf-8") for mod in existing
        )
        assert mentioned, f"{stage_id}: listed tests {existing} do not reference stage id"
