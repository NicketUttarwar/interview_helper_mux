"""Tests for artifact_sanitize nugget_layup_plan (W2 — refuse-hollow)."""

from __future__ import annotations

from interview_mux.artifact_sanitize.nugget_layup_plan import sanitize_nugget_layup_plan
from interview_mux.run_context import RunContext


def _write_selection(ctx: RunContext, ids: list[str]) -> None:
    ctx.path("master").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ids,
            "excluded_segment_ids": [],
            "chapters": [],
            "order_content_hash": "layup_sel_hash",
        },
        skip_handoff=True,
    )


def test_sanitize_layup_refuses_hollow_empty() -> None:
    ctx = RunContext(create=True)
    _write_selection(ctx, ["seg_001", "seg_002", "seg_003"])
    result = sanitize_nugget_layup_plan(
        ctx,
        {"ordered_segment_ids": [], "layups": [], "status": "ok"},
    )
    assert not result.ok
    assert "empty_layup_plan_with_selection" in result.errors


def test_sanitize_layup_refuses_compose_restart() -> None:
    ctx = RunContext(create=True)
    _write_selection(ctx, ["seg_001"])
    result = sanitize_nugget_layup_plan(
        ctx,
        {
            "compose_restart": True,
            "ordered_segment_ids": ["seg_001"],
            "layups": [
                {"segment_id": "seg_001", "text": "ok"},
            ],
        },
    )
    assert not result.ok
    assert "compose_restart_active" in result.errors


def test_sanitize_layup_needs_recompose_on_order_mismatch() -> None:
    ctx = RunContext(create=True)
    _write_selection(ctx, ["seg_001", "seg_002", "seg_003"])
    result = sanitize_nugget_layup_plan(
        ctx,
        {
            "ordered_segment_ids": ["seg_001"],
            "layups": [{"segment_id": "seg_001", "text": "only one"}],
            "status": "ok",
        },
    )
    assert not result.ok
    assert "layup_order_mismatch_needs_recompose" in result.errors
    meta = result.doc.get("_meta") or {}
    assert meta.get("needs_recompose") is True


def test_sanitize_layup_no_fake_freshness_via_adopt_order_alone() -> None:
    """Aligning order must not silently expand to full selection without recompose."""
    ctx = RunContext(create=True)
    full = ["seg_001", "seg_002", "seg_003", "seg_004"]
    _write_selection(ctx, full)
    before_ids = ["seg_001", "seg_002"]
    result = sanitize_nugget_layup_plan(
        ctx,
        {
            "ordered_segment_ids": list(before_ids),
            "layups": [
                {"segment_id": "seg_001", "text": "a"},
                {"segment_id": "seg_002", "text": "b"},
            ],
            "status": "complete",
        },
    )
    # Must not adopt missing natives into ordered_segment_ids
    assert result.doc.get("ordered_segment_ids") == before_ids
    assert result.doc.get("_meta", {}).get("needs_recompose") is True
    assert not result.ok
