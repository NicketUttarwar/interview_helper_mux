from __future__ import annotations

from interview_mux.coverage_limits import fabricate_cap, gap_fill_cap


def test_gap_fill_cap_respects_config_ratio():
    # Default gap_fill_max_ratio is 1.0 (uncapped) — ratio < 1 still floors at 1.
    assert gap_fill_cap(100) == 100
    assert gap_fill_cap(5) == 5
    assert gap_fill_cap(100, {"analysis": {"coverage_limits": {"gap_fill_max_ratio": 0.2}}}) == 20
    assert gap_fill_cap(5, {"analysis": {"coverage_limits": {"gap_fill_max_ratio": 0.2}}}) == 1


def test_fabricate_cap():
    assert fabricate_cap(50, per_call=True) == 10
    assert fabricate_cap(50, per_call=False) == 10
