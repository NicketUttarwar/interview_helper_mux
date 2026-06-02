"""Tests for E2E journey driver state machine."""

from __future__ import annotations

from e2e_runner.journey_driver import decide_next_step, fingerprint
from e2e_runner.types import StepKind


def _base_run(**overrides):
    run = {
        "run_id": "exec_001_test",
        "job": {"status": "idle"},
        "journey": {
            "phase": "prepare",
            "next_action": "Run ingest and transcription",
            "blocking": {"blocked": False},
            "execute_hint": {
                "mode": "analysis",
                "until_stage": "transcript_review_build",
                "label": "Prepare transcript for review",
            },
            "milestones": {"g0_complete": False},
        },
        "stages": [],
    }
    run.update(overrides)
    return run


def test_decide_execute_when_hint_present():
    step = decide_next_step(_base_run(), flow="flow1")
    assert step.kind == StepKind.EXECUTE
    assert step.execute_body["mode"] == "analysis"


def test_decide_resolve_gate_when_blocked():
    run = _base_run()
    run["journey"]["blocking"] = {"blocked": True, "message": "Review transcript"}
    step = decide_next_step(run, flow="flow1")
    assert step.kind == StepKind.RESOLVE_GATE


def test_decide_wait_on_job_error():
    run = _base_run()
    run["job"] = {"status": "error", "message": "boom"}
    step = decide_next_step(run, flow="flow1")
    assert step.kind == StepKind.WAIT
    assert "error:" in step.detail


def test_fingerprint_stable():
    run = _base_run()
    assert fingerprint(run) == fingerprint(run)


def test_until_stage_done():
    run = _base_run()
    run["stages"] = [{"id": "ingest", "status": "done"}]
    step = decide_next_step(run, flow="flow1", until_stage="ingest")
    assert step.kind == StepKind.DONE
