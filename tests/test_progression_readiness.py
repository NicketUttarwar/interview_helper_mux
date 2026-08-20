"""Tests for Flow 1 progression readiness report."""

from __future__ import annotations

import pytest

from run_fixtures import isolated_run_ctx, minimal_content_brief, minimal_speakers, populated_analysis_state

from interview_mux.progression_readiness import build_delivery_readiness_report


def test_flow1_readiness_blocked_without_profile(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "readiness_test")
    ctx.write_json("understanding/speakers.json", minimal_speakers(), skip_handoff=True)
    ctx.write_json("understanding/content_brief.json", minimal_content_brief(), skip_handoff=True)
    ctx.write_json("understanding/analysis_state.json", populated_analysis_state(ctx.run_id), skip_handoff=True)
    report = build_delivery_readiness_report(ctx)
    assert report["ready"] is False
    layers = {b["layer"] for b in report["blockers"]}
    assert "gate" in layers or "completeness" in layers or "cross" in layers


def test_flow1_readiness_includes_layer_on_blockers(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "readiness_layers")
    report = build_delivery_readiness_report(ctx)
    for b in report.get("blockers") or []:
        assert "layer" in b
        assert "message" in b


def test_no_g1_blocker_when_gap_fill_skipped(tmp_path):
    from interview_mux.stages.gaps import ensure_gap_fill_skipped

    ctx = isolated_run_ctx(tmp_path, "readiness_gap_skip")
    ensure_gap_fill_skipped(ctx, reason="test", signals={})
    report = build_delivery_readiness_report(ctx)
    gate_ids = [b.get("id") for b in report.get("blockers") or [] if b.get("layer") == "gate"]
    assert "g1_vo_pickup" not in gate_ids


def test_invisible_staging_does_not_block_delivery_readiness(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "readiness_invisible_staging")
    staging = (
        ctx.run_dir
        / ".pending_writes"
        / "topic_coverage_audit"
        / "understanding"
    )
    staging.mkdir(parents=True)
    (staging / "context_index.json").write_text('{"volley_entries": [], "meta": {}}', encoding="utf-8")

    report = build_delivery_readiness_report(ctx, target_stage="topic_coverage_audit")
    blocker_ids = [b.get("id") for b in report.get("blockers") or []]
    assert "pending_write_approval" not in blocker_ids


def test_operator_visible_staging_blocks_delivery_readiness(tmp_path, monkeypatch):
    from run_fixtures import patch_write_approval_enabled

    patch_write_approval_enabled(monkeypatch, enabled=True)
    monkeypatch.setattr(
        "interview_mux.write_staging.all_pending_stages",
        lambda ctx, savable_only=True: ["topic_coverage_audit"],
    )
    ctx = isolated_run_ctx(tmp_path, "readiness_visible_staging")
    report = build_delivery_readiness_report(ctx, target_stage="topic_coverage_audit")
    assert any(b.get("id") == "pending_write_approval" for b in report.get("blockers") or [])


def test_leftover_pending_writes_do_not_block_when_write_approval_off(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "readiness_leftover_pending")
    staging = ctx.run_dir / ".pending_writes" / "narrative_arc_plan" / "master"
    staging.mkdir(parents=True)
    (staging / "narrative_plan.json").write_text('{"beats": []}', encoding="utf-8")

    report = build_delivery_readiness_report(ctx, target_stage="topic_coverage_audit")
    blocker_ids = [b.get("id") for b in report.get("blockers") or []]
    assert "pending_write_approval" not in blocker_ids


def test_context_index_sync_under_staging_does_not_block_delivery(tmp_path):
    from interview_mux.analysis_memory import ensure_analysis_workspace
    from interview_mux.write_staging import enter_stage_staging, exit_stage_staging

    ctx = isolated_run_ctx(tmp_path, "readiness_context_index_staging")
    committed = ctx.run_dir / "understanding" / "context_index.json"
    committed.parent.mkdir(parents=True, exist_ok=True)
    committed.write_text(
        '{"schema_version":2,"run_id":"readiness_context_index_staging","volley_entries":[],"stage_plans":{},"padding_rules":{},"meta":{}}',
        encoding="utf-8",
    )
    enter_stage_staging("topic_coverage_audit")
    try:
        ensure_analysis_workspace(ctx)
        report = build_delivery_readiness_report(ctx, target_stage="topic_coverage_audit")
        assert not any(
            b.get("id") == "pending_write_approval" for b in report.get("blockers") or []
        )
        pending = ctx.run_dir / ".pending_writes" / "topic_coverage_audit"
        assert not (pending / "understanding" / "context_index.json").is_file()
    finally:
        exit_stage_staging()
