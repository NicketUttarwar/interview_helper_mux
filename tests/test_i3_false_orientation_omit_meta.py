"""Cascade: non-orientation tier-D waive must not flip opening_orientation omit.

MUX_FORENSICS=0 — exec_13181: waived_line_id=vo_question_* stamped
opening_orientation.required=false → preface omit-sync → hosted_vo_floor 2<3
and premature hitch thrash.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from interview_mux.artifact_repairs import repair_gap_report
from interview_mux.execution_contract import VoViolation, _tier_d_logged_waive
from interview_mux.gap_fill_eligibility import count_active_gap_vo_lines
from interview_mux.opening_orientation import (
    is_episode_orientation,
    orientation_omitted,
    repair_false_orientation_omit_from_non_orient_waive,
)
from interview_mux.run_context import RunContext
from run_fixtures import init_run_meta_for_test, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext("exec_i3_orient_meta", create=True)
    init_run_meta_for_test(run)
    return run


def _gap_with_preface_and_question() -> dict:
    return {
        "opening_orientation": {
            "required": True,
            "omitted": False,
            "line_id": "vo_preface_seg_004",
        },
        "interviewer_lines": [
            {
                "line_id": "vo_preface_seg_004",
                "line_category": "episode_preface",
                "episode_orientation": True,
                "text": "Let's hear how that opening beat lands.",
                "delivery": "synthesize",
                "targets_segment_id": "seg_004",
                "required": True,
            },
            {
                "line_id": "vo_question_seg_009",
                "line_category": "framing_question",
                "text": "What should we listen for next?",
                "delivery": "synthesize",
                "targets_segment_id": "seg_009",
            },
            {
                "line_id": "vo_context_seg_004",
                "line_category": "context_setup",
                "text": "A tissue biopsy samples the site; a liquid biopsy samples blood.",
                "delivery": "synthesize",
                "targets_segment_id": "seg_004",
            },
            {
                "line_id": "vo_context_seg_016",
                "line_category": "extracted_context",
                "text": "Cancer data arrives in separate layers from DNA to proteins.",
                "delivery": "synthesize",
                "targets_segment_id": "seg_016",
            },
        ],
    }


def test_tier_d_non_orient_waive_does_not_flip_orientation_meta(ctx: RunContext) -> None:
    os.environ["MUX_FORENSICS"] = "0"
    gap = _gap_with_preface_and_question()
    ctx.write_json("understanding/gap_report.json", gap)
    v = VoViolation(
        "unknown",
        line_id="vo_question_seg_009",
        detail="test non-orient waive",
    )
    _tier_d_logged_waive(ctx, v)
    out = ctx.read_json("understanding/gap_report.json")
    assert orientation_omitted(out) is False, out.get("opening_orientation")
    meta = out.get("opening_orientation") or {}
    assert meta.get("required") is True
    assert meta.get("omitted") is not True
    preface = next(
        ln
        for ln in out["interviewer_lines"]
        if ln.get("line_id") == "vo_preface_seg_004"
    )
    assert is_episode_orientation(preface)
    assert not preface.get("air_script_omit")
    assert not preface.get("skipped_optional")
    q = next(
        ln for ln in out["interviewer_lines"] if ln.get("line_id") == "vo_question_seg_009"
    )
    assert q.get("air_script_omit") or q.get("skipped_optional")


def test_repair_false_orientation_omit_revives_preface_floor(ctx: RunContext) -> None:
    os.environ["MUX_FORENSICS"] = "0"
    dirty = _gap_with_preface_and_question()
    dirty["opening_orientation"] = {
        "required": False,
        "omitted": True,
        "omit_reason": "execution_contract_waive",
        "waived_line_id": "vo_question_seg_009",
        "compensating_path": "tier_d_logged_waive",
    }
    dirty["interviewer_lines"][0]["skipped_optional"] = True
    dirty["interviewer_lines"][0]["air_script_omit"] = True
    dirty["interviewer_lines"][0]["skip_reason_code"] = "execution_contract_waive"
    dirty["interviewer_lines"][1]["skipped_optional"] = True
    dirty["interviewer_lines"][1]["air_script_omit"] = True

    fixed, notes = repair_false_orientation_omit_from_non_orient_waive(dirty)
    assert any(n.get("action") == "clear_false_orientation_omit_meta" for n in notes)
    assert orientation_omitted(fixed) is False
    preface = next(
        ln
        for ln in fixed["interviewer_lines"]
        if ln.get("line_id") == "vo_preface_seg_004"
    )
    assert not preface.get("air_script_omit")
    assert not preface.get("skipped_optional")
    # Preface revived + two context lines still active → floor ≥3 in-memory.
    active_mem = sum(
        1
        for ln in fixed["interviewer_lines"]
        if isinstance(ln, dict)
        and not ln.get("skipped_optional")
        and not ln.get("air_script_omit")
        and str(ln.get("delivery") or "").lower() == "synthesize"
        and str(ln.get("text") or "").strip()
    )
    assert active_mem >= 3, active_mem

    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_004", "seg_009", "seg_016"]},
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_004",
                    "text": "a",
                    "type": "interviewer_question",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewer",
                    "topic_tags": ["a"],
                    "start_ms": 0,
                    "end_ms": 1000,
                },
                {
                    "segment_id": "seg_009",
                    "text": "b",
                    "type": "interviewee_answer",
                    "speaker_id": "spk_1",
                    "speaker_role": "interviewee",
                    "topic_tags": ["b"],
                    "start_ms": 1000,
                    "end_ms": 2000,
                },
                {
                    "segment_id": "seg_016",
                    "text": "c",
                    "type": "interviewee_answer",
                    "speaker_id": "spk_1",
                    "speaker_role": "interviewee",
                    "topic_tags": ["c"],
                    "start_ms": 2000,
                    "end_ms": 3000,
                },
            ]
        },
    )
    repaired, rnotes = repair_gap_report(ctx, dirty)
    assert any(
        n.get("action") == "clear_false_orientation_omit_meta" for n in rnotes
    ), rnotes
    assert orientation_omitted(repaired) is False
    preface2 = next(
        ln
        for ln in repaired["interviewer_lines"]
        if ln.get("line_id") == "vo_preface_seg_004"
    )
    assert not preface2.get("air_script_omit")
    assert not preface2.get("skipped_optional")
    ctx.write_json("understanding/gap_report.json", fixed)
    assert count_active_gap_vo_lines(ctx) >= 3

