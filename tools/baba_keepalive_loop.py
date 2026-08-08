#!/usr/bin/env python3
"""Keep baba server + e2e driver alive until podcast_publish completes.

When the pointed run reaches the ship bar (master + cover + publish), this
loop tears down serve + e2e and exits — it does not relaunch a finished run.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "ASSETS"
STATUS = ASSETS / "baba_status.json"
LOG = ASSETS / "baba_watchdog.log"
RUN_POINTER = ASSETS / "baba_current_run.txt"


def log(msg: str) -> None:
    # stdout is redirected to LOG by baba_daemon_launch; a second file write duplicates lines.
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}", flush=True)


def launch(mode: str, *extra: str) -> None:
    import subprocess

    py = ROOT / ".venv" / "bin" / "python"
    cmd = [str(py), str(ROOT / "tools" / "baba_daemon_launch.py"), mode, *extra]
    subprocess.run(cmd, cwd=str(ROOT), check=False)


def server_alive() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def e2e_alive() -> bool:
    import subprocess

    try:
        out = subprocess.check_output(["pgrep", "-f", "_baba_e2e_driver.py"], text=True)
        return bool(out.strip())
    except subprocess.CalledProcessError:
        return False


def latest_run() -> str | None:
    # The driver writes this on bind — authoritative and race-free at fresh start.
    if RUN_POINTER.is_file():
        pointed = RUN_POINTER.read_text(encoding="utf-8").strip()
        if pointed and (ASSETS / "executions" / pointed).is_dir():
            return pointed
    # Fall back to explicit resume/create lines from the current driver.
    console = ASSETS / "baba_e2e_console.log"
    if console.is_file():
        for line in reversed(console.read_text(errors="ignore").splitlines()):
            if "resuming existing run=" in line or "created fresh run=" in line:
                m = re.search(r"exec_\d+_[a-f0-9]+_\d{8}T\d{6}Z", line)
                if m:
                    return m.group(0)
    # Prefer newest incomplete execution over completed ones.
    execs = sorted(
        (ASSETS / "executions").glob("exec_*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for cand in execs:
        if cand.is_dir() and not pipeline_complete(cand.name):
            return cand.name
    return execs[0].name if execs else None


def pipeline_complete(run_id: str) -> bool:
    root = ASSETS / "executions" / run_id
    master = root / "master" / "master.wav"
    done = root / ".stage_done"
    return (
        master.is_file()
        and master.stat().st_size > 1000
        and (done / "podcast_publish").is_file()
        and (done / "episode_cover_generate").is_file()
        and (done / "junction_snip_qa").is_file()
    )


def write_status(run_id: str | None) -> None:
    status: dict = {"ts": time.time(), "run": run_id, "server": server_alive(), "e2e": e2e_alive()}
    if run_id:
        root = ASSETS / "executions" / run_id
        done_dir = root / ".stage_done"
        done = list(done_dir.glob("*")) if done_dir.is_dir() else []
        status["done"] = len(done)
        status["master"] = (root / "master" / "master.wav").is_file()
        status["publish"] = (done_dir / "podcast_publish").is_file()
        status["cover"] = (done_dir / "episode_cover_generate").is_file()
        status["complete"] = pipeline_complete(run_id)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:8765/api/runs/{run_id}/job", timeout=15) as resp:
                job = json.loads(resp.read().decode())
            status["job_status"] = job.get("status")
            status["stage"] = job.get("stage") or job.get("current_stage")
            status["message"] = (job.get("message") or "")[:240]
        except Exception as exc:
            status["job_err"] = str(exc)[:160]
    STATUS.write_text(json.dumps(status, indent=2))
    log(
        f"status run={run_id} done={status.get('done')} stage={status.get('stage')} "
        f"job={status.get('job_status')} master={status.get('master')} publish={status.get('publish')}"
    )


def pointed_run() -> str | None:
    if not RUN_POINTER.is_file():
        return None
    pointed = RUN_POINTER.read_text(encoding="utf-8").strip()
    if pointed and (ASSETS / "executions" / pointed).is_dir():
        return pointed
    return None


def main() -> None:
    log("keepalive loop start")
    while True:
        run_id = latest_run()
        pointed = pointed_run()
        # Only treat completion as terminal when the authoritative pointer
        # matches a finished run AND the e2e driver has exited. Otherwise a
        # fresh launch (pointer cleared while POST /api/runs is still creating)
        # can latch onto a prior completed exec_* and exit immediately.
        if (
            pointed
            and pipeline_complete(pointed)
            and not e2e_alive()
        ):
            write_status(pointed)
            log(f"DONE pipeline complete run={pointed} — shutting down stack")
            try:
                from baba_daemon_launch import shutdown_baba_stack

                info = shutdown_baba_stack(kill_keepalive=False, exclude_pid=os.getpid())
                log(f"stack shutdown: {info}")
            except Exception as exc:
                log(f"stack shutdown failed: {exc}")
            return
        if run_id and pipeline_complete(run_id) and not pointed and e2e_alive():
            log(f"fresh e2e still binding — ignoring prior complete run={run_id}")
            write_status(None)
            time.sleep(15)
            continue
        # Never relaunch once the pointed run has already shipped.
        if pointed and pipeline_complete(pointed):
            write_status(pointed)
            log(f"DONE pointed run complete (e2e may still be finishing) run={pointed}")
            time.sleep(15)
            continue
        if not server_alive():
            log("server down — relaunch")
            launch("server")
            time.sleep(3)
        if not e2e_alive():
            if pointed and not pipeline_complete(pointed):
                log(f"e2e down — resume {pointed}")
                launch("e2e", "--run-id", pointed)
            elif run_id and not pipeline_complete(run_id):
                log(f"e2e down — resume {run_id}")
                launch("e2e", "--run-id", run_id)
            elif not run_id:
                log("e2e down — fresh")
                launch("e2e", "--fresh")
            elif run_id and pipeline_complete(run_id):
                log(f"DONE incomplete pointer but run complete — shutting down stack run={run_id}")
                write_status(run_id)
                try:
                    from baba_daemon_launch import shutdown_baba_stack

                    info = shutdown_baba_stack(kill_keepalive=False, exclude_pid=os.getpid())
                    log(f"stack shutdown: {info}")
                except Exception as exc:
                    log(f"stack shutdown failed: {exc}")
                return
            time.sleep(3)
        write_status(pointed or run_id)
        time.sleep(45)


if __name__ == "__main__":
    main()
