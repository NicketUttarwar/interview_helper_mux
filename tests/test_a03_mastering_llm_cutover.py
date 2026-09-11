"""A-03 Shape/research LLM cutover — prompt invoke + fail-open complete rules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.mastering_plan_loader import consumers_bind_enabled
from interview_mux.mastering_research import run_mastering_research_routing
from interview_mux.mastering_shape_runtime import (
    run_mastering_plan_synthesize,
    run_mastering_shape_agenda,
    run_mastering_shape_candidates,
)
from interview_mux.run_context import RunContext
from run_fixtures import patch_executions_root


def _minimal_valid_plan(*, pass_name: str = "provisional") -> dict:
    return {
        "version": 1,
        "pass": pass_name,
        "plan_status": "complete",
        "narrative_mode": "conversational_host",
        "montage_grammar": [],
        "cold_open": {
            "kind": "none",
            "rationale": "llm mock",
            "evidence_refs": ["understanding/content_brief.json"],
            "confidence": 0.8,
        },
        "decisions": [],
        "bespoke_rationale": "Mock flagship synthesize for A-03",
        "invariants": {
            "never_invent_unspoken_dialogue": True,
            "prefer_pickup_voice": True,
            "pickup_voice_only": False,
        },
        "listener_outcome": {
            "finishability": "optimize",
            "recommendability": "optimize",
            "rationale": "mock",
        },
        "generated_at": "2026-01-01T00:00:00+00:00",
    }


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return RunContext("exec_a03_llm", create=True)


def test_research_llm_invokes_router_prompt(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.mastering_research.research_llm_enabled",
        lambda _cfg=None: True,
    )
    calls: list[tuple[str, str]] = []

    def _fake_invoke(_ctx, stage_key, prompt_rel, user_payload, *, max_attempts=2):
        calls.append((stage_key, prompt_rel))
        return {
            "version": 1,
            "mode": "advisory",
            "fields": [
                {
                    "field_id": "thesis_claims",
                    "wave": 3,
                    "disposition": "required",
                    "reason": "core thesis present in content_brief",
                }
            ],
            "generated_at": "2026-01-01T00:00:00+00:00",
        }

    monkeypatch.setattr(
        "interview_mux.mastering_llm.invoke_mastering_prompt",
        _fake_invoke,
    )
    ctx.write_json(
        "understanding/content_brief.json",
        {"thesis": "t", "topics": [{"name": "a", "summary": "b"}]},
    )
    run_mastering_research_routing(ctx)
    assert calls == [("mastering_research_routing", "mastering/research-router.system.txt")]
    routing = ctx.read_json("mastering/research/routing.json")
    assert routing.get("source") == "llm"
    assert routing.get("fields")
    assert consumers_bind_enabled() is False


def test_shape_llm_happy_path_invokes_flagship(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.mastering_plan_loader.shape_llm_enabled",
        lambda _cfg=None: True,
    )
    monkeypatch.setattr(
        "interview_mux.mastering_shape_runtime.shape_llm_enabled",
        lambda _cfg=None: True,
    )
    prompts: list[str] = []

    def _fake_invoke(_ctx, stage_key, prompt_rel, user_payload, *, max_attempts=2):
        prompts.append(prompt_rel)
        if "meta-architect" in prompt_rel:
            return {
                "version": 1,
                "pass": "provisional",
                "primary_mode_hypothesis": "conversational_host",
                "mode_candidates": ["conversational_host", "sparse_source"],
                "steps": [{"step_id": "compete", "goal": "best listen"}],
                "budgets": {"max_steps": 4, "max_prompt_edits": 2, "max_flagship_calls": 2},
                "north_star_pillars": ["finishability"],
                "generated_at": "2026-01-01T00:00:00+00:00",
            }
        if "eval-rubric" in prompt_rel:
            return {
                "version": 1,
                "style_axes": [{"axis": "tone", "value": "warm", "confidence": 0.5}],
                "criteria": [
                    {"criterion_id": "finishability", "description": "finish", "weight": 1.0}
                ],
                "generated_at": "2026-01-01T00:00:00+00:00",
            }
        if "l2-candidates" in prompt_rel:
            return {
                "candidates": [
                    {
                        "candidate_id": "cand_0_conversational_host",
                        "narrative_mode": "conversational_host",
                        "montage_grammar": [],
                        "cold_open_kind": "none",
                        "rationale": "llm candidate",
                    }
                ]
            }
        if "flagship-synthesize" in prompt_rel:
            return _minimal_valid_plan()
        return None

    monkeypatch.setattr(
        "interview_mux.mastering_llm.invoke_mastering_prompt",
        _fake_invoke,
    )
    ctx.write_json(
        "understanding/content_brief.json",
        {"thesis": "t", "topics": [{"name": "a", "summary": "b"}]},
    )
    run_mastering_shape_agenda(ctx)
    run_mastering_shape_candidates(ctx)
    run_mastering_plan_synthesize(ctx)
    assert "mastering/shape-meta-architect.system.txt" in prompts
    assert "mastering/shape-l2-candidates.system.txt" in prompts
    assert "mastering/flagship-synthesize.system.txt" in prompts
    plan = ctx.read_json("mastering/mastering_plan.json")
    assert plan.get("plan_status") == "complete"
    assert plan.get("source") == "llm"
    assert consumers_bind_enabled() is False


def test_shape_llm_fail_open_degraded_not_complete(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.mastering_plan_loader.shape_llm_enabled",
        lambda _cfg=None: True,
    )
    monkeypatch.setattr(
        "interview_mux.mastering_shape_runtime.shape_llm_enabled",
        lambda _cfg=None: True,
    )
    monkeypatch.setattr(
        "interview_mux.mastering_llm.invoke_mastering_prompt",
        lambda *_a, **_k: None,
    )
    ctx.write_json(
        "understanding/content_brief.json",
        {"thesis": "t", "topics": [{"name": "a", "summary": "b"}]},
    )
    run_mastering_shape_agenda(ctx)
    run_mastering_shape_candidates(ctx)
    run_mastering_plan_synthesize(ctx)
    plan = ctx.read_json("mastering/mastering_plan.json")
    assert plan.get("plan_status") == "degraded"
    assert plan.get("plan_status") != "complete"
    reasons = list(plan.get("degradation_reasons") or [])
    assert any("soft_gate" in r or "llm" in r for r in reasons)
    defaults = json.loads(Path("config/app.defaults.json").read_text(encoding="utf-8"))
    assert defaults["mastering"]["shape"]["soft_gate"]["consumers_bind"] is False
    assert defaults["mastering"]["research"]["llm"]["enabled"] is False
    assert defaults["mastering"]["shape"]["llm"]["enabled"] is False
    assert consumers_bind_enabled() is False


def test_a03_claim_plan_complete_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.mastering_plan_loader import (
        claim_plan_complete,
        soft_gate_may_claim_complete,
    )

    assert soft_gate_may_claim_complete() is False
    assert claim_plan_complete(source="soft_gate") == "degraded"
    monkeypatch.setattr(
        "interview_mux.mastering_plan_loader.shape_llm_enabled",
        lambda _cfg=None: False,
    )
    assert claim_plan_complete(source="llm") == "degraded"
    monkeypatch.setattr(
        "interview_mux.mastering_plan_loader.research_llm_enabled",
        lambda _cfg=None: True,
    )
    # Research flag must not unlock soft_gate complete.
    assert claim_plan_complete(source="soft_gate") == "degraded"
    monkeypatch.setattr(
        "interview_mux.mastering_plan_loader.shape_llm_enabled",
        lambda _cfg=None: True,
    )
    assert claim_plan_complete(source="llm") == "complete"
    assert claim_plan_complete(source="soft_gate") == "degraded"


def test_a03_defaults_soft_gate_never_complete(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Under real defaults (no flag monkeypatch), soft-gate writes degraded not complete."""
    from interview_mux.mastering_plan_loader import (
        consumers_bind_enabled,
        research_llm_enabled,
        shape_llm_enabled,
        soft_gate_may_claim_complete,
    )
    from interview_mux.mastering_research import run_research_rollup

    assert research_llm_enabled() is False
    assert shape_llm_enabled() is False
    assert consumers_bind_enabled() is False
    assert soft_gate_may_claim_complete() is False

    ctx.write_json(
        "understanding/content_brief.json",
        {"thesis": "t", "topics": [{"name": "a", "summary": "b"}]},
    )
    run_research_rollup(ctx)
    run_mastering_shape_agenda(ctx)
    run_mastering_shape_candidates(ctx)
    run_mastering_plan_synthesize(ctx)
    plan = ctx.read_json("mastering/mastering_plan.json")
    assert plan.get("plan_status") == "degraded"
    assert plan.get("source") == "soft_gate"
    reasons = list(plan.get("degradation_reasons") or [])
    assert "soft_gate_not_authoritative" in reasons
    assert consumers_bind_enabled() is False


def test_a03_hybrid_bind_requires_complete() -> None:
    from interview_mux.shape_order_bind import resolve_air_order, shape_order_bindable

    degraded = {
        "plan_status": "degraded",
        "ordered_segment_ids": ["a", "b", "c"],
        "source": "soft_gate",
    }
    ok, ordered, reason = shape_order_bindable(degraded, kept_ids={"a", "b", "c"})
    assert ok is False
    assert reason == "plan_not_complete"
    bind = resolve_air_order(
        mastering_plan=degraded,
        selection_ordered=["c", "b", "a"],
        prefer_shape=True,
    )
    assert bind["order_authority"] == "ranking"
    assert bind["bind_reason"] == "plan_not_complete"

    complete = {
        "plan_status": "complete",
        "ordered_segment_ids": ["a", "b", "c"],
        "source": "llm",
    }
    ok2, ordered2, reason2 = shape_order_bindable(complete, kept_ids={"a", "b", "c"})
    assert ok2 is True
    assert ordered2 == ["a", "b", "c"]
    assert reason2 == "bind_ok"
    bind2 = resolve_air_order(
        mastering_plan=complete,
        selection_ordered=["c", "b", "a"],
        prefer_shape=True,
    )
    assert bind2["order_authority"] == "shape"
    assert bind2["ordered_segment_ids"] == ["a", "b", "c"]


def test_a03_validate_or_degrade_missing_plan_status(
    ctx: RunContext,
) -> None:
    from interview_mux.mastering_plan_loader import validate_or_degrade

    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "version": 1,
            "narrative_mode": "sparse_source",
            "cold_open": {"kind": "none", "rationale": "x", "evidence_refs": [], "confidence": 0.5},
            "pass": "provisional",
        },
    )
    plan = validate_or_degrade(ctx)
    assert plan.get("plan_status") == "degraded"
    assert "missing_plan_status" in list(plan.get("degradation_reasons") or [])
