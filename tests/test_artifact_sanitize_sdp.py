"""Tests for artifact_sanitize sound_design_plan (W7)."""

from __future__ import annotations

import json

from interview_mux.artifact_sanitize.sound_design_plan import (
    REL,
    sanitize_sound_design_plan,
    sdp_sanitary_errors,
)
from interview_mux.run_context import RunContext


def _dump_raw(ctx: RunContext, rel: str, doc: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _write_selection(ctx: RunContext, ids: list[str]) -> None:
    ctx.path("master").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ids,
            "excluded_segment_ids": [],
            "chapters": [],
        },
        skip_handoff=True,
    )


def test_sanitize_sdp_flow_plans_drops_off_air_cues() -> None:
    ctx = RunContext(create=True)
    _write_selection(ctx, ["seg_001", "seg_002"])
    doc = {
        "producer_stage": "sound_design_plan",
        "flow_plans": {
            "main": {
                "cues": [
                    {
                        "segment_id": "seg_001",
                        "role": "bed",
                        "description": "warm bed under A",
                    },
                    {
                        "segment_id": "seg_999",
                        "role": "bed",
                        "description": "off-air ghost",
                    },
                    {
                        "segment_id": "seg_002",
                        "role": "bed",
                        "description": "",
                    },
                ]
            }
        },
        "palettes": [
            {"name": "p1", "segment_ids": ["seg_001", "seg_gone"]},
            {"name": "p2", "segment_ids": ["seg_gone"]},
        ],
    }
    result = sanitize_sound_design_plan(ctx, doc)
    assert result.ok
    cues = result.doc["flow_plans"]["main"]["cues"]
    assert len(cues) == 1
    assert cues[0]["segment_id"] == "seg_001"
    assert any(a.get("action") == "drop_flow_cues_off_air" for a in result.actions)
    pals = result.doc.get("palettes") or []
    assert len(pals) == 1
    assert pals[0]["segment_ids"] == ["seg_001"]


def test_sdp_sanitary_errors_reports_needs_or_stale() -> None:
    ctx = RunContext(create=True)
    _write_selection(ctx, ["seg_001"])
    dirty = {
        "version": 1,
        "coherence": {},
        "palettes": [],
        "assets": [],
        "generated": {},
        "flow_plans": {
            "podcast": {
                "cues": [
                    {
                        "segment_id": "seg_off",
                        "role": "bed",
                        "description": "ghost",
                    }
                ]
            },
            "main": {
                "cues": [
                    {
                        "segment_id": "seg_off",
                        "role": "bed",
                        "description": "ghost",
                    }
                ]
            },
        },
    }
    _dump_raw(ctx, REL, dirty)
    errs = sdp_sanitary_errors(ctx)
    assert errs
    assert any("sdp_needs_sanitize" in e or "stale" in e for e in errs)

    stale = {
        "version": 1,
        "coherence": {},
        "palettes": [],
        "assets": [],
        "generated": {},
        "flow_plans": {"podcast": {"cues": []}},
        "_meta": {"stale": True, "stale_reason": "selection_changed"},
    }
    _dump_raw(ctx, REL, stale)
    stale_errs = sdp_sanitary_errors(ctx)
    assert any("stale_meta" in e for e in stale_errs)
