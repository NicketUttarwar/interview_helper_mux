"""Spoken transitions must carry real duration when WAV exists; QC blocks zeros."""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.stages.assembly import build_flow1_edl
from interview_mux.transition_vo import (
    assert_spoken_transitions_audible,
    resolve_transition_wav,
    transition_wav_path,
)
from interview_mux.vo_synthesis_audit import record_synthesis
from run_fixtures import isolated_run_ctx, patch_executions_root, patch_merged_config


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
    # Speech + transition + optional air pads around the spoken hinge.
    silence_ms = sum(
        int(c.get("duration_ms") or 0)
        for c in edl["clips"]
        if c.get("type") == "silence"
    )
    assert edl["timeline_duration_ms"] == 1000 + 1500 + 1000 + silence_ms


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


def test_transition_resolver_rejects_stale_copy(tmp_path, monkeypatch) -> None:
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "gap_vo": {
                    "post_synthesis_qc": {
                        "enabled": False,
                        "speech_qa_enabled": False,
                    }
                }
            }
        },
    )
    ctx = isolated_run_ctx(tmp_path, "transition_freshness")
    transitions = {
        "transitions": [
            {
                "after_segment_id": "seg_a",
                "before_segment_id": "seg_b",
                "text": "What changed after that?",
                "source_gap_ms": 1000,
            }
        ]
    }
    ctx.path("master", "transitions.json").parent.mkdir(parents=True, exist_ok=True)
    ctx.path("master", "transitions.json").write_text(
        json.dumps(transitions), encoding="utf-8"
    )
    manifest = {
        "segments": [
            {"segment_id": "seg_a", "text": "The first decision was made."},
            {"segment_id": "seg_b", "text": "The buyer arrived later."},
        ]
    }
    ctx.path("segments", "manifest.json").parent.mkdir(parents=True, exist_ok=True)
    ctx.path("segments", "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    out = transition_wav_path(ctx, "seg_a", "seg_b")
    with wave.open(str(out), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(48_000)
        handle.writeframes(b"\x00\x00" * 4800)
    line = {
        "line_id": "tr_seg_a_seg_b",
        "text": "What changed after that?",
        "targets_segment_id": "seg_a",
        "placement": "after",
        "after_segment_id": "seg_a",
        "before_segment_id": "seg_b",
        "before_excerpt": "The first decision was made.",
        "after_excerpt": "The buyer arrived later.",
        "source_gap_ms": 1000,
    }
    record_synthesis(ctx, line, backend="mlx_audio", out_wav=out)
    assert resolve_transition_wav(ctx, "seg_a", "seg_b") == out

    transitions["transitions"][0]["text"] = "What made the deal possible?"
    ctx.path("master", "transitions.json").write_text(
        json.dumps(transitions), encoding="utf-8"
    )
    assert resolve_transition_wav(ctx, "seg_a", "seg_b") is None
