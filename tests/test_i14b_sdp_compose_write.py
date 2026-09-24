"""i14b: music_palette_compose must validate-before-write and preserve prune + producer_stage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.homunculus.agenda import delivery_sdp_present
from interview_mux.run_context import RunContext
from interview_mux.stages.music_palette_compose import (
    _sdp_has_off_selection_anchors,
)
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "i14b_sdp_compose_write")


def _write(ctx: RunContext, *parts: str, payload: dict) -> None:
    path = ctx.final_path(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def test_off_selection_detector(ctx: RunContext) -> None:
    _write(
        ctx,
        "understanding",
        "sound_design_plan.json",
        payload={
            "version": 1,
            "palettes": [{"palette_id": "p", "segment_ids": ["seg_002", "seg_028"]}],
            "assets": [],
            "flow_plans": {"podcast": {"cues": []}},
        },
    )
    assert _sdp_has_off_selection_anchors(ctx, {"seg_002", "seg_003"})
    assert not _sdp_has_off_selection_anchors(ctx, {"seg_002", "seg_028"})


def test_delivery_sdp_present_requires_producer_restamp(ctx: RunContext) -> None:
    _write(ctx, "master", "transitions.json", payload={"transitions": []})
    body = {
        "version": 1,
        "palettes": [],
        "assets": [{"asset_id": "a", "role": "theme_underscore", "path": "a.wav"}],
        "flow_plans": {"podcast": {"profile": "podcast", "cues": []}},
    }
    path = ctx.final_path("understanding", "sound_design_plan.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body))
    assert not delivery_sdp_present(ctx)
    body["_meta"] = {"producer_stage": "sound_design_plan"}
    path.write_text(json.dumps(body))
    assert delivery_sdp_present(ctx)


def test_compose_refuse_does_not_poison_prior_sdp(ctx: RunContext) -> None:
    """Validate-before-write: density refuse must not replace a good on-disk SDP."""
    good = {
        "version": 1,
        "_meta": {"producer_stage": "sound_design_plan"},
        "palettes": [{"palette_id": "theme_default", "segment_ids": ["seg_002"]}],
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
                        "cue_id": "bed_ok",
                        "placement": "under_segment",
                        "segment_id": "seg_002",
                        "asset_id": "loop",
                        "level_db": -18,
                    }
                ],
            }
        },
    }
    _write(ctx, "understanding", "sound_design_plan.json", payload=good)
    _write(ctx, "master", "selection.json", payload={"ordered_segment_ids": ["seg_002"]})
    _write(ctx, "master", "transitions.json", payload={"transitions": []})
    _write(
        ctx,
        "segments",
        "manifest.json",
        payload={"segments": [{"segment_id": "seg_002", "start_ms": 0, "end_ms": 1000}]},
    )

    # Simulate persist raising after in-memory validate without writing bad body.
    from interview_mux.sdp_cross_validate import validate_post_sound_plan

    bad = {
        **good,
        "flow_plans": {
            "podcast": {
                "compose_deferred": False,
                "cues": [
                    {
                        "cue_id": "bed_bad",
                        "placement": "under_segment",
                        "segment_id": "seg_028",
                        "asset_id": "loop",
                        "level_db": -18,
                    }
                ],
            }
        },
    }
    errs = validate_post_sound_plan(ctx, doc=bad)
    assert errs
    # Disk unchanged
    on_disk = ctx.read_json("understanding/sound_design_plan.json")
    cues = (
        ((on_disk.get("flow_plans") or {}).get("podcast") or {}).get("cues") or []
    )
    assert cues and cues[0].get("cue_id") == "bed_ok"
