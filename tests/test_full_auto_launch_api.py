"""Full-auto launch helpers and create_run wiring."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interview_mux.config import repo_root as real_repo_root
from interview_mux.full_auto_launch import normalize_run_mode
from interview_mux.web.server import create_app


def test_normalize_run_mode() -> None:
    assert normalize_run_mode(None) == "manual"
    assert normalize_run_mode("manual") == "manual"
    assert normalize_run_mode("full-auto") == "full-auto"
    assert normalize_run_mode("full_auto") == "full-auto"
    assert normalize_run_mode("FULLAUTO") == "full-auto"
    assert normalize_run_mode("auto") == "full-auto"


def _seed_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    shutil.copytree(real_repo_root() / "config", tmp_path / "config")
    monkeypatch.setenv("INTERVIEW_MUX_ROOT", str(tmp_path))
    assets = tmp_path / "ASSETS"
    (assets / "input").mkdir(parents=True)
    (assets / "executions").mkdir(parents=True)
    # Minimal RIFF header so create_run accepts the file.
    (assets / "input" / "interview.wav").write_bytes(
        b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
        b"D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    )
    return TestClient(create_app())


def test_create_run_manual_does_not_launch_full_auto(tmp_path, monkeypatch) -> None:
    client = _seed_client(tmp_path, monkeypatch)
    launched: list[dict] = []

    def _fake_launch(**kwargs):
        launched.append(kwargs)
        return {"ok": True, "driver_pid": 1}

    monkeypatch.setattr(
        "interview_mux.full_auto_launch.launch_full_auto_for_run",
        _fake_launch,
    )

    res = client.post(
        "/api/runs",
        json={"input_audio_path": "ASSETS/input/interview.wav", "run_mode": "manual"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["run_mode"] == "manual"
    assert body["full_auto"] is False
    assert launched == []

    meta = (tmp_path / "ASSETS" / "executions" / body["run_id"] / "run_meta.json").read_text(
        encoding="utf-8"
    )
    assert '"run_mode": "manual"' in meta
    assert '"full_auto": false' in meta


def test_create_run_full_auto_launches_run_scoped_worker(tmp_path, monkeypatch) -> None:
    client = _seed_client(tmp_path, monkeypatch)
    launched: list[dict] = []

    def _fake_launch(**kwargs):
        launched.append(kwargs)
        return {
            "ok": True,
            "run_id": kwargs["run_id"],
            "driver_pid": 42,
            "keepalive_pid": 43,
            "keep_gui_server": kwargs.get("keep_gui_server"),
            "console_log": "ASSETS/full_auto_console.log",
        }

    monkeypatch.setattr(
        "interview_mux.full_auto_launch.launch_full_auto_for_run",
        _fake_launch,
    )
    # Patch the name used inside create_run's local import path.
    import interview_mux.web.server as server_mod

    monkeypatch.setattr(
        server_mod,
        "launch_full_auto_for_run",
        _fake_launch,
        raising=False,
    )

    # create_run imports from interview_mux.full_auto_launch inside the handler —
    # patching that module attribute is enough when import resolves at call time.
    import interview_mux.full_auto_launch as fal

    monkeypatch.setattr(fal, "launch_full_auto_for_run", _fake_launch)

    res = client.post(
        "/api/runs",
        json={
            "input_audio_path": "ASSETS/input/interview.wav",
            "run_mode": "full-auto",
            "full_auto": True,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["run_mode"] == "full-auto"
    assert body["full_auto"] is True
    assert body["full_auto_launch"]["driver_pid"] == 42
    assert len(launched) == 1
    assert launched[0]["run_id"] == body["run_id"]
    assert launched[0]["keep_gui_server"] is True
    assert "interview.wav" in launched[0]["input_audio"]

    meta_path = tmp_path / "ASSETS" / "executions" / body["run_id"] / "run_meta.json"
    meta_text = meta_path.read_text(encoding="utf-8")
    assert '"run_mode": "full-auto"' in meta_text
    assert '"full_auto": true' in meta_text
