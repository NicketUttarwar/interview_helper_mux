"""Typer CLI — queue orchestration."""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import typer

from cursor_execute.banner import print_opening_banner, print_starting_command, print_success_banner
from cursor_execute.config import (
    RunConfig,
    resolve_api_key,
    resolve_max_attachment_chars,
    resolve_max_prompt_chars,
    resolve_model,
)
from cursor_execute.errors import (
    EXIT_GIT,
    EXIT_PARSE_CONFIG,
    RunFailure,
    fatal,
)
from cursor_execute.expand_attachments import attachment_size_report, expand_attachments
from cursor_execute.git_stats import diff_since_snapshot, resolve_repo_root, take_snapshot, validate_git_repo
from cursor_execute.logging_setup import log_event, setup_session_logging
from cursor_execute.parse_commands import CommandSpec, filter_command_range, parse_commands
from cursor_execute.prompt_builder import build_full_prompt
from cursor_execute.sdk_run import run_agent_command
from cursor_execute.state import SessionState, load_state, save_state

logger = logging.getLogger("cursor_execute")


def _exec_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(
    markdown: Path = typer.Argument(..., help="Path to markdown command file"),
    from_index: int | None = typer.Option(None, "--from", help="Start at command index N"),
    to_index: int | None = typer.Option(None, "--to", help="End at command index N"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Parse and show prompts only"),
    include_legacy_gc: bool = typer.Option(False, "--include-legacy-gc"),
    skip_done: bool = typer.Option(False, "--skip-done"),
    resume: bool = typer.Option(False, "--resume"),
    repo_root: Path | None = typer.Option(None, "--repo-root"),
    no_expand_attachments: bool = typer.Option(False, "--no-expand-attachments"),
    log_dir: Path | None = typer.Option(None, "--log-dir", help="Set by run.sh"),
) -> None:
    exec_root = _exec_root()
    md_path = markdown.resolve()

    if not md_path.is_file():
        fatal(
            RunFailure(
                exit_code=EXIT_PARSE_CONFIG,
                phase="preflight",
                message=f"Markdown file not found: {md_path}",
                remediation="Pass a valid path to run.sh",
            ),
        )

    api_key = resolve_api_key()
    if not dry_run and not api_key:
        fatal(
            RunFailure(
                exit_code=EXIT_PARSE_CONFIG,
                phase="preflight",
                message="CURSOR_API_KEY is not set",
                remediation="export CURSOR_API_KEY=cursor_...",
            ),
        )

    try:
        root = resolve_repo_root(md_path, repo_root)
    except RuntimeError as e:
        fatal(
            RunFailure(
                exit_code=EXIT_GIT,
                phase="git_preflight",
                message="Could not resolve git repository root",
                technical_detail=str(e),
                remediation="Run from a git repo or pass --repo-root",
            ),
        )

    # Fix duplicate import - use subprocess in resolve only
    try:
        validate_git_repo(root)
    except RuntimeError as e:
        fatal(
            RunFailure(
                exit_code=EXIT_GIT,
                phase="git_preflight",
                message=str(e),
            ),
        )

    session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if log_dir is None:
        log_dir = exec_root / "logs" / f"session_{session_id}"
    log_dir = log_dir.resolve()
    log_dir.mkdir(parents=True, exist_ok=True)

    setup_session_logging(log_dir)
    state_dir = exec_root / "state"

    commands = parse_commands(
        md_path,
        include_legacy_gc=include_legacy_gc,
        skip_done=skip_done,
    )
    commands = filter_command_range(commands, from_index, to_index)

    if not commands:
        fatal(
            RunFailure(
                exit_code=EXIT_PARSE_CONFIG,
                phase="parse",
                message="No runnable commands found in markdown",
                technical_detail=str(md_path),
                log_dir=str(log_dir),
                remediation="Check headers (## Command N —) and ```text blocks",
            ),
            log_dir=log_dir,
        )

    if resume:
        prev = load_state(state_dir, root, md_path)
        if prev is not None:
            commands = [c for c in commands if c.index > prev.last_completed_index]
            logger.info("Resuming after command index %s", prev.last_completed_index)

    cfg = RunConfig(
        markdown_path=md_path,
        repo_root=root,
        exec_root=exec_root,
        log_dir=log_dir,
        api_key=api_key,
        model=resolve_model(),
        include_legacy_gc=include_legacy_gc,
        skip_done=skip_done,
        dry_run=dry_run,
        resume=resume,
        no_expand_attachments=no_expand_attachments,
        from_index=from_index,
        to_index=to_index,
        max_prompt_chars=resolve_max_prompt_chars(),
        max_attachment_chars=resolve_max_attachment_chars(),
    )

    total = len(commands)
    print_opening_banner(
        markdown_path=str(md_path),
        repo_root=str(root),
        log_dir=str(log_dir),
        command_count=total,
    )

    for pos, cmd in enumerate(commands, start=1):
        print_starting_command(
            index=cmd.index,
            total=total,
            command_id=cmd.command_id,
            title=cmd.title,
        )
        log_event(
            log_dir,
            "command_start",
            {"index": cmd.index, "id": cmd.command_id, "position": pos, "total": total},
        )

        body = cmd.prompt_text
        if not cfg.no_expand_attachments:
            expanded = expand_attachments(
                body,
                cfg.repo_root,
                max_attachment_chars=cfg.max_attachment_chars,
            )
            body = expanded.prompt

        full_prompt = build_full_prompt(
            cmd,
            expanded_body=body,
            command_position=pos,
            command_total=total,
        )

        if len(full_prompt) > cfg.max_prompt_chars:
            sizes = attachment_size_report(
                expand_attachments(cmd.prompt_text, cfg.repo_root, max_attachment_chars=cfg.max_attachment_chars).attachments
            )
            fatal(
                RunFailure(
                    exit_code=EXIT_PARSE_CONFIG,
                    phase="expand",
                    message=f"Prompt exceeds max size ({len(full_prompt)} > {cfg.max_prompt_chars})",
                    command_index=cmd.index,
                    command_id=cmd.command_id,
                    command_title=cmd.title,
                    technical_detail=f"Largest attachments: {sizes[:5]}",
                    log_dir=str(log_dir),
                    remediation="Reduce @ attachments or raise CURSOR_EXECUTE_MAX_PROMPT_CHARS",
                ),
                log_dir=log_dir,
            )

        if dry_run:
            print(f"[dry-run] Command {cmd.index} prompt size: {len(full_prompt)} chars")
            log_event(log_dir, "command_dry_run", {"index": cmd.index, "chars": len(full_prompt)})
            continue

        try:
            snapshot = take_snapshot(cfg.repo_root)
        except RuntimeError as e:
            fatal(
                RunFailure(
                    exit_code=EXIT_GIT,
                    phase="git_snapshot",
                    message="Failed to take git snapshot before command",
                    command_index=cmd.index,
                    command_id=cmd.command_id,
                    command_title=cmd.title,
                    technical_detail=str(e),
                    log_dir=str(log_dir),
                ),
                log_dir=log_dir,
            )

        sdk_result = run_agent_command(cfg, cmd, full_prompt, command_position=pos, command_total=total)

        try:
            summary = diff_since_snapshot(
                cfg.repo_root,
                snapshot,
                command_index=cmd.index,
                command_total=total,
                command_id=cmd.command_id,
                command_title=cmd.title,
            )
        except RuntimeError as e:
            fatal(
                RunFailure(
                    exit_code=EXIT_GIT,
                    phase="git_snapshot",
                    message="Failed to compute file changes after command",
                    command_index=cmd.index,
                    command_id=cmd.command_id,
                    command_title=cmd.title,
                    technical_detail=str(e),
                    log_dir=str(log_dir),
                ),
                log_dir=log_dir,
            )

        print_success_banner(summary)

        save_state(
            state_dir,
            SessionState(
                repo_root=str(cfg.repo_root),
                markdown_path=str(cfg.markdown_path),
                last_completed_index=cmd.index,
                last_run_id=sdk_result.run_id,
            ),
        )
        log_event(log_dir, "command_end", {"index": cmd.index, "run_id": sdk_result.run_id})

    if dry_run:
        print(f"\nDry run complete: {total} command(s) parsed.")
    else:
        print(f"\nAll {total} command(s) completed successfully.")
        print(f"Logs: {log_dir}")


def run() -> None:
    try:
        typer.run(main)
    except SystemExit:
        raise
    except typer.Exit as e:
        raise SystemExit(e.exit_code) from e
    except Exception as e:
        fatal(
            RunFailure(
                exit_code=EXIT_PARSE_CONFIG,
                phase="unhandled",
                message=str(e),
                technical_detail=f"{type(e).__name__}: {e}",
            ),
        )


if __name__ == "__main__":
    run()
