"""Hosted VO floor aspirational — stretch then advisory-continue."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.floor_progress import has_floor_advisories
from interview_mux.gap_fill_eligibility import (
    count_active_gap_vo_lines,
    synthetic_vo_incompleteness,
)
from interview_mux.nugget_layup import raise_hosted_vo_floor_unsatisfiable
from interview_mux.seat_authority import hard_freeze_action_permitted
from interview_mux.vo_contract import (
    ensure_hosted_framing_vo_seats,
    revive_discarded_floor_candidates,
)
from run_fixtures import isolated_run_ctx, init_run_meta_for_test


def _write(ctx, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_revive_discarded_allowlisted_under_hard_freeze() -> None:
    assert hard_freeze_action_permitted("revive_discarded_floor_candidate")
    assert not hard_freeze_action_permitted("protect_hosted_vo_floor_reseat")


def test_raise_unsatisfiable_becomes_advisory(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "exec_vo_floor_adv")
    init_run_meta_for_test(ctx)
    # Should not raise when progress floors on (default).
    raise_hosted_vo_floor_unsatisfiable(ctx, need=3, active=2, eligible_nuggets=0)
    assert has_floor_advisories(ctx)
    meta = ctx.read_json("run_meta.json")
    assert meta.get("floor_aspirational_proceeded") is True
    assert not meta.get("hosted_vo_floor_unsatisfiable")


def test_synthetic_vo_incompleteness_clears_under_aspirational(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "exec_vo_floor_inc")
    init_run_meta_for_test(ctx)
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 3,
    )
    _write(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_a",
                    "text": "First host question about the topic.",
                    "delivery": "synthesize",
                    "targets_segment_id": "seg_001",
                },
                {
                    "line_id": "vo_b",
                    "text": "Second host question about the topic.",
                    "delivery": "synthesize",
                    "targets_segment_id": "seg_002",
                },
            ]
        },
    )
    assert count_active_gap_vo_lines(ctx) == 2
    assert synthetic_vo_incompleteness(ctx, "nugget_layup_compose") is None
    assert has_floor_advisories(ctx)


def test_revive_soft_omit_meets_floor(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "exec_vo_floor_revive")
    init_run_meta_for_test(ctx)
    lines = [
        {
            "line_id": "vo_a",
            "text": "First host question about the topic.",
            "delivery": "synthesize",
            "targets_segment_id": "seg_001",
        },
        {
            "line_id": "vo_b",
            "text": "Second host question about the topic.",
            "delivery": "synthesize",
            "targets_segment_id": "seg_002",
        },
        {
            "line_id": "vo_c",
            "text": "Third host question from discarded pile.",
            "delivery": "synthesize",
            "targets_segment_id": "seg_003",
            "skipped_optional": True,
            "air_script_omit": True,
            "air_script_omit_sync": True,
        },
    ]
    out, revived = revive_discarded_floor_candidates(ctx, lines, need=3)
    assert "vo_c" in revived
    assert sum(
        1
        for r in out
        if not r.get("skipped_optional")
        and not r.get("air_script_omit")
        and str(r.get("text") or "").strip()
    ) >= 3


def test_ensure_seats_hard_freeze_advisory_not_invent(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "exec_vo_floor_hf")
    init_run_meta_for_test(ctx)
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 3,
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.soft_freeze_active",
        lambda _ctx: False,
    )
    _write(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_a",
                    "text": "Only one seated host line on air.",
                    "delivery": "synthesize",
                    "targets_segment_id": "seg_001",
                },
            ]
        },
    )
    # No invent — returns without adding phantom lines.
    changed = ensure_hosted_framing_vo_seats(ctx)
    assert changed == [] or all(c for c in changed)
    gap = ctx.read_json("understanding/gap_report.json")
    active = [
        r
        for r in (gap.get("interviewer_lines") or [])
        if isinstance(r, dict)
        and not r.get("skipped_optional")
        and not r.get("air_script_omit")
        and str(r.get("text") or "").strip()
    ]
    assert len(active) == 1
    assert has_floor_advisories(ctx)


def test_i2_aspirational_continue_not_sanitary_dirt(tmp_path, monkeypatch) -> None:
    """have<need with pool exhausted → aspirational_continue must not 500 execute.

    Cascade for exec_13183: air_contract_needs_sanitize:hosted_vo_floor_aspirational_continue.
    """
    from interview_mux.artifact_sanitize.air_script import (
        air_contract_sanitary_errors,
        sanitize_air_contract,
    )

    ctx = isolated_run_ctx(tmp_path, "exec_i2_aspirational")
    init_run_meta_for_test(ctx)
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 3,
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.floor_progress.hosted_vo_aspirational",
        lambda _ctx: True,
    )
    _write(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_a",
                    "text": "First host question about the topic.",
                    "delivery": "synthesize",
                    "targets_segment_id": "seg_001",
                },
                {
                    "line_id": "vo_b",
                    "text": "Second host question about the topic.",
                    "delivery": "synthesize",
                    "targets_segment_id": "seg_002",
                },
            ]
        },
    )
    _write(
        ctx,
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": ["vo_a", "vo_b"],
                    "omitted_line_ids": [],
                }
            }
        },
    )
    dry = sanitize_air_contract(ctx)
    assert dry.ok
    assert any(
        a.get("action") == "hosted_vo_floor_aspirational_continue"
        for a in (dry.actions or [])
    )
    errs = air_contract_sanitary_errors(ctx)
    assert errs == [], errs
    assert not any("hosted_vo_floor_aspirational_continue" in e for e in errs)
