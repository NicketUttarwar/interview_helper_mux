from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.first_try import should_pause_for_write_approval
from interview_mux.run_context import RunContext
from interview_mux.segment_timeline_standard import format_shard_identity
from interview_mux.stage_coupling import publish_boundary_contract
from interview_mux.write_staging import (
    after_stage_write_check,
    approve_segmentation_pair_writes,
    enter_stage_staging,
    exit_stage_staging,
    has_pending_writes,
    list_pending_paths,
    write_pending_content,
)
from run_fixtures import patch_merged_config


def _boundaries_doc() -> dict:
    rows = [
        {
            "segment_id": "seg_001",
            "start_ms": 0,
            "end_ms": 500,
            "speaker_id": "spk_0",
            "proposed_split_reason": "pause",
        },
        {
            "segment_id": "seg_002",
            "start_ms": 500,
            "end_ms": 1200,
            "speaker_id": "spk_1",
            "proposed_split_reason": "pause",
        },
    ]
    return publish_boundary_contract({"boundaries": rows}, timeline_errors=[], publisher_stage="boundary_detection")


def _manifest_doc() -> dict:
    return {
        "segments": [
            {
                "segment_id": "seg_001",
                "start_ms": 0,
                "end_ms": 500,
                "speaker_id": "spk_0",
                "speaker_role": "interviewer",
                "type": "interviewer_question",
                "topic_tags": [],
                "text": "Hello",
            },
            {
                "segment_id": "seg_002",
                "start_ms": 500,
                "end_ms": 1200,
                "speaker_id": "spk_1",
                "speaker_role": "interviewee",
                "type": "interviewee_answer",
                "topic_tags": ["topic_a"],
                "text": "Answer",
            },
        ]
    }


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    root = tmp_path / "repo"
    (root / "ASSETS" / "executions").mkdir(parents=True)
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: root)
    patch_merged_config(
        monkeypatch,
        {
            "assets_root": "ASSETS",
            "executions_root": "ASSETS/executions",
            "data_root": "data",
            "journey_ui": {"require_write_approval_per_stage": True, "segmentation_unified_review": True},
            "analysis": {"artifact_issue_triage": {"enabled": False}},
        },
    )
    ctx = RunContext("exec_unified_review", create=True)
    ctx.write_json(
        "transcript/full.json",
        {"words": [{"start_ms": 0, "end_ms": 1200, "text": "Hello Answer"}]},
    )
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.95},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.95},
            ]
        },
    )
    ctx.write_json("understanding/content_brief.json", {"thesis": "t", "topics": []})
    return ctx


def test_unified_review_defers_boundary_pause():
    assert should_pause_for_write_approval("boundary_detection") is False
    assert should_pause_for_write_approval("segment_classification") is True


def test_after_stage_boundary_stages_without_pause(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("boundary_detection")
    try:
        write_pending_content(
            ctx,
            "boundary_detection",
            "segments/boundaries.json",
            data={"boundaries": []},
        )
        exit_stage_staging()
        after_stage_write_check(ctx, "boundary_detection")
        assert has_pending_writes(ctx, "boundary_detection")
    finally:
        exit_stage_staging()


def test_segment_classification_lists_paired_paths(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("boundary_detection")
    write_pending_content(ctx, "boundary_detection", "segments/boundaries.json", data={"boundaries": []})
    exit_stage_staging()
    enter_stage_staging("segment_classification")
    write_pending_content(ctx, "segment_classification", "segments/manifest.json", data={"segments": []})
    exit_stage_staging()
    paths = list_pending_paths(ctx, "segment_classification")
    assert "segments/boundaries.json" in paths
    assert "segments/manifest.json" in paths


def test_append_shard_summary_uses_span_not_na():
    shard = {"label": "time_1", "start_ms": 0, "end_ms": 5000}
    env = {
        "artifacts": {
            "boundaries": [
                {"segment_id": "seg_001", "start_ms": 0, "end_ms": 5000, "speaker_id": "spk_0"},
            ]
        }
    }
    identity = format_shard_identity(shard, "boundary_detection", env)
    assert "n/a" not in identity
    assert "0" in identity
    assert "5000" in identity
    assert "1 boundaries" in identity


def test_approve_segmentation_pair_writes_flushes_both(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("boundary_detection")
    write_pending_content(ctx, "boundary_detection", "segments/boundaries.json", data=_boundaries_doc())
    exit_stage_staging()
    enter_stage_staging("segment_classification")
    write_pending_content(ctx, "segment_classification", "segments/manifest.json", data=_manifest_doc())
    exit_stage_staging()

    flushed = approve_segmentation_pair_writes(ctx)

    assert "segments/boundaries.json" in flushed
    assert "segments/manifest.json" in flushed
    assert ctx.artifact_exists("segments/boundaries.json")
    assert ctx.artifact_exists("segments/manifest.json")
    assert not has_pending_writes(ctx, "boundary_detection")
    assert not has_pending_writes(ctx, "segment_classification")
    assert ctx.is_done("boundary_detection")
    assert ctx.is_done("segment_classification")
