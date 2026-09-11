"""F-06: retired refine ghosts are non-dispatchable (StageRetired)."""

from __future__ import annotations

import pytest

from interview_mux.pipeline import (
    DELIVERY_ORDER,
    _delivery_stage_fns,
    _run_single_stage_impl,
    run_single_stage,
)
from interview_mux.refinement_passes import (
    RETIRED_REFINE_GHOSTS,
    refuse_retired_refine,
    remap_retired_refine_pin,
    run_ranking_refine,
)
from interview_mux.web.stages import STAGE_BY_ID

EXPECTED_GHOSTS = frozenset(
    {
        "ranking_refine",
        "narrative_arc_refine",
        "transitions_refine",
        "sdp_intent_refine",
        "edl_narrative_refine",
    }
)


def test_f06_retired_set_membership(tmp_path) -> None:
    from run_fixtures import isolated_run_ctx

    assert RETIRED_REFINE_GHOSTS == EXPECTED_GHOSTS
    assert "sfx_prompt_refine" not in RETIRED_REFINE_GHOSTS
    for ghost in RETIRED_REFINE_GHOSTS:
        assert ghost not in DELIVERY_ORDER
        assert ghost not in STAGE_BY_ID
    ctx = isolated_run_ctx(tmp_path, "f06_membership")
    fns = _delivery_stage_fns(ctx)
    for ghost in RETIRED_REFINE_GHOSTS:
        assert ghost not in fns


def test_f06_run_ranking_refine_raises_stage_retired() -> None:
    with pytest.raises(RuntimeError, match="StageRetired"):
        run_ranking_refine(None)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="StageRetired"):
        refuse_retired_refine("ranking_refine")


def test_f06_run_single_stage_ranking_refine_raises(tmp_path, monkeypatch) -> None:
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "f06_dispatch")
    monkeypatch.setattr(
        "interview_mux.pipeline._guard_stage_reuse",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_lifecycle.run_phase_checks",
        lambda *_a, **_k: [],
    )
    with pytest.raises(RuntimeError, match="StageRetired"):
        run_single_stage(ctx, "ranking_refine")
    with pytest.raises(RuntimeError, match="StageRetired"):
        _run_single_stage_impl(ctx, "ranking_refine")


def test_f06_remap_retired_pin_to_live_or_recompose(tmp_path) -> None:
    from run_fixtures import isolated_run_ctx

    ctx = isolated_run_ctx(tmp_path, "f06_remap")
    pin = remap_retired_refine_pin(ctx, "ranking_refine")
    assert pin not in RETIRED_REFINE_GHOSTS
    assert pin in DELIVERY_ORDER or pin == "gap_framing_recompose"
