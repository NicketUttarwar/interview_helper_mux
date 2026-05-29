"""Exit codes, RunFailure, and fatal exit helpers."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Exit code matrix (plan)
EXIT_SUCCESS = 0
EXIT_SDK_STARTUP = 1
EXIT_AGENT_RUN = 2
EXIT_PARSE_CONFIG = 3
EXIT_GIT = 4
EXIT_BOOTSTRAP = 5
EXIT_INTERRUPT = 130

EXIT_LABELS = {
    EXIT_SUCCESS: "success",
    EXIT_SDK_STARTUP: "SDK / environment startup failure",
    EXIT_AGENT_RUN: "agent run failed",
    EXIT_PARSE_CONFIG: "parse / config / attachment error",
    EXIT_GIT: "git snapshot / repo validation failure",
    EXIT_BOOTSTRAP: "bootstrap / venv failure",
    EXIT_INTERRUPT: "user interrupt",
}


@dataclass
class RunFailure:
    exit_code: int
    phase: str
    message: str
    command_index: int | None = None
    command_id: str | None = None
    command_title: str | None = None
    run_id: str | None = None
    technical_detail: str | None = None
    log_dir: str | None = None
    remediation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


def write_last_failure(log_dir: Path | None, failure: RunFailure) -> None:
    if log_dir is None:
        return
    path = log_dir / "last_failure.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(failure.to_dict(), indent=2) + "\n", encoding="utf-8")


def fatal(
    failure: RunFailure,
    *,
    log_dir: Path | None = None,
    print_banner: Any = None,
) -> None:
    """Print loud fatal banner, write last_failure.json, exit."""
    from cursor_execute.banner import print_fatal_banner

    write_last_failure(log_dir, failure)
    print_fatal_banner(failure)
    sys.exit(failure.exit_code)
