"""Detect journey stalls and dead-ends."""

from __future__ import annotations

import time
from typing import Callable


class StallDetector:
    def __init__(
        self,
        *,
        gate_timeout_s: float = 180.0,
        idle_timeout_s: float = 600.0,
        running_timeout_s: float = 7200.0,
    ) -> None:
        self.gate_timeout_s = gate_timeout_s
        self.idle_timeout_s = idle_timeout_s
        self.running_timeout_s = running_timeout_s
        self._fp: tuple[str, ...] | None = None
        self._since = time.monotonic()
        self._job_running_since: float | None = None

    def reset(self) -> None:
        self._fp = None
        self._since = time.monotonic()
        self._job_running_since = None

    def observe(
        self,
        fp: tuple[str, ...],
        *,
        job_running: bool,
    ) -> None:
        if fp != self._fp:
            self._fp = fp
            self._since = time.monotonic()
        if job_running:
            if self._job_running_since is None:
                self._job_running_since = time.monotonic()
        else:
            self._job_running_since = None

    def is_stuck(self, *, job_running: bool) -> tuple[bool, str]:
        elapsed = time.monotonic() - self._since
        if job_running and self._job_running_since:
            run_elapsed = time.monotonic() - self._job_running_since
            if run_elapsed > self.running_timeout_s:
                return True, f"job running > {self.running_timeout_s}s"
            return False, ""

        phase = self._fp[1] if self._fp and len(self._fp) > 1 else ""
        job_status = self._fp[3] if self._fp and len(self._fp) > 3 else "idle"

        if job_status in ("gate", "needs_operator") and elapsed > self.gate_timeout_s:
            return True, f"gate/needs_operator unchanged > {self.gate_timeout_s}s"

        if phase in ("complete", "prepare", "understand") and elapsed > self.idle_timeout_s:
            return True, f"idle journey fingerprint > {self.idle_timeout_s}s"

        if elapsed > self.idle_timeout_s * 3:
            return True, f"fingerprint unchanged > {self.idle_timeout_s * 3}s"

        return False, ""
