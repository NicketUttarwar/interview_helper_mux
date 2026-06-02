"""Render post-run final report markdown."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from e2e_runner.types import IncidentRecord


def write_final_report(
    *,
    session_id: str,
    log_dir: Path,
    repo_root: Path,
    input_audio: str,
    flows: tuple[str, ...],
    outcome: str,
    run_ids: list[str],
    incidents: list[IncidentRecord],
    clean_flows: list[str],
    residual: list[str],
    started_at: datetime,
    ended_at: datetime,
) -> Path:
    docs_dir = repo_root / "docs" / "e2e-reports"
    docs_dir.mkdir(parents=True, exist_ok=True)
    gitkeep = docs_dir / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.touch()

    filename = f"{session_id}_final-report.md"
    docs_path = docs_dir / filename
    session_path = log_dir / "final-report.md"

    body = render_report(
        session_id=session_id,
        input_audio=input_audio,
        flows=flows,
        outcome=outcome,
        run_ids=run_ids,
        incidents=incidents,
        clean_flows=clean_flows,
        residual=residual,
        started_at=started_at,
        ended_at=ended_at,
    )
    docs_path.write_text(body, encoding="utf-8")
    session_path.write_text(body, encoding="utf-8")
    return docs_path


def render_report(
    *,
    session_id: str,
    input_audio: str,
    flows: tuple[str, ...],
    outcome: str,
    run_ids: list[str],
    incidents: list[IncidentRecord],
    clean_flows: list[str],
    residual: list[str],
    started_at: datetime,
    ended_at: datetime,
) -> str:
    duration = (ended_at - started_at).total_seconds()
    lines = [
        f"# E2E final report — {session_id}",
        "",
        "## Session summary",
        f"- Input: {input_audio}",
        f"- Flows attempted: {', '.join(flows)}",
        f"- Outcome: {outcome}",
        f"- Total heal incidents: {len(incidents)}",
        f"- Duration: {duration:.0f}s",
        f"- Run ids: {', '.join(run_ids) if run_ids else '(none)'}",
        "",
    ]

    if incidents:
        lines.append("## Incidents")
        lines.append("")
        for inc in incidents:
            lines.extend(_incident_section(inc))
        lines.append("## Fixes index (all changes)")
        lines.append("")
        lines.append("| # | Severity | Root cause (one line) | Files | Outcome |")
        lines.append("|---|----------|----------------------|-------|---------|")
        for inc in incidents:
            files = ", ".join(inc.files_changed) if inc.files_changed else "—"
            outcome_cell = "fixed" if inc.fix_applied else "unresolved"
            rc = (inc.root_cause or inc.summary).replace("|", "/")[:80]
            lines.append(
                f"| {inc.incident_id} | {inc.severity} | {rc} | {files} | {outcome_cell} |"
            )
        lines.append("")
    else:
        lines.append("## Incidents")
        lines.append("")
        lines.append("No heal incidents — clean run.")
        lines.append("")

    lines.append("## No-incident flows")
    if clean_flows:
        for f in clean_flows:
            lines.append(f"- {f}")
    else:
        lines.append("- (none)")
    lines.append("")

    lines.append("## Residual issues")
    if residual:
        for r in residual:
            lines.append(f"- {r}")
    else:
        lines.append("- None")
    lines.append("")

    return "\n".join(lines)


def _incident_section(inc: IncidentRecord) -> list[str]:
    ctx = inc.phase or "?"
    na = inc.next_action or "?"
    stage = inc.stage_id or "?"
    files = ", ".join(inc.files_changed) if inc.files_changed else "—"
    return [
        f"### Incident {inc.incident_id} — {inc.summary[:60]}",
        f"- **When:** {inc.timestamp} (+{inc.elapsed_s:.0f}s)",
        f"- **Severity:** {inc.severity}",
        f"- **User-flow step:** {ctx} / {na} / stage {stage}",
        f"- **Symptom:** {inc.symptom}",
        f"- **Root cause:** {inc.root_cause or 'See failure bundle'}",
        f"- **Fix applied:** {inc.fix_applied or '—'}",
        f"- **Files changed:** {files}",
        f"- **Verified by:** {inc.verification or '—'}",
        "",
    ]


def load_incidents_from_bundles(log_dir: Path) -> list[dict[str, Any]]:
    failures = log_dir / "failures"
    if not failures.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(failures.glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out
