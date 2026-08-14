"""Registry, escalations, and commit-barrier resilience runtime."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.stage_families import FAMILY_BY_STAGE, family_for_stage, select_source_profile
from interview_mux.stage_resilience import (
    all_pipeline_stage_ids,
    escalate_stage_failure,
    list_open_escalations,
    record_resilience_event,
    registry_coverage,
    resolve_escalation,
    validate_staged_before_flush,
)
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER


def test_registry_covers_all_62_stages():
    ids = all_pipeline_stage_ids()
    assert len(ids) == 62
    assert len(ANALYSIS_ORDER) + len(DELIVERY_ORDER) == 62
    cov = registry_coverage()
    assert cov["ok"] is True
    assert cov["missing_family"] == []
    for sid in ids:
        assert sid in FAMILY_BY_STAGE
        assert family_for_stage(sid)


def test_source_profile_recipes():
    assert select_source_profile() == "clean_interview"
    assert select_source_profile(is_video=True) == "video_container"
    assert select_source_profile(noisy=True) == "noisy_mono"
    assert select_source_profile(duration_s=60) == "short_source"
    assert select_source_profile(duration_s=8000) == "long_source"
    assert select_source_profile(speaker_count=5) == "town_hall_multi"


def test_escalation_quality_first_forbids_waive_publish(tmp_path: Path, monkeypatch):
    from interview_mux.run_context import RunContext

    run_dir = tmp_path / "exec_test"
    run_dir.mkdir()
    (run_dir / "run_meta.json").write_text("{}", encoding="utf-8")
    ctx = RunContext.__new__(RunContext)
    ctx.run_dir = run_dir
    ctx.run_id = "exec_test"

    def artifact_exists(rel: str) -> bool:
        return (run_dir / rel).is_file()

    def read_json(rel: str):
        return json.loads((run_dir / rel).read_text(encoding="utf-8"))

    def log(*_a, **_k):
        return None

    ctx.artifact_exists = artifact_exists  # type: ignore[method-assign]
    ctx.read_json = read_json  # type: ignore[method-assign]
    ctx.log = log  # type: ignore[method-assign]

    doc = escalate_stage_failure(
        ctx,
        "mix",
        failed_invariant="mmaudio_qa_missing",
        evidence={"path": "sound_design/mmaudio_qa.json"},
    )
    assert doc["status"] == "open"
    assert doc["quality_first"] is True
    assert list_open_escalations(ctx)
    option_ids = {o["id"] for o in doc["options"]}
    assert "force_publish" not in option_ids
    assert "soft_ship" not in option_ids
    assert "waive_quality" not in option_ids

    with pytest.raises(ValueError, match="quality_first"):
        # Manually inject a forbidden option then reject resolve.
        bad = dict(doc)
        bad["options"] = list(doc["options"]) + [
            {"id": "force_publish", "label": "Force publish"}
        ]
        from interview_mux.file_store import write_json as fs_write_json

        fs_write_json(run_dir / "operator" / "escalations" / "mix.json", bad)
        resolve_escalation(ctx, "mix", chosen_option="force_publish")

    resolved = resolve_escalation(ctx, "mix", chosen_option="retry_stage")
    assert resolved["status"] == "resolved"
    assert resolved["chosen_option"] == "retry_stage"


def test_record_resilience_event(tmp_path: Path):
    from interview_mux.run_context import RunContext

    run_dir = tmp_path / "exec_res"
    run_dir.mkdir()
    ctx = RunContext.__new__(RunContext)
    ctx.run_dir = run_dir
    ctx.run_id = "exec_res"

    def artifact_exists(rel: str) -> bool:
        return (run_dir / rel).is_file()

    def read_json(rel: str):
        return json.loads((run_dir / rel).read_text(encoding="utf-8"))

    ctx.artifact_exists = artifact_exists  # type: ignore[method-assign]
    ctx.read_json = read_json  # type: ignore[method-assign]

    record_resilience_event(ctx, "edl", event="stage_start", action="pass")
    report = read_json("operator/resilience_report.json")
    assert report["events"]
    assert report["stages"]["edl"]["status"] == "stage_start"


def test_validate_staged_before_flush_no_pending(tmp_path: Path, monkeypatch):
    from interview_mux.run_context import RunContext

    run_dir = tmp_path / "exec_flush"
    run_dir.mkdir()
    ctx = RunContext.__new__(RunContext)
    ctx.run_dir = run_dir
    ctx.run_id = "exec_flush"
    monkeypatch.setattr(
        "interview_mux.write_staging.has_pending_writes",
        lambda *_a, **_k: False,
    )
    decision = validate_staged_before_flush(ctx, "edl")
    assert decision.action == "pass"
