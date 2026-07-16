from __future__ import annotations

import pytest

from interview_mux.llm_shard_plans import (
    _finalize_boundary_plans,
    should_proactive_decompose_boundary_detection,
)
from interview_mux.run_context import RunContext
from interview_mux.segment_timeline_standard import segmentation_cfg
from interview_mux.write_staging import enter_stage_staging, exit_stage_staging, write_pending_content


def test_finalize_boundary_plans_snaps_contiguous_windows():
    plans = [
        {"label": "time_1", "start_ms": 0, "end_ms": 1000},
        {"label": "time_2", "start_ms": 900, "end_ms": 2000},
    ]
    out = _finalize_boundary_plans(plans)
    assert out[1]["start_ms"] == 1000
    assert out[1]["shard_span_ms"] == 1000


def test_short_interview_skips_proactive_decompose():
    stage_input = {
        "transcript": {"words": [{"start_ms": 0, "end_ms": 30000, "text": "hi"}]},
        "pause_ladder_hints": {"candidates": []},
        "source_acoustic_profile": {"pacing": {"pace_class": "calm"}},
    }
    assert should_proactive_decompose_boundary_detection(stage_input) is False


def test_block_invalid_boundary_commit(tmp_path, monkeypatch):
    from interview_mux.artifact_writes import write_validated_artifact

    monkeypatch.setenv("INTERVIEW_MUX_RUNS_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "interview_mux.segment_timeline_standard.validate_boundary_timeline",
        lambda rows, **kw: ["forced invalid"],
    )
    ctx = RunContext("exec_test_boundary_block", create=True)
    enter_stage_staging("boundary_detection")
    try:
        bad = {
            "boundaries": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 500,
                    "speaker_id": "spk_0",
                    "proposed_split_reason": "pause",
                },
            ]
        }
        with pytest.raises(ValueError, match="cannot commit invalid timeline"):
            write_validated_artifact(
                ctx,
                "segments/boundaries.json",
                bad,
                stage_key="boundary_detection",
            )
    finally:
        exit_stage_staging()


def test_segmentation_cfg_defaults():
    cfg = segmentation_cfg()
    assert cfg["deterministic_collate_authoritative"] is True
    assert cfg["block_invalid_boundary_commit"] is True
