"""Re-rank-only audit complaints become warnings once the order is frozen (ISSUES 70)."""

from __future__ import annotations

import pytest

from interview_mux import artifact_repairs as ar

ISSUE = {
    "code": "selected_continuity_broken",
    "issue": "The trial-use chapter opens with a short fragment.",
    "recommended_action": "rerun full_master_ranking to place or remove seg_041",
}
OTHER = {
    "code": "phantom_vo",
    "issue": "A VO clip has no audio.",
    "recommended_action": "rerun vo_synthesize",
}


def _run(monkeypatch: pytest.MonkeyPatch, frozen: bool, rows: list[dict]) -> dict:
    monkeypatch.setattr(ar, "_order_frozen", lambda c: frozen)
    monkeypatch.setattr(ar, "align_narrative_plan_to_selection", lambda c: [])
    monkeypatch.setattr(ar, "_manifest_ids_and_tags", lambda c: (set(), {}))
    monkeypatch.setattr(ar, "_edl_issue_contradicted_by_disk", lambda c, r: False)
    monkeypatch.setattr(ar, "_edl_issue_premature_vo_nle_placement", lambda c, r: False)
    monkeypatch.setattr(ar, "_edl_issue_demands_restore_excluded", lambda r: False)
    monkeypatch.setattr("interview_mux.v2.config.v2_g1_optional", lambda: False)
    out, _ = ar.repair_edl_audit(object(), {"verdict": "fail", "blocking_issues": rows})
    return out


def test_frozen_order_demotes_rerank_complaints(monkeypatch) -> None:
    out = _run(monkeypatch, True, [dict(ISSUE)])
    assert out["verdict"] == "warn"
    assert out["blocking_issues"] == []
    assert "needs operator re-rank" in out["warnings"][0]["issue"]


def test_unfrozen_order_still_blocks(monkeypatch) -> None:
    out = _run(monkeypatch, False, [dict(ISSUE)])
    assert out["verdict"] == "fail"


def test_other_blockers_still_block_when_frozen(monkeypatch) -> None:
    out = _run(monkeypatch, True, [dict(ISSUE), dict(OTHER)])
    assert out["verdict"] == "fail"
    assert [b["code"] for b in out["blocking_issues"]] == ["phantom_vo"]


def test_transition_missing_for_a_deferred_pair_is_premature(monkeypatch) -> None:
    """ISSUES 71: deferred pairs are synthesized at mix, after the audit."""
    monkeypatch.setattr(ar, "_deferred_pair_keys", lambda c: {("seg_037", "seg_041")})
    row = {
        "code": "transition_missing",
        "issue": "Deferred seg_037-to-seg_041 bridge has no transition.",
        "recommended_action": "rerun transitions",
    }
    assert ar._edl_issue_contradicted_by_disk(object(), row) is True
    monkeypatch.setattr(ar, "_deferred_pair_keys", lambda c: set())
    assert ar._edl_issue_contradicted_by_disk(object(), row) is False
