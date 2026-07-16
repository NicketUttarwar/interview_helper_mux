from __future__ import annotations

from interview_mux.coverage_limits import fabricate_cap, gap_fill_cap


def test_gap_fill_cap_twenty_percent():
    assert gap_fill_cap(100) == 20
    assert gap_fill_cap(5) == 1


def test_fabricate_cap():
    assert fabricate_cap(50, per_call=True) == 10
    assert fabricate_cap(50, per_call=False) == 10
