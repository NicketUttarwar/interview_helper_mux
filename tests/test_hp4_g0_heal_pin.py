"""HP-4: G0 open (queue exists, unsigned) pins transcript_review, not rebuild.

Do not start a run. HP-2 missing-queue hollow-done stays open.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.heal_routing import classify_heal_error, resume_stage_for_error_class
from interview_mux.homunculus.agenda import remaining_stages, walk_seed_agenda
from interview_mux.homunculus.runtime import dispatch_stage
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import g0_heal_resume_stage, producer_pin_for_token
from interview_mux.stage_families import default_escalation_options
from interview_mux.thrash_hardening import heal_navigate
from run_fixtures import isolated_run_ctx, mark_done_raw


def _queue() -> dict:
    return {
        "version": 1,
        "chunk_count": 1,
        "chunks": [
            {
                "chunk_id": "tr_0001",
                "rank": 1,
                "start_ms": 0,
                "end_ms": 1000,
                "text": "hello",
                "confidence": 0.4,
            }
        ],
    }


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hp4_g0")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_hp4_queue_exists_pins_gate_not_build(ctx: RunContext) -> None:
    ctx.write_json("transcript/review_queue.json", _queue())
    assert g0_heal_resume_stage(ctx) == "transcript_review"
    assert producer_pin_for_token("g0_pending", ctx=ctx) == "transcript_review"
    assert producer_pin_for_token("g0_pending") == "transcript_review"


def test_hp4_missing_queue_still_pins_build(ctx: RunContext) -> None:
    assert not ctx.artifact_exists("transcript/review_queue.json")
    assert g0_heal_resume_stage(ctx) == "transcript_review_build"
    assert producer_pin_for_token("g0_pending", ctx=ctx) == "transcript_review_build"


def test_hp4_heal_navigate_and_classify_pin_gate(ctx: RunContext) -> None:
    ctx.write_json("transcript/review_queue.json", _queue())
    nav = heal_navigate(
        ctx,
        error="Transcript review required. Open the GUI.",
        stage="audio_probe_build",
    )
    assert nav["from_stage"] == "transcript_review"
    route = classify_heal_error("Transcript review required", ctx, stage="audio_probe_build")
    assert route is not None
    assert route.from_stage == "transcript_review"
    assert resume_stage_for_error_class("g0_pending") == "transcript_review"


def test_hp4_heal_navigate_missing_queue_pins_build(ctx: RunContext) -> None:
    nav = heal_navigate(ctx, error="g0_pending", stage="audio_probe_build")
    assert nav["from_stage"] == "transcript_review_build"


def test_hp4_remaining_analysis_stops_at_build_without_ingest(
    ctx: RunContext,
) -> None:
    ctx.write_json("transcript/review_queue.json", _queue())
    mark_done_raw(ctx, "transcript_review_build")
    rem = remaining_stages(ctx, "analysis")
    assert "audio_probe_build" not in rem
    assert "speaker_roles" not in rem
    assert not ctx.artifact_exists("ingest/transcript.json")


def test_hp4_walk_does_not_run_later_analysis(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx.write_json("transcript/review_queue.json", _queue())
    mark_done_raw(ctx, "transcript_review_build")
    ran: list[str] = []
    monkeypatch.setattr(
        "interview_mux.pipeline.run_single_stage",
        lambda _ctx, sid: ran.append(sid),
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.prepare_delivery_guardrails",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.filter_delivery_candidates",
        lambda _ctx, stages: list(stages),
    )
    walk_seed_agenda(
        ctx,
        ["transcript_review_build", "audio_probe_build", "speaker_roles"],
        reason="hp4",
    )
    assert "audio_probe_build" not in ran
    assert "speaker_roles" not in ran


def test_hp4_dispatch_does_not_sign_off_g0(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx.write_json("transcript/review_queue.json", _queue())
    ran: list[str] = []
    with pytest.raises(RuntimeError, match="operator must-act"):
        dispatch_stage(ctx, "transcript_review", lambda sid: ran.append(sid), source="conductor")
    assert ran == []
    assert not ctx.is_done("transcript_review")


def test_hp4_escalation_open_g0_pins_gate() -> None:
    opts = default_escalation_options("transcribe")
    open_g0 = next(o for o in opts if o.get("id") == "open_g0_review")
    assert open_g0["resume_stage"] == "transcript_review"
