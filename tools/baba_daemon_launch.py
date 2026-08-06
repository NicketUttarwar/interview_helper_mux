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


def ensure_server() -> int | None:
    if server_alive():
        return None
    # Soft-kill stale listeners
    subprocess.run(["pkill", "-f", "interview_mux serve"], check=False)
    time.sleep(1)
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


def ensure_e2e(*, fresh: bool = False, run_id: str | None = None) -> int | None:
    if e2e_alive() and not fresh:
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


def main() -> int:
    args = sys.argv[1:]
    run_id = None
    for i, arg in enumerate(args):
        if arg == "--run-id" and i + 1 < len(args):
            run_id = args[i + 1]
    fresh = "--fresh" in args
    skip = {"--fresh", "--run-id", run_id}
    modes = {a for a in args if a not in skip and not a.startswith("--")}
    if not modes or "all" in modes:
        modes = {"server", "e2e", "keepalive"}

    if "server" in modes:
        pid = ensure_server()
        print(f"server pid={pid or 'already-up'}")
    if "e2e" in modes:
        pid = ensure_e2e(fresh=fresh, run_id=run_id)
        print(f"e2e pid={pid or 'already-up'}")
    if "keepalive" in modes:
        pid = ensure_keepalive()
        print(f"keepalive pid={pid or 'already-up'}")
    print(f"health={server_alive()} e2e={e2e_alive()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
