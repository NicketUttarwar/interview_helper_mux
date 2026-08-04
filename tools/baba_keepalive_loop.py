#!/usr/bin/env python3
"""Keep baba server + e2e driver alive until podcast_publish completes."""

from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "ASSETS"
STATUS = ASSETS / "baba_status.json"
LOG = ASSETS / "baba_watchdog.log"


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


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
    # Prefer explicit resume/create lines from the current driver.
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


def main() -> None:
    log("keepalive loop start")
    while True:
        run_id = latest_run()
        if run_id and pipeline_complete(run_id):
            write_status(run_id)
            log(f"DONE pipeline complete run={run_id}")
            return
        if not server_alive():
            log("server down — relaunch")
            launch("server")
            time.sleep(3)
        if not e2e_alive():
            if run_id and not pipeline_complete(run_id):
                log(f"e2e down — resume {run_id}")
                launch("e2e", "--run-id", run_id)
            elif not run_id:
                log("e2e down — fresh")
                launch("e2e", "--fresh")
            time.sleep(3)
        write_status(run_id)
        time.sleep(45)


if __name__ == "__main__":
    main()
