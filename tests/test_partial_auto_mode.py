"""Partially-accelerated run mode — guardrails on G0 and S3 only."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))


def test_normalize_run_mode_partial_aliases() -> None:
    from interview_mux.full_auto_launch import normalize_run_mode

    assert normalize_run_mode("partial-auto") == "partially-accelerated"
    assert normalize_run_mode("partially_accelerated") == "partially-accelerated"
    assert normalize_run_mode("manual") == "manual"
    assert normalize_run_mode("full-auto") == "full-auto"


def test_normalize_run_mode_manual_default() -> None:
    from interview_mux.full_auto_launch import normalize_run_mode

    assert normalize_run_mode(None) == "manual"
    assert normalize_run_mode("") == "manual"


def test_is_partial_auto_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import full_auto_driver as driver

    monkeypatch.setenv("MUX_PARTIAL_AUTO", "1")
    driver._PARTIAL_AUTO = None
    assert driver.is_partial_auto() is True
    driver._PARTIAL_AUTO = None
    monkeypatch.delenv("MUX_PARTIAL_AUTO", raising=False)
    assert driver.is_partial_auto() is False


def test_complete_g0_skipped_when_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    import full_auto_driver as driver

    monkeypatch.setattr(driver, "is_partial_auto", lambda: True)
    called: list[tuple] = []

    def fake_api(method: str, path: str, body=None, timeout=60):  # type: ignore[no-untyped-def]
        called.append((method, path, body))
        return {}

    monkeypatch.setattr(driver, "api", fake_api)
    driver.complete_g0()
    assert called == []


def test_complete_g0_runs_when_full_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    import full_auto_driver as driver

    monkeypatch.setattr(driver, "is_partial_auto", lambda: False)
    driver.RUN_ID = "exec_test_partial"
    called: list[tuple] = []

    def fake_api(method: str, path: str, body=None, timeout=60):  # type: ignore[no-untyped-def]
        called.append((method, path, body))
        return {}

    monkeypatch.setattr(driver, "api", fake_api)
    driver.complete_g0()
    assert len(called) == 1
    assert called[0][0] == "POST"
    assert "transcript-review/complete" in called[0][1]


def test_finish_complete_run_partial_skips_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    import full_auto_driver as driver

    monkeypatch.setattr(driver, "is_partial_auto", lambda: True)
    monkeypatch.setattr(driver, "assert_fresh_layer_contract", lambda: None)
    monkeypatch.setattr(driver, "wait_for_operator_g_publish", lambda: True)
    monkeypatch.setattr(driver, "finish_partial_complete_run", lambda: 0)
    sync_called: list[bool] = []

    def fake_sync() -> dict:
        sync_called.append(True)
        return {}

    monkeypatch.setattr(driver, "sync_publish_to_s3", fake_sync)
    assert driver.finish_complete_run() == 0
    assert sync_called == []


def test_finish_complete_run_full_auto_syncs(monkeypatch: pytest.MonkeyPatch) -> None:
    import full_auto_driver as driver

    monkeypatch.setattr(driver, "is_partial_auto", lambda: False)
    monkeypatch.setattr(driver, "assert_fresh_layer_contract", lambda: None)
    monkeypatch.setattr(driver, "write_full_auto_status", lambda **_: None)
    monkeypatch.setattr(driver, "summarize_decisions", lambda **_: None)
    monkeypatch.setattr(driver, "_write_terminal_report", lambda **_: None)
    monkeypatch.setattr(driver, "_keep_gui_server", lambda: True)
    monkeypatch.setattr(driver, "MASTER", MagicMock(is_file=lambda: True, stat=lambda: MagicMock(st_size=9999)))

    sync_called: list[bool] = []

    def fake_sync() -> dict:
        sync_called.append(True)
        return {"uploaded": True}

    monkeypatch.setattr(driver, "sync_publish_to_s3", fake_sync)

    with patch("full_auto_daemon_launch.shutdown_full_auto_stack", return_value={}):
        driver.finish_complete_run()
    assert sync_called == [True]


def test_g_publish_operator_done_detects_upload() -> None:
    import full_auto_driver as driver

    driver.RUN_ID = "exec_abc"
    assert driver._g_publish_operator_done({"skipped": True}) is True
    assert driver._g_publish_operator_done({"already_uploaded_count": 1}) is True
    assert driver._g_publish_operator_done({"pending": True}) is False
