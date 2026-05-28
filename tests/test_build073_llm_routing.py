from __future__ import annotations

from interview_mux.analysis_memory import ensure_analysis_workspace
from interview_mux.run_context import RunContext
from interview_mux.stages import analysis_stage


def test_analysis_stage_decompose_records_arbiter_and_shards(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_073", create=True)
    ensure_analysis_workspace(ctx)

    calls: list[tuple[str, str]] = []

    def fake_run_prompt_envelope(stage_key, prompt_rel, **kwargs):
        task_kind = kwargs.get("task_kind", "primary")
        calls.append((stage_key, task_kind))
        if task_kind == "primary":
            return {
                "status": "complete",
                "artifacts": {"segments": [{"segment_id": "seg_001", "type": "story", "text": "t"}]},
                "needs": [],
                "memory_updates": {},
                "_llm_meta": {"model_tier": "standard", "model_id": "gpt-4o", "task_kind": "primary"},
            }
        if task_kind == "shard":
            return {
                "status": "complete",
                "artifacts": {"segments": [{"segment_id": "seg_001", "type": "story", "text": "t"}]},
                "needs": [],
                "memory_updates": {},
                "_llm_meta": {"model_tier": "economy", "model_id": "gpt-4o-mini", "task_kind": "shard"},
            }
        if task_kind == "collate":
            return {
                "status": "complete",
                "artifacts": {"segments": [{"segment_id": "seg_001", "type": "story", "text": "t"}]},
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

    def fake_run_shards_then_collate(*_args, **_kwargs):
        return (
            {
                "status": "complete",
                "artifacts": {"segments": [{"segment_id": "seg_001", "type": "story"}]},
                "needs": [],
                "memory_updates": {},
                "_llm_meta": {"model_tier": "standard", "model_id": "gpt-4o", "task_kind": "collate"},
            },
            1,
        )

    def build_input(_ctx):
        return {"segments": {"segments": [{"segment_id": "seg_001", "text": "hello"}]}, "content_brief": {"thesis": "x"}}

    persisted = {}

    def persist(_ctx, artifacts):
        persisted.update(artifacts)

    monkeypatch.setattr(analysis_stage, "run_prompt_envelope", fake_run_prompt_envelope)
    monkeypatch.setattr(analysis_stage, "run_llm_arbiter", fake_run_llm_arbiter)
    monkeypatch.setattr(analysis_stage, "run_shards_then_collate", fake_run_shards_then_collate)

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
    assert persisted["segments"][0]["segment_id"] == "seg_001"
    assert ("missing_framing", "primary") in calls
