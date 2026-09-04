"""Tests for vo_pickup/synthesis_report.json audit artifact."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.vo_synthesis_audit import (
    SYNTHESIS_REPORT_REL,
    VoScriptWavRebindError,
    backfill_missing_synthesis_entries,
    record_recorded_vo,
    record_skipped_vo,
    record_synthesis,
    synthesis_entry_for_line,
    synthesis_entry_matches_line,
    wav_content_sha256,
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
        {"line_id": "line_001", "text": "Hello.", "estimated_duration_sec": 4.0},
        backend="chatterbox",
        out_wav=wav,
        ref_audio="understanding/speaker_samples/spk_0.wav",
        wav_just_rendered=True,
    )
    doc = ctx.read_json(SYNTHESIS_REPORT_REL)
    entries = doc.get("entries") or []
    assert len(entries) == 1
    assert entries[0]["backend"] == "chatterbox"
    assert entries[0]["line_id"] == "line_001"
    assert entries[0]["wav_sha256"] == wav_content_sha256(wav)


def test_record_skipped_and_recorded(ctx: RunContext) -> None:
    record_skipped_vo(ctx, "line_skip", reason="optional")
    record_recorded_vo(ctx, "line_001", out_wav=ctx.path("vo_pickup", "line_001.wav"), backend="upload")
    entries = ctx.read_json(SYNTHESIS_REPORT_REL).get("entries") or []
    backends = {e["line_id"]: e["backend"] for e in entries}
    assert backends["line_skip"] == "skipped"
    assert backends["line_001"] == "upload"


def test_backfill_missing_synthesis_entries_refuses_forge(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    assert filled == []
    assert synthesis_entry_for_line(ctx, "line_001") is None


def test_refuse_silent_script_rebind_same_wav(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.vo_synthesis_audit.analyze_vo_wav",
        lambda *_a, **_k: {"pass": True},
    )
    wav = ctx.path("vo_pickup", "line_001.wav")
    line = {
        "line_id": "line_001",
        "text": "Original host framing.",
        "targets_segment_id": "seg_001",
        "placement": "before",
    }
    record_synthesis(
        ctx, line, backend="chatterbox", out_wav=wav, wav_just_rendered=True
    )
    rewritten = {**line, "text": "Rewritten host framing after heal."}
    with pytest.raises(VoScriptWavRebindError, match="stale_wav_script_rebind"):
        record_synthesis(ctx, rewritten, backend="chatterbox", out_wav=wav)
    matches, reason = synthesis_entry_matches_line(ctx, rewritten)
    assert matches is False
    assert reason == "stale_script_hash"


def test_resynth_with_new_bytes_allows_script_change(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.vo_synthesis_audit.analyze_vo_wav",
        lambda *_a, **_k: {"pass": True},
    )
    wav = ctx.path("vo_pickup", "line_001.wav")
    line = {
        "line_id": "line_001",
        "text": "Original host framing.",
        "targets_segment_id": "seg_001",
        "placement": "before",
    }
    record_synthesis(
        ctx, line, backend="chatterbox", out_wav=wav, wav_just_rendered=True
    )
    # Renderer wrote different audio for the new script.
    wav.write_bytes(b"RIFF" + b"\x01" * 96)
    rewritten = {**line, "text": "Rewritten host framing after heal."}
    entry = record_synthesis(
        ctx,
        rewritten,
        backend="chatterbox",
        out_wav=wav,
        wav_just_rendered=True,
    )
    assert entry["wav_sha256"] == wav_content_sha256(wav)
    matches, reason = synthesis_entry_matches_line(ctx, rewritten)
    assert matches is True
    assert reason == "match"
