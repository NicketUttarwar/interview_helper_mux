from __future__ import annotations

from interview_mux.coverage_limits import (
    listenability_tier,
    output_ratio_of_source,
    ratio_cap,
    reanchor_min_coverage_ratio,
    spread_sample,
)


def test_ratio_cap_full_when_one():
    assert ratio_cap(40, 1.0) == 40
    assert ratio_cap(40, 0.20) == 8


def test_spread_sample_covers_timeline():
    items = [{"id": i, "start_ms": i * 1000} for i in range(20)]
    picked = spread_sample(items, 4, time_key=lambda x: x["start_ms"])
    assert len(picked) == 4
    starts = [p["start_ms"] for p in picked]
    assert min(starts) == 0
    assert max(starts) >= 15000


def test_output_ratio_and_listenability():
    assert output_ratio_of_source(450_000, 900_000) == 0.5
    assert listenability_tier(0.35) == "strict"
    assert listenability_tier(0.42) == "normal"
    assert listenability_tier(0.50) == "relaxed"


def test_reanchor_min_coverage_short_interview():
    class _Ctx:
        def artifact_exists(self, _path: str) -> bool:
            return False

    ratio = reanchor_min_coverage_ratio({"a", "b", "c"}, _Ctx(), {})
    assert ratio == 1.0
