"""Spoken transitions must carry real duration when WAV exists; QC blocks zeros."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.stages.assembly import build_flow1_edl
from interview_mux.transition_vo import assert_spoken_transitions_audible
from run_fixtures import patch_executions_root, patch_merged_config


def test_build_flow1_edl_transition_duration_from_wav(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    tr = tmp_path / "tr.wav"
    tr.write_bytes(b"x")

    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_001", "seg_002"]},
        segments_by_id={
            "seg_001": {"start_ms": 0, "end_ms": 1000},
            "seg_002": {"start_ms": 1000, "end_ms": 2000},
        },
        transitions={
            "transitions": [
                {
                    "after_segment_id": "seg_001",
                    "before_segment_id": "seg_002",
                    "text": "Next up.",
                    "type": "bridge",
                }
            ]
        },
        resolve_transition_path=lambda a, b: tr,
        vo_duration_ms=lambda _p: 1500,
        vo_relpath=lambda p: p.as_posix(),
    )
    tr_clips = [c for c in edl["clips"] if c.get("type") == "transition"]
    assert len(tr_clips) == 1
    assert tr_clips[0]["duration_ms"] == 1500
    assert tr_clips[0].get("source_path")
    assert edl["timeline_duration_ms"] == 1000 + 1500 + 1000


def test_assert_spoken_transitions_blocks_zero_duration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    patch_merged_config(monkeypatch, {"creative_delivery": {"required": True}})
    ctx = RunContext("exec_tr_qc", create=True)
    edl = {
        "clips": [
            {
                "type": "transition",
                "after_segment_id": "seg_001",
                "before_segment_id": "seg_002",
                "text": "Bridge text",
                "duration_ms": 0,
            }
        ]
    }
    with pytest.raises(SystemExit, match="spoken transitions"):
        assert_spoken_transitions_audible(ctx, edl)
