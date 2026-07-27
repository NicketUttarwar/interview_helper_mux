"""Refinement ledger — anti-loop cap of 1 second-run (refinement) per CFI."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.refinement_identity import cfi_for_pass
from interview_mux.refinement_ledger import (
    can_run_refinement,
    load_ledger,
    record_call,
    refinement_count,
    reset_ledger_from_stages,
)
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return isolated_run_ctx(tmp_path, "exec_ledger_test")


def _cfi():
    cfi = cfi_for_pass("gap_framing_recompose")
    assert cfi is not None
    return cfi


def test_first_pass_call_does_not_count_against_refinement_cap(ctx: RunContext) -> None:
    cfi = _cfi()
    record_call(
        ctx,
        cfi_id=cfi.cfi_id,
        human_key=cfi.human_key,
        stage_id="gap_framing_compose",
        pass_id=None,
        pass_index=1,
        kind="first_pass",
        outcome="ok",
    )
    assert refinement_count(ctx, cfi.cfi_id) == 0
    assert can_run_refinement(ctx, cfi.cfi_id) is True


def test_single_refinement_allowed_then_capped(ctx: RunContext) -> None:
    cfi = _cfi()
    assert can_run_refinement(ctx, cfi.cfi_id) is True
    record_call(
        ctx,
        cfi_id=cfi.cfi_id,
        human_key=cfi.human_key,
        stage_id="gap_framing_recompose",
        pass_id="gap_framing_recompose",
        pass_index=2,
        kind="refinement",
        outcome="accepted",
    )
    assert refinement_count(ctx, cfi.cfi_id) == 1
    assert can_run_refinement(ctx, cfi.cfi_id) is False


def test_second_refinement_call_raises_runtime_error(ctx: RunContext) -> None:
    cfi = _cfi()
    record_call(
        ctx,
        cfi_id=cfi.cfi_id,
        human_key=cfi.human_key,
        stage_id="gap_framing_recompose",
        pass_id="gap_framing_recompose",
        pass_index=2,
        kind="refinement",
        outcome="accepted",
    )
    with pytest.raises(RuntimeError):
        record_call(
            ctx,
            cfi_id=cfi.cfi_id,
            human_key=cfi.human_key,
            stage_id="gap_framing_recompose",
            pass_id="gap_framing_recompose",
            pass_index=2,
            kind="refinement",
            outcome="accepted",
        )
    # Cap enforcement must not have appended a second entry.
    assert refinement_count(ctx, cfi.cfi_id) == 1


def test_ledger_persists_across_load(ctx: RunContext) -> None:
    cfi = _cfi()
    record_call(
        ctx,
        cfi_id=cfi.cfi_id,
        human_key=cfi.human_key,
        stage_id="gap_framing_recompose",
        pass_id="gap_framing_recompose",
        pass_index=2,
        kind="refinement",
        outcome="rejected_rubric",
    )
    doc = load_ledger(ctx)
    assert len(doc["calls"]) == 1
    assert doc["calls"][0]["outcome"] == "rejected_rubric"


def test_reset_ledger_from_stages_clears_counts_for_cleared_stage(ctx: RunContext) -> None:
    cfi = _cfi()
    record_call(
        ctx,
        cfi_id=cfi.cfi_id,
        human_key=cfi.human_key,
        stage_id="gap_framing_recompose",
        pass_id="gap_framing_recompose",
        pass_index=2,
        kind="refinement",
        outcome="accepted",
    )
    assert can_run_refinement(ctx, cfi.cfi_id) is False
    reset_ledger_from_stages(ctx, {"gap_framing_recompose"})
    assert refinement_count(ctx, cfi.cfi_id) == 0
    assert can_run_refinement(ctx, cfi.cfi_id) is True


def test_reset_ledger_from_stages_keeps_unrelated_stage_calls(ctx: RunContext) -> None:
    cfi = _cfi()
    record_call(
        ctx,
        cfi_id=cfi.cfi_id,
        human_key=cfi.human_key,
        stage_id="gap_framing_recompose",
        pass_id="gap_framing_recompose",
        pass_index=2,
        kind="refinement",
        outcome="accepted",
    )
    reset_ledger_from_stages(ctx, {"some_other_stage"})
    assert refinement_count(ctx, cfi.cfi_id) == 1
