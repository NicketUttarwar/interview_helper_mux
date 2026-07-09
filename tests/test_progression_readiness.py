"""Tests for Flow 1 progression readiness report."""

from __future__ import annotations

import pytest

from run_fixtures import isolated_run_ctx, minimal_content_brief, minimal_speakers, populated_analysis_state

from interview_mux.progression_readiness import build_flow1_readiness_report


def test_flow1_readiness_blocked_without_flow_selection(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "readiness_test")
    ctx.write_json("understanding/speakers.json", minimal_speakers(), skip_handoff=True)
    ctx.write_json("understanding/content_brief.json", minimal_content_brief(), skip_handoff=True)
    ctx.write_json("understanding/analysis_state.json", populated_analysis_state(ctx.run_id), skip_handoff=True)
    report = build_flow1_readiness_report(ctx)
    assert report["ready"] is False
    layers = {b["layer"] for b in report["blockers"]}
    assert "gate" in layers or "completeness" in layers or "cross" in layers


def test_flow1_readiness_includes_layer_on_blockers(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "readiness_layers")
    report = build_flow1_readiness_report(ctx)
    for b in report.get("blockers") or []:
        assert "layer" in b
        assert "message" in b
