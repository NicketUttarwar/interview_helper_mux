"""Wave 0.2 — shared-path authority + post_decision_sanitize."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.post_decision_sanitize import (
    SHARED_PATHS,
    post_decision_sanitize,
    stamp_authoritative_producer,
)
from interview_mux.run_context import RunContext
from run_fixtures import mark_done_raw, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return RunContext("exec_post_decision_w0", create=True)


def test_shared_paths_cover_three_artifacts() -> None:
    assert SHARED_PATHS["content_brief"] == "understanding/content_brief.json"
    assert SHARED_PATHS["boundaries"] == "segments/boundaries.json"
    assert SHARED_PATHS["sound_design_plan"] == "understanding/sound_design_plan.json"


def test_stamp_authoritative_producer_writes_meta(ctx: RunContext) -> None:
    rel = "understanding/content_brief.json"
    path = ctx.final_path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "thesis": "test",
                "topics": [{"name": "t", "summary": "s"}],
                "_meta": {"producer_stage": "content_context", "stale": False},
            }
        ),
        encoding="utf-8",
    )
    stamped = stamp_authoritative_producer(ctx, "content_brief", "content_brief_reanchor")
    assert stamped is not None
    meta = stamped.get("_meta") or {}
    assert meta.get("authoritative_producer") == "content_brief_reanchor"
    assert meta.get("content_hash")
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert (on_disk.get("_meta") or {}).get("authoritative_producer") == (
        "content_brief_reanchor"
    )


def test_post_decision_sanitize_writes_inventory_and_unmarks(ctx: RunContext) -> None:
    mark_done_raw(ctx, "segment_classification", "content_brief_reanchor", "edl")
    out = post_decision_sanitize(
        ctx,
        "resplit_heal_demo",
        implicated_stages=["segment_classification", "content_brief_reanchor"],
        reason="A-05/B-01 ritual",
    )
    assert out["decision_id"] == "resplit_heal_demo"
    inv_path = ctx.run_dir / "operator" / "gap_inventory" / "resplit_heal_demo.json"
    assert inv_path.is_file()
    doc = json.loads(inv_path.read_text(encoding="utf-8"))
    assert "segment_classification" in doc.get("cleared") or not ctx.is_done(
        "segment_classification"
    )
    assert not ctx.is_done("segment_classification")
    assert not ctx.is_done("content_brief_reanchor")
    assert ctx.is_done("edl")


def test_post_decision_sanitize_via_profile(ctx: RunContext) -> None:
    mark_done_raw(ctx, "segment_classification", "connector_fuse_pass", "mix")
    out = post_decision_sanitize(
        ctx,
        "seg_via_profile",
        profile_id="seg_resplit_heal",
        reason="bounded",
    )
    assert out.get("invalidation", {}).get("profile_id") == "seg_resplit_heal"
    assert not ctx.is_done("segment_classification")
    assert ctx.is_done("mix")


def test_post_decision_honors_music_clear_blocked(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    mark_done_raw(ctx, "sound_design_plan", "segment_classification")
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.music_clear_blocked",
        lambda _ctx, target, source="": target == "sound_design_plan",
    )
    out = post_decision_sanitize(
        ctx,
        "music_block",
        implicated_stages=["sound_design_plan", "segment_classification"],
    )
    assert "sound_design_plan" in (out.get("blocked_music") or [])
    assert ctx.is_done("sound_design_plan")
    assert not ctx.is_done("segment_classification")
