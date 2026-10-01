"""The Chatterbox probe: slow is not absent, and a miss is never cached (ISSUES 110)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from interview_mux import synthesis_fallback as sf


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    monkeypatch.setattr(sf, "_probe_cache", {})
    monkeypatch.setattr("interview_mux.local_runtime.runtime_python", lambda rid: Path("python"))


def test_a_probe_timeout_counts_as_present(monkeypatch) -> None:
    def _slow(*_a, **kw):
        raise subprocess.TimeoutExpired(cmd="python", timeout=kw.get("timeout", 0))

    monkeypatch.setattr(sf.subprocess, "run", _slow)
    assert sf.chatterbox_runtime_available() is True
    assert sf.PROBE_TIMEOUT_SEC >= 120


def test_an_import_failure_is_absent_and_reprobed_next_time(monkeypatch) -> None:
    calls = {"n": 0}

    def _run(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise subprocess.CalledProcessError(1, "python")
        return subprocess.CompletedProcess(args=[], returncode=0)

    monkeypatch.setattr(sf.subprocess, "run", _run)
    assert sf.chatterbox_runtime_available() is False
    assert sf.chatterbox_runtime_available() is True
    assert calls["n"] == 2


def test_a_positive_answer_is_cached(monkeypatch) -> None:
    calls = {"n": 0}

    def _run(*_a, **_k):
        calls["n"] += 1
        return subprocess.CompletedProcess(args=[], returncode=0)

    monkeypatch.setattr(sf.subprocess, "run", _run)
    assert sf.chatterbox_runtime_available() is True
    assert sf.chatterbox_runtime_available() is True
    assert calls["n"] == 1
