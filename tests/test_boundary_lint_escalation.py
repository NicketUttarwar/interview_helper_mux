from __future__ import annotations

from interview_mux.lint_adaptation import boundary_lint_escalation, lint_retry_strategy


def test_boundary_escalation_proactive_decompose_on_oversplit() -> None:
    strategy = boundary_lint_escalation(
        ["pause_ladder_oversplit_risk"],
        attempt=1,
        prior_strategy_keys=[],
        oversplit=True,
    )
    assert strategy.get("force_decompose") is True
    assert strategy.get("strategy_key") == "proactive_boundary_decompose"


def test_boundary_escalation_timeline_decompose_after_partial_repair() -> None:
    strategy = boundary_lint_escalation(
        ["duplicate segment_id seg_001", "truncation_requires_decompose"],
        attempt=2,
        prior_strategy_keys=["structural_repair_partial"],
        structural_repair_partial=True,
        oversplit=True,
    )
    assert strategy.get("strategy_key") == "timeline_decompose"


def test_lint_retry_strategy_distinct_keys_per_stage() -> None:
    a = lint_retry_strategy(["duplicate segment_id"], "boundary_detection", attempt=1)
    b = lint_retry_strategy(["segment_coverage_ratio: 0.5 < 1.0"], "segment_classification", attempt=1)
    assert a.get("strategy_key") != b.get("strategy_key")
