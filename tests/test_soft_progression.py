from __future__ import annotations

from interview_mux.coverage_limits import (
    effective_shard_min_success_ratio,
    is_non_blocking_lint,
    partition_lint_errors,
    segment_coverage_min_ratio,
    soft_progression_enabled,
)


def test_soft_progression_enabled_by_default():
    assert soft_progression_enabled() is True


def test_partition_lint_errors():
    errors = [
        "segment_coverage_ratio: 0.45 < 0.85 (18/40 segments)",
        "schema_errors_empty: missing thesis",
    ]
    blocking, warnings = partition_lint_errors(errors)
    assert len(blocking) == 1
    assert len(warnings) == 1
    assert "segment_coverage_ratio" in warnings[0]


def test_is_non_blocking_lint_post_listen():
    assert is_non_blocking_lint("post_listen failed for: bed_intro")


def test_adaptive_segment_coverage_scales_down():
    class _Ctx:
        def artifact_exists(self, _path: str) -> bool:
            return False

    manifest = {f"seg_{i}" for i in range(80)}
    ratio = segment_coverage_min_ratio("segment_classification", manifest, _Ctx(), {})
    assert ratio < 0.85
    assert ratio >= 0.15


def test_effective_shard_min_success_long_plan():
    ratio = effective_shard_min_success_ratio(16)
    assert ratio <= 0.75
    assert ratio >= 0.35
