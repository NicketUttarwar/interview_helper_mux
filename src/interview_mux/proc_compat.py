"""Cross-platform process lookup and termination.

The Full-auto daemon manager was written against `pgrep`, `pkill`, `kill` and
`lsof`. None of those exist on Windows, and `subprocess` raises
`FileNotFoundError` rather than returning non-zero, so a bare
`except subprocess.CalledProcessError` does not catch it. That let a
`FileNotFoundError` escape `automation_driver_alive()` all the way out of the
`POST /api/runs` handler.

Every helper here is best-effort and returns empty rather than raising, because
each caller is either a liveness probe or a cleanup sweep: failing to find a
process must never abort the operation that asked.

Platform behaviour is deliberately asymmetric so this is a no-op on macOS:
POSIX always tries `pgrep` / `lsof` first, *even when psutil is importable*, so
matching semantics there stay byte-identical to what shipped. psutil is only a
POSIX fallback for a host genuinely missing those tools. On Windows psutil is
preferred, falling back to CIM via PowerShell and `netstat -ano`.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

IS_WINDOWS = os.name == "nt"

#: Windows console applications get a window unless told otherwise.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0


def _psutil():
    try:
        import psutil

        return psutil
    except ImportError:
        return None


def _iter_pid_cmdlines() -> list[tuple[int, str]]:
    """Return [(pid, full command line)] for every visible process."""
    ps = _psutil()
    if ps is not None:
        out: list[tuple[int, str]] = []
        for proc in ps.process_iter(["pid", "cmdline", "name"]):
            try:
                info = proc.info
                argv = info.get("cmdline") or []
                cmd = " ".join(argv) if argv else str(info.get("name") or "")
                out.append((int(info["pid"]), cmd))
            except Exception:
                # Process died mid-iteration, or access denied. Skip it.
                continue
        return out

    if IS_WINDOWS:
        # CIM exposes CommandLine, which is what `pgrep -f` matches against.
        script = (
            "Get-CimInstance Win32_Process | "
            "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"
        )
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                creationflags=_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        rows: list[tuple[int, str]] = []
        for line in (proc.stdout or "").splitlines():
            pid_str, _, cmd = line.partition("\t")
            try:
                rows.append((int(pid_str.strip()), cmd.strip()))
            except ValueError:
                continue
        return rows

    try:
        proc = subprocess.run(
            ["ps", "-ax", "-o", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        pid_str, _, cmd = line.partition(" ")
        try:
            rows.append((int(pid_str), cmd.strip()))
        except ValueError:
            continue
    return rows


def pids_matching(pattern: str, *, exclude_self: bool = True) -> list[int]:
    """PIDs whose command line matches ``pattern`` (a regex, like ``pgrep -f``)."""
    if not pattern:
        return []
    # On POSIX always try pgrep first, even when psutil is importable, so macOS
    # and Linux keep byte-identical matching semantics. psutil is only a
    # fallback there for the case where pgrep is genuinely absent.
    if not IS_WINDOWS:
        try:
            out = subprocess.check_output(
                ["pgrep", "-f", pattern], text=True, stderr=subprocess.DEVNULL
            )
        except subprocess.CalledProcessError:
            return []  # pgrep ran and matched nothing.
        except OSError:
            out = None  # pgrep missing; fall through to the generic scan.
        if out is not None:
            pids = []
            for tok in out.split():
                try:
                    pids.append(int(tok))
                except ValueError:
                    continue
            return _filter_pids(pids, exclude_self=exclude_self)

    try:
        rx = re.compile(pattern)
    except re.error:
        rx = re.compile(re.escape(pattern))
    found = [pid for pid, cmd in _iter_pid_cmdlines() if cmd and rx.search(cmd)]
    return _filter_pids(found, exclude_self=exclude_self)


def _pid_ppid_map() -> dict[int, int]:
    """Return {pid: ppid} for every visible process, or {} when unavailable."""
    ps = _psutil()
    if ps is not None:
        out: dict[int, int] = {}
        try:
            for proc in ps.process_iter(["pid", "ppid"]):
                try:
                    out[int(proc.info["pid"])] = int(proc.info["ppid"])
                except Exception:
                    continue
        except Exception:
            # Not a usable psutil (stubbed in tests, or an API change). Fall
            # through to the platform command rather than losing the protection.
            out = {}
        if out:
            return out

    if IS_WINDOWS:
        script = (
            "Get-CimInstance Win32_Process | "
            "ForEach-Object { \"$($_.ProcessId)`t$($_.ParentProcessId)\" }"
        )
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
    else:
        cmd = ["ps", "-Ao", "pid=,ppid="]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    rows: dict[int, int] = {}
    for line in (proc.stdout or "").splitlines():
        parts = line.replace("	", " ").split()
        if len(parts) < 2:
            continue
        try:
            rows[int(parts[0])] = int(parts[1])
        except ValueError:
            continue
    return rows


def _self_and_ancestors(limit: int = 64) -> set[int]:
    """This process plus every ancestor, so a sweep cannot kill its own caller.

    A pattern passed as an argument appears in the command line of the shell that
    invoked us, so a sweep that only excludes ``os.getpid()`` matches that shell
    and kills it. On Windows ``taskkill /T`` takes the whole tree with it, so the
    caller loses its session and the failure looks like the tool crashing with no
    output at all. ``pgrep -f`` has the same exposure on POSIX, which is why the
    shell code this replaced always used patterns literal in the script rather
    than passed in.

    Degrades safely: whatever part of the chain can be resolved is excluded, and
    self plus the direct parent are always excluded even if nothing else is.
    """
    protected = {os.getpid()}
    try:
        protected.add(os.getppid())
    except (AttributeError, OSError):
        pass
    parents = _pid_ppid_map()
    if parents:
        pid = os.getpid()
        # Cycle detection uses its own set: `protected` already holds the direct
        # parent, so testing against it would stop the walk on the first step.
        seen = {pid}
        for _ in range(limit):
            ppid = parents.get(pid)
            if not ppid or ppid <= 1 or ppid in seen:
                break
            protected.add(ppid)
            seen.add(ppid)
            pid = ppid
    return {p for p in protected if p > 1}


def _filter_pids(pids: list[int], *, exclude_self: bool) -> list[int]:
    protected = _self_and_ancestors() if exclude_self else set()
    out = []
    for pid in pids:
        if pid <= 1:
            continue
        if pid in protected:
            continue
        out.append(pid)
    return out


def process_alive(pattern: str) -> bool:
    """True when at least one process matches ``pattern``."""
    return bool(pids_matching(pattern))


def terminate_pids(pids: list[int]) -> list[int]:
    """Best-effort terminate; returns the pids a signal was delivered to."""
    killed: list[int] = []
    for pid in pids:
        if pid <= 1 or pid == os.getpid():
            continue
        try:
            if IS_WINDOWS:
                # Windows has no SIGTERM for another process; taskkill /T also
                # takes the child tree, which is what the pkill sweeps intend.
                proc = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    timeout=20,
                    check=False,
                    creationflags=_NO_WINDOW,
                )
                if proc.returncode == 0:
                    killed.append(pid)
            else:
                os.kill(pid, 15)
                killed.append(pid)
        except (ProcessLookupError, PermissionError, OSError, subprocess.SubprocessError):
            continue
    return killed


def kill_matching(pattern: str, *, exclude_pid: int | None = None) -> list[int]:
    """Terminate everything matching ``pattern`` (cross-platform ``pkill -f``)."""
    pids = pids_matching(pattern)
    if exclude_pid is not None:
        pids = [p for p in pids if p != exclude_pid]
    return terminate_pids(pids)


def pids_listening_on_port(port: int) -> list[int]:
    """PIDs with a LISTEN socket on ``port`` (cross-platform ``lsof -tiTCP``)."""
    # POSIX keeps lsof as the primary probe so macOS behaviour is unchanged.
    if not IS_WINDOWS:
        try:
            out_p = subprocess.check_output(
                ["lsof", f"-tiTCP:{int(port)}", "-sTCP:LISTEN"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            return []  # lsof ran and found nothing.
        except OSError:
            out_p = None  # lsof missing; fall through.
        if out_p is not None:
            pids_p = []
            for tok in out_p.split():
                try:
                    pids_p.append(int(tok.strip()))
                except ValueError:
                    continue
            return _filter_pids(pids_p, exclude_self=True)

    ps = _psutil()
    if ps is not None:
        out: list[int] = []
        try:
            for conn in ps.net_connections(kind="inet"):
                try:
                    if (
                        conn.laddr
                        and int(conn.laddr.port) == int(port)
                        and str(conn.status).upper() == "LISTEN"
                        and conn.pid
                    ):
                        out.append(int(conn.pid))
                except Exception:
                    continue
        except Exception:
            # Needs elevation on some systems; fall through to the CLI probes.
            out = []
        if out:
            return _filter_pids(sorted(set(out)), exclude_self=True)

    if IS_WINDOWS:
        try:
            proc = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
                creationflags=_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        pids: list[int] = []
        needle = f":{int(port)}"
        for line in (proc.stdout or "").splitlines():
            parts = line.split()
            if len(parts) < 5 or "LISTENING" not in line.upper():
                continue
            local = parts[1]
            if not local.endswith(needle):
                continue
            try:
                pids.append(int(parts[-1]))
            except ValueError:
                continue
        return _filter_pids(sorted(set(pids)), exclude_self=True)

    try:
        out_s = subprocess.check_output(
            ["lsof", f"-tiTCP:{int(port)}", "-sTCP:LISTEN"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, OSError):
        return []
    pids = []
    for tok in out_s.split():
        try:
            pids.append(int(tok.strip()))
        except ValueError:
            continue
    return _filter_pids(pids, exclude_self=True)


def detach_kwargs() -> dict[str, object]:
    """Popen kwargs that outlive the parent, per platform."""
    if IS_WINDOWS:
        flags = 0
        for name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "CREATE_BREAKAWAY_FROM_JOB"):
            flags |= int(getattr(subprocess, name, 0) or 0)
        return {"creationflags": flags}
    # Every POSIX platform supports start_new_session, which is what the
    # original code passed unconditionally. Keep that exact behaviour.
    return {"start_new_session": True}


__all__ = [
    "IS_WINDOWS",
    "detach_kwargs",
    "kill_matching",
    "pids_listening_on_port",
    "pids_matching",
    "process_alive",
    "terminate_pids",
]


if __name__ == "__main__":  # manual probe
    pat = sys.argv[1] if len(sys.argv) > 1 else "python"
    print(f"pattern {pat!r} -> pids {pids_matching(pat)}")
