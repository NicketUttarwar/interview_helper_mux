"""Holistic simulated operator journey — Prepare → Ship for flow1/2/3 (no external APIs)."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interview_mux import pipeline
from interview_mux.gates import set_selected_flow
from interview_mux.web.server import create_app

from run_fixtures import (
    disable_handoff_gates,
    grant_all_api_consents,
    init_run_meta_for_test,
    patch_executions_root,
    patch_server_ctx,
    seed_analysis_complete,
)
from simulated_services import apply_simulated_services, minimal_wav_bytes


def _copy_fixture_run(tmp_path: Path, run_id: str) -> Path:
    fixture = Path(__file__).parent / "fixtures" / "runs" / "base_smoke"
    executions = tmp_path / "ASSETS" / "executions"
    run_dir = executions / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    shutil.copytree(fixture, run_dir)
    return run_dir


def _wait_for_job(client: TestClient, run_id: str, *, timeout_s: float = 8.0) -> dict:
    deadline = time.time() + timeout_s
    last: dict = {}
    while time.time() < deadline:
        res = client.get(f"/api/runs/{run_id}/job")
        assert res.status_code == 200
        last = res.json()
        status = last.get("status")
        if status in ("complete", "error", "gate", "needs_operator"):
            return last
        if status not in ("running", "running_with_warnings", "idle"):
            return last
        time.sleep(0.05)
    raise TimeoutError(f"Job did not finish: {last}")


def _stub_flow_runners(monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux.web import runner as runner_mod

    def _mark_flow(ctx, order: list[str], deliverable: str | None = None) -> None:
        for stage in order:
            ctx.mark_done(stage)
        if deliverable:
            p = ctx.path(deliverable)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(minimal_wav_bytes())

    def _fake_flow1(ctx, **kwargs) -> None:
        _mark_flow(ctx, pipeline.FLOW1_ORDER, "flow_1_master/master.wav")

    def _fake_flow2(ctx, **kwargs) -> None:
        _mark_flow(ctx, pipeline.FLOW2_ORDER, "flow_2_highlights/master.wav")

    def _fake_flow3(ctx, **kwargs) -> None:
        for stage in pipeline.FLOW3_ORDER:
            ctx.mark_done(stage)
        out_dir = ctx.path("flow_3_description")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "show_description.json").write_text(
            '{"title":"Simulated show","description":"Offline test blurb."}',
            encoding="utf-8",
        )
        (out_dir / "show_description.md").write_text("# Simulated show description\n", encoding="utf-8")

    monkeypatch.setattr(runner_mod, "run_flow1", _fake_flow1)
    monkeypatch.setattr(runner_mod, "run_flow2", _fake_flow2)
    monkeypatch.setattr(runner_mod, "run_flow3", _fake_flow3)
    monkeypatch.setattr(runner_mod.JobRunner, "_run_master_qa", lambda *_a, **_k: None)


@pytest.mark.parametrize("flow", ["flow1", "flow2", "flow3"])
def test_holistic_simulated_journey(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flow: str) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    apply_simulated_services(monkeypatch)
    disable_handoff_gates(monkeypatch)
    _stub_flow_runners(monkeypatch)

    run_id = f"exec_holistic_{flow}"
    _copy_fixture_run(tmp_path, run_id)

    from interview_mux.run_context import RunContext

    ctx = RunContext(run_id, create=False)
    init_run_meta_for_test(ctx)
    seed_analysis_complete(ctx)
    set_selected_flow(ctx, flow)

    patch_server_ctx(monkeypatch, ctx)
    client = TestClient(create_app())
    grant_all_api_consents(client)

    review = client.get(f"/api/runs/{run_id}/transcript-review")
    assert review.status_code == 200
    assert review.json().get("complete") is True

    profile = client.get(f"/api/runs/{run_id}/analysis-profile")
    assert profile.status_code == 200
    assert profile.json().get("operator_verified") is True

    vo = client.post(
        f"/api/runs/{run_id}/vo/line_001",
        files={"file": ("line_001.wav", minimal_wav_bytes(), "audio/wav")},
    )
    assert vo.status_code == 200
    assert vo.json().get("g1_missing") == []

    flow_res = client.post(f"/api/runs/{run_id}/flow", json={"flow": flow})
    assert flow_res.status_code == 200

    exec_res = client.post(
        f"/api/runs/{run_id}/execute",
        json={
            "mode": flow,
            "api_consents": {"openai": True, "aws": True, "elevenlabs": True},
        },
    )
    assert exec_res.status_code == 200
    assert exec_res.json().get("ok") is True

    job = _wait_for_job(client, run_id)
    assert job.get("status") == "complete", job

    if flow == "flow1":
        assert ctx.is_done("master_flow1")
        assert ctx.artifact_exists("flow_1_master/master.wav")
    elif flow == "flow2":
        assert ctx.is_done("master_flow2")
        assert ctx.artifact_exists("flow_2_highlights/master.wav")
    else:
        assert ctx.is_done("export_show_description")
        assert ctx.artifact_exists("flow_3_description/show_description.md")
        assert ctx.artifact_exists("flow_3_description/show_description.json")

    log_text = ctx.path("gui_log.jsonl").read_text(encoding="utf-8")
    assert "Finished" in log_text or "Running Flow" in log_text

    meta = ctx.read_json("run_meta.json")
    assert meta.get("selected_flow") == flow

    if flow != "flow3":
        summary_res = client.get(f"/api/runs/{run_id}/summary")
        assert summary_res.status_code == 200
        assert summary_res.json().get("selected_flow") == flow
        run_body = client.get(f"/api/runs/{run_id}")
        assert run_body.status_code == 200
        stage_status = {s["id"]: s["status"] for s in run_body.json().get("stages") or []}
        if flow == "flow1":
            assert stage_status.get("master_flow1") == "done"
        else:
            assert stage_status.get("master_flow2") == "done"
