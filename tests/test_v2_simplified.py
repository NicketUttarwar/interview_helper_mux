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
    assert len(ANALYSIS_ORDER_V2) == 19
    assert len(DELIVERY_ORDER_V2) == 13
    assert len(ANALYSIS_ORDER_V2) + len(DELIVERY_ORDER_V2) == 32


def test_v2_llm_stage_count():
    assert len(ALL_LLM_STAGES_V2) == 15


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
    assert effective_delivery_order()[-1] == "master_finalize"


def test_v2_phases_module():
    from interview_mux.v2.phases import PHASES, phase_for_stage

    assert len(PHASES) == 10
    assert phase_for_stage("transcript_review") is not None
    assert phase_for_stage("master_finalize") is not None
