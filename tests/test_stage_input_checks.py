from __future__ import annotations

import math
import wave
from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.stage_input_checks import (
    StageInputError,
    collect_stage_input_issues,
    require_stage_inputs,
)
from interview_mux.write_staging import (
    enter_stage_staging,
    exit_stage_staging,
    staging_approval_hint,
)

from tests.test_write_staging import _ctx


def _write_tone_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        n = 1600
        amp = 8000
        frames = bytearray()
        for i in range(n):
            sample = int(amp * math.sin(2.0 * math.pi * 220.0 * (i / 16000)))
            frames += int(sample).to_bytes(2, byteorder="little", signed=True)
        wf.writeframes(bytes(frames))


def test_staging_approval_hint_when_file_only_in_pending_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("ingest")
    staged = ctx.path("ingest", "normalized.wav")
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(b"RIFF" + b"\0" * 40)
    exit_stage_staging()
    hint = staging_approval_hint(ctx, "ingest/normalized.wav")
    assert hint is not None
    assert "ingest" in hint
    assert "Save & continue" in hint


def test_source_acoustic_profile_blocked_without_audio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.write_json(
        "transcript/full.json",
        {"text": "hello world", "words": [], "segments": []},
        skip_handoff=True,
    )
    issues = collect_stage_input_issues(ctx, "source_acoustic_profile")
    assert any("normalized" in issue.message.lower() for issue in issues)


def test_source_acoustic_profile_passes_with_approved_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    _write_tone_wav(ctx.final_path("ingest", "normalized.wav"))
    ctx.write_json(
        "transcript/full.json",
        {"text": "hello world", "words": [], "segments": []},
        skip_handoff=True,
    )
    ctx.mark_done("transcript_review", force=True)
    issues = collect_stage_input_issues(ctx, "source_acoustic_profile")
    assert issues == []


def test_require_stage_inputs_raises_with_remediation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    with pytest.raises(StageInputError) as exc:
        require_stage_inputs(ctx, "master_flow1")
    assert exc.value.stage_id == "master_flow1"
    assert any(issue.remediation for issue in exc.value.issues)


def test_read_path_trap_hint_when_final_exists_but_staging_root_misses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.write_staging import staging_read_trap_hint

    ctx = _ctx(tmp_path, monkeypatch)
    _write_tone_wav(ctx.final_path("ingest", "normalized.wav"))
    enter_stage_staging("source_acoustic_profile")
    try:
        hint = staging_read_trap_hint(ctx, "ingest/normalized.wav")
        assert hint is not None
        assert "read_path" in hint
    finally:
        exit_stage_staging()


def test_vo_ingest_reads_pickup_from_final_path_during_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.stages.gaps import ingest_vo_pickup

    ctx = _ctx(tmp_path, monkeypatch)
    pickup = ctx.final_path("vo_pickup")
    _write_tone_wav(pickup / "line_001.wav")
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "line_001",
                    "delivery": "record",
                    "targets_segment_id": "seg_1",
                    "gap_type": "missing_framing",
                    "placement": "before",
                    "text": "Please clarify.",
                }
            ]
        },
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.config.merged_config",
        lambda: {"mix": {"normalize_vo_pickup": False}},
    )
    enter_stage_staging("vo_ingest")
    try:
        assert not ctx.path("vo_pickup", "line_001.wav").is_file()
        ingest_vo_pickup(ctx)
    finally:
        exit_stage_staging()
    assert ctx.is_done("vo_ingest")
