"""HS-2: resplit heal must not archive its own boundaries.json write.

Live write survives seg_resplit_heal (1A). Same fingerprint does not archive
even if the allowlist is restored (2A). Missing-at-entry and wrote-then-lost
must not _mark_done_raw (3A / clinic B1).

Do not start a run. HS-3 fuse skip-audit, HS-1 remainder cap, HS-5 vernacular stay.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from interview_mux.execution_invalidation_profiles import (
    INVALIDATION_PROFILES,
    apply_bounded_invalidation,
    _boundaries_fingerprint,
    seg_resplit_fingerprint_flipped,
)
from interview_mux.run_context import RunContext
from interview_mux.stages.segmentation import run_boundary_topic_resplit
from run_fixtures import isolated_run_ctx, mark_done_raw

_BOUNDS = "segments/boundaries.json"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "hs2_resplit")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    return run


def _plant_bounds(ctx: RunContext, *, segment_id: str = "seg_001") -> None:
    path = ctx.final_path(*_BOUNDS.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"boundaries":[{"segment_id":"%s","start_ms":0,"end_ms":1000}]}' % segment_id,
        encoding="utf-8",
    )


def test_hs2_profile_does_not_allowlist_own_primary() -> None:
    profile = INVALIDATION_PROFILES["seg_resplit_heal"]
    assert profile.archive_allowlist == ()
    assert _BOUNDS not in (profile.archive_allowlist or ())
    assert profile.require_fingerprint_flip is True


def test_hs2_heal_keeps_live_boundaries_and_unmarks_consumers(ctx: RunContext) -> None:
    _plant_bounds(ctx)
    for sid in ("segment_classification", "content_brief_reanchor", "connector_fuse_pass"):
        mark_done_raw(ctx, sid)

    result = apply_bounded_invalidation(ctx, "seg_resplit_heal", reason="boundary_topic_resplit")
    assert result.get("archived") == []
    assert ctx.artifact_exists(_BOUNDS)
    assert not ctx.is_done("segment_classification")
    assert not ctx.is_done("content_brief_reanchor")
    assert not ctx.is_done("connector_fuse_pass")


def test_hs2_same_fingerprint_does_not_archive_even_with_allowlist(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant_bounds(ctx)
    fp = _boundaries_fingerprint(ctx)
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "boundary_topic_resplit_bounds_fp": fp,
        },
        skip_handoff=True,
    )
    assert seg_resplit_fingerprint_flipped(ctx) is False

    original = INVALIDATION_PROFILES["seg_resplit_heal"]
    monkeypatch.setitem(
        INVALIDATION_PROFILES,
        "seg_resplit_heal",
        replace(original, archive_allowlist=(_BOUNDS,)),
    )
    result = apply_bounded_invalidation(ctx, "seg_resplit_heal", reason="hs2_same_fp")
    assert result.get("archive_skipped_fingerprint") is True
    assert result.get("archived") == []
    assert ctx.artifact_exists(_BOUNDS)


def test_hs2_fingerprint_flip_would_archive_only_when_allowlisted(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant_bounds(ctx)
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "boundary_topic_resplit_bounds_fp": "not-the-live-hash",
        },
        skip_handoff=True,
    )
    assert seg_resplit_fingerprint_flipped(ctx) is True

    original = INVALIDATION_PROFILES["seg_resplit_heal"]
    monkeypatch.setitem(
        INVALIDATION_PROFILES,
        "seg_resplit_heal",
        replace(original, archive_allowlist=(_BOUNDS,)),
    )
    result = apply_bounded_invalidation(ctx, "seg_resplit_heal", reason="hs2_flipped")
    assert result.get("archive_skipped_fingerprint") is False
    assert _BOUNDS in (result.get("archived") or [])
    assert not ctx.artifact_exists(_BOUNDS)


def test_hs2_missing_at_entry_refuses_hollow_done(ctx: RunContext) -> None:
    assert not ctx.artifact_exists(_BOUNDS)
    run_boundary_topic_resplit(ctx)
    assert not ctx.is_done("boundary_topic_resplit")


def test_hs2_wrote_then_lost_does_not_raw_mark(ctx: RunContext) -> None:
    ctx.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "boundary_topic_resplit_wrote": True,
        },
        skip_handoff=True,
    )
    assert not ctx.artifact_exists(_BOUNDS)
    run_boundary_topic_resplit(ctx)
    assert not ctx.is_done("boundary_topic_resplit")
    assert not ctx.artifact_exists(_BOUNDS)


def test_hs2_empty_allowlist_does_not_nuclear_archive(ctx: RunContext) -> None:
    _plant_bounds(ctx)
    result = apply_bounded_invalidation(ctx, "seg_resplit_heal", reason="hs2_empty")
    assert result.get("archived") == []
    assert ctx.artifact_exists(_BOUNDS)


def test_hs2_corrupt_bounds_archive_does_not_self_archive_fresh_write(
    ctx: RunContext,
) -> None:
    from interview_mux.execution_invalidation_profiles import (
        archive_corrupt_boundaries_if_needed,
    )

    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "boundary_topic_resplit_wrote": True},
        skip_handoff=True,
    )
    _plant_bounds(ctx)
    out = archive_corrupt_boundaries_if_needed(ctx)
    assert out.get("reason") == "fresh_write"
    assert out.get("archived") == []
    assert ctx.artifact_exists(_BOUNDS)

    path = ctx.final_path(*_BOUNDS.split("/"))
    path.write_text("{not json", encoding="utf-8")
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "boundary_topic_resplit_wrote": False},
        skip_handoff=True,
    )
    out = archive_corrupt_boundaries_if_needed(ctx)
    assert out.get("reason") == "corrupt"
    assert _BOUNDS in (out.get("archived") or [])
    assert not ctx.artifact_exists(_BOUNDS)
