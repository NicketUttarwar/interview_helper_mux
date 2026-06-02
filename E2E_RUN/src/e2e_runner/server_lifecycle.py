"""Start/stop scripts/run.sh server subprocess."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path


class ServerProcess:
    def __init__(self, repo_root: Path, *, port: int = 8765) -> None:
        self.repo_root = repo_root
        self.port = port
        self._proc: subprocess.Popen[str] | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, *, fresh_session: bool = True) -> None:
        if self._proc and self._proc.poll() is None:
            return
        env = os.environ.copy()
        env["MUX_FRESH_SESSION"] = "1" if fresh_session else "0"
        cmd = [
            str(self.repo_root / "scripts" / "run.sh"),
            "--no-browser",
            "--port",
            str(self.port),
        ]
        self._proc = subprocess.Popen(
            cmd,
            cwd=str(self.repo_root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        time.sleep(2.0)

    def stop(self) -> None:
        if not self._proc:
            return
        if self._proc.poll() is None:
            self._proc.send_signal(signal.SIGTERM)
            try:
                self._proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)
        self._proc = None

    def restart(self, *, fresh_session: bool = False) -> None:
        self.stop()
        time.sleep(1.0)
        self.start(fresh_session=fresh_session)

    def log_tail(self, max_lines: int = 40) -> str:
        if not self._proc or not self._proc.stdout:
            return ""
        # Non-blocking read not implemented; return process state only.
        return f"server pid={self._proc.pid} poll={self._proc.poll()}"
