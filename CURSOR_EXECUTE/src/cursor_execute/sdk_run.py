"""Cursor SDK agent execution with full stream logging."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cursor_execute.config import RunConfig
from cursor_execute.errors import EXIT_AGENT_RUN, EXIT_SDK_STARTUP, RunFailure, fatal
from cursor_execute.logging_setup import log_event
from cursor_execute.parse_commands import CommandSpec

logger = logging.getLogger("cursor_execute")


@dataclass
class SdkRunResult:
    run_id: str
    agent_id: str | None
    status: str


def run_agent_command(
    cfg: RunConfig,
    cmd: CommandSpec,
    full_prompt: str,
    *,
    command_position: int,
    command_total: int,
) -> SdkRunResult:
    try:
        from cursor_sdk import Agent, AgentOptions, CursorAgentError, LocalAgentOptions
    except ImportError as e:
        fatal(
            RunFailure(
                exit_code=EXIT_SDK_STARTUP,
                phase="sdk_import",
                message="cursor-sdk is not installed. Run CURSOR_EXECUTE/bootstrap_venv.sh",
                command_index=cmd.index,
                command_id=cmd.command_id,
                command_title=cmd.title,
                technical_detail=str(e),
                log_dir=str(cfg.log_dir),
                remediation="./CURSOR_EXECUTE/bootstrap_venv.sh",
            ),
            log_dir=cfg.log_dir,
        )

    local_opts: dict[str, Any] = {"cwd": str(cfg.repo_root)}
    # Honor project rules when supported by installed SDK version.
    try:
        local = LocalAgentOptions(**local_opts, setting_sources=["all"])
    except TypeError:
        local = LocalAgentOptions(**local_opts)

    log_event(
        cfg.log_dir,
        "command_sdk_start",
        {
            "command_index": cmd.index,
            "command_id": cmd.command_id,
            "prompt_chars": len(full_prompt),
        },
    )

    try:
        with Agent.create(
            model=cfg.model,
            api_key=cfg.api_key,
            local=local,
        ) as agent:
            run = agent.send(full_prompt)
            run_id = getattr(run, "id", None) or getattr(run, "run_id", "unknown")
            agent_id = getattr(agent, "agent_id", None) or getattr(agent, "id", None)

            logger.info("SDK run started: run_id=%s agent_id=%s", run_id, agent_id)

            for message in run.messages():
                _handle_sdk_message(message, cfg.log_dir, cmd)

            result = run.wait()
            status = getattr(result, "status", None) or "unknown"

            log_event(
                cfg.log_dir,
                "command_sdk_end",
                {
                    "command_index": cmd.index,
                    "run_id": run_id,
                    "status": status,
                },
            )

            if status != "finished":
                detail = getattr(result, "result", None) or str(result)
                fatal(
                    RunFailure(
                        exit_code=EXIT_AGENT_RUN,
                        phase="sdk_run",
                        message=f"Agent run ended with status={status!r}",
                        command_index=cmd.index,
                        command_id=cmd.command_id,
                        command_title=cmd.title,
                        run_id=str(run_id),
                        technical_detail=str(detail)[:2000],
                        log_dir=str(cfg.log_dir),
                        remediation=f"Fix the error, then re-run with --resume or --from {cmd.index}",
                    ),
                    log_dir=cfg.log_dir,
                )

            return SdkRunResult(run_id=str(run_id), agent_id=str(agent_id) if agent_id else None, status=status)

    except Exception as e:
        err_name = type(e).__name__
        if err_name == "CursorAgentError" or "CursorAgentError" in err_name:
            fatal(
                RunFailure(
                    exit_code=EXIT_SDK_STARTUP,
                    phase="sdk_run",
                    message="SDK failed to start or connect",
                    command_index=cmd.index,
                    command_id=cmd.command_id,
                    command_title=cmd.title,
                    technical_detail=str(e),
                    log_dir=str(cfg.log_dir),
                    remediation="Check CURSOR_API_KEY and that Cursor local bridge is available",
                ),
                log_dir=cfg.log_dir,
            )
        raise


def _handle_sdk_message(message: Any, log_dir: Path, cmd: CommandSpec) -> None:
    msg_type = getattr(message, "type", None) or type(message).__name__
    log_event(
        log_dir,
        "sdk_message",
        {"command_index": cmd.index, "message_type": str(msg_type)},
    )

    if msg_type == "assistant":
        inner = getattr(message, "message", message)
        content = getattr(inner, "content", None) or []
        for block in content:
            text = getattr(block, "text", None)
            if text:
                sys.stdout.write(text)
                sys.stdout.flush()
    elif msg_type in ("tool_call", "tool_result", "thinking"):
        summary = str(message)[:500]
        logger.warning("SDK %s: %s", msg_type, summary)
        print(f"[cursor_execute] {msg_type}: {summary[:200]}", file=sys.stderr)
