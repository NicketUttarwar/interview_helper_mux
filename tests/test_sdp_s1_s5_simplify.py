"""SDP S1–S5 simplify: peel policy/narrative side effects; keep deferred placeholders."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from interview_mux.artifact_repairs import repair_sound_design_plan
from interview_mux.run_context import RunContext
from interview_mux.sdp_cross_validate import validate_post_sound_plan
from interview_mux.stages.sound_design_stages import run_sound_design_plan
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "sdp_s1_s5")


def _write(ctx: RunContext, *parts: str, payload: dict) -> None:
    path = ctx.final_path(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def _seed_delivery_ready(ctx: RunContext, *, mix_seated: bool = False) -> None:
    sdp = {
        "version": 1,
        "_meta": {"producer_stage": "sound_design_plan"},
        "coherence": {
            "sonic_identity": "test",
            "primary_mood": "warm",
            "density": "sparse",
            "invent_obligation": "",
        },
        "palettes": [
            {
                "palette_id": "theme_default",
                "theme_label": "test",
                "keywords": ["underscore"],
                "ambient_description": "Soft bed.",
                "accent_description": "Light accent.",
                "avoid": ["vocals"],
                "segment_ids": ["seg_001"],
            }
        ],
        "assets": [
            {
                "asset_id": "show_theme_v1_underscore_loop",
                "role": "theme_underscore",
                "palette_kind": "underscore_loop",
                "description": "Soft bed loop under speech.",
                "duration_seconds": 12.0,
                "path": "assets/show_theme_v1_underscore_loop.wav",
            }
        ],
        "flow_plans": {
            "podcast": {
                "profile": "podcast",
                "compose_deferred": True,
                "cues": [
                    {
                        "cue_id": "palette_bed_placeholder",
                        "placement": "under_segment",
                        "segment_id": "seg_001",
                        "under_segment_id": "seg_001",
                        "asset_id": "show_theme_v1_underscore_loop",
                        "role": "theme_underscore",
                        "level_db": -18,
                    }
                ],
            }
        },
        "generated": {},
    }
    _write(ctx, "understanding", "sound_design_plan.json", payload=sdp)
    _write(ctx, "master", "selection.json", payload={"ordered_segment_ids": ["seg_001"]})
    _write(
        ctx,
        "master",
        "narrative_plan.json",
        payload={
            "arc_summary": "test",
            "ordering_constraints": [],
            "chapters": [{"chapter_id": "c1", "segment_ids": ["seg_001"]}],
        },
    )
    _write(ctx, "master", "transitions.json", payload={"transitions": []})
    _write(ctx, "understanding", "gap_report.json", payload={"interviewer_lines": []})
    _write(
        ctx,
        "segments",
        "manifest.json",
        payload={"segments": [{"segment_id": "seg_001", "start_ms": 0, "end_ms": 2000}]},
    )
    if mix_seated:
        assembly = ctx.final_path("master", "assembly.wav")
        assembly.parent.mkdir(parents=True, exist_ok=True)
        assembly.write_bytes(b"RIFF" + b"\x00" * 64)


def test_s2_persist_does_not_write_soundscape_policy(ctx: RunContext) -> None:
    _seed_delivery_ready(ctx)
    inject = MagicMock()
    refresh = MagicMock()

    def fake_flow(_c, _k, _p, build_input, persist):
        persist(
            _c,
            {
                "assets": [
                    {
                        "asset_id": "show_theme_v1_motif",
                        "role": "theme_cold_open",
                        "palette_kind": "motif",
                        "description": "Bright open motif pulse.",
                        "duration_seconds": 4.0,
                    },
                    {
                        "asset_id": "show_theme_v1_underscore_loop",
                        "role": "theme_underscore",
                        "palette_kind": "underscore_loop",
                        "description": "Soft bed loop under speech.",
                        "duration_seconds": 12.0,
                    },
                    {
                        "asset_id": "show_theme_v1_stinger_01",
                        "role": "theme_emphasis",
                        "palette_kind": "stinger",
                        "description": "Short tonal accent.",
                        "duration_seconds": 1.5,
                    },
                ],
                "motif_family": {"prompt_dna": "warm podcast underscore without vocals"},
                "flow_plans": {"podcast": {"profile": "podcast", "cues": []}},
            },
        )
        return {"status": "complete"}

    with patch(
        "interview_mux.stages.sound_design_stages._sound_design_enabled",
        return_value=True,
    ), patch(
        "interview_mux.stages.sound_design_stages.run_flow_llm_stage",
        fake_flow,
    ), patch(
        "interview_mux.soundscape_policy.admit_inject_cue_slots",
        inject,
    ), patch(
        "interview_mux.soundscape_policy.refresh_cue_slots",
        refresh,
    ):
        run_sound_design_plan(ctx)

    inject.assert_not_called()
    refresh.assert_not_called()
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    podcast = ((sdp.get("flow_plans") or {}).get("podcast") or {})
    assert podcast.get("compose_deferred") is True
    assert podcast.get("cues") == []


def test_s6_invent_defers_cues_to_compose(ctx: RunContext) -> None:
    """S6: invent commits empty deferred cues — compose mints first placement."""
    _seed_delivery_ready(ctx)

    def fake_flow(_c, _k, _p, build_input, persist):
        persist(
            _c,
            {
                "assets": [
                    {
                        "asset_id": "show_theme_v1_motif",
                        "role": "theme_cold_open",
                        "palette_kind": "motif",
                        "description": "Bright open motif pulse.",
                        "duration_seconds": 4.0,
                    },
                    {
                        "asset_id": "show_theme_v1_underscore_loop",
                        "role": "theme_underscore",
                        "palette_kind": "underscore_loop",
                        "description": "Soft bed loop under speech.",
                        "duration_seconds": 12.0,
                    },
                    {
                        "asset_id": "show_theme_v1_stinger_01",
                        "role": "theme_emphasis",
                        "palette_kind": "stinger",
                        "description": "Short tonal accent.",
                        "duration_seconds": 1.5,
                    },
                ],
                "motif_family": {"prompt_dna": "warm podcast underscore without vocals"},
                "flow_plans": {
                    "podcast": {
                        "profile": "podcast",
                        "cues": [
                            {
                                "cue_id": "palette_bed_placeholder",
                                "asset_id": "show_theme_v1_underscore_loop",
                                "placement": "under_segment",
                            }
                        ],
                    }
                },
            },
        )
        return {"status": "complete"}

    with patch(
        "interview_mux.stages.sound_design_stages._sound_design_enabled",
        return_value=True,
    ), patch(
        "interview_mux.stages.sound_design_stages.run_flow_llm_stage",
        fake_flow,
    ):
        run_sound_design_plan(ctx)

    sdp = ctx.read_json("understanding/sound_design_plan.json")
    podcast = ((sdp.get("flow_plans") or {}).get("podcast") or {})
    assert podcast.get("compose_deferred") is True
    assert podcast.get("cues") == []
    assets = [a for a in (sdp.get("assets") or []) if isinstance(a, dict)]
    assert len(assets) >= 1
    meta = sdp.get("_meta") if isinstance(sdp.get("_meta"), dict) else {}
    assert str(meta.get("producer_stage") or "") == "sound_design_plan"


def test_s3_refuse_invent_on_drift_without_narrative_mutate(ctx: RunContext) -> None:
    _seed_delivery_ready(ctx)
    _write(ctx, "master", "selection.json", payload={"ordered_segment_ids": ["seg_001", "seg_002"]})
    _write(
        ctx,
        "segments",
        "manifest.json",
        payload={
            "segments": [
                {"segment_id": "seg_001", "start_ms": 0, "end_ms": 2000},
                {"segment_id": "seg_002", "start_ms": 2000, "end_ms": 4000},
            ]
        },
    )
    # Constraint requires seg_002 before seg_001 — conflicts with selection order.
    _write(
        ctx,
        "master",
        "narrative_plan.json",
        payload={
            "arc_summary": "test",
            "ordering_constraints": [
                {
                    "before_segment_id": "seg_002",
                    "after_segment_id": "seg_001",
                }
            ],
            "chapters": [{"chapter_id": "c1", "segment_ids": ["seg_001", "seg_002"]}],
        },
    )
    before = ctx.read_json("master/narrative_plan.json")

    def fake_flow(c, _k, _p, build_input, persist):
        build_input(c)
        persist(c, {})

    with patch(
        "interview_mux.stages.sound_design_stages._sound_design_enabled",
        return_value=True,
    ), patch(
        "interview_mux.stages.sound_design_stages._sdp_fail_closed_reconcile",
        return_value=True,
    ), patch(
        "interview_mux.stages.sound_design_stages.run_flow_llm_stage",
        fake_flow,
    ):
        with pytest.raises(RuntimeError, match="refuse invent on drifted"):
            run_sound_design_plan(ctx)

    after = ctx.read_json("master/narrative_plan.json")
    assert after == before


def test_s4_deferred_placeholder_skips_strict_cue_slots(ctx: RunContext) -> None:
    _seed_delivery_ready(ctx)
    _write(
        ctx,
        "understanding",
        "soundscape_policy.json",
        payload={"cue_slots": [], "underscore_policy": "normal"},
    )
    errs = validate_post_sound_plan(ctx)
    assert not any("not in soundscape cue_slots" in e for e in errs)


def test_s4_repair_skips_slot_inject_when_deferred(ctx: RunContext) -> None:
    _seed_delivery_ready(ctx)
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    with patch(
        "interview_mux.soundscape_policy.admit_inject_cue_slots"
    ) as inject, patch(
        "interview_mux.soundscape_policy.refresh_cue_slots"
    ) as refresh:
        _out, notes = repair_sound_design_plan(ctx, sdp)
    assert any(
        isinstance(n, dict) and n.get("action") == "skip_cue_slot_align_compose_deferred"
        for n in notes
    )
    inject.assert_not_called()
    refresh.assert_not_called()


def test_s5_mix_seat_skip_uses_heal_not_raw_stamp(ctx: RunContext) -> None:
    _seed_delivery_ready(ctx, mix_seated=True)
    invent = MagicMock()
    raw = MagicMock()

    with patch(
        "interview_mux.stages.sound_design_stages._sound_design_enabled",
        return_value=True,
    ), patch(
        "interview_mux.stages.sound_design_stages.run_flow_llm_stage",
        invent,
    ), patch(
        "interview_mux.done_authority.raw_stamp_session",
        raw,
    ), patch(
        "interview_mux.stages.sound_design_stages.heal_or_refuse_mark",
    ) as heal:
        run_sound_design_plan(ctx)

    invent.assert_not_called()
    raw.assert_not_called()
    heal.assert_called()
