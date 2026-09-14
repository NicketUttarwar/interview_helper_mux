"""Bounded invalidation profile tests — Phase 5A."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.execution_invalidation_profiles import (
    apply_bounded_invalidation,
    INVALIDATION_PROFILES,
)
from interview_mux.run_context import RunContext
from run_fixtures import patch_executions_root, mark_done_raw


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return RunContext("bounded_inval_test", create=True)


def test_vo_coverage_profile_clears_synth_chain_not_layup(ctx: RunContext) -> None:
    for sid in ("nugget_layup_compose", "vo_synthesize", "edl", "mix"):
        mark_done_raw(ctx, sid)

    result = apply_bounded_invalidation(ctx, "vo_coverage_heal", reason="test")
    cleared = set(result.get("cleared") or [])
    assert "vo_synthesize" in cleared or "edl" in cleared
    assert "nugget_layup_compose" not in cleared
    assert ctx.is_done("nugget_layup_compose")
    # mix is forbidden for vo_coverage_heal — must remain done
    assert ctx.is_done("mix")
    assert "mix" in set(result.get("forbidden_skipped") or [])


def test_vo_coverage_forbidden_stages_logged(ctx: RunContext) -> None:
    mark_done_raw(ctx, "mix")
    mark_done_raw(ctx, "vo_synthesize")
    result = apply_bounded_invalidation(ctx, "vo_coverage_heal", reason="test")
    skipped = set(result.get("forbidden_skipped") or [])
    assert "mix" in skipped


def test_structural_profile_exists(ctx: RunContext) -> None:
    profile = INVALIDATION_PROFILES["structural_delivery"]
    assert "mix" in profile.allowed_clear


def test_seg_resplit_heal_does_not_archive_content_brief(ctx: RunContext) -> None:
    """Nested content_brief_reanchor must still read the live brief after resplit."""
    profile = INVALIDATION_PROFILES["seg_resplit_heal"]
    assert "understanding/content_brief.json" not in (profile.archive_allowlist or ())
    assert "segments/boundaries.json" not in (profile.archive_allowlist or ())

    brief_rel = "understanding/content_brief.json"
    ctx.write_json(
        brief_rel,
        {"thesis": "keep me", "topics": [{"name": "t", "summary": "s"}]},
        skip_handoff=True,
    )
    mark_done_raw(ctx, "content_brief_reanchor")
    mark_done_raw(ctx, "segment_classification")

    apply_bounded_invalidation(ctx, "seg_resplit_heal", reason="boundary_topic_resplit")
    assert ctx.artifact_exists(brief_rel), "brief must survive seg_resplit_heal"
    brief = ctx.read_json(brief_rel)
    assert brief.get("thesis") == "keep me"

