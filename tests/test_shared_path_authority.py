"""A-05 shared-path authoritative_producer + co-producer reconcile."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.post_decision_sanitize import (
    after_shared_path_write,
    stamp_authoritative_producer,
)
from interview_mux.run_context import RunContext


def _write_raw(ctx: RunContext, rel: str, data: dict) -> None:
    path = ctx.path(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    from interview_mux.file_store import write_json as fs_write_json

    fs_write_json(path, data)


def test_a05_reanchor_keeps_upstream_content_context_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A-05 / SYN-SHARED-01: a later co-producer restamps, but never unmarks the
    earlier one. Unmarking content_context here made the analysis walk re-run
    it, rewrite the brief, and unmark the reanchor again (ISSUES entry 46)."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_a05_brief", create=True)
    brief = {"thesis": "A clear thesis.", "topics": [{"name": "A", "summary": "B"}]}
    _write_raw(ctx, "understanding/content_brief.json", brief)
    stamp_authoritative_producer(ctx, "understanding/content_brief.json", "content_context")
    (ctx.run_dir / ".stage_done").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / ".stage_done" / "content_context").touch()
    (ctx.run_dir / ".stage_done" / "content_brief_reanchor").touch()
    assert ctx.is_done("content_context")

    brief2 = {
        "thesis": "Reanchored thesis with more detail.",
        "topics": [{"name": "A", "summary": "Updated summary B"}],
    }
    _write_raw(ctx, "understanding/content_brief.json", brief2)
    result = after_shared_path_write(
        ctx, "understanding/content_brief.json", "content_brief_reanchor"
    )
    live = ctx.read_json("understanding/content_brief.json")
    assert (live.get("_meta") or {}).get("authoritative_producer") == "content_brief_reanchor"
    assert result.get("cleared") == []
    assert ctx.is_done("content_context")
    assert ctx.is_done("content_brief_reanchor")


def test_a05_upstream_rewrite_clears_downstream_co_producer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The earlier producer rewriting the path does stale the later one."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_a05_upstream", create=True)
    brief = {"thesis": "A clear thesis.", "topics": [{"name": "A", "summary": "B"}]}
    _write_raw(ctx, "understanding/content_brief.json", brief)
    stamp_authoritative_producer(
        ctx, "understanding/content_brief.json", "content_brief_reanchor"
    )
    (ctx.run_dir / ".stage_done").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / ".stage_done" / "content_context").touch()
    (ctx.run_dir / ".stage_done" / "content_brief_reanchor").touch()
    brief2 = {"thesis": "Fresh context pass.", "topics": [{"name": "C", "summary": "D"}]}
    _write_raw(ctx, "understanding/content_brief.json", brief2)
    result = after_shared_path_write(ctx, "understanding/content_brief.json", "content_context")
    assert "content_brief_reanchor" in (result.get("cleared") or [])
    assert ctx.is_done("content_context")


def test_a05_sound_design_plan_never_unmarks_palettes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exec_047: sound_design_plan landing wiped sound_design_palettes, which
    re-ran, took the plan file back, and wiped sound_design_plan (one LLM call
    per cycle, run stalled at 53 of 72)."""
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_a05_sdp", create=True)
    sdp = {"version": 1, "coherence": {"sonic_identity": "warm"}, "palettes": [], "assets": []}
    _write_raw(ctx, "understanding/sound_design_plan.json", sdp)
    stamp_authoritative_producer(
        ctx, "understanding/sound_design_plan.json", "sound_design_palettes"
    )
    (ctx.run_dir / ".stage_done").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / ".stage_done" / "sound_design_palettes").touch()
    sdp2 = dict(sdp, palettes=[{"palette_id": "p1", "label": "warm keys"}])
    _write_raw(ctx, "understanding/sound_design_plan.json", sdp2)
    result = after_shared_path_write(
        ctx, "understanding/sound_design_plan.json", "sound_design_plan"
    )
    assert result.get("cleared") == []
    assert ctx.is_done("sound_design_palettes")


def test_a05_same_fingerprint_no_unmark_thrash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_a05_same", create=True)
    brief = {"thesis": "A clear thesis.", "topics": [{"name": "A", "summary": "B"}]}
    _write_raw(ctx, "understanding/content_brief.json", brief)
    stamped = stamp_authoritative_producer(
        ctx, "understanding/content_brief.json", "content_context"
    )
    assert stamped is not None
    (ctx.run_dir / ".stage_done").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / ".stage_done" / "content_context").touch()
    (ctx.run_dir / ".stage_done" / "content_brief_reanchor").touch()
    result = after_shared_path_write(ctx, "understanding/content_brief.json", "content_context")
    assert result.get("fingerprint_unchanged") is True or result.get("cleared") == []
