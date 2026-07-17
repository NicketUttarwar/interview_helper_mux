"""Pipeline gap-fill skip path — no LLM gap stages when ineligible."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.gap_fill_eligibility import GapFillDecision, gap_fill_was_skipped
from interview_mux.pipeline import _run_missing_framing_stage, _run_optimal_questions_stage
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, minimal_manifest, patch_merged_config


def test_missing_framing_auto_skips_without_llm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "gap_e2e")
    patch_merged_config(
        monkeypatch,
        {"analysis": {"gap_fill": {"enabled": True, "auto_skip_when_ineligible": True}}},
    )
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest("seg_001", "seg_002"),
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.assess_gap_fill_eligibility",
        lambda _ctx: GapFillDecision(
            eligible=False,
            reason="test ineligible",
            signals={"topology_class": "peer"},
        ),
    )
    llm_called = {"missing": False, "optimal": False}

    def _no_missing(_ctx: RunContext) -> None:
        llm_called["missing"] = True

    def _no_optimal(_ctx: RunContext) -> None:
        llm_called["optimal"] = True

    monkeypatch.setattr("interview_mux.pipeline.gaps.run_missing_framing", _no_missing)
    monkeypatch.setattr("interview_mux.pipeline.gaps.run_optimal_questions", _no_optimal)

    _run_missing_framing_stage(ctx)
    _run_optimal_questions_stage(ctx)

    assert gap_fill_was_skipped(ctx)
    assert ctx.is_done("missing_framing")
    assert ctx.is_done("optimal_questions")
    assert not llm_called["missing"]
    assert not llm_called["optimal"]
    assert ctx.artifact_exists("understanding/gap_report.json")
