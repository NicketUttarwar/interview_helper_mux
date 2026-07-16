from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.segmentation_input_resolver import (
    assert_field_parity,
    assert_reference_closure,
    build_classification_payload,
    resolve_segmentation_inputs,
)
from interview_mux.stage_coupling import publish_boundary_contract
from interview_mux.write_staging import enter_stage_staging, exit_stage_staging, write_pending_content
from run_fixtures import patch_merged_config


def _boundaries_doc() -> dict:
    rows = [
        {"segment_id": "seg_001", "start_ms": 0, "end_ms": 500, "speaker_id": "spk_0", "proposed_split_reason": "pause"},
        {"segment_id": "seg_002", "start_ms": 500, "end_ms": 1200, "speaker_id": "spk_1", "proposed_split_reason": "pause"},
    ]
    return publish_boundary_contract({"boundaries": rows}, timeline_errors=[], publisher_stage="boundary_detection")


def _speakers_doc() -> dict:
    return {
        "speakers": [
            {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.95},
            {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.95},
        ]
    }


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


def _bootstrap_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    root = tmp_path / "repo"
    (root / "ASSETS" / "executions").mkdir(parents=True)
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: root)
    patch_merged_config(
        monkeypatch,
        {
            "assets_root": "ASSETS",
            "executions_root": "ASSETS/executions",
            "data_root": "data",
        },
    )
    ctx = RunContext("exec_test_seg_ref", create=True)
    ctx.write_json("transcript/full.json", {"words": [{"start_ms": 0, "end_ms": 1200, "text": "Hello Answer"}]})
    ctx.write_json("understanding/speakers.json", _speakers_doc())
    ctx.write_json("understanding/content_brief.json", {"thesis": "t", "topics": []})
    return ctx


def test_field_parity_detects_time_mismatch(tmp_path, monkeypatch):
    ctx = _bootstrap_run(tmp_path, monkeypatch)
    boundaries = _boundaries_doc()
    manifest = _manifest_doc()
    manifest["segments"][0]["end_ms"] = 1500
    errors = assert_field_parity(boundaries, manifest, _speakers_doc())
    assert any("end_ms mismatch" in e for e in errors)


def test_reference_closure_requires_manifest_ids(tmp_path, monkeypatch):
    ctx = _bootstrap_run(tmp_path, monkeypatch)
    ctx.write_json("segments/boundaries.json", _boundaries_doc())
    manifest = {"segments": [_manifest_doc()["segments"][0]]}
    errors = assert_reference_closure(ctx, manifest, require_full_coverage=True)
    assert any("missing manifest" in e.lower() or "reference closure" in e.lower() for e in errors)


def test_build_classification_payload_reads_staged_boundary(tmp_path, monkeypatch):
    ctx = _bootstrap_run(tmp_path, monkeypatch)
    enter_stage_staging("boundary_detection")
    try:
        write_pending_content(
            ctx,
            "boundary_detection",
            "segments/boundaries.json",
            data=_boundaries_doc(),
        )
    finally:
        exit_stage_staging()

    payload = build_classification_payload(ctx)
    assert payload["boundaries"]["boundaries"]
    assert payload["_segmentation_source_paths"]["boundaries"]["staged"] is True


def test_resolve_segmentation_inputs_committed_boundary(tmp_path, monkeypatch):
    ctx = _bootstrap_run(tmp_path, monkeypatch)
    ctx.write_json("segments/boundaries.json", _boundaries_doc())
    bundle = resolve_segmentation_inputs(ctx)
    assert not bundle.errors
    assert bundle.boundaries is not None
    assert bundle.source_paths["boundaries"]["staged"] is False
