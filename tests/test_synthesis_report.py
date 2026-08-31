"""Tests for vo_pickup/synthesis_report.json audit artifact."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.vo_synthesis_audit import (
    SYNTHESIS_REPORT_REL,
    backfill_missing_synthesis_entries,
    record_recorded_vo,
    record_skipped_vo,
    record_synthesis,
    synthesis_entry_for_line,
)
from run_fixtures import patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext("exec_synth_report", create=True)
    pickup = run.path("vo_pickup")
    pickup.mkdir(parents=True, exist_ok=True)
    wav = pickup / "line_001.wav"
    wav.write_bytes(b"RIFF" + b"\x00" * 64)
    return run


def test_record_synthesis_writes_entry(ctx: RunContext) -> None:
    wav = ctx.path("vo_pickup", "line_001.wav")
    record_synthesis(
        ctx,
        {"line_id": "line_001", "estimated_duration_sec": 4.0},
        backend="chatterbox",
        out_wav=wav,
        ref_audio="understanding/speaker_samples/spk_0.wav",
    )
    doc = ctx.read_json(SYNTHESIS_REPORT_REL)
    entries = doc.get("entries") or []
    assert len(entries) == 1
    assert entries[0]["backend"] == "chatterbox"
    assert entries[0]["line_id"] == "line_001"


def test_record_skipped_and_recorded(ctx: RunContext) -> None:
    record_skipped_vo(ctx, "line_skip", reason="optional")
    record_recorded_vo(ctx, "line_001", out_wav=ctx.path("vo_pickup", "line_001.wav"), backend="upload")
    entries = ctx.read_json(SYNTHESIS_REPORT_REL).get("entries") or []
    backends = {e["line_id"]: e["backend"] for e in entries}
    assert backends["line_skip"] == "skipped"
    assert backends["line_001"] == "upload"


def test_backfill_missing_synthesis_entries(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.vo_synthesis_audit.analyze_vo_wav",
        lambda *_a, **_k: {"pass": True},
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "line_001",
                    "text": "Hello world.",
                    "targets_segment_id": "seg_001",
                    "required": True,
                    "gap_type": "nugget_layup",
                    "placement": "before",
                    "delivery": "synthesize",
                }
            ]
        },
        skip_handoff=True,
    )
    assert synthesis_entry_for_line(ctx, "line_001") is None
    filled = backfill_missing_synthesis_entries(ctx)
    assert filled == ["line_001"]
    assert synthesis_entry_for_line(ctx, "line_001") is not None
