from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.pipeline import ANALYSIS_ORDER
from interview_mux.run_context import RunContext
from interview_mux.write_staging import (
    check_write_approval_before_execute,
    enter_stage_staging,
    exit_stage_staging,
)


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    root = tmp_path / "repo"
    (root / "ASSETS" / "executions").mkdir(parents=True)
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: root)
    monkeypatch.setattr(
        "interview_mux.run_context.merged_config",
        lambda: {
            "assets_root": "ASSETS",
            "executions_root": "ASSETS/executions",
            "data_root": "data",
            "journey_ui": {
                "require_write_approval_per_stage": True,
                "first_try_mode": False,
                "defer_write_approval_until": "off",
            },
        },
    )
    monkeypatch.setattr(
        "interview_mux.write_staging.merged_config",
        lambda: {
            "journey_ui": {
                "require_write_approval_per_stage": True,
                "first_try_mode": False,
                "defer_write_approval_until": "off",
            }
        },
    )
    monkeypatch.setattr("interview_mux.first_try.first_try_mode_enabled", lambda cfg=None: False)
    monkeypatch.setattr("interview_mux.first_try.write_approval_deferred", lambda cfg=None: False)
    rid = "exec_001_20260101T000000Z"
    ctx = RunContext(rid, create=True)
    ctx.write_json("run_meta.json", {"execution_id": rid}, skip_handoff=True)
    return ctx


def test_clear_from_archives_and_clears_pending_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    checksums = ctx.path("ingest/checksums.json")
    checksums.parent.mkdir(parents=True, exist_ok=True)
    checksums.write_text("{}", encoding="utf-8")
    ctx.mark_done("ingest", force=True)
    boundaries = ctx.final_path("segments/boundaries.json")
    boundaries.parent.mkdir(parents=True, exist_ok=True)
    boundaries.write_text("{}", encoding="utf-8")
    ctx.mark_done("boundary_detection", force=True)
    enter_stage_staging("segment_classification")
    manifest = ctx.path("segments/manifest.json")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("{}", encoding="utf-8")
    exit_stage_staging()
    assert check_write_approval_before_execute(ctx) is not None

    ctx.clear_from("boundary_detection", ANALYSIS_ORDER)

    assert not ctx.final_path("segments/boundaries.json").is_file()
    assert check_write_approval_before_execute(ctx) is None
    assert list(ctx.run_dir.glob(".archived/*"))


def test_discard_on_invalidate_unblocks_execute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    enter_stage_staging("ingest")
    note = ctx.path("ingest/checksums.json")
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("{}", encoding="utf-8")
    exit_stage_staging()
    assert check_write_approval_before_execute(ctx) is not None
    ctx.clear_from("ingest", ANALYSIS_ORDER)
    assert check_write_approval_before_execute(ctx) is None


def test_clear_from_delivery_preserves_analysis_sound_design_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from interview_mux.pipeline import DELIVERY_ORDER

    ctx = _ctx(tmp_path, monkeypatch)
    sdp = ctx.final_path("understanding/sound_design_plan.json")
    sdp.parent.mkdir(parents=True, exist_ok=True)
    sdp.write_text(
        json.dumps(
            {
                "version": 1,
                "coherence": {"sonic_identity": "test identity", "primary_mood": "", "density": ""},
                "palettes": [{"palette_id": "p1", "name": "Warm"}],
                "assets": [],
                "flow_plans": {"podcast": {"profile": "podcast", "cues": []}},
                "generated": {},
            }
        ),
        encoding="utf-8",
    )
    ctx.mark_done("sound_design_palettes", force=True)
    coverage = ctx.final_path("master/coverage_audit.json")
    coverage.parent.mkdir(parents=True, exist_ok=True)
    coverage.write_text("{}", encoding="utf-8")
    ctx.mark_done("topic_coverage_audit", force=True)

    ctx.clear_from("topic_coverage_audit", DELIVERY_ORDER)

    assert sdp.is_file()
    doc = json.loads(sdp.read_text(encoding="utf-8"))
    assert doc.get("palettes")
    assert ctx.is_done("sound_design_palettes")


def test_clear_from_stamps_stale_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    ctx = _ctx(tmp_path, monkeypatch)
    boundaries = ctx.final_path("segments/boundaries.json")
    boundaries.parent.mkdir(parents=True, exist_ok=True)
    boundaries.write_text(
        json.dumps({"boundaries": [], "_meta": {"stale": False, "content_hash": "abc"}}),
        encoding="utf-8",
    )
    ctx.mark_done("boundary_detection", force=True)
    ctx.clear_from("boundary_detection", ANALYSIS_ORDER)
    if boundaries.is_file():
        doc = json.loads(boundaries.read_text(encoding="utf-8"))
        assert (doc.get("_meta") or {}).get("stale") is True
