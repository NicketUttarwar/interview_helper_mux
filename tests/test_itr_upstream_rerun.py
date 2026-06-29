from __future__ import annotations

import pytest

from interview_mux.artifact_issue_triage import execute_recovery_action
from interview_mux.operator_clarifications_store import upsert_items
from run_fixtures import isolated_run_ctx, patch_merged_config


class _FakeRunner:
    def __init__(self) -> None:
        self.invalidated: list[str] = []
        self.started: list[str] = []

    def invalidate_from(self, run_id: str, stage_id: str) -> None:
        self.invalidated.append(stage_id)

    def start(self, run_id: str, **kwargs: object) -> dict[str, object]:
        stage = str(kwargs.get("from_stage") or kwargs.get("stage") or "")
        self.started.append(stage)
        return {"status": "running", "stage": stage}


def test_execute_rerun_upstream(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(
        monkeypatch,
        {"analysis": {"artifact_issue_triage": {"enabled": True, "max_upstream_reruns_per_run": 2}}},
    )
    ctx = isolated_run_ctx(tmp_path, "upstream_rerun")
    upsert_items(
        ctx,
        [
            {
                "id": "itr_up",
                "stage_key": "segment_classification",
                "message": "manifest times not monotonic",
                "status": "open",
                "blocking": True,
                "severity": "critical",
                "kind": "overlap",
                "suggested_upstream_stage": "boundary_detection",
            }
        ],
    )
    runner = _FakeRunner()
    result = execute_recovery_action(
        ctx,
        "segment_classification",
        "itr_up",
        "rerun_upstream",
        upstream_stage="boundary_detection",
        runner=runner,
        run_id=ctx.run_id,
    )
    assert result.ok
    assert runner.invalidated == ["boundary_detection"]
    assert runner.started == ["boundary_detection"]
