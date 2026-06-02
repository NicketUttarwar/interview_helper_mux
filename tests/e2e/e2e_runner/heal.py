"""Cursor Agent self-heal integration."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class HealResult:
    success: bool
    summary: str
    transcript_path: str
    files_changed: list[str]
    pytest_ok: bool


def run_heal(
    repo_root: Path,
    log_dir: Path,
    *,
    incident_id: int,
    failure_summary: str,
    run_id: str | None,
    run_snapshot: dict[str, Any] | None,
    log_tail: list[dict[str, Any]] | None,
    api_key: str | None,
) -> HealResult:
    heal_dir = log_dir / "heal"
    heal_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = heal_dir / f"{incident_id:03d}_transcript.txt"

    prompt = _build_heal_prompt(
        failure_summary=failure_summary,
        run_id=run_id,
        run_snapshot=run_snapshot,
        log_tail=log_tail,
    )
    prompt_path = heal_dir / f"{incident_id:03d}_prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")

    if not api_key:
        transcript_path.write_text("Heal skipped: CURSOR_API_KEY not set\n", encoding="utf-8")
        return HealResult(
            success=False,
            summary="CURSOR_API_KEY not set",
            transcript_path=str(transcript_path),
            files_changed=[],
            pytest_ok=False,
        )

    try:
        from cursor_sdk import Agent, LocalAgentOptions
    except ImportError:
        transcript_path.write_text(
            "Heal skipped: cursor-sdk not installed in tests/e2e venv\n",
            encoding="utf-8",
        )
        return HealResult(
            success=False,
            summary="cursor-sdk not installed",
            transcript_path=str(transcript_path),
            files_changed=[],
            pytest_ok=False,
        )

    lines: list[str] = []
    status = "unknown"
    try:
        try:
            local = LocalAgentOptions(cwd=str(repo_root), setting_sources=["all"])
        except TypeError:
            local = LocalAgentOptions(cwd=str(repo_root))

        with Agent.create(api_key=api_key, local=local) as agent:
            run = agent.send(prompt)
            for message in run.messages():
                msg_type = getattr(message, "type", None) or type(message).__name__
                if msg_type == "assistant":
                    inner = getattr(message, "message", message)
                    for block in getattr(inner, "content", None) or []:
                        text = getattr(block, "text", None)
                        if text:
                            lines.append(text)
                else:
                    lines.append(f"[{msg_type}] {str(message)[:500]}")
            result = run.wait()
            status = getattr(result, "status", None) or "unknown"
    except Exception as exc:
        lines.append(f"HEAL ERROR: {exc}")
        status = "error"

    transcript_path.write_text("\n".join(lines), encoding="utf-8")

    files_changed = _git_changed_files(repo_root)
    pytest_ok = _run_pytest(repo_root, files_changed)

    frontend_changed = any(p.startswith("frontend/") for p in files_changed)
    if frontend_changed:
        _rebuild_gui(repo_root)

    success = status == "finished" and pytest_ok
    summary = lines[-1][:500] if lines else f"status={status}"
    return HealResult(
        success=success,
        summary=summary,
        transcript_path=str(transcript_path),
        files_changed=files_changed,
        pytest_ok=pytest_ok,
    )


def _build_heal_prompt(
    *,
    failure_summary: str,
    run_id: str | None,
    run_snapshot: dict[str, Any] | None,
    log_tail: list[dict[str, Any]] | None,
) -> str:
    import json

    log_lines = []
    for entry in log_tail or []:
        if isinstance(entry, dict):
            log_lines.append(
                f"{entry.get('level', 'info')}: {entry.get('message', '')}"
            )
    return f"""You are fixing interview_helper_mux so the E2E journey can continue.

Failure: {failure_summary}
run_id: {run_id or 'unknown'}
journey: {json.dumps((run_snapshot or {}).get('journey'), indent=2)[:8000]}
job: {json.dumps((run_snapshot or {}).get('job'), indent=2)[:4000]}
Last log lines:
{chr(10).join(log_lines[-50:])}

Reproduce: ./scripts/e2e.sh --resume-run-id {run_id or 'EXEC_ID'}

Rules:
- Read AGENTS.md and .cursor/rules/interview-helper-mux.mdc
- Minimal fix only; run pytest for touched areas
- Do NOT disable gates or auto-enable pre-clean
- Do NOT edit the E2E plan file
"""


def _git_changed_files(repo_root: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def _run_pytest(repo_root: Path, changed: list[str]) -> bool:
    targets = ["tests/"]
    if changed:
        test_files = [
            f"tests/test_{Path(p).stem}.py"
            for p in changed
            if p.startswith("src/interview_mux/")
        ]
        if test_files:
            targets = [t for t in test_files if (repo_root / t).is_file()] or targets
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *targets, "-q", "--tb=no"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def _rebuild_gui(repo_root: Path) -> None:
    script = repo_root / "scripts" / "build_gui.sh"
    if script.is_file():
        subprocess.run(["bash", str(script)], cwd=str(repo_root), check=False)
