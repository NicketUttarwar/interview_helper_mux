"""Build full prompts with automation prefix."""

from __future__ import annotations

from cursor_execute.parse_commands import CommandSpec


def build_full_prompt(
    cmd: CommandSpec,
    *,
    expanded_body: str,
    command_position: int,
    command_total: int,
) -> str:
    prefix = (
        "Automated CURSOR_EXECUTE run. Follow project rules and AGENTS.md if present.\n"
        f"Command {command_position}/{command_total}: {cmd.command_id} — {cmd.title}\n"
        "Do not run pytest unless this prompt explicitly requires it.\n"
        "---\n\n"
    )
    return prefix + expanded_body
