"""refinement_agenda S1–S3 hygiene — ownership re-home, confirm default, priors off."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.artifact_ownership import row_for_path
from interview_mux.refinement_agenda import run_refinement_agenda
from interview_mux.refinement_catalog import refinement_cfg
from interview_mux.refinement_priors import priors_enabled
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return isolated_run_ctx(tmp_path, "exec_ra_s1_s3")


def test_s1_refinement_side_artifacts_not_owned_by_agenda() -> None:
    """S1: plan/cascade/ensemble ALLOW re-homed off refinement_agenda."""
    plan = row_for_path("understanding/refinement_plan.json")
    cascade = row_for_path("understanding/refinement_cascade.json")
    ensemble = row_for_path("understanding/refinement_ensemble_lint.json")
    agenda = row_for_path("understanding/refinement_agenda.json")

    assert agenda is not None
    assert agenda.producers == ("refinement_agenda",)

    assert plan is not None
    assert "refinement_agenda" not in plan.producers
    assert "gap_framing_recompose" in plan.producers
    assert "selection_framing_apply" in plan.producers
    assert plan.authoritative == "selection_framing_apply"

    assert cascade is not None
    assert cascade.producers == ("gap_framing_recompose",)
    assert cascade.authoritative == "gap_framing_recompose"

    assert ensemble is not None
    assert "refinement_agenda" not in ensemble.producers
    assert ensemble.authoritative == "ops"


def test_s2_default_phase_is_confirm(ctx: RunContext) -> None:
    """S2: production-safe default is confirm; draft stays explicit/test-only."""
    import inspect

    from interview_mux import refinement_agenda as mod

    params = inspect.signature(mod.run_refinement_agenda).parameters
    assert params["phase"].default == "confirm"

    doc = run_refinement_agenda(ctx)
    assert doc.get("phase") == "confirm"
    assert ctx.is_done("refinement_agenda")


def test_s3_priors_disabled_by_default() -> None:
    """S3: Full-auto defaults do not soft-bias eligible classes."""
    priors = (refinement_cfg().get("priors") or {})
    assert priors.get("enabled") in (False, "false", 0, "0", "off", None) or (
        not priors_enabled()
    )
    assert priors_enabled() is False
