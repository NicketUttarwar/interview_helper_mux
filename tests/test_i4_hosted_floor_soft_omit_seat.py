"""Cascade: hosted floor must reseat soft-omitted context, not chase omit-wins.

MUX_FORENSICS=0 — exec_13181: 2 prefaces on air + omit-wins question +
air_script_omit_sync context → active stuck at 2; build_vo_seats auto-omitted
eligible body; filter ignored orientation toward need.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from interview_mux.air_script import build_vo_seats, filter_gap_lines_for_air_script
from interview_mux.gap_fill_eligibility import count_active_gap_vo_lines
from interview_mux.run_context import RunContext
from interview_mux.vo_contract import ensure_gap_line_on_air
from run_fixtures import init_run_meta_for_test, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext("exec_i4_floor_seat", create=True)
    init_run_meta_for_test(run)
    return run


def test_filter_and_build_seats_floor_with_prefaces(ctx: RunContext, monkeypatch) -> None:
    os.environ["MUX_FORENSICS"] = "0"
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 3,
    )
    monkeypatch.setattr("interview_mux.air_script.air_script_enabled", lambda: True)

    gap = {
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
                "line_id": "vo_preface_open_precision_oncology",
                "line_category": "episode_preface",
                "episode_orientation": True,
                "text": "Precision oncology is reshaping cancer care.",
                "delivery": "synthesize",
                "targets_segment_id": "seg_004",
                "required": True,
            },
            {
                "line_id": "vo_question_seg_009",
                "line_category": "framing_question",
                "text": "What should we hear next?",
                "delivery": "synthesize",
                "targets_segment_id": "seg_009",
                "skipped_optional": True,
                "air_script_omit": True,
                "skip_reason_code": "execution_contract_waive",
                "compensating_path": "tier_d_logged_waive",
            },
            {
                "line_id": "vo_context_seg_004",
                "line_category": "context_setup",
                "text": "A tissue biopsy samples the site; a liquid biopsy samples blood.",
                "delivery": "synthesize",
                "targets_segment_id": "seg_004",
                "skipped_optional": True,
                "air_script_omit": True,
                "skip_reason_code": "air_script_omit_sync",
            },
        ],
    }
    plan = {
        "air_script": {
            "enabled": True,
            "vo_seats": {
                "seated_line_ids": [
                    "vo_preface_seg_004",
                    "vo_preface_open_precision_oncology",
                ],
                "omitted_line_ids": ["vo_question_seg_009", "vo_context_seg_004"],
                "orientation_id": "vo_preface_seg_004",
            },
            "beats": [],
        }
    }
    monkeypatch.setattr(
        "interview_mux.air_script.load_air_script",
        lambda _plan: plan["air_script"],
    )

    filtered = filter_gap_lines_for_air_script(gap, plan, ctx=ctx)
    assert isinstance(filtered, dict)
    ctx_line = next(
        ln
        for ln in filtered["interviewer_lines"]
        if ln.get("line_id") == "vo_context_seg_004"
    )
    assert not ctx_line.get("air_script_omit"), ctx_line
    assert not ctx_line.get("skipped_optional"), ctx_line
    q = next(
        ln
        for ln in filtered["interviewer_lines"]
        if ln.get("line_id") == "vo_question_seg_009"
    )
    assert q.get("air_script_omit") or q.get("skipped_optional")

    seats = build_vo_seats(plan, filtered)
    assert "vo_context_seg_004" in set(seats.get("seated_line_ids") or [])
    assert "vo_question_seg_009" not in set(seats.get("seated_line_ids") or [])

    active = sum(
        1
        for ln in filtered["interviewer_lines"]
        if isinstance(ln, dict)
        and str(ln.get("delivery") or "").lower() == "synthesize"
        and str(ln.get("text") or "").strip()
        and not ln.get("skipped_optional")
        and not ln.get("air_script_omit")
    )
    assert active >= 3, (
        active,
        [
            (ln.get("line_id"), ln.get("skipped_optional"), ln.get("air_script_omit"))
            for ln in filtered["interviewer_lines"]
        ],
    )
