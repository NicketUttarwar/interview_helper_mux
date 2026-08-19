"""Tests for v2 simplified greenfield configuration and pipeline shape."""

from __future__ import annotations

import pytest

from interview_mux.v2.config import (
    ANALYSIS_ORDER_V2,
    DELIVERY_ORDER_V2,
    ALL_LLM_STAGES_V2,
    effective_analysis_order,
    effective_delivery_order,
    v2_auto_commit,
    v2_enabled,
    v2_g1_optional,
)
from interview_mux.write_staging import write_approval_enabled


def test_v2_analysis_order_excludes_disfluency():
    assert "disfluency_extract" not in ANALYSIS_ORDER_V2
    # Includes 8-wave research + two-pass Shape soft-gate stages
    assert "mastering_plan_synthesize" in ANALYSIS_ORDER_V2
    assert "mastering_plan_confirm" in ANALYSIS_ORDER_V2
    assert "listen_delight_audit" in DELIVERY_ORDER_V2
    assert "junction_snip_qa" in DELIVERY_ORDER_V2
    assert DELIVERY_ORDER_V2.index("mix") < DELIVERY_ORDER_V2.index("junction_snip_qa")
    assert DELIVERY_ORDER_V2.index("junction_snip_qa") < DELIVERY_ORDER_V2.index("master_finalize")
    assert len(DELIVERY_ORDER_V2) == 32
    assert "ranking_refine" not in DELIVERY_ORDER_V2
    assert "gap_framing_recompose" in DELIVERY_ORDER_V2
    assert len(ANALYSIS_ORDER_V2) >= 27


def test_v2_llm_stage_count():
    # Refinement Pass stages (refinement_agenda, gap_framing_recompose, selection_framing_apply,
    # ranking_refine, narrative_arc_refine, transitions_refine, sdp_intent_refine,
    # edl_narrative_refine) are deterministic — not LLM calls — so they are excluded here.
    assert "junction_snip_qa" not in ALL_LLM_STAGES_V2
    assert len(ALL_LLM_STAGES_V2) >= 16


def test_v2_enabled_by_default(monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_CONFIG", "")
    from interview_mux.config import merged_config

    cfg = merged_config()
    assert cfg.get("v2", {}).get("enabled", True) is True
    assert v2_enabled() is True
    assert v2_auto_commit() is True
    assert v2_g1_optional() is True
    assert write_approval_enabled() is False


def test_effective_orders_use_v2_when_enabled():
    assert "disfluency_extract" not in effective_analysis_order()
    order = effective_delivery_order()
    assert "junction_snip_qa" in order
    assert order.index("mix") < order.index("junction_snip_qa") < order.index("master_finalize")
    assert order[-1] == "podcast_publish"


def test_v2_phases_module():
    from interview_mux.v2.phases import PHASES, phase_for_stage

    assert len(PHASES) == 10
    assert phase_for_stage("transcript_review") is not None
    assert phase_for_stage("master_finalize") is not None
