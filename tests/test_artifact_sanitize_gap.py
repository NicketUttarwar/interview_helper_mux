"""Tests for artifact_sanitize gap_report (W1 — no seat/omit authority)."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from interview_mux.artifact_sanitize.gap_report import (
    _line_target,
    sanitize_gap_report,
)
from interview_mux.artifact_sanitize.precedence import GAP_SANITIZE_FORBIDDEN_MUTATIONS
from interview_mux.run_context import RunContext


def _dump_raw(ctx: RunContext, rel: str, doc: dict) -> None:
    """Write JSON without schema validation (minimal sanitize fixtures)."""
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _write_selection(ctx: RunContext, ids: list[str]) -> None:
    ctx.path("master").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ids,
            "excluded_segment_ids": [],
            "chapters": [],
            "order_content_hash": "sel_hash_test",
        },
        skip_handoff=True,
    )


def test_line_target_prefers_targets_segment_id() -> None:
    row = {
        "targets_segment_id": "seg_a",
        "target_segment_id": "seg_wrong",
        "after_segment_id": "seg_b",
    }
    assert _line_target(row) == "seg_a"


def test_sanitize_gap_does_not_mutate_vo_seats_or_omit_ledger() -> None:
    ctx = RunContext(create=True)
    _write_selection(ctx, ["seg_001", "seg_002"])
    seats_before = {
        "seated_line_ids": ["vo_a", "vo_b"],
        "omitted_line_ids": ["vo_c"],
        "orientation_id": "vo_orient",
    }
    omit_before = {
        "entries": [{"subject_id": "vo_c", "kind": "gap_line", "status": "active"}]
    }
    _dump_raw(
        ctx,
        "mastering/mastering_plan.json",
        {"air_script": {"vo_seats": deepcopy(seats_before)}},
    )
    _dump_raw(ctx, "understanding/omit_ledger.json", deepcopy(omit_before))

    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_dup",
                "text": "hello there",
                "targets_segment_id": "seg_001",
                "placement": "before",
            },
            {
                "line_id": "vo_dup2",
                "text": "hello there",
                "targets_segment_id": "seg_001",
                "placement": "before",
            },
            {
                "line_id": "vo_off",
                "text": "off air",
                "targets_segment_id": "seg_999",
            },
        ],
        "gaps": [],
        "nugget_layup_authority": False,
    }
    result = sanitize_gap_report(ctx, gap)
    assert result.ok
    assert any(a.get("action") == "dedupe_text_target" for a in result.actions)
    assert any(a.get("action") == "drop_lines_off_air" for a in result.actions)

    plan = ctx.read_json("mastering/mastering_plan.json")
    assert plan["air_script"]["vo_seats"] == seats_before
    omit = ctx.read_json("understanding/omit_ledger.json")
    assert omit == omit_before
    assert "vo_seats" in GAP_SANITIZE_FORBIDDEN_MUTATIONS
    assert "omit_ledger_entries" in GAP_SANITIZE_FORBIDDEN_MUTATIONS


def test_sanitize_gap_dedupe_and_rebase_off_air() -> None:
    ctx = RunContext(create=True)
    _write_selection(ctx, ["seg_001", "seg_002"])
    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_1",
                "text": "same",
                "targets_segment_id": "seg_001",
                "placement": "before",
            },
            {
                "line_id": "vo_1",
                "text": "different",
                "targets_segment_id": "seg_002",
            },
            {
                "line_id": "vo_ghost",
                "text": "ghost",
                "targets_segment_id": "seg_gone",
            },
            {
                "line_id": "vo_orient",
                "text": "welcome",
                "episode_orientation": True,
                "targets_segment_id": "seg_gone",
            },
        ],
        "gaps": [
            {"after_segment_id": "seg_gone", "before_segment_id": "seg_also_gone"},
            {"after_segment_id": "seg_001", "before_segment_id": "seg_002"},
        ],
    }
    result = sanitize_gap_report(ctx, gap)
    assert result.ok
    lids = [r.get("line_id") for r in result.doc["interviewer_lines"]]
    assert lids.count("vo_1") == 1
    assert "vo_ghost" not in lids
    assert "vo_orient" in lids  # orientation kept even if off-air target
    assert len(result.doc["gaps"]) == 1


def test_sanitize_gap_typeerror_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = RunContext(create=True)
    _write_selection(ctx, ["seg_001"])

    def boom(*_a, **_k):
        raise TypeError("intentional clamp-style TypeError")

    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.gap_report.stamp_sanitize_meta",
        boom,
    )
    with pytest.raises(TypeError, match="intentional"):
        sanitize_gap_report(
            ctx,
            {"interviewer_lines": [{"line_id": "vo_a", "text": "x", "targets_segment_id": "seg_001"}]},
        )


def test_coverage_refuse_only_for_compose_thin_under_authority() -> None:
    ctx = RunContext(create=True)
    order = [f"seg_{i:03d}" for i in range(1, 11)]
    _write_selection(ctx, order)
    thin = {
        "nugget_layup_authority": True,
        "_meta": {"compose_thin": True},
        "interviewer_lines": [
            {
                "line_id": "vo_only",
                "text": "one line",
                "targets_segment_id": "seg_001",
            }
        ],
        "gaps": [],
    }
    refused = sanitize_gap_report(ctx, thin)
    assert not refused.ok
    assert any("layup_coverage_below_floor" in e for e in refused.errors)

    intentional_omits = {
        "nugget_layup_authority": True,
        # no compose_thin / partial status — Pass B style shrink must not refuse
        "interviewer_lines": [
            {
                "line_id": "vo_only",
                "text": "one line",
                "targets_segment_id": "seg_001",
            }
        ],
        "gaps": [],
    }
    ok = sanitize_gap_report(ctx, intentional_omits)
    assert ok.ok
    assert not any("layup_coverage_below_floor" in e for e in ok.errors)
