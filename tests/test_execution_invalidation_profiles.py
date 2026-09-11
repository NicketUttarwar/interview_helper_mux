"""B-06: bounded invalidation profiles — unknown id + archive_allowlist."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.execution_invalidation_profiles import (
    INVALIDATION_PROFILES,
    apply_bounded_invalidation,
)
from interview_mux.run_context import RunContext
from run_fixtures import mark_done_raw, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return RunContext("exec_inval_profiles", create=True)


def test_unknown_profile_raises(ctx: RunContext) -> None:
    with pytest.raises(ValueError, match="unknown invalidation profile_id"):
        apply_bounded_invalidation(ctx, "not_a_real_profile", reason="test")


def test_w0_unknown_profile_raises(ctx: RunContext) -> None:
    """Scorecard alias for B-06 unknown-profile Done-when."""
    with pytest.raises(ValueError, match="unknown invalidation profile_id"):
        apply_bounded_invalidation(ctx, "totally_bogus", reason="scorecard")


def test_archive_allowlist_archives_only_listed_paths(ctx: RunContext) -> None:
    import json

    profile = INVALIDATION_PROFILES["seg_resplit_heal"]
    assert profile.archive_allowlist

    def _raw(rel: str, data: dict) -> None:
        path = ctx.path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    _raw("segments/boundaries.json", {"boundaries": [{"segment_id": "seg_001"}]})
    _raw("understanding/content_brief.json", {"topics": []})
    # Not on allowlist — must survive.
    _raw("understanding/speakers.json", {"speakers": []})
    for sid in profile.allowed_clear[:3]:
        mark_done_raw(ctx, sid)

    result = apply_bounded_invalidation(ctx, "seg_resplit_heal", reason="b06_archive")
    archived = set(result.get("archived") or [])
    assert "segments/boundaries.json" in archived
    assert "understanding/content_brief.json" in archived
    assert "understanding/speakers.json" not in archived
    assert not ctx.artifact_exists("segments/boundaries.json")
    assert not ctx.artifact_exists("understanding/content_brief.json")
    assert ctx.artifact_exists("understanding/speakers.json")


def test_empty_archive_allowlist_is_markers_pending_only(ctx: RunContext) -> None:
    import json

    profile = INVALIDATION_PROFILES["hitch_id_churn"]
    assert profile.archive_allowlist == ()
    path = ctx.path("segments/boundaries.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"boundaries": [{"segment_id": "seg_001"}]}), encoding="utf-8")
    mark_done_raw(ctx, "segment_classification")
    result = apply_bounded_invalidation(ctx, "hitch_id_churn", reason="b06_empty")
    assert result.get("archived") == []
    assert ctx.artifact_exists("segments/boundaries.json")
    assert not ctx.is_done("segment_classification")


def test_structural_profile_exists(ctx: RunContext) -> None:
    profile = INVALIDATION_PROFILES["structural_delivery"]
    assert "mix" in profile.allowed_clear
