"""Workstream C — Music ↔ PMQ architecture cascade (MUX_FORENSICS=0)."""

from __future__ import annotations

import json
import os

import pytest

from interview_mux.junction_snip_qa import REMASTER_MIX_SIDE_EFFECTS
from interview_mux.placement_qa import (
    OUTPUT_PATH,
    music_repair_would_apply,
    run_placement_qa,
)
from interview_mux.post_master_quality import (
    MUSIC_JUNCTION_SOFT_WAIVABLE,
    soft_music_junction_pmq_allowed,
)
from interview_mux.thrash_hardening import note_junction_oscillation_halt
from run_fixtures import MINIMAL_WAV_BYTES, isolated_run_ctx


@pytest.fixture(autouse=True)
def _forensics_off(monkeypatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    os.environ["MUX_FORENSICS"] = "0"


def test_remaster_merge_preserves_pads_snip_music_hints(tmp_path, monkeypatch):
    """C1: remaster regenerate merges pads/snip/music hints — does not wipe."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "c1_merge_remaster")
    sdp_path = ctx.path("understanding", "sound_design_plan.json")
    sdp_path.parent.mkdir(parents=True, exist_ok=True)
    sdp_path.write_text(
        json.dumps(
            {
                "version": 1,
                "assets": [{"asset_id": "theme_a", "role": "theme_emphasis"}],
                "flow_plans": {
                    "podcast": {
                        "profile": "podcast",
                        "cues": [
                            {
                                "cue_id": "c_theme_a",
                                "asset_id": "theme_a",
                                "role": "theme_emphasis",
                                "placement": "after_segment",
                                "crossfade_ms": None,
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    assets_dir = ctx.path("sound_design", "assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "theme_a.wav").write_bytes(MINIMAL_WAV_BYTES)
    ctx.write_json(
        OUTPUT_PATH,
        {
            "version": 1,
            "adjustments": [
                {
                    "asset_id": "theme_a",
                    "action": "adjust_crossfade",
                    "suggested_crossfade_ms": 180,
                    "suggested_pad_ms": 120,
                    "pad_before_ms": 40,
                    "snip_override": {"source_end_ms": 900},
                    "placement_hint": "close",
                    "music_placement": "after_segment",
                    "reason": "junction_snip_qa:music_hard_transition",
                    "provenance": {
                        "rule_id": "junction_snip_qa",
                        "source_artifact": "master/junction_snip_qa.json",
                    },
                }
            ],
        },
        skip_handoff=True,
    )
    doc = run_placement_qa(ctx)
    row = next((a for a in doc["adjustments"] if a.get("asset_id") == "theme_a"), None)
    assert row is not None
    assert int(row.get("suggested_crossfade_ms") or 0) >= 180
    assert int(row.get("suggested_pad_ms") or 0) == 120
    assert int(row.get("pad_before_ms") or 0) == 40
    assert row.get("snip_override") == {"source_end_ms": 900}
    assert row.get("placement_hint") == "close"
    assert row.get("music_placement") == "after_segment"


def test_detect_without_mix_apply_not_marked_applied(tmp_path, monkeypatch):
    """C2: detect-only repair without durable/mix apply path → not applied."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "c2_detect_only")
    hint = {
        "asset_id": "missing_bed",
        "action": "adjust_music_fade",
        "suggested_crossfade_ms": 180,
        "detail": {"asset_id": "missing_bed", "suggested_crossfade_ms": 180},
    }
    # No placement_adjustments on disk → not durable → would_apply False.
    assert music_repair_would_apply(ctx, hint) is False

    ctx.write_json(
        OUTPUT_PATH,
        {
            "version": 1,
            "adjustments": [
                {
                    "asset_id": "missing_bed",
                    "action": "adjust_crossfade",
                    "suggested_crossfade_ms": 180,
                }
            ],
        },
        skip_handoff=True,
    )
    assert music_repair_would_apply(ctx, hint) is True


def test_oscillation_halt_clean_jsq_residual_not_critical(tmp_path, monkeypatch):
    """C3: oscillation halt with clean live JSQ → soft residual, not critical."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "c3_osc_soft")
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "edl.json").write_text(
        json.dumps({"version": 1, "clips": [], "ordered_segment_ids": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [],
    )
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.detect_junction_findings",
        lambda *_a, **_k: [{"kind": "music_hard_transition", "severity": "warn"}],
    )
    note_junction_oscillation_halt(ctx)
    residuals = ctx.read_json("operator/delivery_residuals.json")
    rows = [r for r in (residuals.get("residuals") or []) if isinstance(r, dict)]
    halt = [r for r in rows if str(r.get("kind") or "") == "junction_oscillation_halt"]
    assert halt, f"expected oscillation residual, got {residuals!r}"
    assert str(halt[-1].get("severity") or "") == "soft"


def test_coverage_promote_list_includes_music_qc():
    """C4: remaster promote list includes music_cue_coverage + mix QC."""
    assert "master/music_cue_coverage.json" in REMASTER_MIX_SIDE_EFFECTS
    assert "master/listen_critic.json" in REMASTER_MIX_SIDE_EFFECTS
    assert "master/bed_presence_qc.json" in REMASTER_MIX_SIDE_EFFECTS
    assert "sound_design/placement_adjustments.json" in REMASTER_MIX_SIDE_EFFECTS


def test_soft_pmq_music_junction_disabled_under_production_matrix(tmp_path, monkeypatch):
    """C5: forensics / full-auto / production refuse soft music/junction waivers."""
    from interview_mux.post_master_quality import evaluate_post_master_quality

    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    # Production / full-auto gate soft without quality waivers.
    monkeypatch.setenv("INTERVIEW_MUX_E2E_SOFT", "1")
    monkeypatch.delenv("INTERVIEW_MUX_E2E_QUALITY_WAIVERS", raising=False)
    assert soft_music_junction_pmq_allowed(meta={"full_auto": True}) is False
    assert soft_music_junction_pmq_allowed(meta={"production": True}) is False

    monkeypatch.setenv("MUX_FORENSICS", "1")
    assert soft_music_junction_pmq_allowed(meta={"e2e_quality_waivers": True}) is False
    monkeypatch.setenv("MUX_FORENSICS", "0")

    # Even with soft_pmq flags, music/junction criticals stay blocking under full_auto.
    ctx = isolated_run_ctx(tmp_path, "c5_soft_refuse")
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "master.wav").write_bytes(b"RIFF" + b"\0" * 64)
    (ctx.run_dir / "master" / "edl.json").write_text(
        json.dumps({"version": 1, "clips": [], "ordered_segment_ids": []}),
        encoding="utf-8",
    )
    ctx.write_json(
        "run_meta.json",
        {
            "full_auto": True,
            "e2e_quality_waivers": True,
            "e2e_soft_post_master_quality": True,
            "e2e_soft_junction_residuals": True,
        },
        skip_handoff=True,
    )
    from interview_mux.delivery_guardrails import record_delivery_residual

    record_delivery_residual(
        ctx,
        kind="junction_snip",
        severity="critical",
        stage="junction_snip_qa",
        detail={"test": True},
    )
    # Force a failed planned_music / junction check path via residual view.
    quality = evaluate_post_master_quality(ctx)
    checks = {c["check_id"]: c for c in quality.get("checks") or []}
    # soft_music_junction must be refused; if check present and failed, not softened.
    for cid in MUSIC_JUNCTION_SOFT_WAIVABLE:
        row = checks.get(cid)
        if row and not row.get("passed"):
            detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
            assert not detail.get("e2e_softened"), f"{cid} must not soft-waive under full_auto"
