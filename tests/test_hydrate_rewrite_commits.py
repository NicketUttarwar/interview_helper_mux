"""The approve-time manifest hydrate lands in the committed tree, not back in staging (ISSUES 94)."""

from __future__ import annotations

import json

import pytest
from run_fixtures import isolated_run_ctx, minimal_manifest

from interview_mux import write_staging as ws


def test_hydrate_rewrite_after_flush_is_committed_and_leaves_no_newer_pending(
    tmp_path, monkeypatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_hydrate_commit")
    stage = "segment_classification"

    def _hydrate(_ctx, manifest):
        out = json.loads(json.dumps(manifest))
        out["hydrated_marker"] = True
        return out

    monkeypatch.setattr(
        "interview_mux.artifact_completeness.hydrate_manifest_from_boundaries", _hydrate
    )
    monkeypatch.setattr(
        "interview_mux.artifact_repairs.repair_manifest_segments", lambda _c, doc: (doc, [])
    )
    ws.enter_stage_staging(stage)
    try:
        ctx.write_json("segments/manifest.json", minimal_manifest("seg_001"))
        assert ws.staged_path(ctx, "segments/manifest.json", stage_id=stage).is_file()
        flushed = ws.flush_stage_writes(ctx, stage)
        assert "segments/manifest.json" in flushed
        # Replay the approve-time hydrate exactly as approve_stage_writes does.
        from interview_mux.artifact_completeness import hydrate_manifest_from_boundaries
        from interview_mux.artifact_repairs import repair_manifest_segments

        manifest = ctx.read_json("segments/manifest.json")
        hydrated = hydrate_manifest_from_boundaries(ctx, manifest)
        assert hydrated != manifest
        repaired, _ = repair_manifest_segments(ctx, hydrated)
        ws.write_committed_json(ctx, "segments/manifest.json", repaired, stage_key=stage)

        committed = json.loads(
            ctx.final_path("segments", "manifest.json").read_text(encoding="utf-8")
        )
        assert committed.get("hydrated_marker") is True
        assert ws.uncommitted_pending_reason(ctx, "segments/manifest.json") is None
    finally:
        ws.exit_stage_staging()


def test_a_staged_write_after_flush_would_have_read_as_newer_pending(tmp_path) -> None:
    """The shape the fix removes: a staged copy newer than the commit is incomplete."""
    ctx = isolated_run_ctx(tmp_path, "exec_hydrate_staged")
    stage = "segment_classification"
    ws.enter_stage_staging(stage)
    try:
        ctx.write_json("segments/manifest.json", minimal_manifest("seg_001"))
        ws.flush_stage_writes(ctx, stage)
        doc = ctx.read_json("segments/manifest.json")
        doc["hydrated_marker"] = True
        ctx.write_json("segments/manifest.json", doc, stage_key=stage)
        reason = ws.uncommitted_pending_reason(ctx, "segments/manifest.json")
        assert reason and "newer uncommitted pending" in reason
    finally:
        ws.exit_stage_staging()
