"""R1: opening orientation heal pins edl_heal_resume_stage; producer HARD separate."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import edl_heal_resume_stage, stage_artifact_incompleteness
from run_fixtures import isolated_run_ctx

_ROOT = Path(__file__).resolve().parents[1]
_TOOLS = _ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import full_auto_driver as driver  # noqa: E402

_LINE = "vo_preface_episode_orientation"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "r1_orient")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _plant_unsanitary(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "opening_orientation": {
                "line_id": _LINE,
                "required": True,
                "target_segment_id": "seg_001",
            },
            "interviewer_lines": [
                {
                    "line_id": _LINE,
                    "text": "Before the science, meet the founder at the center.",
                    "delivery": "synthesize",
                    "required": True,
                    "episode_orientation": True,
                    "line_category": "episode_preface",
                    "placement": "before",
                    "targets_segment_id": "seg_001",
                    "orientation_missions": [
                        "guest_identity",
                        "conversation_topic",
                        "listener_stakes",
                    ],
                }
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "version": 1,
            "plan_status": "complete",
            "air_script": {
                "beats": [{"beat_id": "b1"}],
                "vo_seats": {"seated_line_ids": [_LINE], "omitted_line_ids": []},
            },
        },
        skip_handoff=True,
    )


def test_edl_heal_resume_stage_unsanitary_pins_vo_synthesize(ctx: RunContext) -> None:
    _plant_unsanitary(ctx)
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_001"],
            "timeline_duration_ms": 0,
            "clips": [],
        },
        skip_handoff=True,
    )
    assert edl_heal_resume_stage(ctx) == "vo_synthesize"


def test_edl_heal_resume_stage_sanitary_pins_edl(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": []},
        skip_handoff=True,
    )
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_001"],
            "timeline_duration_ms": 0,
            "clips": [],
        },
        skip_handoff=True,
    )
    assert edl_heal_resume_stage(ctx) == "edl"


def test_orientation_contract_heal_resume_producer_vs_consumer(ctx: RunContext) -> None:
    driver._ORIENTATION_EDL_RESUMES = 0
    driver._ORIENTATION_PRODUCER_RESUMES = 0
    _plant_unsanitary(ctx)
    pin, hard = driver.orientation_contract_heal_resume(ctx)
    assert pin == "vo_synthesize"
    assert hard is False
    assert driver._ORIENTATION_PRODUCER_RESUMES == 1
    assert driver._ORIENTATION_EDL_RESUMES == 0

    pin2, hard2 = driver.orientation_contract_heal_resume(ctx)
    assert pin2 == "vo_synthesize"
    assert hard2 is True
    assert driver._ORIENTATION_PRODUCER_RESUMES == 2

    # Sanitary consumer rebuild must not burn producer HARD.
    driver._ORIENTATION_EDL_RESUMES = 0
    driver._ORIENTATION_PRODUCER_RESUMES = 0
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": []},
        skip_handoff=True,
    )
    pin3, hard3 = driver.orientation_contract_heal_resume(ctx)
    assert pin3 == "edl"
    assert hard3 is False
    assert driver._ORIENTATION_EDL_RESUMES == 1
    assert driver._ORIENTATION_PRODUCER_RESUMES == 0


def test_required_orientation_without_wav_refuses_edl_seed_complete(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from run_fixtures import mark_done_raw

    # Isolate the orientation-inaudible gate from earlier VO bind checks.
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.registry.vo_sanitary_errors",
        lambda _ctx: [],
    )
    monkeypatch.setattr(
        "interview_mux.stage_input_checks.compact_vo_coverage_stale_or_missing",
        lambda _ctx: [],
    )
    monkeypatch.setattr(
        "interview_mux.transition_vo.seated_vo_paths_missing",
        lambda _ctx: [],
    )
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "homunculus_kind": "homunculus",
            "gap_framing_enabled": True,
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "opening_orientation": {
                "line_id": _LINE,
                "required": True,
                "target_segment_id": "seg_001",
            },
            "interviewer_lines": [
                {
                    "line_id": _LINE,
                    "text": (
                        "Before the science, meet the founder at the center of "
                        "this conversation."
                    ),
                    "delivery": "synthesize",
                    "required": True,
                    "episode_orientation": True,
                    "line_category": "episode_preface",
                    "placement": "before",
                    "targets_segment_id": "seg_001",
                    "orientation_missions": [
                        "guest_identity",
                        "conversation_topic",
                        "listener_stakes",
                    ],
                }
            ],
        },
        skip_handoff=True,
    )
    # Hollow EDL: orientation required but no vo_pickup clip / WAV.
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_001"],
            "timeline_duration_ms": 1000,
            "clips": [],
        },
        skip_handoff=True,
    )
    mark_done_raw(ctx, "edl")
    reason = stage_artifact_incompleteness(ctx, "edl")
    assert reason is not None
    assert "opening_orientation_inaudible" in reason
    assert seed_stage_complete(ctx, "edl") is False
