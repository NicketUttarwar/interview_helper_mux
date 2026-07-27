"""Integration smoke: v2 pipeline order reaches master_finalize stage id."""

from __future__ import annotations

from interview_mux.v2.config import (
    ANALYSIS_ORDER_V2,
    DELIVERY_ORDER_V2,
    effective_analysis_order,
    effective_delivery_order,
)


def test_path_to_master_stage_order():
    order = list(effective_analysis_order()) + list(effective_delivery_order())
    assert order[0] == "audio_preclean"
    assert order[-1] == "master_finalize"
    assert len(order) == 41  # +8 Refinement Pass stages
    assert "disfluency_extract" not in order
    assert "master_finalize" in DELIVERY_ORDER_V2
    assert "episode_structure_compose" in ANALYSIS_ORDER_V2
