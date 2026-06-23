"""Start/stop interview_mux GUI server for E2E."""

from __future__ import annotations

import signal
import subprocess
import time
from pathlib import Path

from api_client import ApiClient


class ServerLifecycle:
    def __init__(self, repo_root: Path, base_url: str, log_path: Path) -> None:
        self.repo_root = repo_root
        self.base_url = base_url
        self.log_path = log_path
        self._proc: subprocess.Popen[str] | None = None
        self._log_fh = None

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc else None

    def start(self) -> None:
        if self._proc is not None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_fh = self.log_path.open("a", encoding="utf-8")
        self._proc = subprocess.Popen(
            ["./scripts/run.sh"],
            cwd=str(self.repo_root),
            stdout=self._log_fh,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )

    def wait_healthy(self, timeout_s: float = 120.0, poll_s: float = 2.0) -> None:
        client = ApiClient(self.base_url)
        deadline = time.time() + timeout_s
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            try:
                if client.health().get("status") == "ok":
                    return
            except Exception:
                pass
            if self._proc and self._proc.poll() is not None:
                tail = self._read_server_tail(50)
                raise RuntimeError(f"Server exited early (code {self._proc.returncode}). Tail:\n{tail}")
            time.sleep(poll_s)
        raise TimeoutError(f"Server not healthy after {timeout_s}s ({attempt} attempts)")

    def stop(self) -> None:
        if self._proc is None:
            return
        try:
            os.killpg(self._proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            self._proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self._proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self._proc = None
        if self._log_fh:
            self._log_fh.close()
            self._log_fh = None

    def _read_server_tail(self, lines: int) -> str:
        if not self.log_path.is_file():
            return "(no server log)"
        content = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])
