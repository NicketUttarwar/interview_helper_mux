#!/usr/bin/env python3
"""Launch long-running baba e2e processes detached from the parent session (macOS-safe)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "ASSETS"
VENV_PY = ROOT / ".venv" / "bin" / "python"
E2E_CONSOLE = ASSETS / "baba_e2e_console.log"


def _pipeline_complete(run_dir: Path) -> bool:
    master = run_dir / "master" / "master.wav"
    done = run_dir / ".stage_done"
    return (
        master.is_file()
        and master.stat().st_size > 1000
        and (done / "podcast_publish").is_file()
        and (done / "episode_cover_generate").is_file()
    )


def newest_incomplete_run() -> str | None:
    """Newest execution that has not reached the ship bar, else newest execution."""
    execs = sorted(
        (p for p in (ASSETS / "executions").glob("exec_*") if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for cand in execs:
        if not _pipeline_complete(cand):
            return cand.name
    return execs[0].name if execs else None


def rotate_e2e_console() -> None:
    """Archive the driver console log so run discovery never latches a stale run."""
    (ASSETS / "baba_current_run.txt").unlink(missing_ok=True)
    if not E2E_CONSOLE.is_file() or E2E_CONSOLE.stat().st_size == 0:
        return
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    archive = ASSETS / "logs_archive"
    archive.mkdir(parents=True, exist_ok=True)
    E2E_CONSOLE.replace(archive / f"baba_e2e_console.{stamp}.log")


def _popen(cmd: list[str], log_path: Path, env: dict[str, str] | None = None) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    out = open(log_path, "a", buffering=1)
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=out,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        env=full_env,
        start_new_session=True,
        close_fds=True,
    )
    return int(proc.pid)


def server_alive() -> bool:
    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def e2e_alive() -> bool:
    try:
        out = subprocess.check_output(["pgrep", "-f", "_baba_e2e_driver.py"], text=True)
        return bool(out.strip())
    except subprocess.CalledProcessError:
        return False


def ensure_server(*, force_restart: bool = False) -> int | None:
    """Start GUI serve if down. With force_restart, recycle to load current code."""
    if server_alive() and not force_restart:
        return None
    # Soft-kill stale listeners (needed when Python modules changed under a live serve).
    subprocess.run(["pkill", "-f", "interview_mux serve"], check=False)
    _kill_pids_on_port(8765)
    time.sleep(1.5)
    pid = _popen(
        [str(VENV_PY), "-m", "interview_mux", "serve", "--no-browser"],
        ASSETS / "baba_server.log",
    )
    (ASSETS / "baba_server.pid").write_text(str(pid))
    for _ in range(40):
        if server_alive():
            return pid
        time.sleep(0.5)
    raise RuntimeError("server failed to become healthy")


def ensure_e2e(*, fresh: bool = False, run_id: str | None = None, force: bool = False) -> int | None:
    if e2e_alive() and not fresh and not force:
        return None
    subprocess.run(["pkill", "-f", "_baba_e2e_driver.py"], check=False)
    time.sleep(1)
    env = {
        "INTERVIEW_MUX_AUTO_ACCEPT_GATES": "1",
        "MUX_POLL_SEC": "20",
        "MUX_INPUT_AUDIO": os.environ.get("MUX_INPUT_AUDIO", "ASSETS/baba_all_vocals.wav"),
    }
    if fresh:
        rotate_e2e_console()
        env["MUX_FRESH"] = "1"
        env["MUX_RUN_ID"] = ""
    else:
        rid = run_id or newest_incomplete_run()
        if not rid:
            raise RuntimeError("no existing execution to resume — pass --fresh")
        env["MUX_FRESH"] = "0"
        env["MUX_RUN_ID"] = rid
    pid = _popen(
        [str(VENV_PY), str(ROOT / "tools" / "_baba_e2e_driver.py")],
        E2E_CONSOLE,
        env=env,
    )
    (ASSETS / "baba_e2e.pid").write_text(str(pid))
    return pid


def ensure_keepalive() -> int | None:
    try:
        out = subprocess.check_output(["pgrep", "-f", "baba_keepalive_loop.py"], text=True)
        if out.strip():
            return None
    except subprocess.CalledProcessError:
        pass
    pid = _popen(
        [str(VENV_PY), str(ROOT / "tools" / "baba_keepalive_loop.py")],
        ASSETS / "baba_watchdog.log",
    )
    (ASSETS / "baba_keepalive.pid").write_text(str(pid))
    return pid


def _kill_pids_on_port(port: int = 8765) -> list[int]:
    """SIGTERM anything listening on the GUI serve port."""
    killed: list[int] = []
    try:
        out = subprocess.check_output(
            ["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return killed
    self_pid = os.getpid()
    for tok in out.split():
        try:
            pid = int(tok.strip())
        except ValueError:
            continue
        if pid <= 1 or pid == self_pid:
            continue
        try:
            os.kill(pid, 15)
            killed.append(pid)
        except ProcessLookupError:
            pass
        except PermissionError:
            subprocess.run(["kill", "-15", str(pid)], check=False)
            killed.append(pid)
    return killed


def _pkill_pattern(pattern: str, *, exclude_pid: int | None = None) -> None:
    """Best-effort pkill for a process pattern, optionally skipping one pid."""
    try:
        out = subprocess.check_output(["pgrep", "-f", pattern], text=True)
    except subprocess.CalledProcessError:
        return
    self_pid = os.getpid()
    for tok in out.split():
        try:
            pid = int(tok.strip())
        except ValueError:
            continue
        if pid <= 1 or pid == self_pid:
            continue
        if exclude_pid is not None and pid == exclude_pid:
            continue
        try:
            os.kill(pid, 15)
        except ProcessLookupError:
            pass
        except PermissionError:
            subprocess.run(["kill", "-15", str(pid)], check=False)


def shutdown_baba_stack(
    *,
    kill_server: bool = True,
    kill_e2e: bool = True,
    kill_keepalive: bool = True,
    exclude_pid: int | None = None,
    port: int = 8765,
) -> dict[str, object]:
    """Tear down serve + e2e + keepalive after a completed (or abandoned) run.

    Call from the e2e driver with kill_e2e=False so this process can exit cleanly.
    Call from keepalive with kill_keepalive=False for the same reason.
    """
    ASSETS.mkdir(parents=True, exist_ok=True)
    killed_port: list[int] = []
    if kill_keepalive:
        _pkill_pattern("baba_keepalive_loop.py", exclude_pid=exclude_pid)
    if kill_e2e:
        _pkill_pattern("_baba_e2e_driver.py", exclude_pid=exclude_pid)
    if kill_server:
        _pkill_pattern("interview_mux serve", exclude_pid=exclude_pid)
        killed_port = _kill_pids_on_port(port)
        # Second pass after brief settle — catch respawn races / child listeners.
        time.sleep(0.6)
        killed_port.extend(_kill_pids_on_port(port))
        _pkill_pattern("interview_mux serve", exclude_pid=exclude_pid)
    for name in ("baba_server.pid", "baba_e2e.pid", "baba_keepalive.pid"):
        (ASSETS / name).unlink(missing_ok=True)
    return {
        "server_alive": server_alive() if kill_server else None,
        "e2e_alive": e2e_alive() if kill_e2e else None,
        "port_killed": sorted(set(killed_port)),
    }


def main() -> int:
    args = sys.argv[1:]
    run_id = None
    for i, arg in enumerate(args):
        if arg == "--run-id" and i + 1 < len(args):
            run_id = args[i + 1]
    fresh = "--fresh" in args
    restart_server = "--restart-server" in args
    force_e2e = "--force-e2e" in args or restart_server or bool(run_id)
    skip = {"--fresh", "--run-id", "--restart-server", "--force-e2e", run_id}
    modes = {a for a in args if a not in skip and not a.startswith("--")}
    if "stop" in modes or "shutdown" in modes:
        info = shutdown_baba_stack()
        print(f"shutdown={info}")
        return 0
    if not modes or "all" in modes:
        modes = {"server", "e2e", "keepalive"}

    if "server" in modes:
        pid = ensure_server(force_restart=restart_server)
        print(f"server pid={pid or 'already-up'}")
    if "e2e" in modes:
        # Recycle driver when --run-id / --force-e2e / --restart-server so code edits load.
        pid = ensure_e2e(fresh=fresh, run_id=run_id, force=force_e2e)
        print(f"e2e pid={pid or 'already-up'}")
    if "keepalive" in modes:
        pid = ensure_keepalive()
        print(f"keepalive pid={pid or 'already-up'}")
    print(f"health={server_alive()} e2e={e2e_alive()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
