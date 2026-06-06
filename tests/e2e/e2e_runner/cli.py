"""CLI entry for E2E runner."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import typer

from e2e_runner.orchestrator import Orchestrator, _normalize_input_audio
from e2e_runner.types import DEFAULT_INPUT_AUDIO, SessionConfig

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _e2e_root() -> Path:
    return Path(__file__).resolve().parents[1]


@app.callback(invoke_without_command=True)
def run_cmd(
    input_audio: str = typer.Option(DEFAULT_INPUT_AUDIO, "--input"),
    flows: str = typer.Option("flow1,flow2,flow3", "--flows"),
    base_url: str = typer.Option("http://127.0.0.1:8765", "--base-url"),
    resume_run_id: str | None = typer.Option(None, "--resume-run-id"),
    until_stage: str | None = typer.Option(None, "--until-stage"),
    no_heal: bool = typer.Option(False, "--no-heal"),
    headless: bool = typer.Option(True, "--headless/--headed"),
    log_dir: str | None = typer.Option(None, "--log-dir"),
) -> None:
    root = _repo_root()
    session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = Path(log_dir) if log_dir else _e2e_root() / "logs" / f"session_{session_id}"

    flow_tuple = tuple(f.strip() for f in flows.split(",") if f.strip())
    cfg = SessionConfig(
        repo_root=str(root),
        input_audio=_normalize_input_audio(root, input_audio),
        flows=flow_tuple,  # type: ignore[arg-type]
        base_url=base_url,
        heal_enabled=not no_heal,
        max_heal_attempts=int(os.environ.get("E2E_MAX_HEAL_ATTEMPTS", "5")),
        resume_run_id=resume_run_id,
        until_stage=until_stage,
        headless=headless,
        log_dir=str(log_path),
    )
    code = Orchestrator(cfg).run()
    raise typer.Exit(code)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
