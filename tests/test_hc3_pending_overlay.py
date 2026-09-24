"""HC-3: pending overlay must not hollow-complete a stage.

Reads see leftover pending only while that stage is actively staging.
Pending-only or newer pending than commit stays incomplete.
Do not start a run. Seating pending_only_seating stays.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import (
    promote_complete_orphan_stage_done,
    seed_stage_complete,
)
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    heal_or_refuse_mark,
    stage_artifact_incompleteness,
)
from interview_mux.write_staging import enter_stage_staging, exit_stage_staging
from run_fixtures import isolated_run_ctx, mark_done_raw

_VO_REL = "mastering/vo_synthesize.json"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "hc3_pending")


def _plant_pending_vo(ctx: RunContext, body: str = '{"status":"pending"}') -> Path:
    pending = ctx.run_dir / ".pending_writes" / "vo_synthesize" / "mastering"
    pending.mkdir(parents=True, exist_ok=True)
    dest = pending / "vo_synthesize.json"
    dest.write_text(body, encoding="utf-8")
    return dest


def test_hc3_pending_only_invisible_without_active_stage(ctx: RunContext) -> None:
    _plant_pending_vo(ctx)
    assert ctx.artifact_exists(_VO_REL) is False
    assert ctx.final_path("mastering", "vo_synthesize.json").is_file() is False
    reason = stage_artifact_incompleteness(ctx, "vo_synthesize")
    assert reason is not None
    assert "pending_only" in reason or "pending" in reason
    mark_done_raw(ctx, "vo_synthesize")
    assert seed_stage_complete(ctx, "vo_synthesize") is False
    out = heal_or_refuse_mark(ctx, "vo_synthesize")
    assert out.get("unmarked") is True or not ctx.is_done("vo_synthesize")
    assert promote_complete_orphan_stage_done(ctx, ("vo_synthesize",)) == []
    assert not ctx.is_done("vo_synthesize")


def test_hc3_active_stage_can_read_own_pending(ctx: RunContext) -> None:
    _plant_pending_vo(ctx)
    enter_stage_staging("vo_synthesize")
    try:
        assert ctx.artifact_exists(_VO_REL) is True
        assert ctx.read_json(_VO_REL).get("status") == "pending"
    finally:
        exit_stage_staging()
    assert ctx.artifact_exists(_VO_REL) is False


def test_hc3_newer_pending_blocks_complete(ctx: RunContext) -> None:
    committed = ctx.final_path("mastering", "vo_synthesize.json")
    committed.parent.mkdir(parents=True, exist_ok=True)
    committed.write_text('{"status":"committed"}', encoding="utf-8")
    time.sleep(0.02)
    _plant_pending_vo(ctx, '{"status":"newer"}')
    assert ctx.artifact_exists(_VO_REL) is True
    assert ctx.read_json(_VO_REL).get("status") == "committed"
    reason = stage_artifact_incompleteness(ctx, "vo_synthesize")
    assert reason is not None
    assert "newer uncommitted pending" in reason
    mark_done_raw(ctx, "vo_synthesize")
    assert seed_stage_complete(ctx, "vo_synthesize") is False
    assert promote_complete_orphan_stage_done(ctx, ("vo_synthesize",)) == []
    assert seed_stage_complete(ctx, "vo_synthesize") is False


def test_hc3_committed_only_can_complete(ctx: RunContext) -> None:
    dest = ctx.final_path("mastering", "vo_synthesize.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text('{"status":"committed"}', encoding="utf-8")
    mark_done_raw(ctx, "vo_synthesize")
    reason = stage_artifact_incompleteness(ctx, "vo_synthesize")
    # Other vo incompleteness (coverage) may still fire; pending shadow must not.
    if reason:
        assert "pending_only" not in reason
        assert "newer uncommitted pending" not in reason
    else:
        assert seed_stage_complete(ctx, "vo_synthesize") is True


def test_hc3_content_equal_newer_pending_not_incomplete(ctx: RunContext) -> None:
    """Mirrored commit sync can leave pending mtime newer with identical bytes."""
    from interview_mux.write_staging import uncommitted_pending_reason

    body = '{"status":"sealed","n":1}'
    committed = ctx.final_path("master", "selection.json")
    committed.parent.mkdir(parents=True, exist_ok=True)
    committed.write_text(body, encoding="utf-8")
    time.sleep(0.02)
    pending = ctx.run_dir / ".pending_writes" / "selection_order_sanitize" / "master"
    pending.mkdir(parents=True, exist_ok=True)
    twin = pending / "selection.json"
    twin.write_text(body, encoding="utf-8")
    assert twin.stat().st_mtime_ns > committed.stat().st_mtime_ns
    assert uncommitted_pending_reason(ctx, "master/selection.json") is None


def test_write_committed_under_active_stage_does_not_invent_pending(
    ctx: RunContext,
) -> None:
    """exec_13170: write_committed must not create active-stage pending twin."""
    from interview_mux.write_staging import (
        enter_stage_staging,
        exit_stage_staging,
        uncommitted_pending_reason,
        write_committed_json,
    )

    enter_stage_staging("selection_order_sanitize")
    try:
        (ctx.run_dir / ".pending_writes" / "selection_order_sanitize").mkdir(
            parents=True, exist_ok=True
        )
        write_committed_json(
            ctx,
            "master/selection.json",
            {
                "ordered_segment_ids": ["seg_001"],
                "excluded_segment_ids": [],
                "order_lock": {"revision": 1},
            },
            stage_key="selection_order_sanitize",
        )
        pending = (
            ctx.run_dir
            / ".pending_writes"
            / "selection_order_sanitize"
            / "master"
            / "selection.json"
        )
        assert not pending.is_file()
        assert uncommitted_pending_reason(ctx, "master/selection.json") is None
        assert ctx.final_path("master", "selection.json").is_file()
    finally:
        exit_stage_staging()
