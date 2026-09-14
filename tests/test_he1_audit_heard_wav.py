"""HE-1: edl_narrative_audit requires seed-complete heard VO, not hollow done.

Do not start a run. HE-2 EDL playbook, HE-3 preview, F2 bind, HV-2/HV-4 stay as-is.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import seed_stage_complete
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    incompleteness_resume_stage,
    stage_artifact_incompleteness,
)
from interview_mux.stage_input_checks import (
    collect_stage_input_issues,
    compact_vo_coverage_stale_or_missing,
)
from interview_mux.stages.edl_narrative_audit import compact_vo_coverage
from run_fixtures import isolated_run_ctx, mark_done_raw

_LINE = "vo_heard_1"
_AUDIT = {
    "verdict": "pass",
    "blocking_issues": [],
    "warnings": [],
    "recommended_actions": [],
    "reasoning_summary": "fixture",
}


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "he1_audit")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _plant_seated_line(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": _LINE,
                    "text": "Heard line.",
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
                "vo_seats": {"seated_line_ids": [_LINE], "omitted_line_ids": []},
            },
        },
        skip_handoff=True,
    )


def test_he1_hollow_vo_blocks_audit_run(ctx: RunContext) -> None:
    mark_done_raw(ctx, "vo_synthesize")
    issues = collect_stage_input_issues(ctx, "edl_narrative_audit")
    assert any("seed-complete" in i.message for i in issues)
    assert seed_stage_complete(ctx, "vo_synthesize") is False


def test_he1_bind_exception_is_wav_stale_not_rendered(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant_seated_line(ctx)
    wav = ctx.final_path("vo_pickup") / f"{_LINE}.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" + b"\x00" * 64)
    monkeypatch.setattr(
        "interview_mux.vo_synthesis_audit.synthesis_entry_matches_line",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("bind boom")),
    )
    rows = compact_vo_coverage(ctx)
    assert rows and rows[0]["coverage"] == "wav_stale"
    assert rows[0]["script_match"] is False
    assert _LINE in compact_vo_coverage_stale_or_missing(ctx)


def test_he1_audit_json_not_seed_complete_while_vo_hollow(ctx: RunContext) -> None:
    ctx.write_json("master/edl_narrative_audit.json", _AUDIT, skip_handoff=True)
    mark_done_raw(ctx, "edl_narrative_audit")
    mark_done_raw(ctx, "vo_synthesize")
    reason = stage_artifact_incompleteness(ctx, "edl_narrative_audit")
    assert reason is not None
    assert "vo_synthesize" in reason
    assert seed_stage_complete(ctx, "edl_narrative_audit") is False
    assert incompleteness_resume_stage(ctx, "edl_narrative_audit") == "vo_synthesize"
