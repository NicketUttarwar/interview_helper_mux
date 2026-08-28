"""Heal routing table: never remaster mix for text/id problems; halt at 3."""

from __future__ import annotations

from pathlib import Path

from interview_mux.heal_routing import (
    FAMILY_G1_MISSING,
    FAMILY_LAYUP_STALE,
    FAMILY_MIX_WAV_SEATED,
    FAMILY_MIX_WITHOUT_ASSEMBLY,
    FAMILY_SPOKEN_COPY,
    FAMILY_VO_ADJUDICATE_STALE,
    apply_heal_route,
    classify_heal_error,
    heal_is_halted,
    record_heal_fingerprint,
)
from interview_mux.order_hash import bump_order_lock
from interview_mux.recovery_controller import classify_error_class
from run_fixtures import isolated_run_ctx


def _edl(ids: list[str]) -> dict:
    clips = []
    t = 0
    for sid in ids:
        clips.append(
            {
                "type": "speech",
                "segment_id": sid,
                "source_start_ms": 0,
                "source_end_ms": 1000,
                "duration_ms": 1000,
                "timeline_start_ms": t,
            }
        )
        t += 1000
    return {
        "version": 1,
        "ordered_segment_ids": list(ids),
        "clips": clips,
        "timeline_duration_ms": t,
    }


def test_layup_stale_routes_to_adopt_then_edl(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "heal_layup")
    route = classify_heal_error("nugget_layup_plan_stale vs selection", ctx, stage="edl")
    assert route is not None
    assert route.family == FAMILY_LAYUP_STALE
    assert route.from_stage == "edl"
    assert route.action == "adopt_layup"
    assert classify_error_class("edl", RuntimeError("nugget_layup_plan_stale")) == "layup_stale"


def test_g1_missing_does_not_rewind_compose(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "heal_g1")
    route = classify_heal_error("G1 VO pickup missing for line vo_layup_seg_001", ctx, stage="edl")
    assert route is not None
    assert route.family == FAMILY_G1_MISSING
    assert route.from_stage != "nugget_layup_compose"
    assert route.from_stage == "vo_line_adjudicate"


def test_vo_adjudicate_stale_routes_to_adjudicate(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "heal_adj")
    route = classify_heal_error(
        "vo_line_adjudication stale_script_hash before synth",
        ctx,
        stage="vo_synthesize",
    )
    assert route is not None
    assert route.family == FAMILY_VO_ADJUDICATE_STALE
    assert route.from_stage == "vo_line_adjudicate"
    assert route.action == "rerun_adjudicate_synth"


def test_g1_missing_skipped_gap_fill_is_not_a_block(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "heal_g1_skip")
    ctx.write_json("run_meta.json", {"g1_vo_skipped_optional": True}, skip_handoff=True)
    route = classify_heal_error("G1 VO pickup missing for interviewer line", ctx)
    assert route is not None
    assert route.action == "skip_interviewer_g1"
    assert route.from_stage == "edl"


def test_spoken_copy_routes_to_transitions_not_mix(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "heal_copy")
    route = classify_heal_error(
        "post-master quality failed spoken_vo_speakable spoken_repeated_copy",
        ctx,
        stage="master_finalize",
    )
    assert route is not None
    assert route.family == FAMILY_SPOKEN_COPY
    assert route.from_stage == "transitions"


def test_mix_error_with_seated_wav_routes_to_junction(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "heal_mix_seated")
    sel = bump_order_lock({"ordered_segment_ids": ["a", "b"], "version": 1}, source="t")
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    ctx.write_json("master/edl.json", _edl(["a", "b"]), skip_handoff=True)
    (ctx.run_dir / "master" / "assembly.wav").write_bytes(b"RIFF" + b"\x00" * 64)
    route = classify_heal_error(
        "mix finished without required artifact (master/assembly.wav)",
        ctx,
        stage="mix",
    )
    assert route is not None
    assert route.family == FAMILY_MIX_WAV_SEATED
    assert route.from_stage == "junction_snip_qa"


def test_mix_error_without_wav_routes_to_mix_and_halts_at_3(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "heal_mix_missing")
    ctx.write_json("master/edl.json", _edl(["a"]), skip_handoff=True)
    err = "mix finished without required artifact (master/assembly.wav)"
    route = classify_heal_error(err, ctx, stage="mix")
    assert route is not None
    assert route.family == FAMILY_MIX_WITHOUT_ASSEMBLY
    assert route.from_stage == "mix"
    for _ in range(3):
        row = record_heal_fingerprint(ctx, route, reason=err, stage="mix")
    assert row.get("halt")
    assert heal_is_halted(ctx, route, reason=err, stage="mix")


def test_adopt_heal_action_does_not_remine(tmp_path: Path) -> None:
    from interview_mux.nugget_layup import PLAN_REL

    ctx = isolated_run_ctx(tmp_path, "heal_adopt")
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001"]},
        skip_handoff=True,
    )
    ctx.write_json(
        PLAN_REL,
        {
            "ordered_segment_ids": ["seg_001", "seg_099"],
            "layups": [
                {
                    "target_segment_id": "seg_001",
                    "line_id": "vo_layup_seg_001",
                    "text": "The assay sets up the deal terms for listeners.",
                    "skip": False,
                    "target_beat": "deal terms",
                    "listener_need_entering_T": "need",
                    "forward_unlock": "why the assay matters",
                }
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json("understanding/gap_report.json", {"interviewer_lines": []}, skip_handoff=True)
    route = classify_heal_error("nugget_layup_plan_stale", ctx)
    assert route is not None
    result = apply_heal_route(ctx, route)
    assert result.get("ok")
    live = ctx.read_json(PLAN_REL)
    assert live["ordered_segment_ids"] == ["seg_001"]
