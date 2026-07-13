"""Tests for soundscape_verify remediation ladder."""

from __future__ import annotations

import json

from interview_mux.analysis_memory import default_sound_design_plan
from interview_mux.soundscape_verify import apply_cheap_remediation, evaluate_soundscape, run_soundscape_verify
from run_fixtures import isolated_run_ctx


def _raw_write(ctx, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _policy(*, underscore: str = "skip", coverage: float = 0.0) -> dict:
    return {
        "version": 1,
        "underscore_policy": underscore,
        "pace_class": "dense" if underscore == "skip" else "conversational",
        "sfx_density": {"max_beds": 0 if underscore == "skip" else 2, "max_punctuators": 1, "max_foley": 0},
        "mix_contract": {
            "underscore_policy": underscore,
            "duck_under_speech_db": 18,
            "stinger_max_per_minute": 1,
            "max_bed_coverage_ratio": coverage,
            "bed_level_db_range": [-30, -26],
        },
        "standards": {
            "min_speech_relative_db": 12,
            "max_bed_coverage_ratio": coverage,
            "require_intelligibility_pass": True,
        },
        "cue_slots": [],
        "operator_overrides": {},
        "rationale": [],
        "policy_hash": "x",
    }


def test_evaluate_fail_when_beds_under_skip(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_sv_fail")
    ctx.write_json("understanding/soundscape_policy.json", _policy(underscore="skip"))
    sdp = default_sound_design_plan()
    sdp["assets"] = [
        {
            "asset_id": "bed1",
            "role": "ambient_bed",
            "description": "soft bed",
            "duration_seconds": 6.0,
        }
    ]
    sdp["flow_plans"] = {
        "podcast": {
            "profile": "podcast",
            "cues": [
                {
                    "cue_id": "bed_a",
                    "asset_id": "bed1",
                    "placement": "under_segment",
                    "segment_id": "seg_001",
                    "level_db": -20,
                }
            ],
        }
    }
    ctx.write_json("understanding/sound_design_plan.json", sdp)
    _raw_write(
        ctx,
        "segments/manifest.json",
        {"segments": [{"segment_id": "seg_001", "start_ms": 0, "end_ms": 30000}]},
    )
    result = evaluate_soundscape(ctx)
    assert result["verdict"] == "fail"
    assert result["failures"]


def test_remediation_skips_lowest_bed(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_sv_rem")
    pol = _policy(underscore="normal", coverage=0.2)
    pol["cue_slots"] = [
        {
            "slot_id": "bed_seg_001",
            "segment_id": "seg_001",
            "allowed_roles": ["ambient_bed"],
            "priority": 0.3,
        },
        {
            "slot_id": "bed_seg_002",
            "segment_id": "seg_002",
            "allowed_roles": ["ambient_bed"],
            "priority": 0.9,
        },
    ]
    ctx.write_json("understanding/soundscape_policy.json", pol)
    sdp = default_sound_design_plan()
    sdp["flow_plans"] = {
        "podcast": {
            "profile": "podcast",
            "cues": [
                {
                    "cue_id": "bed_a",
                    "asset_id": "b1",
                    "placement": "under_segment",
                    "segment_id": "seg_001",
                    "level_db": -24,
                },
                {
                    "cue_id": "bed_b",
                    "asset_id": "b2",
                    "placement": "under_segment",
                    "segment_id": "seg_002",
                    "level_db": -24,
                },
            ],
        }
    }
    ctx.write_json("understanding/sound_design_plan.json", sdp)
    actions = apply_cheap_remediation(ctx)
    assert actions
    sdp2 = ctx.read_json("understanding/sound_design_plan.json")
    cues = sdp2["flow_plans"]["podcast"]["cues"]
    skipped = [c for c in cues if c.get("skip")]
    assert len(skipped) == 1
    assert skipped[0]["cue_id"] == "bed_a"


def test_run_verify_writes_report(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_sv_report")
    ctx.write_json("understanding/soundscape_policy.json", _policy(underscore="skip"))
    ctx.write_json("understanding/sound_design_plan.json", default_sound_design_plan())
    report = run_soundscape_verify(ctx, remux_cycle=0)
    assert report["verdict"] in {"pass", "warning", "remediate"}
    assert ctx.artifact_exists("sound_design/soundscape_report.json")
