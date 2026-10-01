"""A write under a sealed stage's context lands in the committed tree (ISSUES 118)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.write_staging import (
    enter_stage_staging,
    exit_stage_staging,
    note_stage_sealed,
    stage_sealed_here,
    staged_path,
)
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    return isolated_run_ctx(tmp_path, "post_seal")


def test_staged_path_moves_to_the_committed_tree_after_the_seal(ctx) -> None:
    enter_stage_staging("content_context")
    try:
        rel = "mastering/homunculus/memory.json"
        before = staged_path(ctx, rel)
        assert ".pending_writes" in str(before)
        note_stage_sealed(ctx, "content_context")
        assert stage_sealed_here(ctx, "content_context")
        after = staged_path(ctx, rel)
        assert ".pending_writes" not in str(after)
        assert after == ctx.run_dir.joinpath("mastering", "homunculus", "memory.json")
    finally:
        exit_stage_staging()


def test_re_entering_the_stage_reopens_its_staging(ctx) -> None:
    note_stage_sealed(ctx, "content_context")
    enter_stage_staging("content_context")
    try:
        assert not stage_sealed_here(ctx, "content_context")
        assert ".pending_writes" in str(staged_path(ctx, "understanding/analysis_state.json"))
    finally:
        exit_stage_staging()


def test_mark_done_notes_the_seal(ctx) -> None:
    from interview_mux.done_authority import raw_stamp_session

    # The raw stamp escape writes the marker without the heal ladder, which
    # would refuse a stage with no outputs in this fixture.
    with raw_stamp_session(ctx, "post_master_backfill"):
        ctx.mark_done("content_context")
    assert ctx.is_done("content_context")
    assert stage_sealed_here(ctx, "content_context")
    # Another run directory is not affected by this process's note.
    assert _other_run_not_sealed(ctx)


def _other_run_not_sealed(ctx) -> bool:
    class _Other:
        run_dir = ctx.run_dir.parent / "other"

    return not stage_sealed_here(_Other(), "content_context")
