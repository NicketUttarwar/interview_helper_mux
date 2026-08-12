"""Typed edl_narrative_audit remutate classifier + plan."""

from __future__ import annotations

from interview_mux.edl_narrative_remutate import (
    REMUTATE_REL,
    classify_edl_narrative_audit,
    classify_edl_narrative_issue,
    plan_edl_narrative_remutate,
)
from run_fixtures import isolated_run_ctx


def test_classify_issue_needles() -> None:
    assert classify_edl_narrative_issue("please rerank selection order") == "rerank"
    assert classify_edl_narrative_issue("missing spoken bridge hinge") == "transitions"
    assert classify_edl_narrative_issue("gap VO orphan on timeline") == "rebase_gap_vo"
    assert classify_edl_narrative_issue("blank segment near-silence") == "drop_blank"
    assert classify_edl_narrative_issue("something novel") == "operator"


def test_classify_audit_unique_actions() -> None:
    audit = {
        "verdict": "fail",
        "blocking_issues": [
            {"issue": "reorder leftover after finale", "recommended_action": "rerank"},
            {"issue": "missing transition bridge"},
        ],
    }
    assert classify_edl_narrative_audit(audit) == ["rerank", "transitions"]


def test_plan_increments_and_exhausts(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_narr_remutate")
    audit = {
        "verdict": "fail",
        "blocking_issues": [{"issue": "selection order broken — rerank"}],
    }
    p1 = plan_edl_narrative_remutate(ctx, audit)
    assert p1["attempt"] == 1
    assert "rerank" in p1["actions"]
    assert p1["from_stage"] == "full_master_ranking"
    assert not p1["exhausted"]
    assert ctx.artifact_exists(REMUTATE_REL)

    p2 = plan_edl_narrative_remutate(ctx, audit)
    assert p2["attempt"] == 2
    p3 = plan_edl_narrative_remutate(ctx, audit)
    assert p3["attempt"] == 3
    assert p3["exhausted"] is True
