from interview_mux.classification_obligation import (
    missing_segment_ids,
    obligation_lint_errors,
)
from interview_mux.lint_adaptation import lint_retry_strategy


def test_missing_segment_ids():
    obligation = {"required_segment_ids": ["seg_001", "seg_002", "seg_003"]}
    segments = [{"segment_id": "seg_001", "type": "interviewee_answer"}]
    assert missing_segment_ids(obligation, segments) == ["seg_002", "seg_003"]


def test_obligation_lint_coverage_ratio():
    obligation = {"required_count": 2, "required_segment_ids": ["seg_001", "seg_002"]}
    segments = [{"segment_id": "seg_001", "type": "interviewee_answer"}]
    errors = obligation_lint_errors(obligation, segments)
    assert any("segment_coverage_ratio" in e for e in errors)


def test_obligation_lint_mono_type():
    obligation = {"required_count": 2, "required_segment_ids": ["seg_001", "seg_002"]}
    segments = [
        {"segment_id": "seg_001", "type": "interviewee_answer"},
        {"segment_id": "seg_002", "type": "interviewee_answer"},
    ]
    errors = obligation_lint_errors(obligation, segments)
    assert any("interviewee_answer" in e for e in errors)


def test_lint_retry_strategy_coverage_maps_to_decompose():
    strategy = lint_retry_strategy(["segment_coverage_ratio: 0.80 < 1.0"], "segment_classification")
    assert strategy.get("force_decompose") is True
    assert strategy.get("inject_missing_segment_ids") is True
