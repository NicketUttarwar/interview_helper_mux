"""Ship stages after a re-entry: stale outputs re-run, current ones get their marker back (ISSUES 112)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from interview_mux.homunculus.agenda import (
    backfill_ship_holes_after_master,
    ship_after_master_remaining,
    ship_stage_output_stale,
)
from interview_mux.v2.config import SHIP_AFTER_MASTER
from run_fixtures import isolated_run_ctx

SHIP_OUTPUTS = {
    "master_transcript_build": "master/transcript.json",
    "episode_meta_build": "publish/episode_meta.json",
    "episode_cover_prompt_craft": "publish/cover_prompt.json",
    "podcast_encode_mp3": "publish/audio.mp3",
    "episode_cover_generate": "publish/cover.jpg",
    "podcast_publish": "publish/package_ready.json",
}


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    return isolated_run_ctx(tmp_path, "ship_holes")


def _shipped_run(ctx, *, master_after_outputs: bool = False) -> None:
    master = ctx.final_path("master", "master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF" + b"\0" * 4096)
    done = ctx.final_path(".stage_done")
    done.mkdir(parents=True, exist_ok=True)
    (done / "master_finalize").write_text("")
    for rel in SHIP_OUTPUTS.values():
        p = ctx.final_path(*rel.split("/"))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"ready": true}' if rel.endswith(".json") else "x")
    base = master.stat().st_mtime
    for rel in SHIP_OUTPUTS.values():
        p = ctx.final_path(*rel.split("/"))
        t = base - 120 if master_after_outputs else base + 120
        os.utime(p, (t, t))


def test_current_outputs_without_markers_are_backfilled_not_rerun(ctx) -> None:
    _shipped_run(ctx)
    assert ship_after_master_remaining(ctx) == []
    assert not any(ship_stage_output_stale(ctx, s) for s in SHIP_AFTER_MASTER)
    filled = backfill_ship_holes_after_master(ctx)
    assert filled == list(SHIP_AFTER_MASTER)
    assert all(ctx.is_done(s) for s in SHIP_AFTER_MASTER)
    # Idempotent: nothing left to fill.
    assert backfill_ship_holes_after_master(ctx) == []


def test_outputs_older_than_a_rebuilt_master_are_remaining_and_never_backfilled(ctx) -> None:
    _shipped_run(ctx, master_after_outputs=True)
    assert all(ship_stage_output_stale(ctx, s) for s in SHIP_AFTER_MASTER)
    assert ship_after_master_remaining(ctx) == list(SHIP_AFTER_MASTER)
    assert backfill_ship_holes_after_master(ctx) == []
    assert not any(ctx.is_done(s) for s in SHIP_AFTER_MASTER)


def test_no_backfill_without_an_honest_master_finalize(ctx) -> None:
    _shipped_run(ctx)
    ctx.final_path(".stage_done", "master_finalize").unlink()
    assert backfill_ship_holes_after_master(ctx) == []
