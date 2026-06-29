from interview_mux.adaptation_loop_guard import AdaptationLoopGuard, adaptation_signature


def test_adaptation_signature_stable():
    a = adaptation_signature("coverage_retry", missing=["seg_001"], lint=("segment_coverage_ratio",))
    b = adaptation_signature("coverage_retry", missing=["seg_001"], lint=("segment_coverage_ratio",))
    assert a == b


def test_guard_blocks_repeat_signature():
    guard = AdaptationLoopGuard(stage_key="segment_classification")
    assert guard.record_strategy("coverage_retry", lint_errors=["segment_coverage_ratio"]) is True
    assert guard.record_strategy("coverage_retry", lint_errors=["segment_coverage_ratio"]) is False


def test_guard_decompose_cap():
    guard = AdaptationLoopGuard(stage_key="segment_classification")
    assert guard.can_decompose() is True
    assert guard.mark_decompose(10) is True
    assert guard.can_decompose() is False
