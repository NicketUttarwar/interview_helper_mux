"""A stage re-entered after a refused commit starts from a clean staging overlay (ISSUES 102)."""

from __future__ import annotations

import json

from run_fixtures import isolated_run_ctx, mark_done_raw

from interview_mux import write_staging as ws


def _stage_a_stale_copy(ctx, stage: str, rel: str) -> None:
    """Leave a file in the stage's overlay the way a refused attempt does."""
    staged = ws.staged_path(ctx, rel, stage_id=stage)
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text(json.dumps({"version": 1, "evaluations": []}), encoding="utf-8")
    assert staged.is_file()


def _overlay_files(ctx, stage: str) -> list[str]:
    root = ws.staging_root(ctx, stage)
    return sorted(str(p.relative_to(root)).replace("\\", "/") for p in root.rglob("*") if p.is_file()) if root.is_dir() else []


def test_stale_pending_from_a_refused_attempt_is_discarded(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ws, "write_approval_enabled", lambda: False)
    ctx = isolated_run_ctx(tmp_path, "exec_stale_staging")
    committed = ctx.final_path("understanding", "gap_evaluations.json")
    committed.parent.mkdir(parents=True, exist_ok=True)
    committed.write_text(json.dumps({"version": 1, "evaluations": [{"segment_id": "seg_001"}]}), encoding="utf-8")
    _stage_a_stale_copy(ctx, "gap_framing_compose", "understanding/gap_evaluations.json")

    discarded = ws.discard_stale_staging_before_entry(ctx, "gap_framing_compose")

    assert discarded == ["understanding/gap_evaluations.json"]
    assert _overlay_files(ctx, "gap_framing_compose") == []
    # The committed producer output is untouched.
    assert json.loads(committed.read_text(encoding="utf-8"))["evaluations"][0]["segment_id"] == "seg_001"


def test_a_done_stage_keeps_its_pending(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ws, "write_approval_enabled", lambda: False)
    ctx = isolated_run_ctx(tmp_path, "exec_stale_staging_done")
    _stage_a_stale_copy(ctx, "gap_framing_compose", "understanding/gap_evaluations.json")
    mark_done_raw(ctx, "gap_framing_compose")
    assert ws.discard_stale_staging_before_entry(ctx, "gap_framing_compose") == []
    assert _overlay_files(ctx, "gap_framing_compose") == ["understanding/gap_evaluations.json"]


def test_wav_stages_and_approval_mode_are_left_alone(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_stale_staging_wav")
    _stage_a_stale_copy(ctx, "vo_synthesize", "mastering/vo_synthesize.json")
    monkeypatch.setattr(ws, "write_approval_enabled", lambda: False)
    assert ws.discard_stale_staging_before_entry(ctx, "vo_synthesize") == []
    _stage_a_stale_copy(ctx, "gap_framing_compose", "understanding/gap_evaluations.json")
    monkeypatch.setattr(ws, "write_approval_enabled", lambda: True)
    assert ws.discard_stale_staging_before_entry(ctx, "gap_framing_compose") == []
    assert _overlay_files(ctx, "gap_framing_compose") == ["understanding/gap_evaluations.json"]
