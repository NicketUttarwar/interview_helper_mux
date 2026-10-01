"""A write under a sealed stage's context lands in the committed tree (ISSUES 118).

Only the write target moves. The staging location that readers and the
pre-flush barrier use is unchanged, and a cleared marker voids the seal.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.write_staging import (
    enter_stage_staging,
    exit_stage_staging,
    note_stage_sealed,
    resolve_write_path,
    stage_sealed_here,
    staged_path,
)
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    return isolated_run_ctx(tmp_path, "post_seal")


def _mark(ctx, stage: str) -> None:
    m = ctx.final_path(".stage_done", stage)
    m.parent.mkdir(parents=True, exist_ok=True)
    m.write_text("")


def test_write_target_moves_to_the_committed_tree_after_the_seal(ctx) -> None:
    enter_stage_staging("content_context")
    try:
        rel = "mastering/homunculus/memory.json"
        assert ".pending_writes" in str(resolve_write_path(ctx, rel))
        _mark(ctx, "content_context")
        note_stage_sealed(ctx, "content_context")
        assert stage_sealed_here(ctx, "content_context")
        assert resolve_write_path(ctx, rel) == ctx.run_dir.joinpath("mastering", "homunculus", "memory.json")
        # Readers and the barrier still find the staging location.
        assert ".pending_writes" in str(staged_path(ctx, rel))
    finally:
        exit_stage_staging()


def test_a_cleared_marker_voids_the_seal(ctx) -> None:
    enter_stage_staging("sfx_prompt_craft")
    try:
        _mark(ctx, "sfx_prompt_craft")
        note_stage_sealed(ctx, "sfx_prompt_craft")
        assert stage_sealed_here(ctx, "sfx_prompt_craft")
        ctx.final_path(".stage_done", "sfx_prompt_craft").unlink()
        assert not stage_sealed_here(ctx, "sfx_prompt_craft")
        assert ".pending_writes" in str(resolve_write_path(ctx, "sound_design/sfx_prompts.json"))
    finally:
        exit_stage_staging()


def test_re_entering_the_stage_reopens_its_staging(ctx) -> None:
    _mark(ctx, "content_context")
    note_stage_sealed(ctx, "content_context")
    enter_stage_staging("content_context")
    try:
        assert not stage_sealed_here(ctx, "content_context")
        assert ".pending_writes" in str(resolve_write_path(ctx, "understanding/analysis_state.json"))
    finally:
        exit_stage_staging()


def test_mark_done_notes_the_seal(ctx) -> None:
    from interview_mux.done_authority import raw_stamp_session

    with raw_stamp_session(ctx, "post_master_backfill"):
        ctx.mark_done("content_context")
    assert ctx.is_done("content_context")
    assert stage_sealed_here(ctx, "content_context")

    class _Other:
        run_dir = ctx.run_dir.parent / "other"

        @staticmethod
        def is_done(stage: str) -> bool:
            return True

    assert not stage_sealed_here(_Other(), "content_context")
