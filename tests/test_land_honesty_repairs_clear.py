"""Land Honesty: artifact_repairs clears orphan layup authority (i1 residual).

When gap_report stamps nugget_layup_authority without PLAN_REL on disk, repair
must clear the orphan stamp (not skip seed) so stamp-alone unpaid land lifts
for gap_framing_compose. Promote may still be incomplete for other reasons.

MUX_FORENSICS=0.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ["MUX_FORENSICS"] = "0"

import pytest

from interview_mux.artifact_repairs import (
    _seed_missing_high_gap_interviewer_lines,
    repair_gap_report,
)
from interview_mux.done_authority import (
    layup_authority_without_plan,
    unpaid_land_blocks_promote,
    unpaid_land_reason,
)
from interview_mux.nugget_layup import PLAN_REL
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "exec_land_honesty_repairs_clear")


def _stamp_alone_gap_report(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> dict:
    monkeypatch.setattr(
        "interview_mux.nugget_layup.nugget_layup_enabled", lambda: True
    )
    doc = {"interviewer_lines": [], "nugget_layup_authority": True}
    ctx.write_json("understanding/gap_report.json", doc)
    assert not ctx.artifact_exists(PLAN_REL)
    return doc


def test_seed_missing_high_gap_clears_orphan_authority_and_stamp_alone_unpaid(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """repair_gap_report clears stamp-without-plan (seed helper peeled)."""
    _stamp_alone_gap_report(ctx, monkeypatch)

    assert layup_authority_without_plan(ctx) is True
    before = unpaid_land_reason(ctx, "gap_framing_compose")
    assert before is not None
    assert "stamp-alone" in before
    assert unpaid_land_blocks_promote(ctx, "gap_framing_compose") is True

    out: dict = {
        "nugget_layup_authority": True,
        "interviewer_lines": [],
    }
    patched, applied = repair_gap_report(ctx, out)

    assert patched["nugget_layup_authority"] is False
    assert any(
        a.get("action") == "clear_orphan_nugget_layup_authority"
        and a.get("reason") == "stamp_without_plan"
        for a in applied
    )
    # Persist repair result — unpaid land reads gap_report on disk.
    ctx.write_json("understanding/gap_report.json", patched)

    assert layup_authority_without_plan(ctx) is False
    after = unpaid_land_reason(ctx, "gap_framing_compose")
    assert after is None or "stamp-alone" not in after
    # Promote no longer blocked solely by stamp-alone (may still be incomplete).
    assert unpaid_land_blocks_promote(ctx, "gap_framing_compose") is False


def test_seed_missing_high_gap_helper_is_peeled(
    ctx: RunContext,
) -> None:
    with pytest.raises(RuntimeError, match="peeled"):
        _seed_missing_high_gap_interviewer_lines(
            ctx, {"interviewer_lines": []}, manifest_ids=set(), applied=[]
        )


def test_repair_gap_report_clears_orphan_layup_authority_when_plan_missing(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Public repair_gap_report path exercises the same orphan clear."""
    doc = _stamp_alone_gap_report(ctx, monkeypatch)
    assert layup_authority_without_plan(ctx) is True
    assert unpaid_land_blocks_promote(ctx, "gap_framing_compose") is True

    patched, applied = repair_gap_report(ctx, doc)

    assert patched.get("nugget_layup_authority") is False
    assert any(
        a.get("action") == "clear_orphan_nugget_layup_authority" for a in applied
    )
    ctx.write_json("understanding/gap_report.json", patched)

    assert layup_authority_without_plan(ctx) is False
    reason = unpaid_land_reason(ctx, "gap_framing_compose")
    assert reason is None or "stamp-alone" not in reason
    assert unpaid_land_blocks_promote(ctx, "gap_framing_compose") is False
