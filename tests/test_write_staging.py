from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.write_staging import (
    approve_stage_writes,
    discard_stage_writes,
    enter_stage_staging,
    exit_stage_staging,
    flush_stage_writes,
    has_pending_writes,
    list_pending_paths,
    run_wrapped_stage,
    write_approval_enabled,
)


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    root = tmp_path / "repo"
    executions = root / "ASSETS" / "executions"
    executions.mkdir(parents=True)
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: root)
    monkeypatch.setattr(
        "interview_mux.run_context.merged_config",
        lambda: {
            "assets_root": "ASSETS",
            "executions_root": "ASSETS/executions",
            "data_root": "data",
            "journey_ui": {"require_write_approval_per_stage": True},
        },
    )
    monkeypatch.setattr(
        "interview_mux.write_staging.merged_config",
        lambda: {
            "journey_ui": {"require_write_approval_per_stage": True},
        },
    )
    rid = "exec_001_20260101T000000Z"
    ctx = RunContext(rid, create=True)
    ctx.write_json("run_meta.json", {"execution_id": rid}, skip_handoff=True)
    return ctx


def test_staging_redirect_and_flush(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("ingest")
    try:
        note = ctx.path("ingest/staging_note.txt")
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text("staged", encoding="utf-8")
    finally:
        exit_stage_staging()
    assert has_pending_writes(ctx, "ingest")
    assert not ctx.final_path("ingest", "staging_note.txt").is_file()
    flushed = flush_stage_writes(ctx, "ingest")
    assert "ingest/staging_note.txt" in flushed
    assert ctx.final_path("ingest", "staging_note.txt").is_file()


def test_approve_marks_stage_done(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("ingest")
    note = ctx.path("ingest/staging_note.txt")
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("staged", encoding="utf-8")
    exit_stage_staging()
    approve_stage_writes(ctx, "ingest")
    assert ctx.is_done("ingest")


def test_flush_large_wav(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("audio_preclean")
    wav = ctx.path("preclean/isolated.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"\x00" * (10 << 20))
    exit_stage_staging()
    flushed = flush_stage_writes(ctx, "audio_preclean")
    assert "preclean/isolated.wav" in flushed
    assert ctx.final_path("preclean", "isolated.wav").is_file()
    assert not list_pending_paths(ctx, "audio_preclean")


def test_read_path_falls_back_to_final_during_later_stage_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prior-stage inputs must resolve from the run dir, not the active staging root."""
    from interview_mux.write_staging import resolve_read_path

    ctx = _ctx(tmp_path, monkeypatch)
    wav = ctx.final_path("ingest", "normalized.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" + b"\0" * 40)
    enter_stage_staging("transcribe")
    try:
        assert not ctx.path("ingest", "normalized.wav").is_file()
        assert resolve_read_path(ctx, "ingest/normalized.wav").is_file()
        assert ctx.artifact_exists("ingest/normalized.wav")
    finally:
        exit_stage_staging()


def test_transcript_review_build_reads_prior_stage_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """transcript_review_build must read approved transcribe outputs, not its own staging root."""
    import wave

    from interview_mux.stages.transcript_review import run_transcript_review_build

    ctx = _ctx(tmp_path, monkeypatch)
    wav = ctx.final_path("ingest", "normalized.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 1600)
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "hello",
            "words": [
                {
                    "text": "hello",
                    "start_ms": 0,
                    "end_ms": 500,
                    "speaker_id": "spk_0",
                    "confidence": 0.5,
                }
            ],
            "segments": [],
        },
        skip_handoff=True,
    )
    enter_stage_staging("transcript_review_build")
    try:
        assert not ctx.path("transcript", "full.json").is_file()
        run_transcript_review_build(ctx)
    finally:
        exit_stage_staging()
    assert ctx.artifact_exists("transcript/review_queue.json")


def test_disfluency_extract_reads_prior_stage_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """disfluency_extract must read approved transcript/audio, not its own staging root."""
    from interview_mux.stages.disfluency import run_disfluency_extract

    ctx = _ctx(tmp_path, monkeypatch)
    wav = ctx.final_path("ingest", "normalized.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" + b"\0" * 64)
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "hello",
            "words": [
                {
                    "text": "hello",
                    "start_ms": 0,
                    "end_ms": 500,
                    "speaker_id": "spk_0",
                    "confidence": 0.5,
                }
            ],
            "segments": [],
        },
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.disfluency.config.disfluency_enabled",
        lambda: True,
    )
    enter_stage_staging("disfluency_extract")
    try:
        assert not ctx.path("transcript", "full.json").is_file()
        run_disfluency_extract(ctx)
    finally:
        exit_stage_staging()
    assert ctx.artifact_exists("transcript/disfluencies.json")


def test_source_acoustic_profile_reads_prior_stage_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """source_acoustic_profile must read approved ingest audio, not its own staging root."""
    import math
    import wave

    from interview_mux.stages.understanding import run_source_acoustic_profile

    ctx = _ctx(tmp_path, monkeypatch)
    wav = ctx.final_path("ingest", "normalized.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        n = 16000
        amp = 8000
        frames = bytearray()
        for i in range(n):
            sample = int(amp * math.sin(2.0 * math.pi * 220.0 * (i / 16000)))
            frames += int(sample).to_bytes(2, byteorder="little", signed=True)
        wf.writeframes(bytes(frames))
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "hello world",
            "words": [
                {"text": "hello", "start_ms": 0, "end_ms": 400, "speaker_id": "spk_0"},
                {"text": "world", "start_ms": 450, "end_ms": 900, "speaker_id": "spk_0"},
            ],
            "segments": [],
        },
        skip_handoff=True,
    )
    enter_stage_staging("source_acoustic_profile")
    try:
        assert not ctx.path("ingest", "normalized.wav").is_file()
        run_source_acoustic_profile(ctx)
    finally:
        exit_stage_staging()
    assert ctx.artifact_exists("understanding/source_acoustic_profile.json")


def test_discard_removes_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("ingest")
    note = ctx.path("ingest/staging_note.txt")
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("staged", encoding="utf-8")
    exit_stage_staging()
    discard_stage_writes(ctx, "ingest")
    assert not list_pending_paths(ctx, "ingest")


def test_gate_blocks_write_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.write_staging import (
        WriteApprovalBlockedError,
        assert_write_approval_allowed,
        is_stage_gate_blocked,
        write_approval_allowed,
    )

    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("speaker_roles")
    note = ctx.path("understanding/analysis_state.json")
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("{}", encoding="utf-8")
    exit_stage_staging()
    ctx.write_json(
        "gui_job.json",
        {
            "status": "gate",
            "stage": "speaker_roles",
            "message": "LLM stage gate (speaker_roles): blocked",
        },
        skip_handoff=True,
    )
    assert is_stage_gate_blocked(ctx, "speaker_roles")
    assert not write_approval_allowed(ctx, "speaker_roles")
    with pytest.raises(WriteApprovalBlockedError, match="LLM stage gate"):
        assert_write_approval_allowed(ctx, "speaker_roles")
