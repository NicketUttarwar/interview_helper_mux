"""Kill orphaned interview_mux worker processes on server stop/restart."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from typing import Iterable

_STAGE_WORKER_MARKER = "interview_mux.stage_worker"
_SERVE_MARKER = "interview_mux serve"

_tracked_worker_pids: set[int] = set()


def track_worker_pid(pid: int) -> None:
    if pid > 0:
        _tracked_worker_pids.add(int(pid))


def untrack_worker_pid(pid: int) -> None:
    _tracked_worker_pids.discard(int(pid))


def clear_tracked_workers() -> None:
    _tracked_worker_pids.clear()


def worker_pid_alive(pid: object | None) -> bool:
    """True when ``pid`` is a live process. Read-only on every platform.

    ``os.kill(pid, 0)`` is a probe on POSIX only. On Windows ``os.kill`` with
    any signal other than the CTRL events is ``TerminateProcess``: the probe
    kills what it asks about when it has the right, and reports "dead" for a
    live process when it does not (ISSUES 80: the orchestrator's ownership
    stamp read as stale while the engine ran).
    """
    if pid is None:
        return False
    try:
        pid_i = int(pid)
    except (TypeError, ValueError):
        return False
    if pid_i <= 0:
        return False
    if sys.platform == "win32":
        return _win_pid_alive(pid_i)
    try:
        os.kill(pid_i, 0)
        return True
    except OSError:
        return False


def _win_pid_alive(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, wintypes.DWORD(pid))
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        k32.CloseHandle(handle)


def _list_mux_pids(*markers: str) -> list[int]:
    if sys.platform == "darwin":
        cmd = ["ps", "-ax", "-o", "pid=,command="]
    else:
        cmd = ["ps", "-eo", "pid,args"]
    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return []
    pids: list[int] = []
    self_pid = os.getpid()
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        if pid <= 1 or pid == self_pid:
            continue
        command = parts[1]
        if any(marker in command for marker in markers):
            pids.append(pid)
    return pids


def _signal_pids(pids: Iterable[int], sig: signal.Signals) -> None:
    for pid in pids:
        try:
            os.kill(pid, sig)
        except OSError:
            pass


def kill_stage_workers(*, except_pids: Iterable[int] | None = None) -> int:
    """Terminate orphan stage_worker subprocesses. Returns count signalled."""
    skip = {os.getpid(), *(except_pids or ())}
    targets = [pid for pid in _list_mux_pids(_STAGE_WORKER_MARKER) if pid not in skip]
    if not targets:
        return 0
    _signal_pids(targets, signal.SIGTERM)
    return len(targets)


def kill_tracked_workers() -> int:
    """SIGTERM workers spawned by this server process."""
    targets = [pid for pid in list(_tracked_worker_pids) if worker_pid_alive(pid)]
    if not targets:
        return 0
    _signal_pids(targets, signal.SIGTERM)
    for pid in targets:
        untrack_worker_pid(pid)
    return len(targets)


def kill_mux_workers_for_shutdown() -> int:
    """Best-effort cleanup of in-process tracked workers and orphan stage_workers."""
    count = kill_tracked_workers()
    count += kill_stage_workers()
    return count


def kill_processes_on_tcp_port(port: int) -> int:
    """SIGTERM processes listening on a TCP port (macOS/Linux via lsof)."""
    try:
        out = subprocess.check_output(
            ["lsof", "-ti", f"tcp:{int(port)}"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return 0
    pids = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pids.append(int(line))
        except ValueError:
            continue
    pids = [pid for pid in pids if pid != os.getpid()]
    if not pids:
        return 0
    _signal_pids(pids, signal.SIGTERM)
    return len(pids)
