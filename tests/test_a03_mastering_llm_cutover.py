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


def test_a03_research_routing_llm_fail_refuses_heal(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CSP-05 / MRR: LLM fail → diagnostic stub + refuse (not heal-done)."""
    from interview_mux.llm_simple import StageError
    from interview_mux.stage_completion import stage_artifact_incompleteness

    monkeypatch.setattr(
        "interview_mux.mastering_research.research_llm_enabled",
        lambda: True,
    )
    logs: list[dict] = []

    def _boom(*_a, **_k):
        raise RuntimeError("forced_routing_llm_fail")

    def _capture_log(msg, **kwargs):
        logs.append({"msg": msg, **kwargs})

    monkeypatch.setattr(
        "interview_mux.mastering_llm.invoke_mastering_prompt",
        _boom,
    )
    monkeypatch.setattr(ctx, "log", _capture_log)
    with pytest.raises(StageError, match="hollow/invalid OpenAI primary"):
        run_mastering_research_routing(ctx)
    routing = ctx.read_json("mastering/research/routing.json")
    assert routing.get("source") == "stub"
    assert routing.get("llm_failed") is True
    assert routing.get("skipped") == "llm_failed"
    assert routing.get("authoritative") is False
    assert routing.get("fields") == []
    assert "invoke_exception" in str(routing.get("fail_reason") or "")
    assert any(
        e.get("action_id") == "mastering_research_routing.llm_failed" for e in logs
    )
    assert not ctx.is_done("mastering_research_routing")
    reason = stage_artifact_incompleteness(ctx, "mastering_research_routing")
    assert reason and (
        "llm_failed" in reason
        or "OpenAI primary" in reason
        or "invoke_exception" in reason
    )


def test_a03_research_routing_llm_hollow_arts_refuses_heal(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CSP-05 / MRR: null/unusable LLM arts → refuse heal-done."""
    from interview_mux.llm_simple import StageError

    monkeypatch.setattr(
        "interview_mux.mastering_research.research_llm_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "interview_mux.mastering_llm.invoke_mastering_prompt",
        lambda *_a, **_k: {"fields": []},
    )
    with pytest.raises(StageError, match="hollow/invalid OpenAI primary"):
        run_mastering_research_routing(ctx)
    routing = ctx.read_json("mastering/research/routing.json")
    assert routing.get("llm_failed") is True
    assert routing.get("fail_reason") == "invalid_or_empty_llm_artifacts"
    assert routing.get("source") == "stub"
    assert not ctx.is_done("mastering_research_routing")


def test_msa_b1_rubric_llm_fail_incomplete(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CSP-05 / MSA-B1: agenda LLM ok + rubric hollow → incomplete (no soft heal)."""
    from interview_mux.llm_simple import StageError
    from interview_mux.stage_completion import stage_artifact_incompleteness

    monkeypatch.setattr(
        "interview_mux.mastering_shape_runtime.shape_llm_enabled",
        lambda _cfg=None: True,
    )
    monkeypatch.setattr(
        "interview_mux.mastering_shape_runtime.soft_gate_enabled",
        lambda: True,
    )

    def _fake_invoke(_ctx, stage_key, prompt_rel, user_payload, *, max_attempts=2):
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
            return {"version": 1}  # hollow — no criteria/style_axes
        return {}

    monkeypatch.setattr(
        "interview_mux.mastering_llm.invoke_mastering_prompt",
        _fake_invoke,
    )
    with pytest.raises(StageError, match="rubric_llm_failed"):
        run_mastering_shape_agenda(ctx)
    agenda = ctx.read_json("mastering/shape/agenda.json")
    rubric = ctx.read_json("mastering/shape/eval_rubric.json")
    assert agenda.get("source") == "llm"
    assert "rubric_llm_failed" in (rubric.get("notes") or [])
    assert not ctx.is_done("mastering_shape_agenda")
    reason = stage_artifact_incompleteness(ctx, "mastering_shape_agenda")
    assert reason and "rubric_llm_failed" in reason


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


def test_shape_llm_fail_refuses_incomplete(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CSP-05 / MSA: shape.llm on + hollow invoke → StageError incomplete (no soft degrade heal)."""
    from interview_mux.llm_simple import StageError

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
    with pytest.raises(StageError, match="hollow/invalid OpenAI primary"):
        run_mastering_shape_agenda(ctx)
    assert not ctx.is_done("mastering_shape_agenda")
    defaults = json.loads(Path("config/app.defaults.json").read_text(encoding="utf-8"))
    assert defaults["mastering"]["shape"]["soft_gate"]["consumers_bind"] is False
    assert defaults["mastering"]["research"]["llm"]["enabled"] is False
    assert defaults["mastering"]["shape"]["llm"]["enabled"] is True  # Q6B
    assert consumers_bind_enabled() is False


def test_msc_b2_shape_llm_hollow_refuses_no_heuristic(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MSC-B2: shape.llm on + hollow candidates → StageError (no heuristic heal-done)."""
    from interview_mux.llm_simple import StageError

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
    # Seed a valid agenda so candidates is the stage under test.
    ctx.write_json(
        "mastering/shape/agenda.json",
        {
            "version": 1,
            "pass": "provisional",
            "source": "heuristic",
            "mode_candidates": ["conversational_host"],
            "steps": [{"step_id": "compete", "goal": "best listen"}],
            "budgets": {"max_steps": 1, "max_prompt_edits": 0, "max_flagship_calls": 0},
            "north_star_pillars": ["finishability"],
            "generated_at": "2026-01-01T00:00:00+00:00",
        },
        stage_key="mastering_shape_agenda",
    )
    with pytest.raises(StageError, match="hollow/invalid OpenAI primary"):
        run_mastering_shape_candidates(ctx)
    assert not ctx.is_done("mastering_shape_candidates")


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
    """Soft-gate never claims complete; Q6B defaults may enable shape.llm."""
    from interview_mux.mastering_plan_loader import (
        consumers_bind_enabled,
        research_llm_enabled,
        shape_llm_enabled,
        soft_gate_may_claim_complete,
    )
    from interview_mux.mastering_research import run_research_rollup

    assert research_llm_enabled() is False
    assert shape_llm_enabled() is True  # Q6B default on
    assert consumers_bind_enabled() is False
    assert soft_gate_may_claim_complete() is False

    # Soft-gate path only when shape.llm is forced off — prove it stays degraded.
    monkeypatch.setattr(
        "interview_mux.mastering_plan_loader.shape_llm_enabled",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "interview_mux.mastering_shape_runtime.shape_llm_enabled",
        lambda *_a, **_k: False,
    )

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
    assert reason2 in ("bind_ok", "air_script_bind")
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


def test_mps_lint_rejects_hollow_plan_shell() -> None:
    from interview_mux.mastering_shape_runtime import _plan_from_llm_artifacts

    assert (
        _plan_from_llm_artifacts(
            {
                "version": 1,
                "narrative_mode": "not_a_real_mode",
                "cold_open": {"kind": "none"},
                "bespoke_rationale": "x",
            },
            pass_name="provisional",
            evidence_hash="abc",
        )
        is None
    )
    assert (
        _plan_from_llm_artifacts(
            {
                "version": 1,
                "narrative_mode": "sparse_source",
                "cold_open": {"kind": "none"},
                "decisions": [],
                "bespoke_rationale": "",
            },
            pass_name="provisional",
            evidence_hash="abc",
        )
        is None
    )
    ok = _plan_from_llm_artifacts(_minimal_valid_plan(), pass_name="provisional", evidence_hash="abc")
    assert ok is not None
    assert ok.get("source") == "llm"
    assert ok.get("montage_grammar") == []


def test_mps_llm_hollow_soft_degrades_not_complete(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Honesty: weak LLM plan → soft_gate degraded, never complete."""
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
        lambda *_a, **_k: {
            "version": 1,
            "narrative_mode": "sparse_source",
            "cold_open": {"kind": "none"},
            "bespoke_rationale": "",
            "decisions": [],
        },
    )
    ctx.write_json(
        "mastering/shape/candidates.json",
        {
            "version": 1,
            "candidates": [
                {
                    "candidate_id": "cand_0",
                    "narrative_mode": "sparse_source",
                    "rationale": "fallback",
                }
            ],
            "generated_at": "2026-01-01T00:00:00+00:00",
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/content_brief.json",
        {"thesis": "t", "topics": [{"name": "a", "summary": "b"}]},
        skip_handoff=True,
    )
    run_mastering_plan_synthesize(ctx)
    plan = ctx.read_json("mastering/mastering_plan.json")
    assert plan.get("plan_status") == "degraded"
    assert plan.get("source") == "soft_gate"
    assert "llm_failed" in list(plan.get("degradation_reasons") or [])


def test_shape_payload_slims_evidence_inlines(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.mastering_shape_runtime import _shape_llm_user_payload

    monkeypatch.setattr(
        "interview_mux.mastering_shape_runtime.compile_shape_evidence",
        lambda *_a, **_k: {
            "items": [
                {
                    "ref": "segments/manifest.json",
                    "kind": "artifact",
                    "salience": 0.65,
                    "inline": {
                        "segments": [
                            {"segment_id": f"seg_{i}", "text": "word " * 80}
                            for i in range(60)
                        ]
                    },
                }
            ],
            "omitted": [],
            "token_estimate": 9999,
        },
    )
    payload = _shape_llm_user_payload(
        ctx, consumer_id="shape_synthesize_pass1", pass_name="provisional"
    )
    items = payload["evidence"]["items"]
    assert items
    inline = items[0]["inline"]
    assert inline.get("segment_count") == 60
    assert len(inline.get("segments") or []) <= 40
    assert all(len(str(s.get("text") or "")) <= 160 for s in inline["segments"])


def test_precedence_requires_authoritative_complete() -> None:
    from interview_mux.mastering_plan_loader import precedence_ordered_segment_ids

    degraded = {
        "plan_status": "degraded",
        "ordered_segment_ids": ["a", "b", "c"],
    }
    # Even if consumers_bind were on, degraded must not win over selection.
    import interview_mux.mastering_plan_loader as mpl

    prev = mpl.consumers_bind_enabled
    try:
        mpl.consumers_bind_enabled = lambda _cfg=None: True  # type: ignore[assignment]
        out = precedence_ordered_segment_ids(
            plan=degraded,
            nle_ordered=None,
            selection_ordered=["x", "y"],
        )
        assert out == ["x", "y"]
        complete = {
            "plan_status": "complete",
            "ordered_segment_ids": ["a", "b", "c"],
        }
        out2 = precedence_ordered_segment_ids(
            plan=complete,
            nle_ordered=None,
            selection_ordered=["x", "y"],
        )
        assert out2 == ["a", "b", "c"]
    finally:
        mpl.consumers_bind_enabled = prev  # type: ignore[assignment]


def test_msa_prompt_shaped_agenda_ingests_not_hollow(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cascade (MUX_FORENSICS=0): prompt-shaped meta-architect JSON must ingest.

    exec_13157: LLM returned mastering_shape_agenda with levels={run:[…]} and
    ordered_custom_steps — lint treated it as agenda_llm_hollow and thrash-spun.
    """
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.mastering_shape_runtime import _agenda_from_llm
    from interview_mux.prompt_validation import validate_mastering_shape_agenda

    prompt_shaped = {
        "mastering_shape_agenda": {
            "levels": {
                "run": ["narrative_mode", "cold_open", "montage_grammar"],
                "skip": ["template five-act checklists"],
                "deepen": ["bespoke_rationale"],
            },
            "ordered_custom_steps": [
                {"step": "Define narrative mode", "goal": "Establish style."},
                {"step": "Identify cold open", "goal": "Hook the listener."},
            ],
            "anti_patterns": ["Overly generic introductions"],
            "system_prompt_draft_seeds": {
                "excellence_pillars": ["Engaging narrative", "Clear content"]
            },
            "budgets": {"max_steps": 5, "max_prompt_edits": 3, "max_flagship_calls": 2},
        }
    }
    agenda = _agenda_from_llm(prompt_shaped)
    assert agenda is not None, "prompt-shaped agenda must not be treated as hollow"
    assert agenda["source"] == "llm"
    assert agenda["levels"]["narrative_mode"] == "run"
    assert agenda["levels"]["template five-act checklists"] == "skip"
    assert any(s["step_id"] == "Define narrative mode" for s in agenda["steps"])
    assert "Engaging narrative" in agenda["north_star_pillars"]
    assert validate_mastering_shape_agenda(agenda) == []

    monkeypatch.setattr(
        "interview_mux.mastering_shape_runtime.shape_llm_enabled",
        lambda _cfg=None: True,
    )
    monkeypatch.setattr(
        "interview_mux.mastering_shape_runtime.soft_gate_enabled",
        lambda: True,
    )
    calls = {"n": 0}

    def _fake_invoke(_ctx, stage_key, prompt_rel, user_payload, *, max_attempts=2):
        calls["n"] += 1
        if "meta-architect" in prompt_rel:
            return prompt_shaped
        if "eval-rubric" in prompt_rel:
            return {
                "criteria": [
                    {
                        "criterion_id": "finish",
                        "description": "finishable",
                        "weight": 1.0,
                    }
                ],
                "style_axes": [{"axis": "clarity", "value": "high"}],
            }
        return {}

    monkeypatch.setattr(
        "interview_mux.mastering_llm.invoke_mastering_prompt",
        _fake_invoke,
    )
    ctx.write_json(
        "understanding/content_brief.json",
        {"thesis": "t", "topics": [{"name": "a", "summary": "b"}]},
    )
    run_mastering_shape_agenda(ctx)
    assert ctx.is_done("mastering_shape_agenda")
    assert ctx.artifact_exists("mastering/shape/agenda.json")
    assert calls["n"] >= 2


def test_msa_rubric_payload_rejects_shape_plan_body(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cascade (MUX_FORENSICS=0): rubric invoke must not inherit agenda response_contract.

    exec_13157: shared Shape payload asked for plan/agenda → model returned
    mastering_shape; rubric_llm_failed thrash.
    """
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.mastering_shape_runtime import (
        _rubric_from_llm,
        _shape_llm_user_payload,
    )

    assert _rubric_from_llm({"mastering_shape": {"narrative_mode": "run"}}) is None
    ok = _rubric_from_llm(
        {
            "mastering_eval_rubric": {
                "style_axes": [{"axis": "technical_density", "value": "high"}],
                "criteria": [
                    {
                        "criterion_id": "finishability",
                        "description": "finishable listen",
                        "weight": 1.0,
                    }
                ],
            }
        }
    )
    assert ok is not None and ok["source"] == "llm"
    assert ok["criteria"][0]["criterion_id"] == "finishability"

    payload = _shape_llm_user_payload(
        ctx, consumer_id="shape_agenda_pass1", pass_name="provisional", artifact="rubric"
    )
    assert payload["artifact"] == "rubric"
    assert payload["response_contract"]["required_artifact"] == "mastering_eval_rubric"
    assert "mastering_shape" in payload["response_contract"]["forbid"]
    assert "Produce the best bespoke mastering shape agenda" not in payload["goal"]


def test_msa_rubric_contract_response_format_inlines_defs(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cascade (MUX_FORENSICS=0): rubric response_format must not raise on $ref items.

    exec_13159: _contract_response_format(mastering_eval_rubric) hit OpenAI strict
    lint on style_axes/criteria/anti_patterns $ref → MSA hollow ValueError thrash.
    """
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.mastering_llm import _contract_response_format
    from interview_mux.openai_schema_lint import lint_openai_strict_schema
    from interview_mux.openai_structured_output import load_schema_file

    load_schema_file.cache_clear()
    fmt = _contract_response_format(
        "mastering_eval_rubric", "mastering_eval_rubric.schema.json"
    )
    schema = fmt["json_schema"]["schema"]
    assert lint_openai_strict_schema(schema) == []
    blob = json.dumps(schema)
    assert "$ref" not in blob
    items = schema["properties"]["artifacts"]["properties"]["mastering_eval_rubric"][
        "properties"
    ]["criteria"]["items"]
    assert "properties" in items and "criterion_id" in items["properties"]


def test_msc_candidates_payload_uses_candidates_contract(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cascade (MUX_FORENSICS=0): candidates invoke must not inherit agenda contract.

    exec_13157: default artifact=agenda → model returned mastering_shape_agenda →
    candidates_llm_hollow thrash.
    """
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.mastering_shape_runtime import (
        _candidates_from_llm,
        _shape_llm_user_payload,
    )

    assert _candidates_from_llm({"mastering_shape_agenda": {"mode_candidates": ["a"]}}) is None
    ok = _candidates_from_llm(
        {
            "mastering_shape_candidates": {
                "version": 1,
                "pass": "provisional",
                "candidates": [
                    {
                        "candidate_id": "c1",
                        "narrative_mode": "conversational_host",
                        "rationale": "fit",
                    }
                ],
            }
        }
    )
    assert ok is not None and ok["source"] == "llm"

    payload = _shape_llm_user_payload(
        ctx,
        consumer_id="shape_candidates_pass1",
        pass_name="provisional",
        artifact="candidates",
    )
    assert payload["artifact"] == "candidates"
    assert payload["response_contract"]["required_artifact"] == "mastering_shape_candidates"
