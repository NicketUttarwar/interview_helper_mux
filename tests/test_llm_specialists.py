from __future__ import annotations

from interview_mux.llm_specialists import _process_specialist_investigations
from run_fixtures import isolated_run_ctx


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


def test_emphasis_coverage_specialist_enqueues(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_emph_spec")
    count = _process_specialist_investigations(
        ctx,
        parent_stage="topic_coverage_audit",
        specialist_key="emphasis_coverage_pass",
        envelope={"artifacts": {"emphasis_coverage": {"gaps": [{"segment_id": "seg_2"}]}}},
    )
    assert count == 1
