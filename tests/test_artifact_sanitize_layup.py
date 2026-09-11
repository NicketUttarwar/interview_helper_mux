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


def test_sanitize_layup_justified_skips_not_stuffed() -> None:
    """High justified skip ratio must not force endless recompose."""
    ctx = RunContext(create=True)
    ids = [f"seg_{i:03d}" for i in range(1, 11)]
    _write_selection(ctx, ids)
    layups = []
    for i, sid in enumerate(ids):
        if i < 2:
            layups.append(
                {
                    "target_segment_id": sid,
                    "line_id": f"vo_layup_{sid}",
                    "text": f"Host unlocks the next beat for {sid} with a concrete cue.",
                    "skip": False,
                    "target_beat": "beat",
                    "listener_need_entering_T": "need",
                    "forward_unlock": "unlock",
                }
            )
        else:
            layups.append(
                {
                    "target_segment_id": sid,
                    "line_id": f"vo_layup_{sid}",
                    "skip": True,
                    "skip_reason_code": "self_explanatory_native",
                    "compensating_path": "native_self_orients",
                    "target_beat": "beat",
                    "listener_need_entering_T": "need",
                    "forward_unlock": "unlock",
                }
            )
    result = sanitize_nugget_layup_plan(
        ctx,
        {
            "ordered_segment_ids": ids,
            "layups": layups,
            "status": "ok",
            "_meta": {"needs_recompose": True},
        },
    )
    assert "layup_skip_stuffed_needs_recompose" not in result.errors
    assert not (result.doc.get("_meta") or {}).get("needs_recompose")
