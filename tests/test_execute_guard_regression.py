"""Regression: execute must start jobs while guarded (not self-busy)."""

from __future__ import annotations

import sys
import threading
import time

from fastapi.testclient import TestClient

from interview_mux.run_context import RunContext
from interview_mux.web import runner as runner_mod
from interview_mux.web.server import create_app
from run_fixtures import init_run_meta_for_test, patch_executions_root


def test_execute_starts_stage_under_guard(tmp_path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_guard_start_20260101T001200Z", create=True)
    init_run_meta_for_test(ctx)

    # audio_preclean is the only SUBPROCESS_STAGES member, so the accepted job
    # forks `python -m interview_mux.stage_worker`. A child process inherits no
    # patches: it re-resolves the live repo root and runs DeepFilterNet over the
    # real source audio. Swap the argv (not _run_subprocess_stage) so the pid
    # tracking and exit-code handling around the fork still run.
    dispatched = threading.Event()
    dispatched_stage: list[str] = []

    def _harmless_worker_cmd(self, run_id: str, stage_id: str) -> list[str]:
        dispatched_stage.append(stage_id)
        dispatched.set()
        return [sys.executable, "-c", "pass"]

    monkeypatch.setattr(runner_mod.JobRunner, "_stage_worker_cmd", _harmless_worker_cmd)

    client = TestClient(create_app())
    res = client.post(
        f"/api/runs/{ctx.run_id}/execute",
        json={"mode": "stage", "stage": "audio_preclean"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body.get("ok") is True, body.get("error")

    # The job thread outlives the request, so the accepted start only means
    # something once the stage has actually been dispatched.
    assert dispatched.wait(30), "execute accepted the job but never dispatched the stage"
    assert dispatched_stage == ["audio_preclean"]

    # Join the job thread before teardown: monkeypatch unwinds here, and an
    # unwound argv patch means the next run of this test forks the real worker.
    deadline = time.monotonic() + 30
    while runner_mod.runner.lock_held(ctx.run_id) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not runner_mod.runner.lock_held(ctx.run_id), "job thread still holds the run lock"
