"""Bounded invalidation profile tests — Phase 5A."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.execution_invalidation_profiles import (
    apply_bounded_invalidation,
    INVALIDATION_PROFILES,
)
from interview_mux.run_context import RunContext
from run_fixtures import patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return RunContext("bounded_inval_test", create=True)


def test_vo_coverage_profile_clears_synth_chain_not_layup(ctx: RunContext) -> None:
    for sid in ("nugget_layup_compose", "vo_synthesize", "edl", "mix"):
        ctx.mark_done(sid, force=True)

    result = apply_bounded_invalidation(ctx, "vo_coverage_heal", reason="test")
    cleared = set(result.get("cleared") or [])
    assert "vo_synthesize" in cleared or "edl" in cleared
    assert "nugget_layup_compose" not in cleared
    assert ctx.is_done("nugget_layup_compose")
    assert not ctx.is_done("mix")


def test_vo_coverage_forbidden_stages_logged(ctx: RunContext) -> None:
    ctx.mark_done("mix", force=True)
    ctx.mark_done("vo_synthesize", force=True)
    result = apply_bounded_invalidation(ctx, "vo_coverage_heal", reason="test")
    skipped = set(result.get("forbidden_skipped") or [])
    assert "mix" in skipped


def test_structural_profile_exists(ctx: RunContext) -> None:
    profile = INVALIDATION_PROFILES["structural_delivery"]
    assert "mix" in profile.allowed_clear
