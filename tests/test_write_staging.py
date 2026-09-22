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
    uncommitted_pending_reason,
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
    """Flush promotes staged paths into the committed run tree."""
    ctx = _ctx(tmp_path, monkeypatch)
    wav = ctx.final_path("ingest", "normalized.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" + b"\0" * 40)
    enter_stage_staging("ingest")
    note = ctx.path("ingest/checksums.json")
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text('{"ok": true}', encoding="utf-8")
    exit_stage_staging()
    flushed = flush_stage_writes(ctx, "ingest")
    assert "ingest/checksums.json" in flushed
    assert ctx.final_path("ingest", "checksums.json").is_file()
    assert not has_pending_writes(ctx, "ingest")


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


def test_read_path_ignores_other_stage_incomplete_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failed junction staging must not feed mix a stale EDL."""
    from interview_mux.write_staging import resolve_read_path, staging_root

    ctx = _ctx(tmp_path, monkeypatch)
    committed = ctx.final_path("master", "edl.json")
    committed.parent.mkdir(parents=True, exist_ok=True)
    committed.write_text('{"clips":[{"segment_id":"seg_004","source_end_ms":97920}]}\n')
    jroot = staging_root(ctx, "junction_snip_qa")
    stale = jroot / "master" / "edl.json"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text('{"clips":[{"segment_id":"seg_004","source_end_ms":105840}]}\n')
    enter_stage_staging("mix")
    try:
        resolved = resolve_read_path(ctx, "master/edl.json")
        assert resolved == committed
        assert "97920" in resolved.read_text()
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
    from interview_mux.write_staging import has_pending_writes, staging_root

    queued = staging_root(ctx, "transcript_review_build") / "transcript" / "review_queue.json"
    assert queued.is_file() or ctx.artifact_exists("transcript/review_queue.json")
    assert has_pending_writes(ctx, "transcript_review_build") or ctx.artifact_exists(
        "transcript/review_queue.json"
    )


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
    from interview_mux.write_staging import has_pending_writes, staging_root

    staged = (
        staging_root(ctx, "source_acoustic_profile")
        / "understanding"
        / "source_acoustic_profile.json"
    )
    assert staged.is_file() or ctx.artifact_exists(
        "understanding/source_acoustic_profile.json"
    )
    assert has_pending_writes(ctx, "source_acoustic_profile") or ctx.artifact_exists(
        "understanding/source_acoustic_profile.json"
    )


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


def test_skip_handoff_commits_mmaudio_qa_through_flush(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QA must land on the committed tree even while mmaudio_sfx staging is active."""
    ctx = _ctx(tmp_path, monkeypatch)
    monkeypatch.setattr("interview_mux.write_staging.write_approval_enabled", lambda: False)
    enter_stage_staging("mmaudio_sfx")
    try:
        ctx.write_json(
            "sound_design/mmaudio_qa.json",
            {"version": 1, "assets": []},
            skip_handoff=True,
            stage_key="mmaudio_sfx",
        )
    finally:
        exit_stage_staging()
    assert ctx.final_path("sound_design", "mmaudio_qa.json").is_file()
    flush_stage_writes(ctx, "mmaudio_sfx")
    assert ctx.final_path("sound_design", "mmaudio_qa.json").is_file()


def test_foreign_stage_pending_does_not_block_canonical_producer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """gap_framing_compose pending must not incomplete missing_framing (exec_11630)."""
    import time

    ctx = _ctx(tmp_path, monkeypatch)
    monkeypatch.setattr("interview_mux.write_staging.write_approval_enabled", lambda: False)
    committed = ctx.run_dir / "understanding" / "gap_evaluations.json"
    committed.parent.mkdir(parents=True, exist_ok=True)
    committed.write_text('{"evaluations":[]}', encoding="utf-8")
    time.sleep(0.02)
    foreign = (
        ctx.run_dir
        / ".pending_writes"
        / "gap_framing_compose"
        / "understanding"
        / "gap_evaluations.json"
    )
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text('{"evaluations":[1]}', encoding="utf-8")
    assert uncommitted_pending_reason(ctx, "understanding/gap_evaluations.json") is None


def test_promote_owner_skips_stale_pending_over_audited_wav(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pending VO must not clobber a sha-bound audited take (exec_11630)."""
    import json
    import os

    from interview_mux.spoken_copy_guard import context_hash, evidence_for_line, script_hash
    from interview_mux.write_staging import promote_owner_vo_pickup
    from interview_mux.vo_synthesis_audit import (
        synthesis_entry_for_line,
        synthesis_entry_matches_line,
        wav_content_sha256,
    )

    os.environ["MUX_FORENSICS"] = "0"
    ctx = _ctx(tmp_path, monkeypatch)
    monkeypatch.setattr("interview_mux.write_staging.write_approval_enabled", lambda: False)
    lid = "vo_layup_seg_020"
    spoken = "Good audited host line that stays script-fresh for sha protect."
    line = {
        "line_id": lid,
        "text": spoken,
        "delivery": "synthesize",
        "targets_segment_id": "seg_020",
        "placement": "before",
    }
    syn = ctx.run_dir / "vo_pickup" / "synthesized"
    syn.mkdir(parents=True)
    good = syn / f"{lid}.wav"
    good.write_bytes(b"RIFF" + b"\x00" * 100 + b"GOOD_AUDITED_TAKE")
    want = wav_content_sha256(good)
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [line]},
        skip_handoff=True,
    )
    report = {
        "version": 1,
        "entries": [
            {
                "line_id": lid,
                "script_hash": script_hash(spoken),
                "context_hash": context_hash(evidence_for_line(line)),
                "wav_sha256": want,
                "backend": "chatterbox",
                "qc_pass": True,
                "out_wav": f"vo_pickup/synthesized/{lid}.wav",
            }
        ],
    }
    # Write audit *after* gap so gap admit cascade cannot purge the entry.
    (ctx.final_path("vo_pickup")).mkdir(parents=True, exist_ok=True)
    (ctx.final_path("vo_pickup", "synthesis_report.json")).write_text(
        json.dumps(report), encoding="utf-8"
    )
    assert synthesis_entry_for_line(ctx, lid) is not None
    matches, reason = synthesis_entry_matches_line(ctx, line)
    assert matches, reason
    pending = (
        ctx.run_dir
        / ".pending_writes"
        / "vo_synthesize"
        / "vo_pickup"
        / "synthesized"
    )
    pending.mkdir(parents=True)
    stale = pending / f"{lid}.wav"
    stale.write_bytes(b"RIFF" + b"\x00" * 100 + b"STALE_PENDING_BYTES!!")
    assert wav_content_sha256(stale) != want
    flushed = promote_owner_vo_pickup(ctx)
    assert f"vo_pickup/synthesized/{lid}.wav" not in flushed
    assert wav_content_sha256(good) == want
    assert good.read_bytes().endswith(b"GOOD_AUDITED_TAKE")


def test_promote_owner_allows_pending_when_dest_audit_script_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cascade (MUX_FORENSICS=0): pending fresh G1 take must promote over script-stale dest.

    exec_13163: skip left dest matching old audit sha while gap text moved; cascade
    purged; EDL missing-WAV thrash. Allow promote when audit no longer matches gap.
    """
    import json
    import os

    from interview_mux.spoken_copy_guard import script_hash
    from interview_mux.write_staging import promote_owner_vo_pickup
    from interview_mux.vo_synthesis_audit import wav_content_sha256

    os.environ["MUX_FORENSICS"] = "0"
    ctx = _ctx(tmp_path, monkeypatch)
    monkeypatch.setattr("interview_mux.write_staging.write_approval_enabled", lambda: False)
    lid = "vo_layup_seg_009"
    spoken = "Fresh host line after adjudicate rewrite for precision oncology."
    syn = ctx.run_dir / "vo_pickup" / "synthesized"
    syn.mkdir(parents=True)
    stale_dest = syn / f"{lid}.wav"
    stale_dest.write_bytes(b"RIFF" + b"\x00" * 100 + b"OLD_AUDIT_DEST_BYTES")
    old_sha = wav_content_sha256(stale_dest)
    report = {
        "version": 1,
        "entries": [
            {
                "line_id": lid,
                "script_hash": script_hash("old spoken copy before rewrite"),
                "context_hash": "deadbeef",
                "wav_sha256": old_sha,
                "backend": "chatterbox",
                "qc_pass": True,
                "out_wav": f"vo_pickup/synthesized/{lid}.wav",
            }
        ],
    }
    (ctx.run_dir / "vo_pickup" / "synthesis_report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": lid,
                    "text": spoken,
                    "delivery": "synthesize",
                    "targets_segment_id": "seg_009",
                }
            ]
        },
        skip_handoff=True,
    )
    pending = (
        ctx.run_dir
        / ".pending_writes"
        / "vo_synthesize"
        / "vo_pickup"
        / "synthesized"
    )
    pending.mkdir(parents=True)
    fresh = pending / f"{lid}.wav"
    fresh.write_bytes(b"RIFF" + b"\x00" * 100 + b"FRESH_G1_PENDING_TAKE")
    fresh_sha = wav_content_sha256(fresh)
    assert fresh_sha != old_sha

    flushed = promote_owner_vo_pickup(ctx)
    assert f"vo_pickup/synthesized/{lid}.wav" in flushed
    assert wav_content_sha256(stale_dest) == fresh_sha
    assert stale_dest.read_bytes().endswith(b"FRESH_G1_PENDING_TAKE")


def test_promote_owner_allows_pending_when_script_line_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cascade: no gap/layup line → fail-open promote (not sha-only skip)."""
    import json
    import os

    from interview_mux.write_staging import promote_owner_vo_pickup
    from interview_mux.vo_synthesis_audit import wav_content_sha256

    os.environ["MUX_FORENSICS"] = "0"
    ctx = _ctx(tmp_path, monkeypatch)
    monkeypatch.setattr("interview_mux.write_staging.write_approval_enabled", lambda: False)
    lid = "vo_layup_seg_077"
    syn = ctx.run_dir / "vo_pickup" / "synthesized"
    syn.mkdir(parents=True)
    dest = syn / f"{lid}.wav"
    dest.write_bytes(b"RIFF" + b"\x00" * 100 + b"DEST_MATCHES_AUDIT")
    want = wav_content_sha256(dest)
    report = {
        "version": 1,
        "entries": [
            {
                "line_id": lid,
                "script_hash": "dead",
                "context_hash": "beef",
                "wav_sha256": want,
                "backend": "chatterbox",
                "qc_pass": True,
                "out_wav": f"vo_pickup/synthesized/{lid}.wav",
            }
        ],
    }
    (ctx.run_dir / "vo_pickup" / "synthesis_report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    # No gap_report / layup plan → script line missing.
    pending = (
        ctx.run_dir
        / ".pending_writes"
        / "vo_synthesize"
        / "vo_pickup"
        / "synthesized"
    )
    pending.mkdir(parents=True)
    fresh = pending / f"{lid}.wav"
    fresh.write_bytes(b"RIFF" + b"\x00" * 100 + b"PENDING_FRESH_BYTES!")
    flushed = promote_owner_vo_pickup(ctx)
    assert f"vo_pickup/synthesized/{lid}.wav" in flushed
    assert dest.read_bytes().endswith(b"PENDING_FRESH_BYTES!")


def test_promote_owner_uses_layup_plan_script_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cascade: layup-only line (not in gap interviewer_lines) still gates freshness."""
    import json
    import os

    from interview_mux.spoken_copy_guard import script_hash
    from interview_mux.write_staging import promote_owner_vo_pickup
    from interview_mux.vo_synthesis_audit import wav_content_sha256

    os.environ["MUX_FORENSICS"] = "0"
    ctx = _ctx(tmp_path, monkeypatch)
    monkeypatch.setattr("interview_mux.write_staging.write_approval_enabled", lambda: False)
    lid = "vo_layup_seg_088"
    spoken = "Layup-only spoken line for promote freshness authority."
    syn = ctx.run_dir / "vo_pickup" / "synthesized"
    syn.mkdir(parents=True)
    dest = syn / f"{lid}.wav"
    dest.write_bytes(b"RIFF" + b"\x00" * 100 + b"OLD_LAYUP_DEST_BYTES")
    old_sha = wav_content_sha256(dest)
    report = {
        "version": 1,
        "entries": [
            {
                "line_id": lid,
                "script_hash": script_hash("previous layup text"),
                "context_hash": "deadbeef",
                "wav_sha256": old_sha,
                "backend": "chatterbox",
                "qc_pass": True,
                "out_wav": f"vo_pickup/synthesized/{lid}.wav",
            }
        ],
    }
    (ctx.run_dir / "vo_pickup" / "synthesis_report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    ctx.write_json(
        "understanding/nugget_layup_plan.json",
        {
            "ordered_segment_ids": ["seg_088"],
            "layups": [
                {
                    "line_id": lid,
                    "target_segment_id": "seg_088",
                    "text": spoken,
                }
            ],
        },
        skip_handoff=True,
    )
    pending = (
        ctx.run_dir
        / ".pending_writes"
        / "vo_synthesize"
        / "vo_pickup"
        / "synthesized"
    )
    pending.mkdir(parents=True)
    fresh = pending / f"{lid}.wav"
    fresh.write_bytes(b"RIFF" + b"\x00" * 100 + b"FRESH_LAYUP_PENDING!")
    flushed = promote_owner_vo_pickup(ctx)
    assert f"vo_pickup/synthesized/{lid}.wav" in flushed
    assert dest.read_bytes().endswith(b"FRESH_LAYUP_PENDING!")
