from __future__ import annotations

from typing import Any

from interview_mux.analysis_memory import (
    ensure_analysis_workspace,
    load_analysis_state,
    should_merge_envelope,
    uptier_budget_remaining,
)
from interview_mux.context_volley import build_message_volley
from interview_mux import llm_stage_routing, llm_subtasks
from interview_mux.stages import analysis_stage
from run_fixtures import isolated_run_ctx, patch_merged_config


def test_analysis_stage_decompose_records_arbiter_and_shards(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "run_073")
    ensure_analysis_workspace(ctx)
    monkeypatch.setattr("interview_mux.llm_stage_routing.run_preflight", lambda *_a, **_k: [])
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": True, "strict_critical_stages": False}}},
    )

    calls: list[tuple[str, str]] = []

    def fake_run_prompt_envelope(stage_key, prompt_rel, **kwargs):
        task_kind = kwargs.get("task_kind", "primary")
        calls.append((stage_key, task_kind))
        gap_artifact = {
            "evaluations": [
                {
                    "segment_id": "seg_001",
                    "self_explanatory": True,
                    "gap_type": "ok_with_light_bridge",
                    "listener_confusion": "",
                    "severity": "low",
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

    arbiter_calls = 0

    def fake_run_llm_arbiter(**_kwargs):
        nonlocal arbiter_calls
        arbiter_calls += 1
        if arbiter_calls > 1:
            return {
                "verdict": "accept",
                "confidence": 0.9,
                "gaps": [],
                "shard_plan": [],
                "suggested_investigation": None,
                "reasoning_summary": "collate accepted",
            }
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

    monkeypatch.setattr(llm_stage_routing, "run_prompt_envelope", fake_run_prompt_envelope)
    monkeypatch.setattr(llm_stage_routing, "run_llm_arbiter", fake_run_llm_arbiter)
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
    assert attempt["shard_count"] >= 1
    assert attempt["arbiter_result"]["verdict"] in ("decompose", "accept", "enqueue_investigation")
    assert attempt.get("routed_via_collate") or attempt["arbiter_result"]["verdict"] == "decompose"
    assert attempt["shard_count"] == 1
    if "evaluations" in persisted:
        assert persisted["evaluations"][0]["segment_id"] == "seg_001"
    assert ("missing_framing", "primary") in calls
    assert ("missing_framing", "shard") in calls
    assert ("missing_framing", "collate") in calls


def test_primary_arbiter_accept_path_no_decompose(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "run_073_accept")
    ensure_analysis_workspace(ctx)
    monkeypatch.setattr("interview_mux.llm_stage_routing.run_preflight", lambda *_a, **_k: [])
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": False}}},
    )

    calls: list[tuple[str, str]] = []

    def fake_run_prompt_envelope(stage_key, prompt_rel, **kwargs):
        task_kind = kwargs.get("task_kind", "primary")
        calls.append((stage_key, task_kind))
        return {
            "status": "complete",
            "confidence": 0.9,
            "reasoning_summary": "ok",
            "artifacts": {
                "evaluations": [
                    {
                        "segment_id": "seg_001",
                        "self_explanatory": True,
                        "gap_type": "ok_with_light_bridge",
                        "listener_confusion": "",
                        "severity": "low",
                    }
                ]
            },
            "needs": [],
            "memory_updates": {},
            "_llm_meta": {"model_tier": "standard", "model_id": "gpt-4o", "task_kind": task_kind},
        }

    def fake_run_llm_arbiter(**_kwargs):
        return {
            "verdict": "accept",
            "confidence": 0.95,
            "gaps": [],
            "shard_plan": [],
            "suggested_investigation": None,
            "reasoning_summary": "primary ok",
        }

    persisted: dict[str, Any] = {}

    def persist(_ctx, artifacts):
        persisted.update(artifacts)

    monkeypatch.setattr(llm_stage_routing, "run_prompt_envelope", fake_run_prompt_envelope)
    monkeypatch.setattr(llm_stage_routing, "run_llm_arbiter", fake_run_llm_arbiter)
    monkeypatch.setattr(llm_stage_routing, "validate_stage_artifacts", lambda *_a, **_k: [])
    monkeypatch.setattr(llm_stage_routing, "validate_envelope", lambda *_a, **_k: [])

    analysis_stage.run_analysis_llm_stage(
        ctx,
        "missing_framing",
        "interviewer-gap/missing-framing.system.txt",
        lambda _c: {"segments": {"segments": [{"segment_id": "seg_001", "text": "hello"}]}, "content_brief": {"thesis": "x"}},
        persist,
        max_iterations=1,
    )
    attempt = ctx.read_json("understanding/stage_runs/missing_framing/attempt_001.json")
    assert attempt["arbiter_result"]["verdict"] == "accept"
    assert attempt.get("shard_count", 0) == 0
    assert ("missing_framing", "primary") in calls
    assert not any(kind != "primary" for _, kind in calls)


def test_deterministic_shard_plan_from_truncation_without_arbiter():
    from interview_mux.llm_shard_plans import build_deterministic_shard_plan

    stage_input = {"transcript": "word " * 20000}
    plan, source = build_deterministic_shard_plan(
        "content_context",
        stage_input,
        truncation_flags=["max_stage_data_chars"],
    )
    assert source == "deterministic"
    assert len(plan) >= 2


def test_uptier_cap_blocks_third_retry(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "run_073_uptier")
    ensure_analysis_workspace(ctx)
    monkeypatch.setattr("interview_mux.llm_stage_routing.run_preflight", lambda *_a, **_k: [])
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": True, "strict_critical_stages": False}}},
    )
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

    monkeypatch.setattr(llm_stage_routing, "run_prompt_envelope", fake_run_prompt_envelope)
    monkeypatch.setattr(llm_stage_routing, "run_llm_arbiter", fake_run_llm_arbiter)

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


def test_enqueue_investigation_does_not_merge_memory(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "run_084_merge")
    ensure_analysis_workspace(ctx)
    monkeypatch.setattr("interview_mux.llm_stage_routing.run_preflight", lambda *_a, **_k: [])
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": True, "strict_critical_stages": False}}},
    )
    state_before = load_analysis_state(ctx)
    themes_before = list(state_before.get("themes") or [])

    def fake_run_prompt_envelope(stage_key, prompt_rel, **kwargs):
        return {
            "status": "complete",
            "artifacts": {"gap_evaluations": []},
            "needs": [],
            "memory_updates": {"themes_append": [{"id": "bad_theme", "label": "Should Not Merge"}]},
            "reasoning_summary": "reject me",
            "_llm_meta": {"model_tier": "standard", "model_id": "gpt-4o", "task_kind": "primary"},
        }

    def fake_run_llm_arbiter(**_kwargs):
        return {
            "verdict": "enqueue_investigation",
            "confidence": 0.5,
            "gaps": ["cross-stage"],
            "shard_plan": [],
            "suggested_investigation": {
                "kind": "theme_unmapped",
                "question": "fix themes",
                "blocking": True,
            },
            "reasoning_summary": "enqueue",
        }

    monkeypatch.setattr(llm_stage_routing, "run_prompt_envelope", fake_run_prompt_envelope)
    monkeypatch.setattr(llm_stage_routing, "run_llm_arbiter", fake_run_llm_arbiter)

    analysis_stage.run_analysis_llm_stage(
        ctx,
        "missing_framing",
        "interviewer-gap/missing-framing.system.txt",
        lambda _c: {"segments": {"segments": []}, "content_brief": {"thesis": "x"}},
        lambda _c, _a: None,
        max_iterations=1,
    )

    state_after = load_analysis_state(ctx)
    assert state_after.get("themes") == themes_before
    assert not should_merge_envelope(
        {"verdict": "enqueue_investigation"},
        {"status": "blocked"},
    )


def test_shard_min_success_ratio_blocks_collate(tmp_path, monkeypatch):
    from run_fixtures import patch_merged_config

    ctx = isolated_run_ctx(tmp_path, "run_shard_ratio")
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": True, "shard_min_success_ratio": 0.75}}},
    )
    shard_plan = [
        {"label": "a", "segment_ids": ["seg_1"]},
        {"label": "b", "segment_ids": ["seg_2"]},
        {"label": "c", "segment_ids": ["seg_3"]},
        {"label": "d", "segment_ids": ["seg_4"]},
    ]

    def fake_shard_envelope(stage_key, prompt_rel, **kwargs):
        task = kwargs.get("task_kind", "primary")
        if task == "shard":
            return {"status": "blocked", "artifacts": {}, "needs": []}
        return {
            "status": "complete",
            "artifacts": {"gap_evaluations": [{"segment_id": "seg_1", "self_explanatory": True}]},
            "needs": [],
        }

    monkeypatch.setattr(llm_subtasks, "run_prompt_envelope", fake_shard_envelope)
    monkeypatch.setattr(llm_subtasks, "prepare_volley_for_llm", lambda *_a, **_k: ([], None))

    env, count = llm_subtasks.run_shards_then_collate(
        ctx,
        stage_key="missing_framing",
        prompt_rel="interviewer-gap/missing-framing.system.txt",
        stage_input={"segments": {"segments": []}},
        shard_plan=shard_plan,
    )
    assert count == 4
    assert env["status"] == "blocked"
    assert any("shard_min_success_ratio" in str(n.get("reason", "")) for n in env.get("needs") or [])


def test_finalize_stage_attempt_records_lint_and_budget(tmp_path, monkeypatch):
    from interview_mux.llm_stage_routing import finalize_stage_attempt

    ctx = isolated_run_ctx(tmp_path, "run_finalize_audit")
    ensure_analysis_workspace(ctx)
    monkeypatch.setattr("interview_mux.llm_stage_routing.run_preflight", lambda *_a, **_k: [])
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": True, "strict_critical_stages": False}}},
    )
    envelope = {
        "status": "partial",
        "artifacts": {},
        "_routing_meta": {"deterministic_lint_errors": ["thesis empty"]},
    }
    finalize_stage_attempt(
        ctx,
        "content_context",
        1,
        envelope,
        [{"role": "user", "content": "x"}],
        {"verdict": "reject"},
        [],
        0,
    )
    attempt = ctx.read_json("understanding/stage_runs/content_context/attempt_001.json")
    assert attempt.get("deterministic_lint_errors")
    assert "primary_attempt_count" in attempt or "budget_remaining_primary" in attempt


def test_should_persist_artifacts_blocks_on_lint_errors(tmp_path):
    from interview_mux.analysis_memory import should_persist_artifacts

    envelope = {
        "artifacts": {"thesis": "ok"},
        "_routing_meta": {"deterministic_lint_errors": ["thesis empty"]},
    }
    assert not should_persist_artifacts({"verdict": "accept"}, envelope, [])


def test_collate_volley_has_assistant_per_shard(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_084_collate")
    ensure_analysis_workspace(ctx)
    collate_input = {
        "mode": "collate",
        "stage_key": "missing_framing",
        "shard_outputs": [
            {
                "label": "a",
                "segment_ids": ["seg_1"],
                "envelope": {
                    "status": "complete",
                    "reasoning_summary": "shard one done",
                    "artifacts": {"gap_evaluations": [{"segment_id": "seg_1"}]},
                },
            },
            {
                "label": "b",
                "segment_ids": ["seg_2"],
                "envelope": {
                    "status": "complete",
                    "reasoning_summary": "shard two done",
                    "artifacts": {"gap_evaluations": [{"segment_id": "seg_2"}]},
                },
            },
        ],
        "instruction": "merge",
    }
    volley = build_message_volley(ctx, "missing_framing", collate_input, profile="collate")
    assistant_turns = [m for m in volley if m.get("role") == "assistant"]
    assert len(assistant_turns) == 2
    assert "shard one done" in assistant_turns[0]["content"]
    assert "shard two done" in assistant_turns[1]["content"]
