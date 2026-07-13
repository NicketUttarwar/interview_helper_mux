from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from interview_mux.stages.audio_preclean import ensure_preclean_skipped
from interview_mux.ui_truth import validate_run_snapshot
from interview_mux.web.server import _build_stage_list


from run_fixtures import patch_merged_config


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    root = tmp_path / "repo"
    executions = root / "ASSETS" / "executions"
    executions.mkdir(parents=True)
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: root)
    patch_merged_config(
        monkeypatch,
        {
            "assets_root": "ASSETS",
            "executions_root": "ASSETS/executions",
            "data_root": "data",
            "journey_ui": {"require_write_approval_per_stage": False},
        },
    )
    rid = "exec_001_20260101T000000Z"
    ctx = RunContext(rid, create=True)
    ctx.write_json("run_meta.json", {"execution_id": rid}, skip_handoff=True)
    return ctx


def test_preclean_skip_outputs_not_pending(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    ensure_preclean_skipped(ctx, checkpoint="before_ingest", scope="ingest", reason="test")
    stages = _build_stage_list(
        ctx,
        [],
        False,
        False,
        False,
        False,
    )
    preclean = next(s for s in stages if s["id"] == "audio_preclean")
    assert preclean["status"] in ("done", "incomplete")
    assert ctx.artifact_exists("preclean/skip.json")
