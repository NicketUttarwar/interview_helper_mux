"""Every gap-body resume mapper names a stage the sole-writer rule lets write (ISSUES 158).

exec_015: the floor snapshot was built with stage_id="gap_framing_compose" and
hosted_vo_authority.resume_producer returned it unchanged, although the gap
report carried nugget_layup_authority. Compose then looped authority_denied.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from run_fixtures import isolated_run_ctx, minimal_gap_report

PLAN = "understanding/nugget_layup_plan.json"
GAP = "understanding/gap_report.json"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr("interview_mux.nugget_layup.nugget_layup_enabled", lambda: True)
    return isolated_run_ctx(tmp_path, "exec_gap_body_resume")


def test_all_mappers_pin_layup_when_layup_owns_the_body(ctx) -> None:
    from interview_mux import hosted_vo_authority, stage_completion, thrash_hardening

    ctx.write_json(PLAN, {"ordered_segment_ids": ["seg_001"], "layups": []}, skip_handoff=True)
    ctx.write_json(GAP, {**minimal_gap_report(), "nugget_layup_authority": True}, skip_handoff=True)
    assert stage_completion.layup_owns_gap_body(ctx)
    assert hosted_vo_authority.resume_producer(ctx, stage_id="gap_framing_compose") == "nugget_layup_compose"
    assert thrash_hardening.resume_producer(ctx, "gap_framing_compose") == "nugget_layup_compose"
    assert stage_completion.high_gap_heal_resume_stage(ctx) == "nugget_layup_compose"


def test_compose_stays_when_compose_owns_the_body(ctx) -> None:
    from interview_mux import hosted_vo_authority, thrash_hardening

    ctx.write_json(PLAN, {"ordered_segment_ids": ["seg_001"], "layups": []}, skip_handoff=True)
    ctx.write_json(GAP, minimal_gap_report(), skip_handoff=True)
    assert hosted_vo_authority.resume_producer(ctx, stage_id="gap_framing_compose") == "gap_framing_compose"
    assert thrash_hardening.resume_producer(ctx, "gap_framing_compose") == "gap_framing_compose"


def test_orphan_stamp_without_plan_keeps_compose(ctx) -> None:
    from interview_mux import hosted_vo_authority

    ctx.write_json(GAP, {**minimal_gap_report(), "nugget_layup_authority": True}, skip_handoff=True)
    assert hosted_vo_authority.resume_producer(ctx, stage_id="gap_framing_compose") == "gap_framing_compose"
