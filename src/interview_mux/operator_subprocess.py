"""Run shell commands with stdout/stderr mirrored to gui_log.jsonl."""

from __future__ import annotations

import shlex
import subprocess
import threading
from datetime import datetime, timezone
from typing import Any

from interview_mux.operator_trace import resolve_ctx, resolve_stage
from interview_mux.run_context import RunContext

_MAX_LINE = 4000
_RUNNING_STATUSES = frozenset({"running", "running_with_warnings"})


def format_command(cmd: list[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in cmd)


def _stderr_tail(capture: list[str], *, max_chars: int = 2048) -> str | None:
    text = "".join(capture)
    if not text:
        return None
    return text[-max_chars:]


def _log_stream_line(
    ctx: RunContext,
    *,
    stage: str,
    stream: str,
    line: str,
) -> None:
    text = line.rstrip("\r\n")
    if not text.strip():
        return
    if len(text) > _MAX_LINE:
        text = text[: _MAX_LINE - 3] + "..."
    ctx.log(
        text,
        level="info",
        stage=stage,
        detail={"stream": stream, "journey_kind": "execute"},
    )


def _pump_stream(
    pipe: Any,
    ctx: RunContext,
    *,
    stage: str,
    stream: str,
    capture: list[str] | None,
) -> None:
    try:
        for raw in iter(pipe.readline, ""):
            if not raw:
                continue
            _log_stream_line(ctx, stage=stage, stream=stream, line=raw)
            if capture is not None:
                capture.append(raw)
    finally:
        pipe.close()


def touch_job_message(ctx: RunContext, message: str) -> None:
    """Update gui_job.json message while a background job is running."""
    path = ctx.path("gui_job.json")
    if not path.is_file():
        return
    try:
        data = ctx.read_json("gui_job.json")
    except OSError:
        return
    if not isinstance(data, dict):
        return
    if data.get("status") not in _RUNNING_STATUSES:
        return
    data["message"] = message
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    ctx.write_json("gui_job.json", data)


def run_logged_command(
    ctx: RunContext,
    cmd: list[str],
    *,
    stage: str,
    label: str | None = None,
    cwd: str | None = None,
    timeout: int | None = None,
    capture_output: bool = False,
    log_start: bool = True,
    action_id: str | None = "subprocess.run",
) -> subprocess.CompletedProcess[str]:
    """Execute a command; stream stdout/stderr to the operator log."""
    desc = label or format_command(cmd)
    trace_id = None
    if action_id:
        from interview_mux.operator_action_trace import begin_action, end_action

        trace_id = begin_action(
            action_id,
            run_dir=ctx.run_dir,
            stage=stage,
            origin="subprocess",
            summary=desc,
            command=cmd,
            function="operator_subprocess.run_logged_command",
        )
    if log_start:
        ctx.log(
            f"$ {desc}",
            level="action",
            stage=stage,
            detail={"journey_kind": "execute", "cmd": cmd, "action_id": action_id},
            action_id=action_id,
            origin="subprocess",
        )
        touch_job_message(ctx, f"Running: {desc}")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
    )
    stdout_buf: list[str] = []
    stderr_capture: list[str] = []
    threads: list[threading.Thread] = []
    if proc.stdout is not None:
        t = threading.Thread(
            target=_pump_stream,
            args=(proc.stdout, ctx),
            kwargs={
                "stage": stage,
                "stream": "stdout",
                "capture": stdout_buf if capture_output else None,
            },
            daemon=True,
        )
        t.start()
        threads.append(t)
    if proc.stderr is not None:
        t = threading.Thread(
            target=_pump_stream,
            args=(proc.stderr, ctx),
            kwargs={
                "stage": stage,
                "stream": "stderr",
                "capture": stderr_capture,
            },
            daemon=True,
        )
        t.start()
        threads.append(t)

    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        for thread in threads:
            thread.join(timeout=2)
        stderr_tail = _stderr_tail(stderr_capture)
        detail: dict[str, Any] = {"journey_kind": "execute", "timed_out": True}
        if stderr_tail:
            detail["stderr_tail"] = stderr_tail
        ctx.log(
            f"Command timed out after {timeout}s: {desc}",
            level="error",
            stage=stage,
            detail=detail,
            action_id=action_id,
            origin="subprocess",
        )
        if trace_id:
            from interview_mux.operator_action_trace import end_action

            end_action(trace_id, run_dir=ctx.run_dir, status="error", detail=detail)
        raise LocalCommandError(desc, returncode=None, timed_out=True) from exc
    finally:
        for thread in threads:
            thread.join(timeout=2)

    if rc != 0:
        stderr_tail = _stderr_tail(stderr_capture)
        detail = {"journey_kind": "execute", "returncode": rc}
        if stderr_tail:
            detail["stderr_tail"] = stderr_tail
        ctx.log(
            f"Command failed (exit {rc}): {desc}",
            level="error",
            stage=stage,
            detail=detail,
            action_id=action_id,
            origin="subprocess",
        )
        if trace_id:
            from interview_mux.operator_action_trace import end_action

            end_action(trace_id, run_dir=ctx.run_dir, status="error", detail=detail)
        raise LocalCommandError(desc, returncode=rc)

    if log_start:
        ctx.log(
            f"Command finished (exit 0): {desc}",
            level="success",
            stage=stage,
            detail={"journey_kind": "execute", "action_id": action_id},
            action_id=action_id,
            origin="subprocess",
        )
    if trace_id:
        from interview_mux.operator_action_trace import end_action

        end_action(trace_id, run_dir=ctx.run_dir, status="ok")
    return subprocess.CompletedProcess(
        cmd,
        rc,
        "".join(stdout_buf),
        "".join(stderr_capture),
    )


def run_command(
    cmd: list[str],
    *,
    ctx: RunContext | None = None,
    stage: str | None = None,
    label: str | None = None,
    cwd: str | None = None,
    timeout: int | None = None,
    capture_output: bool = True,
    check: bool = True,
    log_start: bool = True,
    text: bool = True,
    action_id: str | None = "subprocess.run",
) -> subprocess.CompletedProcess[str]:
    """
    Run a subprocess with operator logging when a run context is active.

    Falls back to plain subprocess.run when no run context is available (CLI bootstrap).
    """
    run = resolve_ctx(ctx)
    sid = resolve_stage(stage)
    if run:
        proc = run_logged_command(
            run,
            cmd,
            stage=sid,
            label=label,
            cwd=cwd,
            timeout=timeout,
            capture_output=capture_output,
            log_start=log_start,
            action_id=action_id,
        )
        return proc

    proc = subprocess.run(
        cmd,
        capture_output=capture_output,
        text=text,
        cwd=cwd,
        timeout=timeout,
        check=False,
    )
    if check and proc.returncode != 0:
        desc = label or format_command(cmd)
        raise subprocess.CalledProcessError(proc.returncode, cmd, proc.stdout, proc.stderr)
    return proc


class LocalCommandError(RuntimeError):
    def __init__(
        self,
        command: str,
        *,
        returncode: int | None,
        timed_out: bool = False,
    ) -> None:
        self.command = command
        self.returncode = returncode
        self.timed_out = timed_out
        if timed_out:
            super().__init__(f"Command timed out: {command}")
        else:
            super().__init__(f"Command failed (exit {returncode}): {command}")
