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


def test_a05_reanchor_clears_content_context_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A-05 / SYN-SHARED-01: rewrite restamps producer + reconciles co-producer done."""
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
    assert "content_context" in (result.get("cleared") or []) or not ctx.is_done("content_context")


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
