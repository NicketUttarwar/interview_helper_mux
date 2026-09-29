"""A layup typed skip satisfies the high-gap lint under layup authority (ISSUES 69)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.deterministic_lint import _lint_optimal_questions
from interview_mux.run_context import RunContext


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, skip_row: dict) -> RunContext:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_high_gap_layup", create=True)
    for rel, doc in (
        ("understanding/gap_evaluations.json", {"evaluations": [{"segment_id": "seg_059", "severity": "high"}]}),
        ("master/selection.json", {"ordered_segment_ids": ["seg_058", "seg_059"]}),
        ("understanding/nugget_layup_plan.json", {"layups": [skip_row]}),
    ):
        path = ctx.path(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        import json

        path.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(
        "interview_mux.artifact_repairs._segment_is_blank_or_unusable", lambda c, s: False
    )
    return ctx


def _high_gap_errors(ctx: RunContext, authority: bool) -> list[str]:
    report = {"interviewer_lines": [], "nugget_layup_authority": authority}
    return [e for e in _lint_optimal_questions(report, ctx) if "has no interviewer line" in e]


def test_typed_skip_is_a_decision_under_layup_authority(tmp_path, monkeypatch) -> None:
    ctx = _ctx(
        tmp_path,
        monkeypatch,
        {"target_segment_id": "seg_059", "skip": True, "skip_reason_code": "no_eligible_unspent_nugget"},
    )
    assert _high_gap_errors(ctx, authority=True) == []


def test_without_layup_authority_the_line_is_still_owed(tmp_path, monkeypatch) -> None:
    ctx = _ctx(
        tmp_path,
        monkeypatch,
        {"target_segment_id": "seg_059", "skip": True, "skip_reason_code": "no_eligible_unspent_nugget"},
    )
    assert _high_gap_errors(ctx, authority=False)


def test_untyped_skip_is_not_a_decision(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch, {"target_segment_id": "seg_059", "skip": True})
    assert _high_gap_errors(ctx, authority=True)
