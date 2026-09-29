"""A pid liveness probe must never be able to kill what it asks about (ISSUES 80)."""

from __future__ import annotations

import os
import sys

import pytest

from interview_mux import process_cleanup as pc
from interview_mux.driver_singleton import _pid_alive


def test_self_is_alive_and_a_bogus_pid_is_not() -> None:
    assert pc.worker_pid_alive(os.getpid()) is True
    assert pc.worker_pid_alive(2**22) is False
    assert pc.worker_pid_alive(None) is False
    assert pc.worker_pid_alive("x") is False
    assert _pid_alive(os.getpid()) is True
    assert _pid_alive(2**22) is False


@pytest.mark.skipif(sys.platform != "win32", reason="os.kill is TerminateProcess only on Windows")
def test_windows_probe_never_calls_os_kill(monkeypatch) -> None:
    def _boom(*a, **k):
        raise AssertionError("os.kill used as a liveness probe on Windows")

    monkeypatch.setattr(pc.os, "kill", _boom)
    assert pc.worker_pid_alive(os.getpid()) is True
    assert _pid_alive(os.getpid()) is True


def test_driver_singleton_never_falls_back_to_os_kill(monkeypatch) -> None:
    monkeypatch.setattr(pc, "worker_pid_alive", lambda pid: (_ for _ in ()).throw(RuntimeError("x")))

    def _boom(*a, **k):
        raise AssertionError("fallback os.kill")

    monkeypatch.setattr(os, "kill", _boom)
    assert _pid_alive(os.getpid()) is False
