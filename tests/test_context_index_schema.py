import json
from pathlib import Path

import pytest

from interview_mux.analysis_memory import ensure_analysis_workspace
from interview_mux.context_resolver import (
    append_stage_conclusion,
    append_volley_entry,
    context_index_enabled,
    load_context_index,
    migrate_context_index_v1_to_v2,
    prefer_index_over_legacy,
    select_entries_for_stage,
)
from interview_mux.prompt_validation import validate_context_index
from interview_mux.stage_input_helpers import STAGE_PLANS, plan_for_stage
from interview_mux.run_context import RunContext
from run_fixtures import mark_done_raw


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "minimal_run"
RUN_ID = "exec_001_a1b2c3d4e5f6_20260601T120000Z"


@pytest.fixture
def minimal_ctx(tmp_path):
    import shutil

    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, RUN_ID)
    shutil.copytree(FIXTURE, ctx.run_dir, dirs_exist_ok=True)
    return ctx


def test_migrate_context_index_v1_to_v2():
    v1 = {"schema_version": 1, "run_id": "x", "padding_rules": {"max_user_json_chars": 96000}}
    v2 = migrate_context_index_v1_to_v2(v1, "x")
    assert v2["schema_version"] == 2
    assert "volley_entries" in v2
    assert "artifacts_registry" in v2


def test_validate_context_index_empty():
    doc = migrate_context_index_v1_to_v2({}, "run")
    doc["stage_plans"] = {"speaker_roles": {"prior_stages": []}}
    errors = validate_context_index(doc)
    assert not errors


def test_append_and_supersede_stage_conclusion(minimal_ctx, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_CONFIG", str(Path(__file__).resolve().parents[1] / "config"))
    append_stage_conclusion(
        minimal_ctx,
        stage_key="content_context",
        attempt=1,
        reasoning_summary="First pass summary.",
    )
    append_stage_conclusion(
        minimal_ctx,
        stage_key="content_context",
        attempt=2,
        reasoning_summary="Second pass summary.",
    )
    idx = load_context_index(minimal_ctx, write=False)
    active = [
        e
        for e in idx["volley_entries"]
        if e["kind"] == "stage_conclusion" and e["source"]["stage_key"] == "content_context"
    ]
    assert any(e["status"] == "active" for e in active)
    assert any(e["status"] == "superseded" for e in active)


def test_select_entries_for_stage(minimal_ctx):
    append_volley_entry(
        minimal_ctx,
        {
            "kind": "stage_conclusion",
            "role": "assistant",
            "content": "Boundary: 12 segments proposed.",
            "source": {"stage_key": "boundary_detection", "attempt": 1},
        },
    )
    idx = load_context_index(minimal_ctx, write=False)
    selected = select_entries_for_stage(
        idx,
        stage_key="segment_classification",
        prior_stages=("boundary_detection",),
        profile="full",
        task_kind="primary",
        investigation_kinds=frozenset(),
        max_investigations=0,
    )
    kinds = {e["kind"] for e in selected}
    assert "stage_conclusion" in kinds


def test_stage_plans_parity_with_index(minimal_ctx):
    ensure_analysis_workspace(minimal_ctx)
    idx = load_context_index(minimal_ctx, write=False)
    assert set(STAGE_PLANS.keys()) == set(idx.get("stage_plans") or {})


def test_plan_for_stage_returns_empty_default():
    """v2 has no per-stage volley plans; every lookup yields the neutral default."""
    plan = plan_for_stage("topic_coverage_audit")
    assert plan.prior_stages == ()
    assert plan.max_investigations == 0


def test_apply_envelope_writes_volley_entry(minimal_ctx):
    from interview_mux.analysis_memory import apply_envelope_to_memory
    from run_fixtures import minimal_content_brief

    minimal_ctx.write_json(
        "understanding/content_brief.json",
        minimal_content_brief(),
        skip_handoff=True,
    )
    mark_done_raw(minimal_ctx, "content_context")

    apply_envelope_to_memory(
        minimal_ctx,
        "content_context",
        {
            "status": "complete",
            "reasoning_summary": "Accepted thesis and topics.",
            "memory_updates": {"themes_append": [{"id": "t1", "label": "AI"}]},
            "needs": [],
            "follow_up_investigations": [],
        },
        arbiter_result={"verdict": "accept"},
    )
    idx = load_context_index(minimal_ctx, write=False)
    kinds = [e.get("kind") for e in idx.get("volley_entries") or []]
    assert "stage_conclusion" in kinds


def test_invalidate_stage_summaries_clears_index(minimal_ctx):
    from interview_mux.artifact_cross_validate import invalidate_stage_summaries

    append_stage_conclusion(
        minimal_ctx,
        stage_key="content_context",
        attempt=1,
        reasoning_summary="To invalidate.",
    )
    invalidate_stage_summaries(minimal_ctx, ("content_context",))
    idx = load_context_index(minimal_ctx, write=False)
    for e in idx["volley_entries"]:
        if (e.get("source") or {}).get("stage_key") == "content_context":
            assert e["status"] == "invalidated"
