"""Pipeline execution order must match GUI stage metadata (web/stages.py)."""

from __future__ import annotations

from pathlib import Path

import interview_mux.pipeline as pipeline
from interview_mux.web.stages import EXECUTABLE_ORDER

TESTS_DIR = Path(__file__).parent

# Gate/checkpoint and on-demand stages in STAGE_BY_ID but not in pipeline EXECUTABLE_ORDER:
GATE_AND_ON_DEMAND_STAGES = frozenset(
    {
        "transcript_review",
        "g1_vo_pickup",
        "g1_5_preview_pickup",
        "vo_ingest",
    }
)

# Each pipeline stage must be covered by at least one listed test module.
STAGE_TEST_COVERAGE: dict[str, list[str]] = {
    "audio_preclean": ["test_audio_preclean.py", "test_pipeline.py"],
    "ingest": ["test_ingest_preclean.py", "test_assets_audio.py", "test_pipeline.py"],
    "transcribe": ["test_stage_reuse_api.py", "test_api_providers.py", "test_pipeline.py"],
    "audio_probe_build": ["test_audio_probes.py", "test_pipeline.py"],
    "transcript_review_build": ["test_transcript_review.py", "test_pipeline.py"],
    "vernacular_segment_sanitize": ["test_audio_probes.py", "test_pipeline.py"],
    "source_acoustic_profile": ["test_source_acoustic_profile.py", "test_recompute_acoustic_profile.py", "test_pipeline.py"],
    "interview_spine_build": ["test_interview_spine.py", "test_pipeline.py"],
    "speaker_roles": ["test_prompt_validation.py", "test_pipeline.py"],
    "source_topology_build": ["test_source_topology.py", "test_production_profile.py"],
    "content_context": ["test_prompt_validation.py", "test_value_analysis_auto_extract.py", "test_pipeline.py"],
    "talking_points_compose": ["test_talking_points_authority.py", "test_ideal_cuts.py", "test_pipeline.py"],
    "ideal_cuts_propose": ["test_ideal_cuts.py", "test_talking_points_authority.py", "test_pipeline.py"],
    "ideal_cuts_materialize": ["test_ideal_cuts.py", "test_talking_points_authority.py", "test_pipeline.py"],
    "content_brief_reanchor": ["test_content_brief_reanchor.py", "test_pipeline.py"],
    "framing_posture_decide": ["test_framing_posture_decide.py", "test_pipeline.py"],
    "boundary_topic_resplit": ["test_boundary_topic_resplit.py", "test_pipeline.py"],
    "sonic_context_build": ["test_sonic_context.py", "test_sfx_schema_build_sfx01.py", "test_pipeline.py"],
    "boundary_detection": ["test_prompt_validation.py", "test_llm_harness_084.py", "test_pipeline.py"],
    "segment_classification": ["test_prompt_validation.py", "test_llm_harness_084.py", "test_pipeline.py"],
    "sound_design_palettes": ["test_sound_design_stages.py", "test_sound_design_scenario.py", "test_pipeline.py"],
    "mastering_research_routing": ["test_mastering.py", "test_pipeline.py"],
    "mastering_research_waves": ["test_mastering.py", "test_pipeline.py"],
    "mastering_research_rollup": ["test_mastering.py", "test_pipeline.py"],
    "mastering_shape_agenda": ["test_mastering.py", "test_pipeline.py"],
    "mastering_shape_candidates": ["test_mastering.py", "test_pipeline.py"],
    "mastering_plan_synthesize": ["test_mastering.py", "test_pipeline.py"],
    "mastering_plan_confirm": ["test_mastering.py", "test_pipeline.py"],
    "missing_framing": ["test_llm_runner_structured.py", "test_prompt_validation.py", "test_pipeline.py"],
    "gap_framing_compose": ["test_gap_framing_gates.py", "test_gaps_skip.py", "test_pipeline.py"],
    "delivery_brief_build": ["test_delivery_brief.py", "test_pipeline.py"],
    "soundscape_policy_build": ["test_soundscape_policy.py", "test_pipeline.py"],
    "episode_structure_compose": ["test_episode_structure.py", "test_pipeline.py"],
    "topic_coverage_audit": ["test_coherence_topic_coverage_volley.py", "test_pipeline.py"],
    "narrative_arc_plan": ["test_pipeline.py", "test_chapter_close_hitch.py"],
    "chapter_close_hitch": ["test_chapter_close_hitch.py"],
    "full_master_ranking": ["test_llm_specialists.py", "test_nle_state.py", "test_pipeline.py"],
    "refinement_agenda": ["test_refinement_core.py", "test_refinement_gate.py", "test_pipeline.py"],
    "gap_framing_recompose": ["test_refinement_core.py", "test_refinement_flow_integrity.py", "test_pipeline.py"],
    "selection_framing_apply": ["test_refinement_core.py", "test_pipeline.py"],
    "ranking_refine": ["test_refinement_core.py", "test_pipeline.py"],
    "narrative_arc_refine": ["test_refinement_core.py", "test_pipeline.py"],
    "transitions": ["test_pipeline.py"],
    "transitions_refine": ["test_refinement_core.py", "test_pipeline.py"],
    "sound_design_plan": ["test_sound_design_stages.py", "test_sound_design_plan_build060.py", "test_sound_design_scenario.py", "test_pipeline.py"],
    "sdp_intent_refine": ["test_refinement_core.py", "test_pipeline.py"],
    "sound_design_vo_finalize": ["test_mix_acoustic_profile.py", "test_pipeline.py"],
    "vo_line_adjudicate": ["test_vo_line_adjudicate.py", "test_pipeline.py"],
    "edl_narrative_audit": ["test_edl_narrative_qc.py", "test_pipeline.py"],
    "vo_synthesize": ["test_vo_edl_file_contract.py", "test_pipeline.py"],
    "edl_narrative_refine": ["test_refinement_core.py", "test_pipeline.py"],
    "edl": ["test_assembly.py", "test_edl_qc.py", "test_pipeline.py"],
    "assembly_preview": ["test_assembly.py", "test_sound_design_crossfade.py", "test_pipeline.py"],
    "listen_delight_audit": ["test_pipeline.py", "test_master_qc.py"],
    "junction_snip_qa": ["test_junction_snip_qa.py", "test_pipeline.py"],
    "sfx_prompt_craft": ["test_sound_design_stages.py", "test_g1_5_prompt_review.py", "test_sfx_gates.py", "test_pipeline.py"],
    "mmaudio_sfx": ["test_sfx_mmaudio.py", "test_sfx_gates.py", "test_pipeline.py"],
    "mix": ["test_mix_engine.py", "test_mix_completeness.py", "test_sfx_gates.py", "test_pipeline.py"],
    "master_finalize": ["test_mastering.py", "test_master_qc.py", "test_pipeline.py"],
    "master_transcript_build": ["test_asset_transcripts.py"],
    "low_conf_island_scan": ["test_stage_read_paths.py"],
    "connector_fuse_pass": ["test_low_conf_fuse_selection.py"],
    "connector_fuse_pass_pre_ranking": ["test_stage_read_paths.py"],
    "air_script_compose": ["test_air_script.py"],
    "air_script_seams": ["test_air_script.py"],
    "nugget_corpus_mine": ["test_nugget_layup.py"],
    "information_package_plan": ["test_information_packages.py"],
    "nugget_layup_compose": ["test_nugget_layup.py"],
    "music_palette_compose": ["test_music_palette_compose.py"],
    "episode_meta_build": ["test_podcast_rss.py", "test_pipeline.py"],
    "episode_cover_prompt_craft": ["test_podcast_rss.py", "test_pipeline.py"],
    "podcast_encode_mp3": ["test_podcast_rss.py", "test_pipeline.py"],
    "episode_cover_generate": ["test_podcast_rss.py", "test_pipeline.py"],
    "podcast_publish": ["test_podcast_rss.py", "test_pipeline.py"],
}

def test_operator_linear_stage_order() -> None:
    from interview_mux.web.stages import operator_linear_stage_ids

    ids = operator_linear_stage_ids(None)
    assert ids.index("transcript_review_build") < ids.index("transcript_review")
    assert "disfluency_extract" not in ids
    assert "disfluency_review" not in ids
    assert "analysis_profile" not in ids
    assert "optimal_questions" not in ids
    assert ids.index("transcript_review") < ids.index("source_acoustic_profile")
    assert ids.index("gap_framing_compose") < ids.index("g1_vo_pickup")

    operator_linear_stage_ids("podcast")


def test_executable_order_matches_pipeline() -> None:
    from interview_mux.v2.config import effective_analysis_order, effective_delivery_order

    pairs = [
        ("analysis", effective_analysis_order()),
        ("delivery", effective_delivery_order()),
    ]
    for name, pipe_order in pairs:
        web_order = EXECUTABLE_ORDER[name]
        if name == "analysis":
            from interview_mux.v2.config import v2_enabled

            if v2_enabled():
                assert list(pipe_order) == list(web_order) or set(pipe_order) <= set(web_order), (
                    f"{name}: v2 pipeline stages should be subset of GUI EXECUTABLE_ORDER"
                )
                continue
        assert list(pipe_order) == list(web_order), (
            f"{name}: pipeline vs GUI mismatch {set(pipe_order) ^ set(web_order)}"
        )

def test_stage_by_id_covers_pipeline_stages() -> None:
    from interview_mux.v2.config import effective_analysis_order, effective_delivery_order
    from interview_mux.web.stages import STAGE_BY_ID

    for order in (
        effective_analysis_order(),
        effective_delivery_order(),
    ):
        for stage_id in order:
            assert stage_id in STAGE_BY_ID, f"missing GUI metadata for {stage_id}"

def test_each_pipeline_stage_has_test_coverage() -> None:
    from interview_mux.v2.config import effective_analysis_order, effective_delivery_order

    all_stages = list(effective_analysis_order()) + list(effective_delivery_order())
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

def test_gate_stages_documented_outside_pipeline_coverage() -> None:
    from interview_mux.web.stages import STAGE_BY_ID

    for stage_id in GATE_AND_ON_DEMAND_STAGES:
        assert stage_id in STAGE_BY_ID, f"missing GUI metadata for gate/on-demand {stage_id}"
        assert stage_id not in STAGE_TEST_COVERAGE, (
            f"{stage_id} should remain outside STAGE_TEST_COVERAGE (gate/on-demand)"
        )
