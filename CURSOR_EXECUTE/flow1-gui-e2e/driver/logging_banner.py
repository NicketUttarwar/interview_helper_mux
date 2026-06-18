"""Terminal logging with ANSI prefixes for Flow 1 GUI E2E."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_RESET = "\033[0m"
_COLORS = {
    "STEP": "\033[1;36m",
    "ACTION": "\033[1;32m",
    "WAIT": "\033[1;33m",
    "GATE": "\033[1;35m",
    "INFO": "",
    "BLOCKER": "\033[1;31m",
    "FATAL": "\033[1;31m",
}


class EventLogger:
    """Writes human lines to stdout and structured lines to events.jsonl."""

    def __init__(self, session_dir: Path | None = None) -> None:
        self.session_dir = session_dir
        self._events_path: Path | None = None
        if session_dir:
            session_dir.mkdir(parents=True, exist_ok=True)
            self._events_path = session_dir / "events.jsonl"

    def log(self, prefix: str, message: str, **extra: Any) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        color = _COLORS.get(prefix, "")
        line = f"{ts} | {prefix} | {message}"
        print(f"{color}{line}{_RESET}", flush=True)
        if self._events_path is not None:
            payload = {"ts": ts, "prefix": prefix, "message": message, **extra}
            with self._events_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, default=str) + "\n")

    def step(self, phase: str, message: str) -> None:
        self.log("STEP", f"[{phase}] {message}")

    def action(self, message: str, **extra: Any) -> None:
        self.log("ACTION", message, **extra)

    def wait(self, message: str, **extra: Any) -> None:
        self.log("WAIT", message, **extra)

    def gate(self, message: str, **extra: Any) -> None:
        self.log("GATE", message, **extra)

    def info(self, message: str, **extra: Any) -> None:
        self.log("INFO", message, **extra)

    def blocker(self, message: str, **extra: Any) -> None:
        self.log("BLOCKER", message, **extra)

    def fatal(self, message: str) -> None:
        self.log("FATAL", message)
        sys.exit(1)


def tee_transcript(session_dir: Path, line: str) -> None:
    path = session_dir / "transcript.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
