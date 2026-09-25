from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.write_staging import approve_stage_writes, enter_stage_staging, exit_stage_staging
from run_fixtures import write_fixture_theme_wav


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    root = tmp_path / "repo"
    executions = root / "ASSETS" / "executions"
    executions.mkdir(parents=True)
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: root)
    monkeypatch.setattr(
        "interview_mux.run_context.merged_config",
        lambda: {
            "assets_root": "ASSETS",
            "executions_root": "ASSETS/executions",
            "data_root": "data",
            "journey_ui": {"require_write_approval_per_stage": True},
        },
    )
    monkeypatch.setattr(
        "interview_mux.write_staging.merged_config",
        lambda: {"journey_ui": {"require_write_approval_per_stage": True}},
    )
    rid = "exec_001_20260101T000000Z"
    ctx = RunContext(rid, create=True)
    ctx.write_json("run_meta.json", {"execution_id": rid}, skip_handoff=True)
    return ctx


def test_approve_integration_marks_done_and_commits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    # Operator-approved ingest: committed primary must exist before approve seals.
    write_fixture_theme_wav(ctx, "ingest/normalized.wav")
    enter_stage_staging("ingest")
    final_rel = "ingest/checksums.json"
    staged = ctx.path(final_rel)
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text(
        json.dumps(
            {
                "source_path": "fixture.wav",
                "source_sha256": "a" * 64,
                "normalized_sha256": "b" * 64,
                "sample_rate": 48000,
            }
        ),
        encoding="utf-8",
    )
    exit_stage_staging()
    assert not ctx.final_path("ingest", "checksums.json").is_file()
    approve_stage_writes(ctx, "ingest")
    assert ctx.final_path("ingest", "checksums.json").is_file()
    assert ctx.is_done("ingest")
