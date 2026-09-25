"""i1: G0 gate must flush staged review_queue before SystemExit pause.

exec_11871: transcript_review_build wrote queue+clips to .pending_writes, then
raised SystemExit(\"Transcript review required\") inside the wrapped stage —
skipping after_stage_write_check. Homunculus cleared hollow stage_done and
rebuilt forever; G0 complete returned 400 Review queue not ready.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux import pipeline
from interview_mux.gates import check_transcript_review_pending
from interview_mux.run_context import RunContext
from interview_mux.write_staging import (
    enter_stage_staging,
    exit_stage_staging,
    has_pending_writes,
    staging_root,
)
from run_fixtures import isolated_run_ctx, plant_primary_and_stamp


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "i1_g0_flush")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _plant_staged_queue(ctx: RunContext) -> None:
    enter_stage_staging("transcript_review_build")
    try:
        clips = ctx.path("transcript", "review_clips")
        clips.mkdir(parents=True, exist_ok=True)
        (clips / "tr_0001.wav").write_bytes(b"RIFF" + b"\0" * 40)
        ctx.write_json(
            "transcript/review_queue.json",
            {
                "version": 1,
                "chunks": [
                    {
                        "chunk_id": "tr_0001",
                        "rank": 1,
                        "start_ms": 0,
                        "end_ms": 500,
                        "text": "hello",
                        "speaker_id": "spk_0",
                        "confidence": 0.4,
                        "clip_path": "transcript/review_clips/tr_0001.wav",
                        "reviewed": False,
                    }
                ],
            },
        )
        ctx.write_json("transcript/corrections.json", {"corrections": {}})
        # Keep G0 pending: do not mark_done while queue writes are still staged.
    finally:
        exit_stage_staging()
    assert has_pending_writes(ctx, "transcript_review_build")
    assert not ctx.final_path("transcript", "review_queue.json").is_file()


def test_i1_staged_queue_keeps_g0_pending(ctx: RunContext) -> None:
    _plant_staged_queue(ctx)
    assert check_transcript_review_pending(ctx) is True
    staged = staging_root(ctx, "transcript_review_build") / "transcript" / "review_queue.json"
    assert staged.is_file()


def test_i1_g0_systemexit_flushes_pending_queue(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    plant_primary_and_stamp(ctx, "audio_preclean")
    plant_primary_and_stamp(ctx, "ingest")
    plant_primary_and_stamp(ctx, "transcribe")
    monkeypatch.setattr(
        "interview_mux.stage_input_checks.require_stage_inputs",
        lambda _ctx, _name: None,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_lifecycle.run_phase_checks",
        lambda _ctx, _stage, _phase: [],
    )
    monkeypatch.setattr(
        "interview_mux.llm_flow_hardening.maybe_require_upstream_llm_progress",
        lambda _ctx, _name: None,
    )

    def _writer() -> None:
        # run_wrapped_stage already entered transcript_review_build staging.
        clips = ctx.path("transcript", "review_clips")
        clips.mkdir(parents=True, exist_ok=True)
        (clips / "tr_0001.wav").write_bytes(b"RIFF" + b"\0" * 40)
        ctx.write_json(
            "transcript/review_queue.json",
            {
                "version": 1,
                "chunks": [
                    {
                        "chunk_id": "tr_0001",
                        "rank": 1,
                        "start_ms": 0,
                        "end_ms": 500,
                        "text": "hello",
                        "speaker_id": "spk_0",
                        "confidence": 0.4,
                        "clip_path": "transcript/review_clips/tr_0001.wav",
                        "reviewed": False,
                    }
                ],
            },
        )
        ctx.write_json("transcript/corrections.json", {"corrections": {}})
        # Flush happens in execute_stage before the G0 SystemExit — do not mark_done here.

    monkeypatch.setattr(
        pipeline,
        "_analysis_stage_fns",
        lambda _ctx: {"transcript_review_build": _writer},
    )

    with pytest.raises(SystemExit, match="Transcript review required"):
        pipeline.run_single_stage(ctx, "transcript_review_build")

    assert ctx.final_path("transcript", "review_queue.json").is_file()
    assert not has_pending_writes(ctx, "transcript_review_build")
    assert check_transcript_review_pending(ctx) is True
    assert ctx.is_done("transcript_review_build")
