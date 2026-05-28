from __future__ import annotations

from interview_mux.analysis_memory import ensure_analysis_workspace, uptier_budget_remaining
from interview_mux import llm_subtasks
from interview_mux.stages import analysis_stage
from run_fixtures import isolated_run_ctx


def test_analysis_stage_decompose_records_arbiter_and_shards(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "run_073")
    ensure_analysis_workspace(ctx)

    calls: list[tuple[str, str]] = []

    def fake_run_prompt_envelope(stage_key, prompt_rel, **kwargs):
        task_kind = kwargs.get("task_kind", "primary")
        calls.append((stage_key, task_kind))
        gap_artifact = {
            "gap_evaluations": [
                {
                    "segment_id": "seg_001",
                    "gap_severity": "low",
                    "listener_needs_context": False,
                    "rationale": "self-explanatory",
                }
            ]
        }
        if task_kind == "primary":
            return {
                "status": "complete",
                "artifacts": gap_artifact,
                "needs": [],
                "memory_updates": {},
                "_llm_meta": {"model_tier": "standard", "model_id": "gpt-4o", "task_kind": "primary"},
            }
        if task_kind == "shard":
            return {
                "status": "complete",
                "artifacts": gap_artifact,
                "needs": [],
                "memory_updates": {},
                "_llm_meta": {"model_tier": "economy", "model_id": "gpt-4o-mini", "task_kind": "shard"},
            }
        if task_kind == "collate":
            return {
                "status": "complete",
                "artifacts": gap_artifact,
                "needs": [],
                "memory_updates": {},
                "_llm_meta": {"model_tier": "standard", "model_id": "gpt-4o", "task_kind": "collate"},
            }
        raise AssertionError(f"unexpected task_kind {task_kind}")

    def fake_run_llm_arbiter(**_kwargs):
        return {
            "verdict": "decompose",
            "confidence": 0.9,
            "gaps": ["too much context"],
            "shard_plan": [{"label": "part1", "segment_ids": ["seg_001"]}],
            "suggested_investigation": None,
            "reasoning_summary": "use shard/collate",
        }

    def build_input(_ctx):
        return {"segments": {"segments": [{"segment_id": "seg_001", "text": "hello"}]}, "content_brief": {"thesis": "x"}}

    persisted = {}

    def persist(_ctx, artifacts):
        persisted.update(artifacts)

    monkeypatch.setattr(analysis_stage, "run_prompt_envelope", fake_run_prompt_envelope)
    monkeypatch.setattr(analysis_stage, "run_llm_arbiter", fake_run_llm_arbiter)
    monkeypatch.setattr(llm_subtasks, "run_prompt_envelope", fake_run_prompt_envelope)

    analysis_stage.run_analysis_llm_stage(
        ctx,
        "missing_framing",
        "interviewer-gap/missing-framing.system.txt",
        build_input,
        persist,
        max_iterations=1,
    )
    attempt = ctx.read_json("understanding/stage_runs/missing_framing/attempt_001.json")
    assert attempt["arbiter_result"]["verdict"] == "decompose"
    assert attempt["shard_count"] == 1
    assert persisted["gap_evaluations"][0]["segment_id"] == "seg_001"
    assert ("missing_framing", "primary") in calls
    assert ("missing_framing", "shard") in calls
    assert ("missing_framing", "collate") in calls


def test_uptier_cap_blocks_third_retry(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "run_073_uptier")
    ensure_analysis_workspace(ctx)
    assert uptier_budget_remaining(ctx, "missing_framing") == 2

    def fake_run_prompt_envelope(stage_key, prompt_rel, **kwargs):
        return {
            "status": "complete",
            "artifacts": {"gap_evaluations": []},
            "needs": [],
            "memory_updates": {},
            "_llm_meta": {"model_tier": "standard", "model_id": "gpt-4o", "task_kind": kwargs.get("task_kind", "primary")},
        }

    def fake_run_llm_arbiter(**_kwargs):
        return {
            "verdict": "retry_uptier",
            "confidence": 0.7,
            "gaps": ["weak"],
            "shard_plan": [],
            "suggested_investigation": None,
            "reasoning_summary": "bump tier",
        }

    monkeypatch.setattr(analysis_stage, "run_prompt_envelope", fake_run_prompt_envelope)
    monkeypatch.setattr(analysis_stage, "run_llm_arbiter", fake_run_llm_arbiter)

    for _ in range(3):
        analysis_stage.run_analysis_llm_stage(
            ctx,
            "missing_framing",
            "interviewer-gap/missing-framing.system.txt",
            lambda _c: {"segments": {"segments": []}, "content_brief": {"thesis": "x"}},
            lambda _c, _a: None,
            max_iterations=1,
        )

    assert uptier_budget_remaining(ctx, "missing_framing") == 0
    attempt = ctx.read_json("understanding/stage_runs/missing_framing/attempt_001.json")
    assert attempt["envelope"]["status"] == "blocked"
