"""Cascade: framing floor topup clears soft-omit wipe (exec_13196).

MUX_FORENSICS=0.
Also: pre-synth process soft-omit cannot peel below hosted floor need.
"""

from __future__ import annotations

import os

import pytest

os.environ["MUX_FORENSICS"] = "0"

from interview_mux.air_script import filter_gap_lines_for_air_script
from interview_mux.hosted_vo_authority import may_soft_omit_hosted_line
from interview_mux.nugget_layup import _count_active_synthetic_lines, _framing_floor_topup
from interview_mux.run_context import RunContext
from interview_mux.vo_contract import (
    clamp_hosted_seats_docs,
    mark_gap_line_not_on_air,
    repair_vo_contract_drift,
)
from run_fixtures import init_run_meta_for_test, isolated_run_ctx


def _synth_line(lid: str, seg: str, *, active: bool = True) -> dict:
    row = {
        "line_id": lid,
        "origin": "nugget_layup",
        "gap_type": "nugget_layup",
        "targets_segment_id": seg,
        "placement": "before",
        "delivery": "synthesize",
        "text": f"Host bridge for {seg}.",
        "required": True,
    }
    if not active:
        row["skipped_optional"] = True
        row["air_script_omit"] = True
        row["skip_reason_code"] = "air_script_omit_sync"
    return row


@pytest.fixture
def ctx(tmp_path, monkeypatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    c = isolated_run_ctx(tmp_path, "floor_soft_omit")
    init_run_meta_for_test(c)
    c._one_writer_raw = True
    c.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_037", "seg_040", "seg_041"],
            "excluded_segment_ids": [],
        },
        skip_handoff=True,
    )
    return c


def test_framing_floor_topup_clears_soft_omit_when_hollow(ctx: RunContext) -> None:
    prior = [
        {
            "line_id": "vo_layup_seg_037",
            "origin": "nugget_layup",
            "targets_segment_id": "seg_037",
            "placement": "before",
            "delivery": "synthesize",
            "text": "Why adaptive monitoring creates a regulatory path?",
            "skipped_optional": True,
            "air_script_omit": True,
            "omit": True,
            "skip_reason_code": "air_script_omit_sync",
        }
    ]
    out, restored = _framing_floor_topup(
        ctx,
        candidate_lines=[],
        prior_lines=prior,
        seen_targets=set(),
        need=3,
        plan={"layups": []},
    )
    assert restored == ["vo_layup_seg_037"]
    assert _count_active_synthetic_lines(out) == 1
    line = out[0]
    assert not line.get("skipped_optional")
    assert not line.get("air_script_omit")
    assert (line.get("_meta") or {}).get("framing_floor_soft_omit_cleared") is True


def test_may_soft_omit_refuses_below_floor_pre_synth(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _c: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _c: 3,
    )
    lines = [
        _synth_line("vo_a", "seg_037"),
        _synth_line("vo_b", "seg_040"),
        _synth_line("vo_c", "seg_041"),
    ]
    gap = {"interviewer_lines": lines}
    # Omitting one of three → active_after=2 < need=3 → refuse.
    assert (
        may_soft_omit_hosted_line(
            ctx,
            lines[0],
            gap_report=gap,
            reason_code="air_script_omit_sync",
            peer_lines=lines,
        )
        is False
    )
    stamped = mark_gap_line_not_on_air(
        lines[0],
        reason_code="air_script_omit_sync",
        ctx=ctx,
        gap_report=gap,
        peer_lines=lines,
    )
    assert not stamped.get("air_script_omit")
    assert not stamped.get("skipped_optional")


def test_filter_gap_lines_pre_synth_keeps_floor(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _c: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _c: 3,
    )
    monkeypatch.setattr("interview_mux.air_script.air_script_enabled", lambda: True)
    gap = {
        "interviewer_lines": [
            _synth_line("vo_a", "seg_037"),
            _synth_line("vo_b", "seg_040"),
            _synth_line("vo_c", "seg_041"),
        ]
    }
    # Empty seats → Pass B would omit all; floor gate must keep ≥ need active.
    plan = {"air_script": {"vo_seats": {"seated_line_ids": [], "omitted_line_ids": []}}}
    out = filter_gap_lines_for_air_script(gap, plan, ctx=ctx)
    assert out is not None
    active = sum(
        1
        for ln in (out.get("interviewer_lines") or [])
        if isinstance(ln, dict)
        and not ln.get("skipped_optional")
        and not ln.get("air_script_omit")
        and str(ln.get("text") or "").strip()
    )
    assert active >= 3


def test_repair_vo_contract_drift_pre_synth_no_process_omit(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _c: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _c: 3,
    )
    lines = [
        _synth_line("vo_a", "seg_037"),
        _synth_line("vo_b", "seg_040"),
        _synth_line("vo_c", "seg_041"),
    ]
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": lines},
        skip_handoff=True,
    )
    # Unseated in plan — drift repair must not process-omit below floor.
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": [],
                    "omitted_line_ids": ["vo_a", "vo_b", "vo_c"],
                }
            }
        },
        skip_handoff=True,
    )
    repair_vo_contract_drift(ctx)
    gap = ctx.read_json("understanding/gap_report.json")
    active = sum(
        1
        for ln in (gap.get("interviewer_lines") or [])
        if isinstance(ln, dict)
        and not ln.get("skipped_optional")
        and not ln.get("air_script_omit")
        and str(ln.get("text") or "").strip()
    )
    assert active >= 3


def test_clamp_pre_synth_is_noop(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _c: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _c: 3,
    )
    gap = {
        "interviewer_lines": [
            _synth_line("vo_a", "seg_037"),
            _synth_line("vo_b", "seg_040"),
            _synth_line("vo_c", "seg_041"),
            _synth_line("vo_d", "seg_037"),
        ]
    }
    out, unseated = clamp_hosted_seats_docs(ctx, gap, apply_freeze_gate=False)
    assert unseated == []
    assert out is gap or out.get("interviewer_lines") == gap["interviewer_lines"]


def test_clamp_post_synth_still_omits_non_wav(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _c: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _c: 3,
    )
    # Mark vo_synthesize done so clamp era is open.
    done = ctx.path(".stage_done")
    done.mkdir(parents=True, exist_ok=True)
    (done / "vo_synthesize").write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "interview_mux.vo_contract._gap_row_has_pickup_stem",
        lambda _ctx, row: str(row.get("line_id") or "") in {"vo_a", "vo_b", "vo_c"},
    )
    gap = {
        "interviewer_lines": [
            _synth_line("vo_a", "seg_037"),
            _synth_line("vo_b", "seg_040"),
            _synth_line("vo_c", "seg_041"),
            _synth_line("vo_d", "seg_037"),
        ]
    }
    out, unseated = clamp_hosted_seats_docs(ctx, gap, apply_freeze_gate=False)
    assert "vo_d" in unseated
    by_id = {
        str(r.get("line_id")): r
        for r in (out.get("interviewer_lines") or [])
        if isinstance(r, dict)
    }
    assert by_id["vo_d"].get("air_script_omit") is True
    assert not by_id["vo_a"].get("air_script_omit")
