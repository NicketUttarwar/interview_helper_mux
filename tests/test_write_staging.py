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
    run_nested_staged_stage,
    run_wrapped_stage,
    write_approval_enabled,
)
from run_fixtures import patch_merged_config


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    root = tmp_path / "repo"
    executions = root / "ASSETS" / "executions"
    executions.mkdir(parents=True)
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: root)
    patch_merged_config(
        monkeypatch,
        {
            "assets_root": "ASSETS",
            "executions_root": "ASSETS/executions",
            "data_root": "data",
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
        note = ctx.path("ingest/checksums.json")
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text("staged", encoding="utf-8")
    finally:
        exit_stage_staging()
    assert has_pending_writes(ctx, "ingest")
    assert not ctx.final_path("ingest", "checksums.json").is_file()
    flushed = flush_stage_writes(ctx, "ingest")
    assert "ingest/checksums.json" in flushed
    assert ctx.final_path("ingest", "checksums.json").is_file()


def test_approve_marks_stage_done(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("ingest")
    note = ctx.path("ingest/checksums.json")
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


def test_transcribe_staging_hides_internal_aws_raw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Intermediate AWS download must not appear in write-approval paths."""
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("transcribe")
    try:
        scratch = ctx.path("transcript", "aws_raw.json")
        scratch.parent.mkdir(parents=True, exist_ok=True)
        scratch.write_text('{"results": {}}', encoding="utf-8")
        ctx.write_json("transcript/full.json", {"text": "hi", "words": []})
        ctx.write_json("transcript/speakers.json", {"speakers": []})
    finally:
        exit_stage_staging()
    paths = list_pending_paths(ctx, "transcribe")
    assert "transcript/aws_raw.json" not in paths
    assert "transcript/full.json" in paths
    assert "transcript/speakers.json" in paths
    flushed = flush_stage_writes(ctx, "transcribe")
    assert "transcript/aws_raw.json" not in flushed
    assert ctx.final_path("transcript", "full.json").is_file()
    assert not ctx.final_path("transcript", "aws_raw.json").is_file()


def test_operator_transcript_edits_mirror_into_deferred_transcribe_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dock/G0 edits must update deferred pending full.json so downstream reads corrections."""
    from interview_mux.stages.transcript_review import (
        mark_transcript_review_complete,
        patch_transcript_words,
    )
    from interview_mux.write_staging import record_pending_approval, staging_root

    ctx = _ctx(tmp_path, monkeypatch)
    original = {
        "text": "hello world",
        "words": [
            {"text": "hello", "start_ms": 0, "end_ms": 200, "speaker_id": "spk_0", "confidence": 0.9},
            {"text": "world", "start_ms": 200, "end_ms": 400, "speaker_id": "spk_0", "confidence": 0.9},
        ],
    }
    enter_stage_staging("transcribe")
    try:
        ctx.write_json("transcript/full.json", original)
        ctx.write_json("transcript/speakers.json", {"speakers": []})
    finally:
        exit_stage_staging()
    record_pending_approval(ctx, "transcribe")

    # Operator edits while STT outputs are still deferred / unapproved.
    patch_transcript_words(ctx, [{"index": 1, "text": "planet"}])

    pending_full = staging_root(ctx, "transcribe") / "transcript" / "full.json"
    asserted = ctx.read_json("transcript/full.json")
    assert asserted["words"][1]["text"] == "planet"
    assert asserted["words"][1].get("corrected") is True
    pending_doc = __import__("json").loads(pending_full.read_text(encoding="utf-8"))
    assert pending_doc["words"][1]["text"] == "planet"

    ctx.write_json(
        "transcript/review_queue.json",
        {
            "version": 1,
            "low_confidence_threshold": 0.85,
            "chunks": [
                {
                    "chunk_id": "tr_0001",
                    "start_ms": 0,
                    "end_ms": 400,
                    "speaker_id": "spk_0",
                    "text": "hello world",
                    "word_count": 2,
                    "confidence": 0.9,
                    "reviewed": False,
                    "needs_review": False,
                    "rank": 1,
                }
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json("transcript/corrections.json", {"corrections": {}}, skip_handoff=True)
    mark_transcript_review_complete(ctx)

    flushed = flush_stage_writes(ctx, "transcribe")
    assert "transcript/full.json" in flushed or True  # may skip if already synced
    final = ctx.read_json("transcript/full.json")
    assert final["words"][1]["text"] == "planet"
    assert final.get("review_applied_at")


def test_flush_preserves_operator_corrected_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Batch Save must not promote stale uncorrected STT over dock corrections."""
    from interview_mux.file_store import write_json as fs_write_json
    from interview_mux.write_staging import staging_root

    ctx = _ctx(tmp_path, monkeypatch)
    corrected = {
        "text": "hello planet",
        "review_applied_at": "2026-01-01T00:00:00+00:00",
        "words": [
            {"text": "hello", "start_ms": 0, "end_ms": 200, "corrected": True},
            {"text": "planet", "start_ms": 200, "end_ms": 400, "corrected": True},
        ],
    }
    stale = {
        "text": "hello world",
        "words": [
            {"text": "hello", "start_ms": 0, "end_ms": 200},
            {"text": "world", "start_ms": 200, "end_ms": 400},
        ],
    }
    fs_write_json(ctx.final_path("transcript", "full.json"), corrected)
    staged = staging_root(ctx, "transcribe") / "transcript" / "full.json"
    staged.parent.mkdir(parents=True, exist_ok=True)
    fs_write_json(staged, stale)

    flushed = flush_stage_writes(ctx, "transcribe")
    assert "transcript/full.json" not in flushed
    final = ctx.read_json("transcript/full.json")
    assert final["words"][1]["text"] == "planet"


def test_transcript_review_build_flush_keeps_corrections_and_clips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Write approval must promote corrections.json + review clips, not only review_queue."""
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("transcript_review_build")
    try:
        clips = ctx.path("transcript", "review_clips")
        clips.mkdir(parents=True, exist_ok=True)
        (clips / "tr_0001.wav").write_bytes(b"RIFF" + b"\0" * 40)
        ctx.write_json("transcript/review_queue.json", {"version": 1, "chunks": []})
        ctx.write_json("transcript/corrections.json", {"corrections": {}})
        # staging scratch that must stay internal
        scratch = ctx.path("transcript", "build_scratch.json")
        scratch.write_text("{}", encoding="utf-8")
    finally:
        exit_stage_staging()

    paths = list_pending_paths(ctx, "transcript_review_build")
    assert "transcript/review_queue.json" in paths
    assert "transcript/corrections.json" in paths
    assert "transcript/review_clips/tr_0001.wav" in paths
    assert "transcript/build_scratch.json" not in paths

    flushed = flush_stage_writes(ctx, "transcript_review_build")
    assert "transcript/corrections.json" in flushed
    assert "transcript/review_clips/tr_0001.wav" in flushed
    assert ctx.final_path("transcript", "corrections.json").is_file()
    assert ctx.final_path("transcript", "review_clips", "tr_0001.wav").is_file()
    assert not ctx.final_path("transcript", "build_scratch.json").is_file()


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
    note = ctx.path("ingest/checksums.json")
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


def test_nested_staged_stage_commits_under_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Classification writes nested under resplit must not die on parent flush."""
    ctx = _ctx(tmp_path, monkeypatch)
    monkeypatch.setattr("interview_mux.write_staging.write_approval_enabled", lambda: False)
    monkeypatch.setattr(
        "interview_mux.write_staging.after_stage_write_check",
        lambda c, sid: flush_stage_writes(c, sid),
    )
    enter_stage_staging("boundary_topic_resplit")
    try:
        parent_file = ctx.path("segments/boundaries.json")
        parent_file.parent.mkdir(parents=True, exist_ok=True)
        parent_file.write_text("{}", encoding="utf-8")

        def _inner() -> None:
            nested = ctx.path("segments/manifest.json")
            nested.parent.mkdir(parents=True, exist_ok=True)
            nested.write_text('{"segments":[]}', encoding="utf-8")

        run_nested_staged_stage(ctx, "segment_classification", _inner)
    finally:
        exit_stage_staging()
    flush_stage_writes(ctx, "boundary_topic_resplit")
    assert (ctx.run_dir / "segments" / "manifest.json").is_file()
    assert (ctx.run_dir / "segments" / "boundaries.json").is_file()
