from __future__ import annotations

from unittest.mock import patch

from interview_mux.analysis_orchestrator import (
    apply_needs_reruns,
    drain_investigation_queue,
    process_needs_after_stage,
)
from run_fixtures import isolated_run_ctx


def test_process_needs_after_stage_collects_rerun_stage(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_needs")
    reruns = process_needs_after_stage(
        ctx,
        "content_context",
        {
            "needs": [
                {"type": "rerun_stage", "stage": "segment_classification"},
                {"type": "operator", "reason": "verify theme"},
            ],
        },
    )
    assert reruns == ["segment_classification"]


def test_apply_needs_reruns_invokes_runner(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_apply_needs")
    called: list[str] = []

    def runner() -> None:
        called.append("segment_classification")

    apply_needs_reruns(
        ctx,
        "content_context",
        {"needs": [{"type": "rerun_stage", "stage": "segment_classification"}]},
        {"segment_classification": runner},
    )
    assert called == ["segment_classification"]


def test_drain_investigation_rerun_not_marked_done_on_no_improvement(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_drain_fail")
    ctx.path("understanding").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "understanding/investigation_queue.json",
        {
            "items": [
                {
                    "id": "inv_rerun",
                    "kind": "rerun_stage",
                    "status": "open",
                    "question": "retry content context",
                    "suggested_action": {"type": "rerun_stage", "stage": "content_context"},
                }
            ]
        },
    )

    def failing_runner() -> None:
        pass

    drain_investigation_queue(ctx, {"content_context": failing_runner})
    queue = ctx.read_json("understanding/investigation_queue.json")
    assert queue["items"][0]["status"] == "open"


def test_drain_investigation_queue_run_specialist(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_drain_spec")
    ctx.path("understanding").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "understanding/investigation_queue.json",
        {
            "items": [
                {
                    "id": "inv_1",
                    "kind": "run_specialist",
                    "status": "open",
                    "question": "run specialist",
                    "suggested_action": {
                        "type": "run_specialist",
                        "stage": "full_master_ranking",
                        "specialist": "comprehension_risk_blind",
                    },
                }
            ]
        },
    )
    with (
        patch("interview_mux.llm_specialists.specialists_enabled", return_value=True),
        patch("interview_mux.llm_specialists.run_specialist") as mock_run,
    ):
        mock_run.return_value = {"artifacts": {}}
        drain_investigation_queue(ctx, {}, specialist_input_fn=lambda _c, _s: {})
        mock_run.assert_called_once()
