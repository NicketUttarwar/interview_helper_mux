"""Loud success and fatal banners (Rich)."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

if TYPE_CHECKING:
    from cursor_execute.errors import RunFailure
    from cursor_execute.git_stats import FileChangeSummary

_console = Console(stderr=False)
_err_console = Console(stderr=True)


def print_opening_banner(
    *,
    markdown_path: str,
    repo_root: str,
    log_dir: str,
    command_count: int,
) -> None:
    body = (
        f"Markdown: {markdown_path}\n"
        f"Repo:     {repo_root}\n"
        f"Logs:     {log_dir}\n"
        f"Commands: {command_count}"
    )
    _console.print()
    _console.print(
        Panel(
            Text(body, style="bold"),
            title="[bold cyan]CURSOR_EXECUTE — SESSION START[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    _console.print()


def print_starting_command(
    *,
    index: int,
    total: int,
    command_id: str,
    title: str,
) -> None:
    _console.print()
    _console.print(Rule(f"[bold yellow]STARTING COMMAND {index} / {total}[/bold yellow]"))
    _console.print(f"[bold]  {command_id}[/bold] — {title}")
    _console.print()


def print_success_banner(summary: FileChangeSummary) -> None:
    lines = [
        f"COMMAND {summary.command_index} / {summary.command_total}",
        f"{summary.command_id} — {summary.command_title}",
        "",
        f"FILES CHANGED: {summary.total}",
        f"  CREATED:  {summary.created}",
        f"  MODIFIED: {summary.modified}",
        f"  DELETED:  {summary.deleted}",
        f"  RENAMED:  {summary.renamed}",
    ]
    if summary.paths:
        lines.append("")
        for status, path in summary.paths[:50]:
            lines.append(f"  {status:2}  {path}")
        if len(summary.paths) > 50:
            lines.append(f"  ... and {len(summary.paths) - 50} more")
    _console.print()
    _console.print(
        Panel(
            Text("\n".join(lines), style="bold green"),
            title="[bold green]COMMAND COMPLETE — FILES CHANGED[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )
    _console.print()


def print_fatal_banner(failure: RunFailure) -> None:
    label = failure.exit_code
    from cursor_execute.errors import EXIT_LABELS

    exit_desc = EXIT_LABELS.get(label, "unknown error")
    lines = [
        "FATAL — CURSOR_EXECUTE STOPPED",
        "",
    ]
    if failure.command_index is not None:
        lines.append(f"Command: {failure.command_index}" + (
            f"  ({failure.command_id})" if failure.command_id else ""
        ))
    if failure.command_title:
        lines.append(f"Title:   {failure.command_title}")
    lines.extend([
        f"Phase:   {failure.phase}",
        f"Exit:    {failure.exit_code} ({exit_desc})",
        "",
        failure.message,
    ])
    if failure.technical_detail:
        lines.extend(["", f"Detail: {failure.technical_detail}"])
    if failure.run_id:
        lines.append(f"Run id:  {failure.run_id}")
    if failure.log_dir:
        lines.extend([
            "",
            f"Logs: {failure.log_dir}",
            f"      {failure.log_dir}/transcript.log",
            f"      {failure.log_dir}/last_failure.json",
        ])
    if failure.remediation:
        lines.extend(["", f"Next: {failure.remediation}"])

    _err_console.print()
    _err_console.print(
        Panel(
            Text("\n".join(lines), style="bold white on red"),
            title="[bold white on red] FATAL [/bold white on red]",
            border_style="red",
            padding=(1, 2),
        )
    )
    _err_console.print(file=sys.stderr)
    # Also emit block chars for scrollback visibility
    block = "█" * 56
    _err_console.print(f"[bold red]{block}[/bold red]", file=sys.stderr)
    for line in lines[:8]:
        _err_console.print(f"[bold red]██  {line[:52]:<52} ██[/bold red]", file=sys.stderr)
    _err_console.print(f"[bold red]{block}[/bold red]", file=sys.stderr)
    _err_console.print(file=sys.stderr)


def print_bash_fatal(message: str, line: int | None = None) -> None:
    _err_console.print()
    _err_console.print(
        Panel(
            Text(f"{message}\n" + (f"Line: {line}" if line else ""), style="bold red"),
            title="[bold red]FATAL — run.sh[/bold red]",
            border_style="red",
        ),
        file=sys.stderr,
    )
