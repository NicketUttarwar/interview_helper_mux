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
    assert "audio_probe_build" in order
    assert "vernacular_segment_sanitize" in order
    assert "disfluency_extract" not in order
    assert "master_finalize" in DELIVERY_ORDER_V2
    assert "episode_structure_compose" in ANALYSIS_ORDER_V2
    assert order.index("transcribe") < order.index("audio_probe_build")
    assert order.index("boundary_topic_resplit") < order.index("vernacular_segment_sanitize")
