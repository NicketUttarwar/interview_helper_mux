from __future__ import annotations

from unittest.mock import patch

from interview_mux.llm_specialists import (
    _process_specialist_investigations,
    maybe_run_post_stage_specialists,
    specialists_enabled,
)
from run_fixtures import isolated_run_ctx

_PILOT_CFG = {
    "analysis": {
        "specialists": {
            "enabled": True,
            "pilot_stages": ["full_master_ranking"],
        }
    }
}


def test_theme_coverage_specialist_enqueues(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_theme_spec")
    count = _process_specialist_investigations(
        ctx,
        parent_stage="segment_classification",
        specialist_key="theme_coverage_pass",
        envelope={
            "artifacts": {
                "segment_topic_patches": [{"segment_id": "seg_1", "topic_tags": ["t1"]}],
            }
        },
    )
    assert count == 1


def test_pilot_stage_invokes_specialist_when_enabled(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_pilot_spec")
    with patch("interview_mux.llm_specialists.run_specialist") as mock_run:
        mock_run.return_value = {"artifacts": {}}
        outputs = maybe_run_post_stage_specialists(
            ctx,
            "full_master_ranking",
            {"segments": {}},
            cfg=_PILOT_CFG,
        )
        mock_run.assert_called_once_with(
            ctx,
            "comprehension_risk_blind",
            "full_master_ranking",
            {"segments": {}},
        )
        assert len(outputs) == 1


def test_non_pilot_stage_skips_when_pilot_configured(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_skip_spec")
    with patch("interview_mux.llm_specialists.run_specialist") as mock_run:
        outputs = maybe_run_post_stage_specialists(
            ctx,
            "missing_framing",
            {"segments": {}},
            cfg=_PILOT_CFG,
        )
        mock_run.assert_not_called()
        assert outputs == []


def test_specialists_disabled_by_default(tmp_path):
    assert not specialists_enabled()
    assert not specialists_enabled(stage_key="full_master_ranking")


def test_emphasis_coverage_specialist_enqueues(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_emph_spec")
    count = _process_specialist_investigations(
        ctx,
        parent_stage="topic_coverage_audit",
        specialist_key="emphasis_coverage_pass",
        envelope={"artifacts": {"emphasis_coverage": {"gaps": [{"segment_id": "seg_2"}]}}},
    )
    assert count == 1
