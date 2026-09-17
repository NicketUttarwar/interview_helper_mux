"""i2: G0 sign-off must actually stamp transcript_review stage_done.

exec_11871: after i1 flush, complete API returned ok and logged success, but
mark_done(transcript_review) was refused authority_denied:mark_done:hollow
because stage_outputs_present had no registered outputs for the gate stage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.homunculus.agenda import stage_outputs_present
from interview_mux.run_context import RunContext
from interview_mux.stages.transcript_review import mark_transcript_review_complete
from run_fixtures import isolated_run_ctx, mark_done_raw


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "i2_g0_signoff")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _plant_g0_ready(ctx: RunContext) -> None:
    mark_done_raw(ctx, "transcript_review_build")
    ctx.write_json(
        "transcript/review_queue.json",
        {
            "version": 1,
            "chunks": [
                {
                    "chunk_id": "tr_0001",
                    "rank": 1,
                    "start_ms": 0,
                    "end_ms": 400,
                    "text": "hello",
                    "speaker_id": "spk_0",
                    "confidence": 0.5,
                    "reviewed": False,
                }
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json("transcript/corrections.json", {"corrections": {}}, skip_handoff=True)
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "hello",
            "words": [
                {
                    "text": "hello",
                    "start_ms": 0,
                    "end_ms": 400,
                    "speaker_id": "spk_0",
                    "confidence": 0.5,
                }
            ],
        },
        skip_handoff=True,
    )


def test_i2_stage_outputs_present_for_transcript_review(ctx: RunContext) -> None:
    _plant_g0_ready(ctx)
    assert stage_outputs_present(ctx, "transcript_review") is True


def test_i2_mark_complete_stamps_stage_done(ctx: RunContext) -> None:
    _plant_g0_ready(ctx)
    assert not ctx.is_done("transcript_review")
    mark_transcript_review_complete(ctx)
    assert ctx.is_done("transcript_review")
