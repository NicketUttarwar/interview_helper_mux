"""i15: under mix seat, sound_design_plan must not fail-closed on order_reconcile deny."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from interview_mux.artifact_repairs import align_narrative_plan_to_selection
from interview_mux.run_context import RunContext
from interview_mux.stages.sound_design_stages import run_sound_design_plan
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "i15_mix_seat_reconcile")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.2.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _write(ctx: RunContext, *parts: str, payload: dict) -> None:
    path = ctx.final_path(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def _seed_mix_seated_delivery_sdp(ctx: RunContext) -> None:
    sdp = {
        "version": 1,
        "_meta": {"producer_stage": "sound_design_plan"},
        "palettes": [{"palette_id": "theme_default", "segment_ids": ["seg_002"]}],
        "assets": [
            {
                "asset_id": "show_theme_v1_underscore_loop",
                "role": "theme_underscore",
                "path": "assets/show_theme_v1_underscore_loop.wav",
            }
        ],
        "flow_plans": {
            "podcast": {
                "profile": "podcast",
                "cues": [
                    {
                        "cue_id": "bed_ok",
                        "placement": "under_segment",
                        "segment_id": "seg_002",
                        "asset_id": "show_theme_v1_underscore_loop",
                        "level_db": -18,
                    }
                ],
            }
        },
    }
    path = ctx.final_path("understanding", "sound_design_plan.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sdp))
    assembly = ctx.final_path("master", "assembly.wav")
    assembly.parent.mkdir(parents=True, exist_ok=True)
    assembly.write_bytes(b"RIFF" + b"\x00" * 64)
    _write(ctx, "master", "selection.json", payload={"ordered_segment_ids": ["seg_002"]})
    _write(
        ctx,
        "master",
        "narrative_plan.json",
        payload={
            "arc_summary": "test",
            "ordering_constraints": [],
            "chapters": [{"chapter_id": "c1", "segment_ids": ["seg_002"]}],
        },
    )
    _write(ctx, "master", "transitions.json", payload={"transitions": []})
    _write(ctx, "understanding", "gap_report.json", payload={"interviewer_lines": []})
    _write(
        ctx,
        "segments",
        "manifest.json",
        payload={"segments": [{"segment_id": "seg_002", "start_ms": 0, "end_ms": 1000}]},
    )


def test_mix_seated_reconcile_deny_does_not_raise(ctx: RunContext) -> None:
    _seed_mix_seated_delivery_sdp(ctx)
    invent = MagicMock()

    with patch(
        "interview_mux.stages.sound_design_stages._sound_design_enabled",
        return_value=True,
    ), patch(
        "interview_mux.stages.sound_design_stages._sdp_fail_closed_reconcile",
        return_value=True,
    ), patch(
        "interview_mux.order_reconcile.reconcile_selection_and_narrative",
        side_effect=RuntimeError(
            "authority_denied:persist:master/narrative_plan.json:edl_narrative_audit:mix_seated"
        ),
    ), patch(
        "interview_mux.stages.sound_design_stages.run_flow_llm_stage",
        invent,
    ):
        run_sound_design_plan(ctx)

    invent.assert_not_called()
    assert ctx.is_done("sound_design_plan")
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    assert isinstance(sdp, dict)
    meta = sdp.get("_meta") if isinstance(sdp.get("_meta"), dict) else {}
    assert str(meta.get("producer_stage") or "") == "sound_design_plan"


def test_align_narrative_skips_persist_under_mix_seat(ctx: RunContext) -> None:
    _seed_mix_seated_delivery_sdp(ctx)
    # Drift chapter onto a segment outside selection so align would want to persist.
    _write(
        ctx,
        "master",
        "narrative_plan.json",
        payload={
            "arc_summary": "test",
            "ordering_constraints": [],
            "chapters": [
                {"chapter_id": "c1", "segment_ids": ["seg_002", "seg_999"]},
            ],
        },
    )
    notes = align_narrative_plan_to_selection(ctx)
    assert any(
        isinstance(n, dict) and n.get("action") == "narrative_align_skipped_mix_seated"
        for n in notes
    )
    # Disk narrative must not have been rewritten via edl_narrative_audit persist.
    plan = ctx.read_json("master/narrative_plan.json")
    assert isinstance(plan, dict)
    chapters = plan.get("chapters") or []
    assert chapters and "seg_999" in (chapters[0].get("segment_ids") or [])
