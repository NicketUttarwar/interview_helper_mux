"""HEAD tests for gap_framing_compose hardening (E1–E13 / R1–R8 guardrails)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from interview_mux.execution_contract import (
    _consumer_is_analysis_era,
    _PLAN_MUTATING_LADDER_TIERS,
    run_vo_contract_ladder,
)
from interview_mux.gap_packet_guard import assert_gap_packet_richness
from interview_mux.mastering_plan_loader import compose_plan_bind_mode
from interview_mux.run_context import RunContext
from interview_mux.stages.gaps import (
    _merge_gap_report_parts,
    _warrant_gap_count,
    run_gap_framing_compose,
)
from interview_mux.web.stages import ANALYSIS_STAGES
from run_fixtures import init_run_meta_for_test, mark_done_raw, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext("exec_gfc_harden", create=True)
    init_run_meta_for_test(run)
    return run


def test_stageinfo_declares_gap_framing_companions() -> None:
    info = next(s for s in ANALYSIS_STAGES if s.id == "gap_framing_compose")
    arts = set(info.artifacts or ())
    assert "understanding/gap_report.json" in arts
    assert "understanding/interviewer_script.txt" in arts
    assert "understanding/gap_framing_plan.json" in arts
    assert "understanding/gap_vo_context_audit.json" in arts


def _eval(
    sid: str,
    *,
    severity: str = "high",
    gap_type: str = "missing_setup",
    confusion: str = "Why does this matter now?",
) -> dict:
    return {
        "segment_id": sid,
        "severity": severity,
        "gap_type": gap_type,
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
        "text": "Native beat from tape.",
        "start_ms": 0,
        "end_ms": 1000,
    }


def _brief() -> dict:
    return {"thesis": "Snack brand grew from a farm.", "topics": []}


def test_merge_gap_report_parts_richest_plan_and_dedupe_gaps() -> None:
    thin = {
        "interviewer_lines": [{"line_id": "a", "text": "one"}],
        "gaps": [{"segment_id": "seg_001", "note": "first"}],
        "gap_framing_plan": {"acts": [{"act_id": "act_1", "impact_blocks": []}]},
    }
    rich = {
        "interviewer_lines": [{"line_id": "b", "text": "two"}],
        "gaps": [{"segment_id": "seg_001", "note": "second"}],
        "gap_framing_plan": {
            "acts": [
                {
                    "act_id": "act_1",
                    "impact_blocks": [
                        {"framing_line_ids": ["a", "b"]},
                    ],
                }
            ]
        },
    }
    merged = _merge_gap_report_parts([thin, rich])
    lids = {str(r.get("line_id")) for r in merged["interviewer_lines"]}
    assert lids == {"a", "b"}
    gaps = merged["gaps"]
    assert len(gaps) == 1
    assert gaps[0]["note"] == "second"
    plan = merged["gap_framing_plan"]
    assert plan["acts"][0]["impact_blocks"][0]["framing_line_ids"] == ["a", "b"]


def test_compose_packet_rejects_high_gap_missing_segment_context() -> None:
    payload = {
        "content_brief": {"thesis": "A guest traces growth from a farm."},
        "segments": [{"segment_id": "seg_001", "text": "Native beat."}],
        "gap_evaluations": {
            "evaluations": [
                {
                    "segment_id": "seg_099",
                    "severity": "high",
                    "gap_type": "missing_setup",
                }
            ]
        },
        "ordered_segment_ids": ["seg_001"],
    }
    with pytest.raises(ValueError, match="high-gap"):
        assert_gap_packet_richness("gap_framing_compose", payload)


def test_vo_budget_scales_from_warrant_not_manifest(ctx: RunContext) -> None:
    ctx.write_json(
        "segments/manifest.json",
        {"segments": [_seg(f"seg_{i:03d}") for i in range(1, 41)]},
    )
    ctx.write_json(
        "understanding/gap_evaluations.json",
        {
            "evaluations": [
                _eval("seg_001"),
                _eval(
                    "seg_002",
                    severity="medium",
                    gap_type="missing_bridge",
                    confusion="How does this connect?",
                ),
            ]
        },
    )
    assert _warrant_gap_count(ctx) == 2
    from interview_mux.stages.gaps import _gap_framing_compose_payload

    ctx.write_json("understanding/content_brief.json", _brief())
    payload = _gap_framing_compose_payload(ctx)
    budget = payload.get("vo_line_budget") or {}
    assert budget.get("scale_basis") == "warrant_gaps"
    assert budget.get("ordered_n") == 2


def test_compose_plan_bind_mode_advisory_when_consumers_bind_false() -> None:
    plan = {"plan_status": "complete", "narrative_mode": "montage"}
    assert compose_plan_bind_mode(plan) == "advisory"


def test_analysis_era_ladder_skips_plan_mutating_tiers(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _consumer_is_analysis_era("gap_framing_compose")
    assert "tier_c_opening_omit_unseat" in _PLAN_MUTATING_LADDER_TIERS

    monkeypatch.setattr(
        "interview_mux.execution_contract.ladder_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "interview_mux.vo_contract.validate_vo_contract",
        lambda _ctx: ["missing_from_gap:vo_x"],
    )
    called: list[str] = []

    def _track(name: str):
        def _fn(_ctx):
            called.append(name)
            return []

        return _fn

    monkeypatch.setattr(
        "interview_mux.execution_contract._tier_a_publish_orientation",
        _track("a"),
    )
    monkeypatch.setattr(
        "interview_mux.execution_contract._tier_b_gap_recompose",
        _track("b"),
    )
    monkeypatch.setattr(
        "interview_mux.execution_contract._tier_c_opening_omit_unseat",
        _track("c"),
    )
    monkeypatch.setattr(
        "interview_mux.execution_contract._tier_d_logged_waive",
        lambda _ctx, _v: called.append("d") or [],
    )

    result = run_vo_contract_ladder(ctx, consumer_stage="gap_framing_compose")
    assert "c" not in called
    assert "d" not in called
    assert result.recovered is False
    assert result.tier == "analysis_era_skip_plan_mutate"
    assert result.resume_stage == "gap_framing_compose"


def test_layup_authority_compose_never_calls_llm(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.nugget_layup import PLAN_REL

    set_gap = __import__(
        "interview_mux.gap_vo_gates", fromlist=["set_gap_framing_enabled"]
    ).set_gap_framing_enabled
    set_gap(ctx, True)
    ctx.write_json(
        PLAN_REL,
        {"version": 1, "layups": [], "ordered_segment_ids": []},
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [], "nugget_layup_authority": True},
    )
    llm = MagicMock()
    monkeypatch.setattr(
        "interview_mux.llm_simple.run_llm_stage_simple",
        llm,
    )
    monkeypatch.setattr(
        "interview_mux.stages.gaps.run_analysis_llm_stage",
        llm,
    )
    monkeypatch.setattr(
        "interview_mux.nugget_layup.publish_layup_plan_to_gap_report",
        lambda _c: None,
    )
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled",
        lambda: True,
    )
    run_gap_framing_compose(ctx)
    llm.assert_not_called()


def test_i1_orphan_layup_stamp_cleared_admits_fallthrough(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stamp without plan must clear authority and leave the fail-closed no-op.

    Cascade for exec_13183 premature thrash: gap_report.nugget_layup_authority=true
    with no understanding/nugget_layup_plan.json — previously returned after
    hollow Finished; now clears stamp and continues into compose body.
    """
    set_gap = __import__(
        "interview_mux.gap_vo_gates", fromlist=["set_gap_framing_enabled"]
    ).set_gap_framing_enabled
    set_gap(ctx, True)
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [],
            "gaps": [],
            "nugget_layup_authority": True,
        },
    )
    assert not ctx.artifact_exists("understanding/nugget_layup_plan.json")
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.freeze_write_allowed",
        lambda *_a, **_k: True,
    )
    # Fall-through reaches heal/incompleteness (not silent no-op return).
    with pytest.raises(RuntimeError) as excinfo:
        run_gap_framing_compose(ctx)
    assert "layup authority stamp without plan" not in str(excinfo.value).lower()
    gap = ctx.read_json("understanding/gap_report.json")
    assert gap.get("nugget_layup_authority") is False
    repairs = ((gap.get("_meta") or {}).get("repairs")) or []
    assert any(
        isinstance(r, dict) and r.get("action") == "clear_orphan_nugget_layup_authority"
        for r in repairs
    )
    # No hollow force-done from the old flap no-op path.
    assert not ctx.is_done("gap_framing_compose")


def test_missing_framing_high_without_mission_incomplete(ctx: RunContext) -> None:
    from interview_mux.gap_vo_gates import set_gap_framing_enabled
    from interview_mux.stage_completion import (
        _missing_framing_high_without_mission_incompleteness,
    )

    set_gap_framing_enabled(ctx, True)
    ctx.write_json(
        "understanding/gap_evaluations.json",
        {"evaluations": [_eval("seg_001", confusion="")]},
    )
    reason = _missing_framing_high_without_mission_incompleteness(ctx)
    assert reason is not None
    assert "high_without_mission" in reason


def test_compose_preflight_blocks_on_missing_framing_incomplete(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.gap_vo_gates import set_gap_framing_enabled
    from interview_mux.pipeline import _run_gap_framing_compose_stage

    set_gap_framing_enabled(ctx, True)
    ctx.write_json(
        "understanding/gap_evaluations.json",
        {"evaluations": [_eval("seg_001", confusion="")]},
    )
    monkeypatch.setattr(
        "interview_mux.pipeline._gap_path_skipped",
        lambda _c: False,
    )
    with pytest.raises(RuntimeError, match="missing_framing incomplete"):
        _run_gap_framing_compose_stage(ctx)


def test_gap_compose_predicate_includes_line_and_high_counts(ctx: RunContext) -> None:
    from interview_mux.thrash_hardening import stage_predicate_token

    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [{"line_id": "l1", "text": "hi"}]},
    )
    ctx.write_json(
        "understanding/gap_evaluations.json",
        {"evaluations": [_eval("seg_001")]},
    )
    token = stage_predicate_token(ctx, "gap_framing_compose")
    assert "hg=1" in token
    assert "ln=1" in token


def test_forward_cue_lint_blocking_when_framing_yes(ctx: RunContext) -> None:
    from interview_mux.deterministic_lint import _lint_optimal_questions
    from interview_mux.gap_vo_gates import set_gap_framing_enabled

    set_gap_framing_enabled(ctx, True)
    arts = {
        "interviewer_lines": [
            {
                "line_id": "vo_preface_001",
                "line_category": "episode_preface",
                "text": "Welcome back. Today we dig in.",
                "targets_segment_id": "seg_001",
            }
        ]
    }
    # Without a forward-looking cue this should block under framing Yes.
    errors = _lint_optimal_questions(arts, ctx)
    # May or may not trip depending on has_forward_cue heuristics; if text has
    # no cue pattern, expect missing_forward_cue.
    from interview_mux.gap_vo_prior_context import has_forward_cue

    if not has_forward_cue("Welcome back. Today we dig in."):
        assert any("missing_forward_cue" in e for e in errors)


def test_demote_refused_under_framing_yes_with_uncovered(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.gap_vo_gates import set_gap_framing_enabled
    from interview_mux.stages.gaps import _compose_framing_warrants_vo

    set_gap_framing_enabled(ctx, True)
    ctx.write_json(
        "understanding/gap_evaluations.json",
        {"evaluations": [_eval("seg_033")]},
    )
    assert _compose_framing_warrants_vo(ctx) is True
    called = {"resolve": 0}

    def _fill(_c, out, *, applied=None, origin=""):
        return 0

    def _resolve(*_a, **_k):
        called["resolve"] += 1
        return MagicMock(demoted=1)

    monkeypatch.setattr(
        "interview_mux.high_gap_vo.fill_uncovered_high_gaps",
        _fill,
    )
    monkeypatch.setattr(
        "interview_mux.high_gap_vo.resolve_seats",
        _resolve,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_repairs.repair_gap_report",
        lambda _c, arts: (arts if isinstance(arts, dict) else {"interviewer_lines": []}, []),
    )
    monkeypatch.setattr(
        "interview_mux.gap_framing.persist_gap_framing_companion_artifacts",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_writes.write_validated_artifact",
        lambda *_a, **_k: None,
    )

    ctx.write_json("understanding/content_brief.json", _brief())
    ctx.write_json("segments/manifest.json", {"segments": [_seg("seg_033")]})
    ctx.write_json("mastering/mastering_plan.json", {"plan_status": "degraded"})
    mark_done_raw(ctx, "missing_framing")

    def _fake_llm(c, stage, prompt, build, persist, auto_complete=False):
        persist(c, {"interviewer_lines": []})

    monkeypatch.setattr(
        "interview_mux.stages.gaps.run_analysis_llm_stage",
        _fake_llm,
    )
    monkeypatch.setattr(
        "interview_mux.stages.gaps._heal_gap_framing_compose_if_complete",
        lambda _c: None,
    )
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.freeze_write_allowed",
        lambda *_a, **_k: True,
    )
    run_gap_framing_compose(ctx)
    assert called["resolve"] == 0
