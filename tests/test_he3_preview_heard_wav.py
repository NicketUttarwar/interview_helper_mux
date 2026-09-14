"""HE-3: assembly_preview must not skip-then-stamp unsourced heard glue.

Do not start a run. HE-1 audit, HE-2 EDL playbook, F2 bind, F4 classify stay.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.heal_routing import classify_heal_error
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    assembly_preview_unsourced_glue_ids,
    incompleteness_resume_stage,
    producer_pin_for_token,
    stage_artifact_incompleteness,
)
from interview_mux.stage_input_checks import collect_stage_input_issues
from interview_mux.stages import assembly
from interview_mux.thrash_hardening import heal_navigate
from run_fixtures import isolated_run_ctx, mark_done_raw

_PAIR = "seg_001->seg_002"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "he3_preview")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _edl(*, unsourced_spoken: bool = False, seated_vo: bool = False) -> dict:
    clips: list[dict] = [
        {
            "type": "speech",
            "segment_id": "seg_001",
            "source_start_ms": 0,
            "source_end_ms": 1000,
            "timeline_start_ms": 0,
            "duration_ms": 1000,
        }
    ]
    if unsourced_spoken:
        clips.append(
            {
                "type": "transition",
                "after_segment_id": "seg_001",
                "before_segment_id": "seg_002",
                "text": "Heard glue before the next beat.",
                "timeline_start_ms": 1000,
                "duration_ms": 0,
            }
        )
    if seated_vo:
        clips.append(
            {
                "type": "vo_pickup",
                "line_id": "vo_edl_1",
                "targets_segment_id": "seg_001",
                "placement": "before",
                "timeline_start_ms": 0,
                "duration_ms": 0,
            }
        )
    return {
        "version": 1,
        "ordered_segment_ids": ["seg_001", "seg_002"],
        "timeline_duration_ms": 1000,
        "clips": clips,
    }


def _plant_preview_wav(ctx: RunContext) -> None:
    wav = ctx.path("master", "assembly_preview.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" + b"\x00" * 64)


def _plant_unsanitary_seated(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_edl_1",
                    "text": "Need a heard WAV.",
                    "delivery": "synthesize",
                    "required": True,
                    "placement": "before",
                    "targets_segment_id": "seg_001",
                }
            ]
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
                "vo_seats": {"seated_line_ids": ["vo_edl_1"], "omitted_line_ids": []},
            },
        },
        skip_handoff=True,
    )


def test_he3_unsourced_spoken_glue_ids() -> None:
    edl = _edl(unsourced_spoken=True)
    assert _PAIR in assembly_preview_unsourced_glue_ids(edl)
    empty_seat = _edl()
    empty_seat["clips"].append(
        {
            "type": "transition",
            "after_segment_id": "seg_001",
            "before_segment_id": "seg_002",
            "text": "",
            "timeline_start_ms": 1000,
            "duration_ms": 0,
        }
    )
    assert assembly_preview_unsourced_glue_ids(empty_seat) == []


def test_he3_run_preview_refuses_unsourced_spoken_transition(tmp_path: Path) -> None:
    run_dir = tmp_path / "he3_preview_refuse"
    (run_dir / "ingest").mkdir(parents=True)
    (run_dir / "master").mkdir(parents=True)
    (run_dir / "ingest" / "normalized.wav").write_bytes(b"\x00")
    edl = _edl(unsourced_spoken=True)

    class FakeCtx:
        def __init__(self) -> None:
            self.run_dir = run_dir
            self.done: list[str] = []

        def read_json(self, rel: str) -> dict:
            return edl

        def path(self, *parts: str) -> Path:
            return self.run_dir.joinpath(*parts)

        def read_path(self, *parts: str) -> Path:
            return self.path(*parts)

        def log(self, *args, **kwargs) -> None:
            return None

        def mark_done(self, stage: str) -> None:
            self.done.append(stage)

        def artifact_exists(self, rel: str) -> bool:
            return False

    with pytest.raises(RuntimeError, match="vo_synthesize"):
        assembly.run_preview(FakeCtx())


def test_he3_speech_only_preview_wav_not_seed_complete(ctx: RunContext) -> None:
    ctx.write_json("master/edl.json", _edl(unsourced_spoken=True), skip_handoff=True)
    _plant_preview_wav(ctx)
    mark_done_raw(ctx, "assembly_preview")
    reason = stage_artifact_incompleteness(ctx, "assembly_preview")
    assert reason is not None
    assert "resume vo_synthesize" in reason
    assert seed_stage_complete(ctx, "assembly_preview") is False
    assert incompleteness_resume_stage(ctx, "assembly_preview") == "vo_synthesize"
    assert incompleteness_resume_stage(ctx, "assembly_preview") != "edl"
    issues = collect_stage_input_issues(ctx, "assembly_preview")
    assert any("missing WAV" in i.message or "vo_synthesize" in (i.related_stage or "") for i in issues)


def test_he3_unsanitary_bind_blocks_preview_complete(ctx: RunContext) -> None:
    _plant_unsanitary_seated(ctx)
    ctx.write_json("master/edl.json", _edl(), skip_handoff=True)
    _plant_preview_wav(ctx)
    mark_done_raw(ctx, "assembly_preview")
    reason = stage_artifact_incompleteness(ctx, "assembly_preview")
    assert reason is not None
    assert "VO coverage not rendered" in reason
    assert seed_stage_complete(ctx, "assembly_preview") is False
    issues = collect_stage_input_issues(ctx, "assembly_preview")
    assert any("VO coverage not rendered" in i.message for i in issues)


def test_he3_heal_pins_vo_synthesize_not_edl(ctx: RunContext) -> None:
    ctx.write_json("master/edl.json", _edl(unsourced_spoken=True), skip_handoff=True)
    reason = stage_artifact_incompleteness(ctx, "assembly_preview")
    assert reason is not None
    assert producer_pin_for_token(reason, ctx=ctx) == "vo_synthesize"
    route = classify_heal_error(reason, ctx, stage="assembly_preview")
    assert route is not None
    assert route.from_stage == "vo_synthesize"
    assert route.from_stage != "edl"
    nav = heal_navigate(ctx, error=reason, stage="assembly_preview")
    assert nav["from_stage"] == "vo_synthesize"
    assert nav["from_stage"] != "edl"
