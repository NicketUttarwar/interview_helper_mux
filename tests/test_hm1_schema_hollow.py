"""HM-1: research/shape cannot hollow-complete on {} or illegal schema.

Routing skip stub is schema-valid (mode off/advisory, fields: []). Heuristic
agenda maps onto steps/budgets/north_star_pillars. Heal refuses a hollow marker.

Do not start a run. HM-2 shape-core thin pin and HM-3 soft-plan bind stay.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.homunculus.agenda import skip_stage, stage_outputs_present
from interview_mux.mastering_research import (
    run_mastering_research_routing,
    run_mastering_research_waves,
    run_research_rollup,
)
from interview_mux.mastering_shape_runtime import (
    ensure_schema_agenda,
    run_mastering_shape_agenda,
    run_mastering_shape_candidates,
)
from interview_mux.prompt_validation import (
    validate_mastering_research_routing,
    validate_mastering_shape_agenda,
)
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    heal_or_refuse_mark,
    parse_resume_stage_from_reason,
    stage_artifact_incompleteness,
)
from run_fixtures import isolated_run_ctx, mark_done_raw

_ROUTING = "mastering_research_routing"
_WAVES = "mastering_research_waves"
_ROLLUP = "mastering_research_rollup"
_AGENDA = "mastering_shape_agenda"
_CAND = "mastering_shape_candidates"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hm1_schema")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _plant_json(ctx: RunContext, rel: str, text: str) -> None:
    dest = ctx.final_path(*rel.split("/"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")


def test_hm1_missing_routing_is_incomplete(ctx: RunContext) -> None:
    mark_done_raw(ctx, _ROUTING)
    reason = stage_artifact_incompleteness(ctx, _ROUTING)
    assert reason is not None
    assert "pending" in reason
    assert parse_resume_stage_from_reason(reason) == _ROUTING
    assert stage_outputs_present(ctx, _ROUTING) is False
    assert seed_stage_complete(ctx, _ROUTING) is False
    out = heal_or_refuse_mark(ctx, _ROUTING)
    assert out.get("unmarked") is True or not ctx.is_done(_ROUTING)


def test_hm1_empty_routing_is_schema_hollow(ctx: RunContext) -> None:
    _plant_json(ctx, "mastering/research/routing.json", "{}")
    reason = stage_artifact_incompleteness(ctx, _ROUTING)
    assert reason is not None
    assert "schema-hollow" in reason
    mark_done_raw(ctx, _ROUTING)
    out = heal_or_refuse_mark(ctx, _ROUTING)
    assert out.get("unmarked") is True or not ctx.is_done(_ROUTING)


def test_hm1_sequential_waves_is_schema_hollow(ctx: RunContext) -> None:
    _plant_json(
        ctx,
        "mastering/research/routing.json",
        '{"version": 1, "mode": "sequential_waves", "generated_at": "2026-01-01T00:00:00Z"}',
    )
    reason = stage_artifact_incompleteness(ctx, _ROUTING)
    assert reason is not None
    assert "schema-hollow" in reason
    assert seed_stage_complete(ctx, _ROUTING) is False


def test_hm1_routing_stub_is_schema_valid_and_marks(ctx: RunContext) -> None:
    run_mastering_research_routing(ctx)
    routing = ctx.read_json("mastering/research/routing.json")
    assert routing.get("mode") in {"off", "advisory", "authoritative"}
    assert routing.get("fields") == []
    assert routing.get("source") == "stub"
    assert validate_mastering_research_routing(routing) == []
    assert ctx.is_done(_ROUTING)
    assert stage_artifact_incompleteness(ctx, _ROUTING) is None
    assert seed_stage_complete(ctx, _ROUTING) is True


def test_hm1_waves_and_rollup_write_schema_and_mark(ctx: RunContext) -> None:
    run_mastering_research_waves(ctx)
    run_research_rollup(ctx)
    waves = ctx.read_json("mastering/research/waves.json")
    assert isinstance(waves.get("waves"), list)
    assert ctx.is_done(_WAVES)
    rollup = ctx.read_json("mastering/research/rollup.json")
    assert isinstance(rollup.get("fields"), dict)
    assert isinstance(rollup.get("field_reports"), list)
    assert isinstance(rollup.get("salience_map"), dict)
    assert ctx.is_done(_ROLLUP)
    assert stage_artifact_incompleteness(ctx, _ROLLUP) is None


def test_hm1_empty_agenda_is_schema_hollow(ctx: RunContext) -> None:
    _plant_json(ctx, "mastering/shape/agenda.json", "{}")
    reason = stage_artifact_incompleteness(ctx, _AGENDA)
    assert reason is not None
    assert "schema-hollow" in reason
    mark_done_raw(ctx, _AGENDA)
    out = heal_or_refuse_mark(ctx, _AGENDA)
    assert out.get("unmarked") is True or not ctx.is_done(_AGENDA)


def test_hm1_heuristic_agenda_maps_schema_and_marks(ctx: RunContext) -> None:
    run_mastering_shape_agenda(ctx)
    agenda = ctx.read_json("mastering/shape/agenda.json")
    assert agenda.get("steps")
    assert agenda.get("budgets", {}).get("max_steps")
    assert agenda.get("north_star_pillars")
    assert agenda.get("mode_candidates")  # kept for candidates heuristic
    assert validate_mastering_shape_agenda(agenda) == []
    assert ctx.is_done(_AGENDA)
    assert seed_stage_complete(ctx, _AGENDA) is True


def test_hm1_ensure_schema_agenda_fills_missing_keys() -> None:
    out = ensure_schema_agenda(
        {"version": 1, "mode_candidates": ["sparse_source"], "custom_steps": [{"id": "a", "goal": "g"}]}
    )
    assert out["steps"] == [{"step_id": "a", "goal": "g"}]
    assert out["budgets"]["max_steps"] >= 1
    assert out["north_star_pillars"]
    assert validate_mastering_shape_agenda(out) == []


def test_hm1_candidates_heuristic_marks(ctx: RunContext) -> None:
    run_mastering_shape_agenda(ctx)
    run_mastering_shape_candidates(ctx)
    doc = ctx.read_json("mastering/shape/candidates.json")
    assert isinstance(doc.get("candidates"), list)
    assert ctx.is_done(_CAND)
    assert stage_artifact_incompleteness(ctx, _CAND) is None


def test_hm1_skip_without_routing_refused(ctx: RunContext) -> None:
    with pytest.raises(RuntimeError, match="cannot skip"):
        skip_stage(ctx, _ROUTING, reason="conductor whim")
    assert not ctx.is_done(_ROUTING)


def test_hm1_provisional_plan_does_not_complete_confirm(ctx: RunContext) -> None:
    _plant_json(
        ctx,
        "mastering/mastering_plan.json",
        '{"version": 1, "pass": "provisional", "plan_status": "complete", "narrative_mode": "sparse_source"}',
    )
    mark_done_raw(ctx, "mastering_plan_confirm")
    reason = stage_artifact_incompleteness(ctx, "mastering_plan_confirm")
    assert reason is not None
    assert "confirm-hollow" in reason
    out = heal_or_refuse_mark(ctx, "mastering_plan_confirm")
    assert out.get("unmarked") is True or not ctx.is_done("mastering_plan_confirm")


def test_hm1_confirmed_plan_completes_confirm(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.stage_completion._research_thin_late_refuse",
        lambda *_a, **_k: None,
    )
    _plant_json(
        ctx,
        "mastering/mastering_plan.json",
        '{"version": 1, "pass": "confirmed", "confirmed_mode": "sparse_source", "plan_status": "complete"}',
    )
    assert stage_artifact_incompleteness(ctx, "mastering_plan_confirm") is None
    out = heal_or_refuse_mark(ctx, "mastering_plan_confirm")
    assert ctx.is_done("mastering_plan_confirm") or out.get("marked") is True
