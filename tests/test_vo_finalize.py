"""VO finalize sonic_context patching tests."""

from __future__ import annotations

import json
import wave
from pathlib import Path

from interview_mux.analysis_memory import default_sound_design_plan
from interview_mux.run_context import RunContext
from interview_mux.stages.sound_design_vo_finalize import run_sound_design_vo_finalize
from run_fixtures import minimal_gap_line, minimal_gap_report, seed_from_sonic_fixture, write_fixture_vo_wav


def _write_test_wav(path: Path) -> None:
    rate = 48000
    frames = int(rate * 0.8)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * frames)


def test_vo_finalize_patches_sonic_context_vo_bridge(tmp_path):
    ctx = RunContext("run_vo_sonic", create=True)
    pickup = ctx.path("vo_pickup")
    pickup.mkdir(exist_ok=True)
    write_fixture_vo_wav(pickup / "line_001.wav", duration_sec=0.8)
    ctx.write_json(
        "understanding/gap_report.json",
        minimal_gap_report(
            minimal_gap_line(
                line_id="line_001",
                targets_segment_id="seg_001",
                delivery="record",
            )
        ),
    )
    doc = seed_from_sonic_fixture(ctx, "one_on_one", seed_base=False)
    doc["cue_opportunities"] = [
        {
            "kind": "vo_bridge",
            "segment_id": "seg_001",
            "confidence": 0.8,
            "provenance": ["understanding/gap_report.json"],
        }
    ]
    ctx.write_json("understanding/sonic_context.json", doc, skip_handoff=True)
    plan = default_sound_design_plan()
    plan["assets"] = [
        {
            "asset_id": "vo_bridge_1",
            "role": "vo_bridge",
            "description": "Recorded VO bridge",
            "duration_seconds": 1.0,
        }
    ]
    plan["flow_plans"]["podcast"]["cues"] = [
        {
            "cue_id": "cue_vo_1",
            "asset_id": "vo_bridge_1",
            "line_id": "line_001",
            "segment_id": "seg_001",
            "placement": "before_segment",
        }
    ]
    dest = ctx.final_path("understanding", "sound_design_plan.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(plan), encoding="utf-8")
    run_sound_design_vo_finalize(ctx)
    sonic = ctx.read_json("understanding/sonic_context.json")
    cue = sonic["cue_opportunities"][0]
    assert cue.get("measured_duration_ms") == 800
    assert cue.get("asset_id") == "vo_bridge_1"
    assert cue.get("line_id") == "line_001"
