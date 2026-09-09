"""Anti-footgun invariants for artifact_sanitize (W0/W8 skeleton + landed waves)."""

from __future__ import annotations

from interview_mux.artifact_sanitize.air_script import commit_air_contract
from interview_mux.artifact_sanitize.halt import (
    DEFAULT_HALT_AFTER,
    ERROR_PREFIX,
    halt_after_for_sanitize,
    sanitize_refused_message,
)
from interview_mux.artifact_sanitize.reentry import sanitize_reentry_guard
from interview_mux.delivery_guardrails import G3_RECONCILE_CHAIN
from interview_mux.pipeline import canonical_stage_id
from interview_mux.run_context import RunContext
from interview_mux.v2.config import DELIVERY_ORDER


def test_reentry_guard_nested_skip() -> None:
    ctx = RunContext(create=True)
    seen: list[bool] = []
    with sanitize_reentry_guard(ctx) as nested_outer:
        assert nested_outer is False
        seen.append(nested_outer)
        with sanitize_reentry_guard(ctx) as nested_inner:
            assert nested_inner is True
            seen.append(nested_inner)
            # Nested commit must no-op via guard
            result = commit_air_contract(ctx, reason="nested")
            assert result.metrics.get("skipped") == "reentry" or result.ok
    assert seen == [False, True]
    # Flag cleared after exit
    with sanitize_reentry_guard(ctx) as again:
        assert again is False


def test_sanitize_refused_message_format() -> None:
    msg = sanitize_refused_message("gap_report", ["layup_coverage_below_floor:0.1", "other"])
    assert msg.startswith(ERROR_PREFIX)
    assert msg.startswith("sanitize_refused:gap_report:")
    assert "layup_coverage_below_floor" in msg


def test_halt_after_default() -> None:
    assert halt_after_for_sanitize("gap_report") >= 1
    assert DEFAULT_HALT_AFTER == 3


def test_delivery_order_gap_after_layup_and_air_after_seams() -> None:
    i_layup = DELIVERY_ORDER.index("nugget_layup_compose")
    assert DELIVERY_ORDER[i_layup + 1] == "gap_report_sanitize"
    i_seams = DELIVERY_ORDER.index("air_script_seams")
    assert DELIVERY_ORDER[i_seams + 1] == "air_contract_sanitize"


def test_pipeline_aliases_gap_and_air() -> None:
    assert canonical_stage_id("gap") == "gap_report_sanitize"
    assert canonical_stage_id("gap_report") == "gap_report_sanitize"
    assert canonical_stage_id("air") == "air_contract_sanitize"
    assert canonical_stage_id("air_contract") == "air_contract_sanitize"


def test_g3_reconcile_includes_layup_gap_air_sanitize() -> None:
    assert "nugget_layup_compose" in G3_RECONCILE_CHAIN
    assert "gap_report_sanitize" in G3_RECONCILE_CHAIN
    assert "air_contract_sanitize" in G3_RECONCILE_CHAIN
    assert G3_RECONCILE_CHAIN.index("nugget_layup_compose") < G3_RECONCILE_CHAIN.index(
        "gap_report_sanitize"
    )
    assert G3_RECONCILE_CHAIN.index("gap_report_sanitize") < G3_RECONCILE_CHAIN.index(
        "air_contract_sanitize"
    )


def test_g3_includes_transitions_sdp_adjudicate() -> None:
    assert "transitions" in G3_RECONCILE_CHAIN
    assert "sound_design_plan" in G3_RECONCILE_CHAIN
    assert "vo_line_adjudicate" in G3_RECONCILE_CHAIN
    assert G3_RECONCILE_CHAIN.index("transitions") < G3_RECONCILE_CHAIN.index(
        "vo_line_adjudicate"
    )
