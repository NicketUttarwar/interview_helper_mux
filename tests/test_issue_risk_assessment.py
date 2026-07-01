"""Tests for issue_risk_assessment."""

from interview_mux.issue_risk_assessment import IssueRisk, assess_issue_risk


def test_guaranteed_breakage_duplicate_segment_id():
    risk = assess_issue_risk(
        {
            "message": "duplicate segment_id seg_001 in manifest",
            "kind": "cross_validate",
            "severity": "critical",
        }
    )
    assert risk == IssueRisk.GUARANTEED_BREAKAGE


def test_guaranteed_breakage_non_monotonic_timeline():
    risk = assess_issue_risk(
        {
            "message": "boundary timeline not monotonic at seg_003",
            "kind": "cross_validate",
        }
    )
    assert risk == IssueRisk.GUARANTEED_BREAKAGE


def test_repairable_merge_overlap():
    risk = assess_issue_risk(
        {
            "message": "adjacent segments share boundary by 200ms",
            "repair_strategy": "merge_overlap",
            "severity": "major",
        }
    )
    assert risk == IssueRisk.REPAIRABLE


def test_passable_infer_segment_types():
    risk = assess_issue_risk(
        {
            "message": "uncertain segment type for seg_007",
            "repair_strategy": "infer_segment_types",
            "severity": "minor",
            "options": [{"label": "Question", "value": "question"}],
        }
    )
    assert risk == IssueRisk.PASSABLE


def test_passable_ambiguous_options_without_recommendation():
    risk = assess_issue_risk(
        {
            "message": "pick classification",
            "options": [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}],
            "severity": "major",
        }
    )
    assert risk == IssueRisk.PASSABLE
