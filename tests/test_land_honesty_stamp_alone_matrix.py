"""i1 stamp-alone / layup authority hollow-done matrix.

MUX_FORENSICS=0. Land Honesty: nugget_layup_authority without PLAN_REL must not
greenwash gap_framing_compose (or other LAYUP_AUTHORITY_STAGES) as complete.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ["MUX_FORENSICS"] = "0"

import pytest

from interview_mux.artifact_repairs import _seed_missing_high_gap_interviewer_lines
from interview_mux.delivery_guardrails import (
    promote_complete_orphan_stage_done,
    seed_stage_complete,
)
from interview_mux.done_authority import (
    LAYUP_AUTHORITY_STAGES,
    land_honest,
    layup_authority_without_plan,
    unpaid_land_blocks_promote,
    unpaid_land_reason,
)
from interview_mux.nugget_layup import PLAN_REL
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import heal_or_raise
from interview_mux.stages.gaps import _heal_gap_framing_compose_if_complete
from run_fixtures import isolated_run_ctx, mark_done_raw


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "exec_stamp_alone_matrix")


def _enable_layup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled",
        lambda: True,
    )


def _stamp_alone_gap(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [], "nugget_layup_authority": True},
    )


def test_gap_framing_compose_unpaid_when_authority_without_plan(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1. gap_framing_compose unpaid when authority True and PLAN_REL missing."""
    _enable_layup(monkeypatch)
    _stamp_alone_gap(ctx)
    assert not ctx.artifact_exists(PLAN_REL)
    assert layup_authority_without_plan(ctx) is True
    reason = unpaid_land_reason(ctx, "gap_framing_compose")
    assert reason is not None
    assert "stamp-alone" in reason
    assert "nugget_layup_authority without nugget_layup_plan" in reason


def test_stamp_alone_blocks_land_honest_and_promote(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2. land_honest False / seed_stage_complete False / unpaid_land_blocks_promote True."""
    _enable_layup(monkeypatch)
    _stamp_alone_gap(ctx)
    mark_done_raw(ctx, "gap_framing_compose")
    assert unpaid_land_blocks_promote(ctx, "gap_framing_compose") is True
    assert seed_stage_complete(ctx, "gap_framing_compose") is False
    assert land_honest(ctx, "gap_framing_compose") is False


def test_writing_plan_clears_stamp_alone_unpaid_authority_still_set(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """3. Writing PLAN_REL clears stamp-alone unpaid (authority flag still set)."""
    _enable_layup(monkeypatch)
    _stamp_alone_gap(ctx)
    assert unpaid_land_reason(ctx, "gap_framing_compose") is not None

    ctx.write_json(PLAN_REL, {"version": 1, "layups": [], "ordered_segment_ids": []})
    assert layup_authority_without_plan(ctx) is False
    assert unpaid_land_reason(ctx, "gap_framing_compose") is None
    assert unpaid_land_blocks_promote(ctx, "gap_framing_compose") is False
    gap = ctx.read_json("understanding/gap_report.json")
    assert gap.get("nugget_layup_authority") is True


def test_seed_missing_high_gap_clears_orphan_authority_or_unpaid(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """4. artifact_repairs clear orphan authority when plan missing."""
    _enable_layup(monkeypatch)
    assert not ctx.artifact_exists(PLAN_REL)
    out: dict = {"nugget_layup_authority": True, "interviewer_lines": []}
    applied: list[dict] = []
    _seed_missing_high_gap_interviewer_lines(
        ctx, out, manifest_ids=set(), applied=applied
    )
    assert out.get("nugget_layup_authority") is False
    assert any(
        a.get("action") == "clear_orphan_nugget_layup_authority" for a in applied
    )
    # Persist cleared authority → stamp-alone unpaid must clear for the family.
    ctx.write_json("understanding/gap_report.json", out)
    assert layup_authority_without_plan(ctx) is False
    assert unpaid_land_reason(ctx, "gap_framing_compose") is None


def test_bare_mark_done_without_gap_report_not_land_honest(ctx: RunContext) -> None:
    """5. Bare mark_done_raw without gap_report is NOT land_honest."""
    assert not ctx.artifact_exists("understanding/gap_report.json")
    mark_done_raw(ctx, "gap_framing_compose")
    assert ctx.is_done("gap_framing_compose")
    assert land_honest(ctx, "gap_framing_compose") is False
    assert seed_stage_complete(ctx, "gap_framing_compose") is False


@pytest.mark.parametrize("stage", sorted(LAYUP_AUTHORITY_STAGES))
def test_layup_authority_stages_unpaid_without_plan(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    """6. Each LAYUP_AUTHORITY_STAGES unpaid when authority without plan."""
    _enable_layup(monkeypatch)
    _stamp_alone_gap(ctx)
    assert not ctx.artifact_exists(PLAN_REL)
    reason = unpaid_land_reason(ctx, stage)
    assert reason is not None
    assert "stamp-alone" in reason
    assert unpaid_land_blocks_promote(ctx, stage) is True
    assert land_honest(ctx, stage) is False


def test_heal_raises_and_does_not_leave_hollow_finished(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """7. heal_or_raise / _heal_gap_framing_compose_if_complete raises; no hollow Finished."""
    _enable_layup(monkeypatch)
    _stamp_alone_gap(ctx)
    mark_done_raw(ctx, "gap_framing_compose")
    assert ctx.is_done("gap_framing_compose")

    with pytest.raises(RuntimeError):
        heal_or_raise(ctx, "gap_framing_compose")
    # is_done may unmark; either way must not remain land-honest / seed-complete.
    assert land_honest(ctx, "gap_framing_compose") is False
    assert seed_stage_complete(ctx, "gap_framing_compose") is False

    # Re-stamp hollow and exercise the gaps helper (thin wrapper over heal_or_raise).
    mark_done_raw(ctx, "gap_framing_compose")
    with pytest.raises(RuntimeError):
        _heal_gap_framing_compose_if_complete(ctx)
    assert land_honest(ctx, "gap_framing_compose") is False
    assert seed_stage_complete(ctx, "gap_framing_compose") is False


def test_promote_does_not_stamp_gap_framing_compose_under_stamp_alone(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """8. promote_complete_orphan_stage_done does not promote under stamp-alone."""
    _enable_layup(monkeypatch)
    _stamp_alone_gap(ctx)
    assert not ctx.is_done("gap_framing_compose")
    assert unpaid_land_blocks_promote(ctx, "gap_framing_compose") is True

    promoted = promote_complete_orphan_stage_done(ctx, ("gap_framing_compose",))
    assert "gap_framing_compose" not in promoted
    assert not ctx.is_done("gap_framing_compose")
