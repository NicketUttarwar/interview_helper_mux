"""Unit tests for heavy-task kill detection and abort backoff."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from interview_mux.heavy_task_policy import (
    abort_backoff_sec,
    is_heavy_kill_returncode,
    record_heavy_abort,
    wait_abort_backoff,
)


def test_is_heavy_kill_returncode() -> None:
    assert is_heavy_kill_returncode(-15)
    assert is_heavy_kill_returncode(-9)
    assert is_heavy_kill_returncode(-6)
    assert is_heavy_kill_returncode(134)
    assert not is_heavy_kill_returncode(0)
    assert not is_heavy_kill_returncode(1)
    assert not is_heavy_kill_returncode(None)


def test_abort_backoff_sec_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INTERVIEW_MUX_GPU_ABORT_BACKOFF_SEC", raising=False)
    assert abort_backoff_sec() == 30.0


def test_record_and_wait_abort_backoff(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import interview_mux.heavy_task_policy as htp

    sleeps: list[float] = []
    monkeypatch.setattr(htp.time, "sleep", lambda s: sleeps.append(float(s)))
    monkeypatch.setattr(htp, "_state_path", lambda: tmp_path / "state.json")
    monkeypatch.setenv("INTERVIEW_MUX_GPU_ABORT_BACKOFF_SEC", "30")

    record_heavy_abort("musicgen", -15, stage="musicgen")
    slept = wait_abort_backoff(consumer="chatterbox")
    assert slept > 0
    assert sleeps and sleeps[0] > 0


def test_wait_abort_backoff_no_recent_abort(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import interview_mux.heavy_task_policy as htp

    monkeypatch.setattr(htp, "_state_path", lambda: tmp_path / "state.json")
    monkeypatch.setattr(htp.time, "sleep", lambda s: (_ for _ in ()).throw(AssertionError("should not sleep")))
    assert wait_abort_backoff() == 0.0


def test_is_abort_returncode_delegates() -> None:
    from interview_mux.musicgen_runner import is_abort_returncode

    assert is_abort_returncode(-15)
    assert is_abort_returncode(-6)
