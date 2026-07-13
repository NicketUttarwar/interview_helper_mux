from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.assembly_timeline import build_assembly_timeline
from interview_mux.run_context import RunContext
from run_fixtures import init_run_meta_for_test, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    run_id = "exec_asm_tl"
    c = RunContext(run_id, create=True)
    init_run_meta_for_test(c)
    c.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_a",
                    "start_ms": 0,
                    "end_ms": 5000,
                    "text": "Hello world",
                    "speaker_id": "spk1",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": ["topic"],
                }
            ]
        },
    )
    c.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_a"],
            "clips": [
                {
                    "type": "speech",
                    "segment_id": "seg_a",
                    "source_start_ms": 0,
                    "source_end_ms": 5000,
                    "timeline_start_ms": 0,
                    "duration_ms": 5000,
                }
            ],
            "gap_placements": [],
            "timeline_duration_ms": 5000,
        },
    )
    return c


def test_build_assembly_timeline_ready(ctx: RunContext) -> None:
    payload = build_assembly_timeline(ctx)
    assert payload["ready"] is True
    assert payload["timeline_duration_ms"] == 5000
    assert len(payload["clips"]) == 1
    assert payload["clips"][0]["text"] == "Hello world"


def test_build_assembly_timeline_missing_edl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    c = RunContext("exec_no_edl", create=True)
    init_run_meta_for_test(c)
    payload = build_assembly_timeline(c)
    assert payload["ready"] is False
