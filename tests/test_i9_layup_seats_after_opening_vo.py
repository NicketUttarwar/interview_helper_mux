"""i9: nugget_layup still seats after opening orientation VO (no phantom WAV)."""

from __future__ import annotations

import json
import os
import wave
from pathlib import Path

os.environ["MUX_FORENSICS"] = "0"

from interview_mux.hosted_vo_authority import (
    EDL_SURVIVORS_AFTER_ORIENTATION,
    edl_before_line_survives,
)
from interview_mux.stages.assembly import build_flow1_edl
from interview_mux.artifact_sanitize.edl import LEDGER_REL, edl_sanitary_errors
from interview_mux.heal_routing import classify_heal_error
from interview_mux.publishability_boundary import _phantom_vo_violation
from run_fixtures import init_run_meta_for_test, isolated_run_ctx


def _write_wav(path: Path, *, frames: int = 4800) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(48000)
        wf.writeframes(b"\x00\x00" * frames)


def test_edl_survivors_constant_matches_predicate() -> None:
    assert EDL_SURVIVORS_AFTER_ORIENTATION == frozenset(
        {"nugget_layup", "required", "orientation"}
    )
    assert edl_before_line_survives(
        {
            "line_id": "vo_preface_episode_orientation",
            "episode_orientation": True,
            "origin": "deterministic_orientation_guard",
        },
        after_vo_stack=True,
    )
    assert edl_before_line_survives(
        {"line_id": "vo_layup_x", "origin": "nugget_layup"},
        after_vo_stack=True,
    )
    assert edl_before_line_survives(
        {"line_id": "vo_req", "required": True, "origin": "gap_framing"},
        after_vo_stack=False,
    )
    assert not edl_before_line_survives(
        {"line_id": "vo_optional_bridge", "origin": "story_bridge"},
        after_vo_stack=True,
    )


def test_i9_layup_seats_after_opening_orientation(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_i9_layup")
    init_run_meta_for_test(ctx)

    orient = "vo_preface_episode_orientation"
    layup = "vo_layup_seg_007"
    for lid in (orient, layup):
        _write_wav(ctx.path("vo_pickup", "synthesized", f"{lid}.wav"))

    gap = {
        "interviewer_lines": [
            {
                "line_id": orient,
                "delivery": "synthesize",
                "placement": "before",
                "targets_segment_id": "seg_002",
                "origin": "deterministic_orientation_guard",
                "episode_orientation": True,
                "text": "Welcome — today we talk with our guest about cancer science.",
            },
            {
                "line_id": layup,
                "delivery": "synthesize",
                "placement": "before",
                "targets_segment_id": "seg_007",
                "origin": "nugget_layup",
                "gap_type": "nugget_layup",
                "clone_adjacency_exempt": True,
                "text": "Host asks a follow-up about the guest's clinical work.",
                "voice_speaker_id": "spk_1",
            },
        ]
    }
    selection = {"ordered_segment_ids": ["seg_002", "seg_007"]}
    segments_by_id = {
        "seg_002": {
            "segment_id": "seg_002",
            "start_ms": 0,
            "end_ms": 4000,
            "speaker_id": "spk_0",
        },
        "seg_007": {
            "segment_id": "seg_007",
            "start_ms": 10000,
            "end_ms": 14000,
            "speaker_id": "spk_0",
        },
    }

    def _resolve(line: dict):
        lid = str(line.get("line_id") or "")
        return ctx.path("vo_pickup", "synthesized", f"{lid}.wav")

    edl = build_flow1_edl(
        selection=selection,
        segments_by_id=segments_by_id,
        gap_report=gap,
        resolve_vo_path=_resolve,
        vo_duration_ms=lambda _p: 500,
        vo_relpath=lambda p: f"vo_pickup/synthesized/{p.name}",
        ctx=ctx,
    )
    vo_ids = [
        str(c.get("line_id"))
        for c in (edl.get("clips") or [])
        if isinstance(c, dict) and c.get("type") == "vo_pickup"
    ]
    assert orient in vo_ids
    assert layup in vo_ids, vo_ids


def test_i9_two_later_layups_seat_after_orientation(tmp_path) -> None:
    """exec_13183 shape: orientation + vo_layup_seg_007 + vo_layup_seg_037."""
    ctx = isolated_run_ctx(tmp_path, "exec_i9_multi_layup")
    init_run_meta_for_test(ctx)

    orient = "vo_preface_episode_orientation"
    layups = ("vo_layup_seg_007", "vo_layup_seg_037")
    for lid in (orient, *layups):
        _write_wav(ctx.path("vo_pickup", "synthesized", f"{lid}.wav"))

    gap = {
        "interviewer_lines": [
            {
                "line_id": orient,
                "delivery": "synthesize",
                "placement": "before",
                "targets_segment_id": "seg_002",
                "origin": "deterministic_orientation_guard",
                "episode_orientation": True,
                "text": "Welcome — today we talk with our guest about cancer science.",
            },
            {
                "line_id": "vo_layup_seg_007",
                "delivery": "synthesize",
                "placement": "before",
                "targets_segment_id": "seg_007",
                "origin": "nugget_layup",
                "gap_type": "nugget_layup",
                "clone_adjacency_exempt": True,
                "text": "Host asks a follow-up about the guest's clinical work.",
                "voice_speaker_id": "spk_1",
            },
            {
                "line_id": "vo_layup_seg_037",
                "delivery": "synthesize",
                "placement": "before",
                "targets_segment_id": "seg_037",
                "origin": "nugget_layup",
                "gap_type": "nugget_layup",
                "clone_adjacency_exempt": True,
                "text": "Host asks how the guest's lab work translates to patients.",
                "voice_speaker_id": "spk_1",
            },
        ]
    }
    selection = {"ordered_segment_ids": ["seg_002", "seg_007", "seg_037"]}
    segments_by_id = {
        "seg_002": {
            "segment_id": "seg_002",
            "start_ms": 0,
            "end_ms": 4000,
            "speaker_id": "spk_0",
        },
        "seg_007": {
            "segment_id": "seg_007",
            "start_ms": 10000,
            "end_ms": 14000,
            "speaker_id": "spk_0",
        },
        "seg_037": {
            "segment_id": "seg_037",
            "start_ms": 40000,
            "end_ms": 44000,
            "speaker_id": "spk_0",
        },
    }

    def _resolve(line: dict):
        lid = str(line.get("line_id") or "")
        return ctx.path("vo_pickup", "synthesized", f"{lid}.wav")

    edl = build_flow1_edl(
        selection=selection,
        segments_by_id=segments_by_id,
        gap_report=gap,
        resolve_vo_path=_resolve,
        vo_duration_ms=lambda _p: 500,
        vo_relpath=lambda p: f"vo_pickup/synthesized/{p.name}",
        ctx=ctx,
    )
    vo_ids = {
        str(c.get("line_id"))
        for c in (edl.get("clips") or [])
        if isinstance(c, dict) and c.get("type") == "vo_pickup"
    }
    assert orient in vo_ids
    assert set(layups).issubset(vo_ids), vo_ids


def test_i9_edl_sanitary_auto_writes_missing_ledger(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_i9_ledger")
    init_run_meta_for_test(ctx)
    edl = {
        "version": 1,
        "ordered_segment_ids": ["seg_002"],
        "timeline_duration_ms": 1000,
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_002",
                "source_start_ms": 0,
                "source_end_ms": 1000,
                "duration_ms": 1000,
                "timeline_start_ms": 0,
            }
        ],
    }
    # Bypass admit schema gate — sanitary path must repair missing ledger from raw EDL.
    path = ctx.path("master", "edl.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(edl), encoding="utf-8")
    assert not ctx.artifact_exists(LEDGER_REL)
    errs = edl_sanitary_errors(ctx)
    assert "assembly_ledger" not in " ".join(errs)
    assert ctx.artifact_exists(LEDGER_REL)


def test_i9_survivor_phantom_tags_edl_survivor_wipe_and_pins_edl(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_i9_heal_tag")
    init_run_meta_for_test(ctx)
    line = {
        "line_id": "vo_layup_seg_007",
        "delivery": "synthesize",
        "origin": "nugget_layup",
        "targets_segment_id": "seg_007",
        "text": "Host follow-up that must stay seated after orientation.",
    }
    v = _phantom_vo_violation(ctx, line, "vo_layup_seg_007")
    assert v.error_class == "vo_audibility_drift"
    assert v.code == "edl_survivor_wipe"
    assert "rebuild edl" in v.detail.lower() or "do not remint" in v.detail.lower()

    route = classify_heal_error(v.detail, ctx, stage="mix")
    assert route is not None
    assert route.family == "vo_audibility_drift"
    assert route.from_stage == "edl"
    assert route.action == "rebuild_edl"
