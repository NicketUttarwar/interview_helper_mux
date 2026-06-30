from __future__ import annotations

import pytest

from interview_mux import llm_stage_routing
from interview_mux.analysis_memory import ensure_analysis_workspace
from interview_mux.attempt_budget import record_primary_attempt
from interview_mux.stages import analysis_stage
from run_fixtures import isolated_run_ctx, patch_merged_config


def _patch_flow_hardening(monkeypatch) -> None:
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "flow_hardening": {
                    "enabled": True,
                    "strict_critical_stages": False,
                    "inner_retry_require_delta": True,
                    "max_primary_attempts_per_stage": 3,
                },
                "max_iterations_per_stage": 3,
            }
        },
    )


def test_flow_stage_budget_exhaustion_sets_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "flow_budget")
    ensure_analysis_workspace(ctx)
    _patch_flow_hardening(monkeypatch)
    for _ in range(3):
        record_primary_attempt(ctx, "full_master_ranking")
    monkeypatch.setattr("interview_mux.llm_stage_routing.run_preflight", lambda *_a, **_k: [])

    analysis_stage.run_flow_llm_stage(
        ctx,
        "full_master_ranking",
        "selection/full-master-ranking.system.txt",
        lambda _c: {"segments": {"segments": []}},
        lambda _c, _a: None,
        max_iterations=1,
        auto_complete=False,
    )
    job = ctx.read_json("gui_job.json")
    assert job["status"] == "gate"
    assert "primary attempt budget exhausted" in str(job.get("message", "")).lower()


def test_flow_stage_retries_on_partial(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "flow_retry")
    ensure_analysis_workspace(ctx)
    _patch_flow_hardening(monkeypatch)
    monkeypatch.setattr("interview_mux.llm_stage_routing.run_preflight", lambda *_a, **_k: [])
    calls: list[int] = []

    def fake_routing(ctx_, stage_key, prompt_rel, stage_input, *, attempt=1, **kwargs):
        calls.append(attempt)
        status = "partial" if attempt == 1 else "complete"
        envelope = {
            "status": status,
            "artifacts": {"ordered_segment_ids": ["seg_001"]},
            "needs": [],
            "_routing_meta": {},
        }
        return envelope, [], {"verdict": "accept"}, [], 0, "primary"

    monkeypatch.setattr(analysis_stage, "run_llm_stage_with_routing", fake_routing)
    monkeypatch.setattr(
        "interview_mux.llm_flow_hardening.llm_stage_progress_ok",
        lambda *_a, **_k: True,
    )

    analysis_stage.run_flow_llm_stage(
        ctx,
        "full_master_ranking",
        "selection/full-master-ranking.system.txt",
        lambda _c: {"segments": {"segments": [{"segment_id": "seg_001"}]}},
        lambda _c, _a: None,
        max_iterations=3,
        auto_complete=False,
    )
    assert calls == [1, 2]


def test_flow_stage_stops_on_unchanged_signature(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "flow_delta")
    ensure_analysis_workspace(ctx)
    _patch_flow_hardening(monkeypatch)
    monkeypatch.setattr("interview_mux.llm_stage_routing.run_preflight", lambda *_a, **_k: [])
    calls: list[int] = []

    def fake_routing(ctx_, stage_key, prompt_rel, stage_input, *, attempt=1, **kwargs):
        calls.append(attempt)
        return (
            {"status": "partial", "artifacts": {}, "needs": [], "_routing_meta": {}},
            [{"role": "user", "content": "same"}],
            {"verdict": "accept"},
            [],
            0,
            "primary",
        )

    monkeypatch.setattr(analysis_stage, "run_llm_stage_with_routing", fake_routing)

    analysis_stage.run_flow_llm_stage(
        ctx,
        "transitions",
        "assembly/transitions.system.txt",
        lambda _c: {},
        lambda _c, _a: None,
        max_iterations=5,
        auto_complete=False,
    )
    assert len(calls) == 2


def test_flow_stage_retries_on_lint_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "flow_lint")
    ensure_analysis_workspace(ctx)
    _patch_flow_hardening(monkeypatch)
    monkeypatch.setattr("interview_mux.llm_stage_routing.run_preflight", lambda *_a, **_k: [])
    calls: list[int] = []
    lint_calls: list[int] = []

    def fake_lint(stage_key, envelope, ctx_, **kwargs):
        lint_calls.append(1)
        if len(lint_calls) == 1:
            return ["confidence_gte_min: 0.5 < 0.75"]
        return []

    monkeypatch.setattr("interview_mux.llm_stage_routing.deterministic_lint", fake_lint)

    def fake_routing(ctx_, stage_key, prompt_rel, stage_input, *, attempt=1, **kwargs):
        calls.append(attempt)
        envelope = {
            "status": "complete",
            "confidence": 0.5,
            "artifacts": {"ordered_segment_ids": ["seg_001"]},
            "needs": [],
            "_routing_meta": {},
        }
        arbiter = {"verdict": "accept"}
        lint_errors = llm_stage_routing._post_arbiter_hardening(
            ctx_, stage_key, envelope, arbiter, []
        )
        envelope.setdefault("_routing_meta", {})["deterministic_lint_errors"] = lint_errors
        return envelope, [], arbiter, [], 0, "primary"

    monkeypatch.setattr(analysis_stage, "run_llm_stage_with_routing", fake_routing)
    monkeypatch.setattr(
        "interview_mux.llm_flow_hardening.llm_stage_progress_ok",
        lambda *_a, **_k: True,
    )

    analysis_stage.run_flow_llm_stage(
        ctx,
        "full_master_ranking",
        "selection/full-master-ranking.system.txt",
        lambda _c: {"segments": {"segments": [{"segment_id": "seg_001"}]}},
        lambda _c, _a: None,
        max_iterations=3,
        auto_complete=False,
    )
    assert calls == [1, 2]
    assert len(lint_calls) == 2
