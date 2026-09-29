"""The boundary-quality floor scales with tape length; full episodes are unchanged.

A flat floor of 8 segments meant no tape under several minutes could ever be
judged fine-grained: a 6-minute excerpt with 5 boundaries at 79% coverage and a
2-minute one with 3 at 71.5% were both rejected as coarse, and every delivery
stage refused behind that flag. End-to-end checks therefore needed a full
episode and its full token cost. Real episodes keep the exact old rule.
"""

from __future__ import annotations

from interview_mux.stages.segmentation import (
    BOUNDARY_FULL_EPISODE_MS,
    _boundary_segment_floor,
    evaluate_boundary_quality,
)


def _doc(durs_s: list[float], gap_s: float = 0.0) -> dict:
    rows, t = [], 0.0
    for i, d in enumerate(durs_s, 1):
        rows.append({"segment_id": f"seg_{i:03d}", "start_ms": int(t * 1000), "end_ms": int((t + d) * 1000)})
        t += d + gap_s
    return {"boundaries": rows}


def test_floor_is_eight_for_a_full_episode() -> None:
    assert _boundary_segment_floor(BOUNDARY_FULL_EPISODE_MS) == 8
    assert _boundary_segment_floor(60 * 60 * 1000) == 8
    assert _boundary_segment_floor(0) == 8


def test_floor_scales_down_but_never_below_two() -> None:
    assert _boundary_segment_floor(6 * 60 * 1000) == 5
    assert _boundary_segment_floor(2 * 60 * 1000) == 2
    assert _boundary_segment_floor(10 * 1000) == 2


def test_six_minute_excerpt_with_five_boundaries_is_accepted() -> None:
    """The real 6-minute run: 62, 3, 90, 113, 17 seconds, 79.2% covered."""
    rep = evaluate_boundary_quality(_doc([62.3, 3.4, 90.1, 113.0, 16.5], gap_s=18.7), duration_ms=360_000)
    assert rep["reject"] is False, rep


def test_two_minute_excerpt_with_three_boundaries_is_accepted() -> None:
    """The real 2-minute run: 36, 4, 46 seconds, 71.5% covered (above critical 0.70)."""
    rep = evaluate_boundary_quality(_doc([35.9, 3.8, 46.1], gap_s=17.1), duration_ms=120_000)
    assert rep["reject"] is False, rep


def test_full_episode_with_three_boundaries_is_still_rejected() -> None:
    """Long-form behaviour is untouched: three slabs over an hour is coarse."""
    rep = evaluate_boundary_quality(_doc([1000.0, 1000.0, 1000.0], gap_s=100.0), duration_ms=3600_000)
    assert rep["reject"] is True, rep


def test_short_tape_below_critical_coverage_is_still_rejected() -> None:
    """Scaling the floor does not waive the critical coverage rule."""
    rep = evaluate_boundary_quality(_doc([20.0, 20.0, 20.0], gap_s=20.0), duration_ms=120_000)
    assert rep["coverage_ratio"] < 0.70
    assert rep["reject"] is True, rep
