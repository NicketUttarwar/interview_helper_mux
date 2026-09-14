"""Wave 9 — residual SSOT + F-01/F-04/F-05 behavioral Done-when proofs."""

from __future__ import annotations

import json

import pytest

from interview_mux.delivery_guardrails import (
    critical_residual_view,
    has_critical_residuals,
    record_delivery_residual,
    ship_path_ready,
)
from interview_mux.listen_delight import _cut_integrity
from interview_mux.post_master_quality import evaluate_post_master_quality
from interview_mux.publishability_boundary import validate_publishability
from interview_mux.stage_completion import stage_artifact_incompleteness
from run_fixtures import (
    isolated_run_ctx,
    mark_done_raw,
    minimal_manifest,
    minimal_manifest_segment,
    sound_design_plan_with,
)


def _write_raw(ctx, rel: str, payload: dict) -> None:
    path = ctx.run_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _ship_ready_fixture(ctx, monkeypatch) -> None:
    asm = ctx.path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(b"RIFF" + b"\x00" * 4096)
    mark_done_raw(ctx, "mix")
    mark_done_raw(ctx, "listen_delight_audit")
    mark_done_raw(ctx, "junction_snip_qa")
    delight = ctx.path("mastering", "listen_delight_audit.json")
    delight.parent.mkdir(parents=True, exist_ok=True)
    delight.write_text(json.dumps({"status": "complete", "passed": True}), encoding="utf-8")
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda.assembly_stale_versus_edl",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.homunculus.agenda._junction_commitment_matches_assembly",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.seed_stage_complete",
        lambda _ctx, sid: sid in {"mix", "junction_snip_qa", "listen_delight_audit"},
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.listen_delight_cleared_for_progress",
        lambda _ctx: True,
    )


# ---------------------------------------------------------------------------
# F-01
# ---------------------------------------------------------------------------


def test_f01_quality_eval_exception_skips_boundary_write(tmp_path, monkeypatch):
    """F-01: evaluate_boundary_quality raise → no boundaries write, skip reason."""
    from interview_mux.ideal_cuts import (
        BOUNDARIES_REL,
        IDEAL_CUTS_REL,
        MATERIALIZED_REL,
        run_ideal_cuts_materialize,
    )

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "f01_eval_raise")
    ctx.write_json(
        IDEAL_CUTS_REL,
        {
            "cuts": [
                {
                    "cut_id": "c1",
                    "talking_point_id": "tp_1",
                    "start_ms": 0,
                    "end_ms": 5000,
                    "priority": "must_keep",
                    "rationale": "f01 fixture",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                {"word": "hello", "start_ms": 0, "end_ms": 400},
                {"word": "world", "start_ms": 450, "end_ms": 900},
            ]
        },
        skip_handoff=True,
    )
    # Pre-seed ideal-cuts-authored boundaries so the unlink path is exercised.
    _write_raw(
        ctx,
        BOUNDARIES_REL,
        {
            "boundaries": [
                {
                    "segment_id": "seg_001",
                    "start_ms": 0,
                    "end_ms": 5000,
                    "proposed_split_reason": "ideal_cut",
                }
            ],
            "_meta": {
                "segment_contract": {
                    "publisher_stage": "ideal_cuts_materialize",
                    "timeline_valid": True,
                    "segment_count": 1,
                }
            },
        },
    )
    monkeypatch.setattr(
        "interview_mux.ideal_cuts.snap_ideal_cuts",
        lambda *a, **k: {
            "cuts": [
                {
                    "cut_id": "c1",
                    "start_ms": 0,
                    "end_ms": 5000,
                    "segment_id": "seg_001",
                    "priority": "must_keep",
                }
            ],
            "snap_warnings": [],
        },
    )
    monkeypatch.setattr(
        "interview_mux.ideal_cuts.bind_boundaries_enabled",
        lambda cfg=None: True,
    )
    monkeypatch.setattr(
        "interview_mux.ideal_cuts.bind_ranking_enabled",
        lambda cfg=None: True,
    )

    def _boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "interview_mux.stages.segmentation.evaluate_boundary_quality",
        _boom,
    )
    run_ideal_cuts_materialize(ctx)
    assert not ctx.artifact_exists(BOUNDARIES_REL)
    mat = ctx.read_json(MATERIALIZED_REL)
    assert mat.get("wrote_boundaries") is False
    skip = str(mat.get("boundary_skip_reason") or mat.get("boundary_bind_skipped") or "")
    assert skip.startswith("quality_eval_failed:")
    for cut in mat.get("cuts") or []:
        if isinstance(cut, dict):
            assert not cut.get("segment_id")


# ---------------------------------------------------------------------------
# F-04
# ---------------------------------------------------------------------------


def test_f04_air_cfg_fail_open_false_under_auto_env(monkeypatch):
    """F-04: automation env forces fail_open=False unless config forces open."""
    from interview_mux.air_script import air_script_cfg

    monkeypatch.delenv("MUX_FULL_AUTO", raising=False)
    monkeypatch.delenv("MUX_RUN_MODE", raising=False)
    monkeypatch.setenv("MUX_RUN_MODE", "full-auto")
    monkeypatch.setattr(
        "interview_mux.air_script.merged_config",
        lambda: {"mastering": {"air_script": {}}},
    )
    assert air_script_cfg().get("fail_open") is False

    monkeypatch.setattr(
        "interview_mux.air_script.merged_config",
        lambda: {"mastering": {"air_script": {"fail_open": True}}},
    )
    assert air_script_cfg().get("fail_open") is True


def test_f04_compose_raises_under_auto_does_not_swallow(tmp_path, monkeypatch):
    """F-04: under auto, compose exceptions re-raise (fail closed)."""
    from interview_mux.air_script import run_air_script_compose

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("MUX_RUN_MODE", "full-auto")
    ctx = isolated_run_ctx(tmp_path, "f04_compose_raise")
    monkeypatch.setattr(
        "interview_mux.air_script.air_script_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "interview_mux.air_script.air_script_cfg",
        lambda: {"enable": True, "fail_open": False},
    )
    monkeypatch.setattr(
        "interview_mux.air_script.compose_pass_a",
        lambda _ctx: (_ for _ in ()).throw(RuntimeError("compose_boom")),
    )
    with pytest.raises(RuntimeError, match="compose_boom"):
        run_air_script_compose(ctx)


def test_f04_hollow_seats_incompleteness_blocks_seed(tmp_path, monkeypatch):
    """F-04: live VO lines + empty seated_line_ids → incompleteness."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "f04_hollow_seats")
    monkeypatch.setattr(
        "interview_mux.air_script.air_script_enabled",
        lambda: True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_live_1",
                    "text": "What happened next?",
                    "delivery": "synthesize",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "version": 1,
            "plan_status": "complete",
            "air_script": {
                "beats": [{"beat_id": "b1"}],
                "vo_seats": {"seated_line_ids": [], "omitted_line_ids": []},
            },
        },
        skip_handoff=True,
    )
    reason = stage_artifact_incompleteness(ctx, "air_script_seams")
    assert reason is not None
    assert "hollow seats" in reason
    # HR-3: Pass A is markable without seats; F-04 hollow-seats stays on seams.
    reason_a = stage_artifact_incompleteness(ctx, "air_script_compose")
    assert reason_a is None or "hollow seats" not in reason_a


# ---------------------------------------------------------------------------
# F-05
# ---------------------------------------------------------------------------


def test_f05_sdp_missing_wav_uses_placeholders_not_legacy(tmp_path, monkeypatch):
    """F-05: SDP cues with missing wav → sdp_placeholders + missing_assets>0."""
    from interview_mux.sound_design import build_flow1_overlays

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "f05_placeholders")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_a", start_ms=0, end_ms=2000)),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/sound_design_plan.json",
        sound_design_plan_with(
            assets=[
                {
                    "asset_id": "missing_bed",
                    "role": "theme_bed",
                    "description": "missing bed",
                    "duration_seconds": 2.0,
                }
            ],
            flow_plans={
                "podcast": {
                    "cues": [
                        {
                            "cue_id": "bed_1",
                            "asset_id": "missing_bed",
                            "placement": "under_segment",
                            "segment_id": "seg_a",
                            "level_db": -26.0,
                        }
                    ]
                }
            },
            generated={},  # no wav on disk
        ),
        skip_handoff=True,
    )
    legacy_calls: list[int] = []

    def _legacy(*_a, **_k):
        legacy_calls.append(1)
        return [{"role": "bed", "legacy": True}]

    monkeypatch.setattr("interview_mux.sound_design.flow1_overlays_legacy", _legacy)
    overlays, stats = build_flow1_overlays(
        ctx, segment_timing={"seg_a": (0, 2000)}, timeline_ms=2000
    )
    assert legacy_calls == []
    assert stats.get("overlay_authority") == "sdp_placeholders"
    assert int(stats.get("missing_assets") or 0) > 0
    assert any(isinstance(o, dict) and o.get("missing_asset") for o in overlays)


def test_f05_sdp_plan_empty_realized_no_legacy_invent(tmp_path, monkeypatch):
    """F-05: SDP exists but realized empty → authority none, no legacy invent."""
    from interview_mux.sound_design import build_flow1_overlays

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "f05_empty_realized")
    ctx.write_json(
        "understanding/sound_design_plan.json",
        sound_design_plan_with(
            assets=[{"asset_id": "a1", "role": "theme_bed", "description": "x"}],
            flow_plans={"podcast": {"cues": [{"cue_id": "c1", "asset_id": "a1"}]}},
        ),
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.sound_design.flow1_overlays_from_sdp",
        lambda *a, **k: [],
    )
    legacy_calls: list[int] = []

    def _legacy(*_a, **_k):
        legacy_calls.append(1)
        return [{"role": "bed"}]

    monkeypatch.setattr("interview_mux.sound_design.flow1_overlays_legacy", _legacy)
    overlays, stats = build_flow1_overlays(
        ctx, segment_timing={"seg_a": (0, 1000)}, timeline_ms=1000
    )
    assert overlays == []
    assert stats.get("overlay_authority") == "none"
    assert legacy_calls == []


def test_f05_no_sdp_may_use_legacy_fallback(tmp_path, monkeypatch):
    """F-05: no SDP cues → legacy_fallback OK."""
    from interview_mux.sound_design import build_flow1_overlays

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "f05_legacy")
    # No sound_design_plan → no SDP.
    monkeypatch.setattr(
        "interview_mux.sound_design.load_sound_design_plan",
        lambda _ctx: None,
    )
    monkeypatch.setattr(
        "interview_mux.sound_design.flow1_overlays_from_sdp",
        lambda *a, **k: [],
    )
    monkeypatch.setattr(
        "interview_mux.sound_design.flow1_overlays_legacy",
        lambda *a, **k: [{"role": "bed", "missing_asset": False}],
    )
    monkeypatch.setattr(
        "interview_mux.sound_design.count_overlay_roles",
        lambda overlays: {"beds": len(overlays), "stingers": 0, "bridges": 0},
    )
    overlays, stats = build_flow1_overlays(
        ctx, segment_timing={"seg_a": (0, 1000)}, timeline_ms=1000
    )
    assert len(overlays) == 1
    assert stats.get("overlay_authority") == "legacy_fallback"


# ---------------------------------------------------------------------------
# B-02 residual SSOT
# ---------------------------------------------------------------------------


def test_b02_ssot_ledger_blocks_ship_pmq_and_publishability(tmp_path, monkeypatch):
    """B-02: critical delivery residual blocks ship + PMQ residual check + publishability."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "b02_ssot_ledger")
    _write_raw(
        ctx,
        "master/junction_snip_qa.json",
        {
            "version": 1,
            "generated_at": "2026-01-01T00:00:00+00:00",
            "critical_count": 0,
            "critical_residual_count": 0,
            "critical_residuals": 0,
            "residual_findings": [],
            "findings": [],
            "applied": [],
            "mode": "authoritative",
        },
    )
    record_delivery_residual(
        ctx,
        kind="fuse_oscillation",
        severity="critical",
        stage="connector_fuse_pass",
        detail={"pass_id": "wave9", "sig": "a|b"},
    )
    assert has_critical_residuals(ctx)
    view = critical_residual_view(ctx)
    assert view.count >= 1
    assert "delivery_ledger" in view.sources
    # Mirror appends residual_findings for PMQ/delight dialects.
    qa_doc = json.loads((ctx.run_dir / "master/junction_snip_qa.json").read_text(encoding="utf-8"))
    assert any(
        isinstance(f, dict) and f.get("kind") == "fuse_oscillation"
        for f in (qa_doc.get("residual_findings") or [])
    )
    assert int(qa_doc.get("critical_residuals") or 0) >= 1

    _ship_ready_fixture(ctx, monkeypatch)
    ready, reason = ship_path_ready(ctx)
    assert ready is False
    assert reason == "critical_delivery_residuals"

    quality = evaluate_post_master_quality(ctx)
    checks = {
        str(c.get("check_id")): c
        for c in (quality.get("checks") or [])
        if isinstance(c, dict)
    }
    assert "no_critical_junction_residuals" in checks
    assert checks["no_critical_junction_residuals"].get("passed") is False

    report = validate_publishability(ctx, checkpoint="post_junction")
    assert any(v.code == "critical_junction_residual" for v in report.violations)
    assert _cut_integrity(ctx) < 1.0


def test_b02_ssot_junction_findings_alone_block_via_view(tmp_path, monkeypatch):
    """B-02: junction residual_findings alone (no ledger) block via SSOT view."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "b02_ssot_findings")
    _write_raw(
        ctx,
        "master/junction_snip_qa.json",
        {
            "version": 1,
            "generated_at": "2026-01-01T00:00:00+00:00",
            "critical_count": 0,
            "critical_residual_count": 0,
            "critical_residuals": 0,
            "residual_findings": [
                {
                    "kind": "incomplete_clause",
                    "severity": "critical",
                    "detail": {"unrecoverable_within_clip": True},
                }
            ],
            "findings": [],
            "applied": [],
            "mode": "authoritative",
        },
    )
    assert has_critical_residuals(ctx)
    view = critical_residual_view(ctx)
    assert view.count >= 1
    assert "junction_findings" in view.sources
    assert "delivery_ledger" not in view.sources

    _ship_ready_fixture(ctx, monkeypatch)
    ready, reason = ship_path_ready(ctx)
    assert ready is False
    assert reason == "critical_junction_residuals"

    report = validate_publishability(ctx, checkpoint="post_junction")
    assert any(v.code == "critical_junction_residual" for v in report.violations)


def test_ship_path_ready_fail_closed_on_residual_view_error(tmp_path, monkeypatch):
    """DW-09: residual SSOT exceptions must not fail-open ship_path_ready."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "ship_residual_fail_closed")
    _ship_ready_fixture(ctx, monkeypatch)
    _write_raw(
        ctx,
        "master/junction_snip_qa.json",
        {
            "version": 1,
            "critical_residual_count": 0,
            "critical_residuals": 0,
            "residual_findings": [],
            "mode": "authoritative",
        },
    )

    def _boom(_ctx):
        raise RuntimeError("ssot exploded")

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.critical_residual_view",
        _boom,
    )
    ready, reason = ship_path_ready(ctx)
    assert ready is False
    assert reason == "critical_residual_check_failed"
