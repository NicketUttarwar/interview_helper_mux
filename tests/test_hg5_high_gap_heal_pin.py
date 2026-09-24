"""HG-5: high_gap_unframed pins the live writer, not compose-under-layup.

Do not start a run. HG-1 sticky Yes and F3 skip/omit stay open/closed as-is.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.heal_routing import classify_heal_error, resume_stage_for_error_class
from interview_mux.recovery_controller import (
    handle_stage_failure,
    playbook_high_gap_unframed,
)
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import high_gap_heal_resume_stage, producer_pin_for_token
from interview_mux.thrash_hardening import heal_navigate
from run_fixtures import isolated_run_ctx, minimal_gap_evaluations, minimal_gap_line, minimal_gap_report

_HIGH_ERR = "high gap segment seg_001 has no interviewer line"
_HIGH_EVAL = {
    "segment_id": "seg_001",
    "self_explanatory": False,
    "gap_type": "missing_setup",
    "listener_confusion": "who is speaking",
    "severity": "high",
}


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    run = isolated_run_ctx(tmp_path, "hg5_high_gap")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_hg5_no_layup_pins_compose(ctx: RunContext) -> None:
    assert high_gap_heal_resume_stage(ctx) == "gap_framing_compose"
    assert high_gap_heal_resume_stage(None) == "gap_framing_compose"
    assert producer_pin_for_token(_HIGH_ERR, ctx=ctx) == "gap_framing_compose"
    assert producer_pin_for_token("high_gap_unframed") == "gap_framing_compose"
    assert resume_stage_for_error_class("high_gap_unframed") == "gap_framing_compose"


def test_hg5_plan_on_disk_pins_layup_not_compose(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/nugget_layup_plan.json",
        {"ordered_segment_ids": ["seg_001"], "layups": []},
        skip_handoff=True,
    )
    assert high_gap_heal_resume_stage(ctx) == "nugget_layup_compose"
    assert producer_pin_for_token(_HIGH_ERR, ctx=ctx) == "nugget_layup_compose"
    assert producer_pin_for_token(_HIGH_ERR, ctx=ctx) != "gap_framing_compose"


def test_hg5_authority_without_plan_pins_compose(ctx: RunContext) -> None:
    """Orphan stamp (no plan) is not layup ownership — pin analysis-era compose."""
    ctx.write_json(
        "understanding/gap_report.json",
        {**minimal_gap_report(), "nugget_layup_authority": True},
        skip_handoff=True,
    )
    assert high_gap_heal_resume_stage(ctx) == "gap_framing_compose"


def test_hg5_probe_error_with_stamp_only_pins_compose(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stamp without plan never routes to layup even if authority helper booms."""
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled",
        lambda: True,
    )

    def _boom(*_a, **_k):
        raise RuntimeError("simulated layup authority probe failure")

    monkeypatch.setattr(
        "interview_mux.nugget_layup.gap_report_has_layup_authority",
        _boom,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {**minimal_gap_report(), "nugget_layup_authority": True},
        skip_handoff=True,
    )
    assert high_gap_heal_resume_stage(ctx) == "gap_framing_compose"


def test_hg5_probe_error_without_plan_refuses_compose(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled",
        lambda: True,
    )

    real_exists = ctx.artifact_exists

    def _boom_plan(rel: str) -> bool:
        if str(rel).endswith("nugget_layup_plan.json"):
            raise RuntimeError(f"simulated artifact probe failure for {rel}")
        return real_exists(rel)

    monkeypatch.setattr(ctx, "artifact_exists", _boom_plan)
    ctx.write_json(
        "understanding/gap_report.json",
        minimal_gap_report(),
        skip_handoff=True,
    )
    with pytest.raises(RuntimeError, match="refusing gap_framing_compose"):
        high_gap_heal_resume_stage(ctx)


def test_hg5_heal_navigate_and_classify_live_pin(ctx: RunContext) -> None:
    nav = heal_navigate(ctx, error=_HIGH_ERR, stage="gap_framing_compose")
    assert nav["from_stage"] == "gap_framing_compose"
    ctx.write_json(
        "understanding/nugget_layup_plan.json",
        {"ordered_segment_ids": ["seg_001"], "layups": []},
        skip_handoff=True,
    )
    assert high_gap_heal_resume_stage(ctx) == "nugget_layup_compose"
    nav2 = heal_navigate(ctx, error=_HIGH_ERR, stage="gap_framing_compose")
    # Authority gate may clamp layup → information_package_plan when prereqs
    # are red; never pin compose while a plan is on disk.
    assert nav2["from_stage"] != "gap_framing_compose"
    assert (
        nav2["from_stage"] == "nugget_layup_compose"
        or nav2.get("heal_clamped_from") == "nugget_layup_compose"
    )
    assert nav2["from_stage"] != "edl"
    route = classify_heal_error(_HIGH_ERR, ctx, stage="gap_framing_compose")
    assert route is not None
    assert route.from_stage == "nugget_layup_compose"
    assert route.family == "high_gap_unframed"


def test_hg5_playbook_seeds_orphan_stamp_highs(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Land Honesty: orphan layup stamp clears; playbook seeds coverage (no demote).

    Authority-without-plan used to skip seed then demote. Repair now clears the
    stamp and seeds a targeting line so high_gap_unframed cannot greenwash.
    """
    monkeypatch.setattr(
        "interview_mux.high_gap_vo.fill_uncovered_high_gaps",
        lambda *_a, **_k: 0,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {**minimal_gap_report(), "nugget_layup_authority": True},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_evaluations.json",
        minimal_gap_evaluations(_HIGH_EVAL),
        skip_handoff=True,
    )
    written = playbook_high_gap_unframed(ctx)
    assert "understanding/gap_report.json" in written
    report = ctx.read_json("understanding/gap_report.json")
    assert report.get("nugget_layup_authority") is False
    lines = report.get("interviewer_lines") or []
    assert any(
        isinstance(ln, dict) and str(ln.get("targets_segment_id") or "") == "seg_001"
        for ln in lines
    )
    evals = ctx.read_json("understanding/gap_evaluations.json")
    row = (evals.get("evaluations") or [])[0]
    # Seeded coverage keeps severity high — demotion is for leftovers after fill.
    assert row.get("severity") == "high"
    assert not row.get("severity_demotion_reason")


def test_hg5_playbook_does_not_demote_covered_high(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.high_gap_vo.fill_uncovered_high_gaps",
        lambda *_a, **_k: 0,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        minimal_gap_report(minimal_gap_line(targets_segment_id="seg_001")),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_evaluations.json",
        minimal_gap_evaluations(_HIGH_EVAL),
        skip_handoff=True,
    )
    playbook_high_gap_unframed(ctx)
    evals = ctx.read_json("understanding/gap_evaluations.json")
    row = (evals.get("evaluations") or [])[0]
    assert row.get("severity") == "high"


def test_hg5_recovery_resumes_layup_when_plan_exists(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/nugget_layup_plan.json",
        {"ordered_segment_ids": ["seg_001"], "layups": []},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {**minimal_gap_report(), "nugget_layup_authority": True},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_evaluations.json",
        minimal_gap_evaluations(_HIGH_EVAL),
        skip_handoff=True,
    )
    result = handle_stage_failure(ctx, "gap_framing_compose", RuntimeError(_HIGH_ERR))
    assert result.resume_stage != "gap_framing_compose"
    assert result.resume_stage in (
        "nugget_layup_compose",
        "information_package_plan",  # heal authority clamp when layup prereqs red
    )
    assert result.playbook_id == "high_gap_unframed"


def test_hg5_recovery_resumes_compose_without_layup(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/gap_report.json",
        minimal_gap_report(),
        skip_handoff=True,
    )
    result = handle_stage_failure(ctx, "edl", RuntimeError(_HIGH_ERR))
    assert result.resume_stage == "gap_framing_compose"
    assert result.playbook_id == "high_gap_unframed"
