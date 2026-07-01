"""Tests for stage_finalize helpers."""

from interview_mux.operator_decisions import OperatorDecision, set_stage_decisions, stage_decisions_summary
from interview_mux.stage_finalize import FinalizeResult


def test_finalize_result_to_dict_includes_pending_count():
    result = FinalizeResult(ok=True, stage_key="boundary_detection")
    payload = result.to_dict()
    assert payload["pending_decision_count"] == 0
    assert payload["stage_key"] == "boundary_detection"


def test_stage_decisions_summary_empty(tmp_path, monkeypatch):
    from interview_mux.run_context import RunContext

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ctx = RunContext(str(run_dir))
    summary = stage_decisions_summary(ctx, "boundary_detection")
    assert summary["open_count"] == 0
    assert summary["ready_for_review"] is True


def test_set_stage_decisions_persists_queue(tmp_path):
    from interview_mux.run_context import RunContext

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ctx = RunContext(str(run_dir))
    set_stage_decisions(
        ctx,
        "boundary_detection",
        [
            OperatorDecision(
                id="dec_test",
                kind="acknowledge_warning",
                headline="2 segments removed",
                detail="Timeline would have been invalid.",
                options=[],
            )
        ],
    )
    summary = stage_decisions_summary(ctx, "boundary_detection")
    assert summary["open_count"] == 1
    assert summary["current"]["id"] == "dec_test"
    assert summary["ready_for_review"] is False
