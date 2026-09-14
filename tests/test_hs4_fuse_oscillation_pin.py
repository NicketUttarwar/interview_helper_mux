"""HS-4: fuse_oscillation pins the fuse writer, never edl.

Do not start a run. HS-1 re-entry, HS-3 skip-audit, F5 junction/mix QC stay as-is.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.delivery_guardrails import record_delivery_residual
from interview_mux.heal_routing import (
    FAMILY_JUNCTION,
    classify_heal_error,
    resume_stage_for_error_class,
)
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import (
    fuse_oscillation_heal_resume_stage,
    producer_pin_for_token,
)
from interview_mux.thrash_hardening import heal_navigate
from run_fixtures import isolated_run_ctx

_FUSE_ERR = "fuse_oscillation_halt on connector_fuse"
_PRE_ERR = "fuse_oscillation pass_id=pre_ranking"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hs4_fuse")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def test_hs4_fuse_oscillation_pins_fuse_not_edl(ctx: RunContext) -> None:
    assert fuse_oscillation_heal_resume_stage(ctx, error=_FUSE_ERR) == "connector_fuse_pass"
    assert producer_pin_for_token(_FUSE_ERR, ctx=ctx) == "connector_fuse_pass"
    assert producer_pin_for_token("fuse_oscillation") == "connector_fuse_pass"
    assert resume_stage_for_error_class("fuse_oscillation") == "connector_fuse_pass"
    route = classify_heal_error(_FUSE_ERR, ctx, stage="edl")
    assert route is not None
    assert route.from_stage == "connector_fuse_pass"
    assert route.from_stage != "edl"
    assert route.family == FAMILY_JUNCTION
    nav = heal_navigate(ctx, error=_FUSE_ERR, stage="edl")
    assert nav["from_stage"] == "connector_fuse_pass"
    assert nav["from_stage"] != "edl"


def test_hs4_pre_ranking_error_pins_pre_ranking_pass(ctx: RunContext) -> None:
    assert (
        fuse_oscillation_heal_resume_stage(ctx, error=_PRE_ERR)
        == "connector_fuse_pass_pre_ranking"
    )
    route = classify_heal_error(_PRE_ERR, ctx, stage="connector_fuse_pass")
    assert route is not None
    assert route.from_stage == "connector_fuse_pass_pre_ranking"
    assert route.from_stage != "edl"
    nav = heal_navigate(ctx, error=_PRE_ERR, stage="connector_fuse_pass")
    assert nav["from_stage"] == "connector_fuse_pass_pre_ranking"


def test_hs4_residual_pass_id_pre_ranking_pins_pre_ranking(ctx: RunContext) -> None:
    record_delivery_residual(
        ctx,
        kind="fuse_oscillation",
        severity="critical",
        stage="connector_fuse_pass",
        detail={"pass_id": "pre_ranking", "sig": "a|b"},
    )
    assert (
        fuse_oscillation_heal_resume_stage(ctx, error="fuse_oscillation")
        == "connector_fuse_pass_pre_ranking"
    )
    route = classify_heal_error("fuse_oscillation", ctx)
    assert route is not None
    assert route.from_stage == "connector_fuse_pass_pre_ranking"


def test_hs4_junction_remaster_stays_on_junction_not_fuse(ctx: RunContext) -> None:
    for err in (
        "junction_oscillation remaster loop",
        "junction_remaster_budget exhausted",
        "junction_budget_exhaust",
    ):
        route = classify_heal_error(err, ctx, stage="mix")
        assert route is not None, err
        assert route.from_stage == "junction_snip_qa", err
        assert route.from_stage not in {
            "connector_fuse_pass",
            "connector_fuse_pass_pre_ranking",
            "edl",
        }
        assert route.family == FAMILY_JUNCTION
        assert producer_pin_for_token(err, ctx=ctx) != "connector_fuse_pass"
