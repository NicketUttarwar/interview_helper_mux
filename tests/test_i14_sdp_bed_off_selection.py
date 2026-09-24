"""i14: SDP bed seeds must drop cues whose segment is off the ranked selection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.artifact_repairs import repair_sound_design_plan
from interview_mux.artifact_sanitize.sound_design_plan import sanitize_sound_design_plan
from interview_mux.run_context import RunContext
from interview_mux.sdp_cross_validate import validate_post_sound_plan
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "i14_sdp_off_selection")


def _seed_selection_manifest(ctx: RunContext) -> None:
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_002", "seg_003", "seg_037"]},
        skip_handoff=True,
    )
    manifest_path = ctx.final_path("segments", "manifest.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "segments": [
                    {"segment_id": "seg_002", "start_ms": 0, "end_ms": 10_000},
                    {"segment_id": "seg_003", "start_ms": 10_000, "end_ms": 20_000},
                    {"segment_id": "seg_028", "start_ms": 20_000, "end_ms": 30_000},
                    {"segment_id": "seg_037", "start_ms": 30_000, "end_ms": 40_000},
                ]
            }
        )
    )


def test_repair_drops_bed_seed_outside_selection(ctx: RunContext) -> None:
    _seed_selection_manifest(ctx)
    sdp = {
        "version": 1,
        "palettes": [
            {
                "palette_id": "theme_default",
                "segment_ids": ["seg_002", "seg_003", "seg_028", "seg_037"],
            }
        ],
        "assets": [
            {
                "asset_id": "show_theme_v1_underscore_loop",
                "role": "theme_underscore",
                "path": "assets/show_theme_v1_underscore_loop.wav",
            }
        ],
        "flow_plans": {
            "podcast": {
                "cues": [
                    {
                        "cue_id": "bed_coverage_seed_11",
                        "placement": "under_segment",
                        "segment_id": "seg_028",
                        "asset_id": "show_theme_v1_underscore_loop",
                        "level_db": -18,
                    },
                    {
                        "cue_id": "bed_ok",
                        "placement": "under_segment",
                        "segment_id": "seg_003",
                        "asset_id": "show_theme_v1_underscore_loop",
                        "level_db": -18,
                    },
                ],
                "compose_deferred": False,
            }
        },
    }
    out, notes = repair_sound_design_plan(ctx, sdp)
    cues = ((out.get("flow_plans") or {}).get("podcast") or {}).get("cues") or []
    ids = {str(c.get("cue_id")) for c in cues if isinstance(c, dict)}
    assert "bed_coverage_seed_11" not in ids
    assert "bed_ok" in ids
    assert any(
        isinstance(n, dict) and n.get("action") == "drop_cue_outside_selection"
        for n in notes
    )
    for c in cues:
        if isinstance(c, dict) and c.get("segment_id"):
            assert str(c.get("segment_id")) in {"seg_002", "seg_003", "seg_037"}
    pals = out.get("palettes") or []
    assert pals and "seg_028" not in (pals[0].get("segment_ids") or [])
    assert any(
        isinstance(n, dict) and n.get("action") == "prune_palette_segment_ids"
        for n in notes
    )


def test_repair_drops_under_segment_id_only_off_selection(ctx: RunContext) -> None:
    _seed_selection_manifest(ctx)
    sdp = {
        "version": 1,
        "palettes": [{"palette_id": "theme_default", "segment_ids": ["seg_003"]}],
        "assets": [
            {
                "asset_id": "show_theme_v1_underscore_loop",
                "role": "theme_underscore",
                "path": "assets/loop.wav",
            }
        ],
        "flow_plans": {
            "podcast": {
                "cues": [
                    {
                        "cue_id": "bed_under_only",
                        "placement": "under_segment",
                        "under_segment_id": "seg_028",
                        "asset_id": "show_theme_v1_underscore_loop",
                        "level_db": -18,
                    },
                    {
                        "cue_id": "bed_ok",
                        "placement": "under_segment",
                        "segment_id": "seg_003",
                        "asset_id": "show_theme_v1_underscore_loop",
                        "level_db": -18,
                    },
                ],
                "compose_deferred": False,
            }
        },
    }
    out, notes = repair_sound_design_plan(ctx, sdp)
    cues = ((out.get("flow_plans") or {}).get("podcast") or {}).get("cues") or []
    ids = {str(c.get("cue_id")) for c in cues if isinstance(c, dict)}
    assert "bed_under_only" not in ids
    assert "bed_ok" in ids
    assert any(
        isinstance(n, dict) and n.get("action") == "drop_cue_outside_selection"
        for n in notes
    )


def test_sanitize_drops_any_off_air_anchor(ctx: RunContext) -> None:
    _seed_selection_manifest(ctx)
    sdp = {
        "version": 1,
        "palettes": [{"palette_id": "theme_default", "segment_ids": ["seg_003", "seg_028"]}],
        "assets": [
            {
                "asset_id": "loop",
                "role": "theme_underscore",
                "path": "assets/loop.wav",
            }
        ],
        "flow_plans": {
            "podcast": {
                "cues": [
                    {
                        "cue_id": "mixed_anchors",
                        "placement": "under_segment",
                        "segment_id": "seg_003",
                        "under_segment_id": "seg_028",
                        "asset_id": "loop",
                        "description": "underscore bed",
                        "role": "theme_underscore",
                        "level_db": -18,
                    },
                ],
            }
        },
    }
    result = sanitize_sound_design_plan(ctx, sdp)
    cues = (
        ((result.doc.get("flow_plans") or {}).get("podcast") or {}).get("cues") or []
    )
    assert "mixed_anchors" not in {
        str(c.get("cue_id")) for c in cues if isinstance(c, dict)
    }
    pals = result.doc.get("palettes") or []
    assert pals and "seg_028" not in (pals[0].get("segment_ids") or [])


def test_validate_errors_on_under_segment_id_off_selection(ctx: RunContext) -> None:
    _seed_selection_manifest(ctx)
    sdp = {
        "version": 1,
        "_meta": {"producer_stage": "sound_design_plan"},
        "palettes": [{"palette_id": "theme_default", "segment_ids": ["seg_003"]}],
        "assets": [
            {
                "asset_id": "loop",
                "role": "theme_underscore",
                "path": "assets/loop.wav",
            }
        ],
        "flow_plans": {
            "podcast": {
                "compose_deferred": False,
                "cues": [
                    {
                        "cue_id": "bad_under",
                        "placement": "under_segment",
                        "under_segment_id": "seg_028",
                        "asset_id": "loop",
                        "level_db": -18,
                    },
                ],
            }
        },
    }
    # Raw disk write — bypass admit schema (validate reads body as-is).
    path = ctx.final_path("understanding", "sound_design_plan.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sdp))
    errs = validate_post_sound_plan(ctx)
    assert any("under_segment_id=seg_028" in e for e in errs)
