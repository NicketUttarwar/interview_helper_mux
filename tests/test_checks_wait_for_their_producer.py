"""Checks that ran before the stage producing what they check (ISSUES 161).

Found by an audit after entries 156 and 160 (same family). Each test pins one
member: the check must stay inert, or advisory, until its producer has run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from run_fixtures import isolated_run_ctx

PLAN = "understanding/nugget_layup_plan.json"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "exec_producer_first")


def _capture_identical(monkeypatch) -> list[str]:
    seen: list[str] = []
    monkeypatch.setattr(
        "interview_mux.identical_failures.record_identical_failure",
        lambda c, **k: seen.append(str(k.get("reason"))),
    )
    monkeypatch.setattr("interview_mux.delivery_guardrails.seed_stage_complete", lambda c, s: True)
    monkeypatch.setattr("interview_mux.seat_authority.hard_freeze_active", lambda c: False)
    monkeypatch.setattr("interview_mux.hosted_vo_authority.may_aspirational_proceed", lambda *a, **k: False)
    return seen


def test_floor_miss_before_layup_is_not_layups_failure(ctx, monkeypatch) -> None:
    from interview_mux.vo_contract import _record_hosted_floor_unmet

    seen = _capture_identical(monkeypatch)
    _record_hosted_floor_unmet(ctx, need=3, active=0, cta_only=True)
    assert seen == []
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    assert not meta.get("needs_operator")


def test_floor_miss_after_layup_still_counts(ctx, monkeypatch) -> None:
    from interview_mux.vo_contract import _record_hosted_floor_unmet

    seen = _capture_identical(monkeypatch)
    ctx.write_json(PLAN, {"ordered_segment_ids": [], "layups": []}, skip_handoff=True)
    _record_hosted_floor_unmet(ctx, need=3, active=0)
    assert seen == ["hosted_vo_floor_unmet"]


def test_layup_preflight_skips_floor_reseat_until_plan(ctx) -> None:
    from interview_mux.stage_input_checks import _hosted_floor_due

    assert not _hosted_floor_due(ctx, "nugget_layup_compose")
    assert _hosted_floor_due(ctx, "vo_synthesize")
    ctx.write_json(PLAN, {"ordered_segment_ids": [], "layups": []}, skip_handoff=True)
    assert _hosted_floor_due(ctx, "nugget_layup_compose")


def test_coverage_tier_c_leaves_unrendered_wavs_to_vo_synthesize(ctx, monkeypatch) -> None:
    from interview_mux import execution_contract as ec

    rows = [{"line_id": "vo_a", "coverage": "missing", "required": True}]
    monkeypatch.setattr("interview_mux.stages.edl_narrative_audit.compact_vo_coverage", lambda c: rows)
    marker = ctx.run_dir / ".stage_done" / "vo_line_adjudicate"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("{}")
    assert ec._tier_c_vo_adjudicate_heal(ctx) == []
    assert marker.exists()
    rows[0]["coverage"] = "wav_stale"
    monkeypatch.setattr(ec, "_vo_coverage_clear", lambda c, reason: [])
    assert ec._tier_c_vo_adjudicate_heal(ctx) == [".stage_done/vo_line_adjudicate"]


def test_contract_tier_d_never_waives_a_missing_wav(ctx, monkeypatch) -> None:
    from interview_mux import execution_contract as ec

    from run_fixtures import minimal_gap_report

    monkeypatch.setattr("interview_mux.seat_authority.gate_seat_mutation", lambda *a, **k: True)
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo", lambda c: False
    )
    line = {"text": "A host line on air.", "targets_segment_id": "seg_001", "delivery": "synthesize"}
    gap = {
        **minimal_gap_report(),
        "interviewer_lines": [{**line, "line_id": "vo_a"}, {**line, "line_id": "vo_b"}],
    }
    ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)
    violation = ec.classify_vo_violation("seated synthesize vo_a missing WAV")
    assert violation.kind == "missing_wav"
    assert ec._tier_d_logged_waive(ctx, violation) == []
    rows = ctx.read_json("understanding/gap_report.json")["interviewer_lines"]
    assert not any(r.get("skipped_optional") or r.get("air_script_omit") for r in rows)


def test_contract_tier_b_waits_for_layup_plan(ctx, monkeypatch) -> None:
    from interview_mux import execution_contract as ec

    monkeypatch.setattr("interview_mux.seat_authority.gate_seat_mutation", lambda *a, **k: True)
    monkeypatch.setattr("interview_mux.nugget_layup.nugget_layup_enabled", lambda: True)
    called: list[str] = []
    monkeypatch.setattr(
        "interview_mux.refinement_passes.run_gap_framing_recompose", lambda c: called.append("x")
    )
    assert ec._tier_b_gap_recompose(ctx) == []
    assert called == []
