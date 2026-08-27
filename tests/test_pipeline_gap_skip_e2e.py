"""Pipeline gap-fill: opt-in auto-skip vs default hard-stop when ineligible."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.gap_fill_eligibility import GapFillDecision, gap_fill_was_skipped
from interview_mux.loud_fail import LoudStageFailure
from interview_mux.pipeline import (
    _run_gap_framing_compose_stage,
    _run_missing_framing_stage,
    _run_optimal_questions_stage,
)
from interview_mux.run_context import RunContext
from interview_mux.session_log import read_log
from run_fixtures import isolated_run_ctx, minimal_manifest


def test_missing_framing_auto_skips_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "gap_e2e")
    # Local import inside _run_missing_framing_stage — patch the source module.
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.gap_fill_auto_skip_enabled",
        lambda cfg=None: True,
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


def test_missing_framing_hard_stops_when_ineligible_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "gap_hard")
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.gap_fill_auto_skip_enabled",
        lambda cfg=None: False,
    )
    monkeypatch.setattr(
        "interview_mux.pipeline._skip_ineligible_gap_fill_unattended",
        lambda _ctx: False,
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
            reason="No frame/interviewer speaker identified — skip gap-fill VO",
            signals={"skip_signal": "zero_frame_speakers"},
        ),
    )
    llm_called = {"missing": False}

    def _no_missing(_ctx: RunContext) -> None:
        llm_called["missing"] = True

    monkeypatch.setattr("interview_mux.pipeline.gaps.run_missing_framing", _no_missing)

    with pytest.raises(LoudStageFailure, match="not eligible"):
        _run_missing_framing_stage(ctx)

    assert not llm_called["missing"]
    assert not gap_fill_was_skipped(ctx)
    errors = [e for e in read_log(ctx.run_dir) if e.get("level") == "error"]
    assert any("not eligible" in e.get("message", "").lower() for e in errors)


def test_missing_framing_full_auto_does_not_skip_hosted_ineligible_signals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "gap_full_auto")
    ctx.write_json(
        "run_meta.json",
        {"run_mode": "full-auto", "full_auto": True, "homunculus_version": "0.1.0"},
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.gap_fill_auto_skip_enabled",
        lambda cfg=None: False,
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
            reason="Frame speaker confidence below 0.65 — skip gap-fill VO",
            signals={"skip_signal": "low_frame_confidence"},
        ),
    )
    llm_called = {"missing": False}

    def _no_missing(_ctx: RunContext) -> None:
        llm_called["missing"] = True

    monkeypatch.setattr("interview_mux.pipeline.gaps.run_missing_framing", _no_missing)

    with pytest.raises(LoudStageFailure, match="not eligible"):
        _run_missing_framing_stage(ctx)

    assert not llm_called["missing"]
    assert not gap_fill_was_skipped(ctx)


def test_missing_framing_full_auto_skips_true_monologue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "gap_full_auto_mono")
    ctx.write_json(
        "run_meta.json",
        {"run_mode": "full-auto", "full_auto": True, "homunculus_version": "0.1.0"},
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.gap_fill_auto_skip_enabled",
        lambda cfg=None: False,
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
            reason="True monologue — no interviewer frame for gap-fill VO",
            signals={"skip_signal": "true_monologue"},
        ),
    )
    llm_called = {"missing": False}

    def _no_missing(_ctx: RunContext) -> None:
        llm_called["missing"] = True

    monkeypatch.setattr("interview_mux.pipeline.gaps.run_missing_framing", _no_missing)

    _run_missing_framing_stage(ctx)

    assert gap_fill_was_skipped(ctx)
    assert not llm_called["missing"]


def test_gap_framing_compose_skip_rewrites_discarded_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.stages.gaps import ensure_gap_fill_skipped

    ctx = isolated_run_ctx(tmp_path, "compose_skip_restore")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest("seg_001", "seg_002"),
        skip_handoff=True,
    )
    ensure_gap_fill_skipped(ctx, reason="low_frame_confidence", signals={})
    ctx.path("understanding", "gap_report.json").unlink(missing_ok=True)
    assert not ctx.artifact_exists("understanding/gap_report.json")

    _run_gap_framing_compose_stage(ctx)

    assert ctx.artifact_exists("understanding/gap_report.json")
    report = ctx.read_json("understanding/gap_report.json")
    assert report.get("interviewer_lines") == []
