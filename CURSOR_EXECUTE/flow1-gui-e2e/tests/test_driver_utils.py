"""Tests for Flow 1 GUI E2E driver utilities."""

from __future__ import annotations

import sys
from pathlib import Path

_DRIVER = Path(__file__).resolve().parents[1] / "driver"
sys.path.insert(0, str(_DRIVER))

from logging_banner import EventLogger  # noqa: E402
from state import DriverState, default_state_path  # noqa: E402


def test_event_logger_writes_jsonl(tmp_path: Path) -> None:
    log = EventLogger(tmp_path)
    log.step("TEST", "hello")
    events = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    assert "STEP" in events
    assert "hello" in events


def test_driver_state_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    state = DriverState(run_id="exec_001_test", started=True)
    state.save(path)
    loaded = DriverState.load(path)
    assert loaded.run_id == "exec_001_test"
    assert loaded.started is True


def test_default_state_path() -> None:
    campaign = Path(__file__).resolve().parents[1]
    assert default_state_path(campaign).name == "state.json"


def test_newest_matching_run_picks_highest_execution_number() -> None:
    from gate_handlers import newest_matching_run  # noqa: E402

    rows = [
        {"run_id": "exec_10_old", "input_audio_path": "ASSETS/foo.wav", "execution_number": 10},
        {"run_id": "exec_99_new", "input_audio_path": "ASSETS/foo.wav", "execution_number": 99},
        {"run_id": "exec_50_other", "input_audio_path": "ASSETS/bar.wav", "execution_number": 50},
    ]
    assert newest_matching_run(rows, "foo.wav") == "exec_99_new"


def test_api_client_default_timeout() -> None:
    from api_client import ApiClient  # noqa: E402

    client = ApiClient("http://127.0.0.1:8765", request_timeout_s=15)
    assert client.request_timeout_s == 15


def test_screenshot_archive_rate_limit(tmp_path: Path) -> None:
    from execution_screenshots import ExecutionScreenshotArchive  # noqa: E402

    class FakePage:
        def __init__(self) -> None:
            self.calls = 0

        def screenshot(self, **kwargs: object) -> None:
            self.calls += 1

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ASSETS").mkdir()
    page = FakePage()
    arch = ExecutionScreenshotArchive(repo, "sess_test", archive_dir="ASSETS/flow1-gui-e2e-screenshots", min_interval_s=120)
    assert arch.maybe_capture_after_click(page, "first") is not None
    assert arch.maybe_capture_after_click(page, "second") is None
    assert page.calls == 1
    assert arch.capture_count == 1
