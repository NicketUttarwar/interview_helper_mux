"""At run end, staged files of done stages that the committed tree never got are promoted (ISSUES 118)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from interview_mux.write_staging import promote_lost_staged_writes
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    return isolated_run_ctx(tmp_path, "promote_lost")


def _staged(ctx, stage: str, rel: str, text: str) -> Path:
    p = ctx.run_dir / ".pending_writes" / stage / Path(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _committed(ctx, rel: str, text: str) -> Path:
    p = ctx.run_dir / Path(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _mark(ctx, stage: str) -> None:
    m = ctx.final_path(".stage_done", stage)
    m.parent.mkdir(parents=True, exist_ok=True)
    m.write_text("")


def test_a_missing_committed_copy_is_promoted_and_an_older_one_is_not_overwritten(ctx, monkeypatch) -> None:
    monkeypatch.setattr("interview_mux.write_staging._owned_staging_path", lambda c, s, r: True)
    _mark(ctx, "edl")
    lost = _staged(ctx, "edl", "master/clone_adjacency_verify.json", '{"lost": true}')
    staged_old = _staged(ctx, "edl", "master/air_order_integrity.json", '{"v": "staged"}')
    newer = _committed(ctx, "master/air_order_integrity.json", '{"v": "committed_newer"}')
    t = staged_old.stat().st_mtime + 60
    os.utime(newer, (t, t))
    promoted = promote_lost_staged_writes(ctx)
    assert promoted == ["edl/master/clone_adjacency_verify.json"]
    assert (ctx.run_dir / "master/clone_adjacency_verify.json").read_text(encoding="utf-8") == '{"lost": true}'
    assert not lost.exists()
    assert newer.read_text(encoding="utf-8") == '{"v": "committed_newer"}'
    assert staged_old.exists()


def test_an_undone_stage_and_a_foreign_path_are_left_alone(ctx, monkeypatch) -> None:
    monkeypatch.setattr("interview_mux.write_staging._owned_staging_path", lambda c, s, r: r.endswith("own.json"))
    _mark(ctx, "edl")
    _staged(ctx, "edl", "master/foreign.json", "{}")
    _staged(ctx, "mix", "master/own.json", "{}")  # mix is not done
    assert promote_lost_staged_writes(ctx) == []
    assert not (ctx.run_dir / "master/foreign.json").exists()
    assert not (ctx.run_dir / "master/own.json").exists()
