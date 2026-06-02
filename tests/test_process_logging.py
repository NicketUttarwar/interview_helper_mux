"""Process logging mirrors operator errors to stderr when launched via run.sh."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.process_logging import (
    mirror_operator_entry,
    serve_uvicorn_options,
)
from interview_mux.session_log import append_log


def test_mirror_operator_entry_errors_only(capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_MIRROR_OPERATOR_ERRORS", "1")
    mirror_operator_entry(
        {"ts": "t", "level": "info", "message": "ignored"},
    )
    mirror_operator_entry(
        {
            "ts": "t",
            "level": "error",
            "stage": "ingest",
            "message": "ffmpeg failed",
            "detail": "exit 1",
        },
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ffmpeg failed" in captured.err
    assert "[ingest]" in captured.err
    assert "exit 1" in captured.err


def test_append_log_mirrors_error_to_stderr(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MUX_MIRROR_OPERATOR_ERRORS", "1")
    run_dir = tmp_path / "exec_001_test"
    run_dir.mkdir()
    append_log(run_dir, "boom", level="error", stage="transcribe")
    captured = capsys.readouterr()
    assert "boom" in captured.err
    line = (run_dir / "gui_log.jsonl").read_text(encoding="utf-8").strip()
    assert json.loads(line)["message"] == "boom"


def test_serve_uvicorn_options_quiet_when_run_sh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_LAUNCHED_VIA", "run.sh")
    opts = serve_uvicorn_options()
    assert opts["log_level"] == "error"
    assert opts["access_log"] is False

    monkeypatch.delenv("MUX_LAUNCHED_VIA", raising=False)
    opts = serve_uvicorn_options()
    assert opts["log_level"] == "info"
    assert opts["access_log"] is True
