"""Cross-stage sanity: outputs from stage 11 (segment_classification) through flow text stages."""

from __future__ import annotations

import pytest

from interview_mux.pipeline import ANALYSIS_ORDER, FLOW1_ORDER, FLOW2_ORDER, FLOW3_ORDER
from progression_chain_sanity_helpers import (
    FULL_PROGRESSION_CHAIN,
    PROGRESSION_ANALYSIS_STAGES,
    PROGRESSION_FLOW_STAGES,
    PROGRESSION_START_STAGE,
    load_stage_fixtures,
    run_progression_chain_sanity,
    seed_prefix_through_boundary,
    simulate_segment_classification_write_approval,
    validate_content_brief_segment_id_hygiene,
    validate_stage_committed,
    write_stage_producer_artifact,
)
from run_fixtures import isolated_run_ctx, patch_merged_config


def _itr_config() -> dict:
    return {
        "journey_ui": {
            "require_write_approval_per_stage": True,
            "full_autopilot": True,
        },
        "analysis": {
            "artifact_issue_triage": {"enabled": True},
            "flow_hardening": {"enabled": True},
        },
    }


@pytest.fixture
def sanity_ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, _itr_config())
    monkeypatch.setattr(
        "interview_mux.interview_spine.config.spine_enabled",
        lambda *_a, **_k: False,
    )
    return isolated_run_ctx(tmp_path, "progression_sanity")


def test_progression_start_is_segment_classification():
    assert ANALYSIS_ORDER[11] == PROGRESSION_START_STAGE


def test_content_understanding_prefix_supports_segment_classification(sanity_ctx):
    fixtures = load_stage_fixtures()
    seed_prefix_through_boundary(sanity_ctx, fixtures)
    for stage_id in ("content_context", "boundary_detection"):
        assert stage_id in fixtures or stage_id == "content_context"
    failures = validate_stage_committed(sanity_ctx, "boundary_detection")
    assert failures == [], failures


def test_segment_classification_write_approval_regression(sanity_ctx):
    fixtures = load_stage_fixtures()
    seed_prefix_through_boundary(sanity_ctx, fixtures)
    failures = simulate_segment_classification_write_approval(sanity_ctx, fixtures)
    assert failures == [], failures


def test_full_progression_chain_stage_by_stage(sanity_ctx):
    report = run_progression_chain_sanity(sanity_ctx)
    assert report["ok"], report["failures"]


def test_analysis_stages_only(sanity_ctx):
    report = run_progression_chain_sanity(
        sanity_ctx,
        chain=PROGRESSION_ANALYSIS_STAGES,
        include_write_approval_regression=True,
    )
    assert report["ok"], report["failures"]


def test_flow_fixture_stages_after_analysis(sanity_ctx):
    report = run_progression_chain_sanity(
        sanity_ctx,
        chain=[*PROGRESSION_ANALYSIS_STAGES, *PROGRESSION_FLOW_STAGES],
        include_write_approval_regression=True,
    )
    assert report["ok"], report["failures"]
    for stage_id in PROGRESSION_FLOW_STAGES:
        assert stage_id in report["stages"]


def test_content_brief_reanchor_has_manifest_segment_ids(sanity_ctx):
    fixtures = load_stage_fixtures()
    seed_prefix_through_boundary(sanity_ctx, fixtures)
    write_stage_producer_artifact(sanity_ctx, "segment_classification", fixtures)
    write_stage_producer_artifact(sanity_ctx, "content_brief_reanchor", fixtures)
    failures = validate_content_brief_segment_id_hygiene(sanity_ctx)
    assert failures == [], failures


def test_pipeline_orders_are_subsets_of_executable_progression():
    analysis_tail = ANALYSIS_ORDER[ANALYSIS_ORDER.index(PROGRESSION_START_STAGE) :]
    for sid in analysis_tail:
        assert sid in FULL_PROGRESSION_CHAIN
    for sid in PROGRESSION_FLOW_STAGES:
        assert sid in FLOW1_ORDER or sid in FLOW2_ORDER or sid in FLOW3_ORDER
