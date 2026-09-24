"""Residual harden patches R1–R8 for gap_framing_compose (no soak)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.high_gap_vo import (
    fill_uncovered_high_gaps,
    seed_uncovered_high_gaps_deterministic,
)
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import _gap_evals_warrant_hosted_vo
from run_fixtures import init_run_meta_for_test, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext("exec_residual_harden", create=True)
    init_run_meta_for_test(run)
    return run


def _eval(sid: str, *, confusion: str = "Why does this matter for the listener?") -> dict:
    return {
        "segment_id": sid,
        "severity": "high",
        "gap_type": "missing_setup",
        "self_explanatory": False,
        "listener_confusion": confusion,
    }


def _seg(sid: str) -> dict:
    return {
        "segment_id": sid,
        "type": "interviewee_answer",
        "speaker_id": "spk_1",
        "speaker_role": "interviewee",
        "topic_tags": [],
        "text": "Native beat from tape about the snack brand.",
        "start_ms": 0,
        "end_ms": 1000,
    }


def test_r1_deterministic_seed_covers_high_without_api_key(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    ctx.write_json(
        "understanding/gap_evaluations.json",
        {"evaluations": [_eval("seg_033"), _eval("seg_034")]},
    )
    ctx.write_json("segments/manifest.json", {"segments": [_seg("seg_033"), _seg("seg_034")]})
    out: dict = {"interviewer_lines": []}
    applied: list = []
    n = fill_uncovered_high_gaps(ctx, out, applied=applied, origin="test_fill")
    assert n >= 2
    lids = {str(r.get("line_id")) for r in out["interviewer_lines"]}
    assert "vo_seed_seg_033" in lids
    assert "vo_seed_seg_034" in lids
    assert any(a.get("action") == "high_gap_vo_seed" for a in applied)


def test_r1_seed_helper_alone(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/gap_evaluations.json",
        {"evaluations": [_eval("seg_001")]},
    )
    out: dict = {"interviewer_lines": []}
    applied: list = []
    n = seed_uncovered_high_gaps_deterministic(ctx, out, applied=applied)
    assert n == 1
    text = out["interviewer_lines"][0]["text"]
    assert "next" in text.lower() or "?" in text


def test_r4_any_missing_type_warrants(ctx: RunContext) -> None:
    from interview_mux.gap_vo_gates import set_gap_framing_enabled

    set_gap_framing_enabled(ctx, True)
    ctx.write_json(
        "understanding/gap_evaluations.json",
        {
            "evaluations": [
                {
                    "segment_id": "seg_001",
                    "severity": "low",
                    "gap_type": "missing_context",
                    "self_explanatory": False,
                    "listener_confusion": "short",
                }
            ]
        },
    )
    assert _gap_evals_warrant_hosted_vo(ctx) is True


def test_r8_keep_context_setup_on_spoken_omit(ctx: RunContext) -> None:
    from interview_mux.artifact_repairs import repair_gap_report

    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_009"]},
    )
    ctx.write_json(
        "segments/manifest.json",
        {"segments": [_seg("seg_009")]},
    )
    doc = {
        "interviewer_lines": [
            {
                "line_id": "vo_context_seg_009",
                "line_category": "context_setup",
                "targets_segment_id": "seg_009",
                "text": (
                    "Liquid biopsy looks for cancer-related material in blood, "
                    "where tumour DNA can be mixed with DNA from normal dying cells."
                ),
                "delivery": "synthesize",
                "rationale": "orient the listener before the clip",
            }
        ]
    }
    repaired, notes = repair_gap_report(ctx, doc)
    lines = repaired.get("interviewer_lines") or []
    # Must not silently empty — keep or seed.
    assert lines, f"expected kept framing line, notes={notes[:8]}"


def test_r3_rebudget_after_selection(ctx: RunContext) -> None:
    from interview_mux.gap_vo_gates import set_gap_framing_enabled
    from interview_mux.gap_vo_rebudget import note_gap_vo_rebudget_after_selection

    set_gap_framing_enabled(ctx, True)
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001", "seg_002", "seg_003", "seg_004"]},
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [{"line_id": "l1", "text": "hi", "delivery": "synthesize"}]},
    )
    doc = note_gap_vo_rebudget_after_selection(ctx)
    assert doc is not None
    assert doc["ordered_n"] == 4
    assert doc["vo_line_budget"]["scale_basis"] == "selection"
    assert ctx.artifact_exists("understanding/gap_vo_rebudget_after_selection.json")


def test_r5_shape_plan_admit_missing(ctx: RunContext) -> None:
    from interview_mux.gap_vo_gates import set_gap_framing_enabled
    from interview_mux.pipeline import _compose_shape_plan_admit_reason

    set_gap_framing_enabled(ctx, True)
    reason = _compose_shape_plan_admit_reason(ctx)
    assert reason is not None
    assert "mastering_plan" in reason


def test_r5_shape_plan_admit_ok_with_degraded(ctx: RunContext) -> None:
    from interview_mux.pipeline import _compose_shape_plan_admit_reason

    ctx.write_json(
        "mastering/mastering_plan.json",
        {"plan_status": "degraded", "narrative_mode": "montage"},
    )
    assert _compose_shape_plan_admit_reason(ctx) is None
