"""Forensic-run ledger of minor rectifications applied mid-execution.

When ``MUX_FORENSICS`` is on, every successful small heal / recovery the run
performs is appended under ``operator/forensics_minor_fixes.json`` and mirrored
to a human-readable ``operator/forensics_minor_fixes.md`` for later review.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

FORENSICS_MINOR_FIXES_JSON = "operator/forensics_minor_fixes.json"
FORENSICS_MINOR_FIXES_MD = "operator/forensics_minor_fixes.md"
_MAX_ENTRIES = 500


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _forensics_on() -> bool:
    try:
        from interview_mux.identical_failures import forensics_mode

        return bool(forensics_mode())
    except Exception:
        return False


def _load(ctx: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "version": 1,
        "run_id": str(getattr(ctx, "run_id", "") or ""),
        "entries": [],
        "updated_at": None,
    }
    if not ctx.artifact_exists(FORENSICS_MINOR_FIXES_JSON):
        return doc
    try:
        raw = ctx.read_json(FORENSICS_MINOR_FIXES_JSON)
    except Exception:
        return doc
    if isinstance(raw, dict):
        doc.update({k: v for k, v in raw.items() if k in doc or k in ("version", "run_id", "entries", "updated_at", "summary")})
        if not isinstance(doc.get("entries"), list):
            doc["entries"] = []
    return doc


def _render_md(doc: dict[str, Any]) -> str:
    entries = [e for e in (doc.get("entries") or []) if isinstance(e, dict)]
    lines = [
        f"# Forensics minor fixes — `{doc.get('run_id') or ''}`",
        "",
        "Ledger of small rectifications this forensic execution applied mid-run",
        "(recovery playbooks, driver heals, remediation stamps) so later review",
        "can see where the run picked itself up.",
        "",
        f"- Updated: `{doc.get('updated_at') or ''}`",
        f"- Entry count: **{len(entries)}**",
        "",
        "| # | When (UTC) | Source | Stage | Action | Detail |",
        "|---|---|---|---|---|---|",
    ]
    for i, row in enumerate(entries, start=1):
        ts = str(row.get("at") or "")[:26]
        source = str(row.get("source") or "").replace("|", "/")
        stage = str(row.get("stage") or "").replace("|", "/")
        action = str(row.get("action") or "").replace("|", "/")
        detail = str(row.get("detail") or "").replace("|", "/")[:160]
        lines.append(f"| {i} | {ts} | {source} | {stage} | {action} | {detail} |")
    lines.append("")
    return "\n".join(lines)


def record_forensics_minor_fix(
    ctx: Any,
    *,
    source: str,
    stage: str = "",
    action: str = "",
    detail: str = "",
    status: str = "applied",
    extra: dict[str, Any] | None = None,
) -> None:
    """Append one successful forensic rectification (no-op unless forensics mode)."""
    if not _forensics_on():
        return
    # Only record rectifications that actually landed, not escalations.
    if str(status or "").lower() not in {"applied", "recovered", "healed", "ok"}:
        return
    try:
        doc = _load(ctx)
        entry: dict[str, Any] = {
            "at": _utc_now(),
            "source": str(source or "")[:80],
            "stage": str(stage or "")[:120],
            "action": str(action or "")[:160],
            "detail": str(detail or "")[:400],
            "status": "applied",
        }
        if extra and isinstance(extra, dict):
            # Keep ledger compact — only shallow scalars.
            slim = {
                k: v
                for k, v in extra.items()
                if isinstance(v, (str, int, float, bool)) or v is None
            }
            if slim:
                entry["extra"] = slim
        entries = list(doc.get("entries") or [])
        entries.append(entry)
        doc["entries"] = entries[-_MAX_ENTRIES:]
        doc["version"] = 1
        doc["run_id"] = str(getattr(ctx, "run_id", "") or doc.get("run_id") or "")
        doc["updated_at"] = _utc_now()
        doc["summary"] = {
            "count": len(doc["entries"]),
            "by_source": _count_by(doc["entries"], "source"),
            "by_stage": _count_by(doc["entries"], "stage"),
        }
        ctx.write_json(FORENSICS_MINOR_FIXES_JSON, doc, skip_handoff=True)
        md_path = ctx.path(FORENSICS_MINOR_FIXES_MD)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_render_md(doc), encoding="utf-8")
    except Exception:
        pass


def _count_by(entries: list[Any], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in entries:
        if not isinstance(row, dict):
            continue
        k = str(row.get(key) or "") or "(none)"
        out[k] = int(out.get(k) or 0) + 1
    return out


def record_from_recovery_action(ctx: Any, row: dict[str, Any]) -> None:
    """Hook for recovery_controller ``_append_action`` when status is recovered."""
    if not isinstance(row, dict):
        return
    status = str(row.get("status") or "").lower()
    if status != "recovered":
        return
    sig = str(row.get("signature") or "")
    stage = sig.split(":", 1)[0] if ":" in sig else str(row.get("resume_stage") or "")
    record_forensics_minor_fix(
        ctx,
        source="recovery_controller",
        stage=stage,
        action=str(row.get("playbook_id") or "recovery"),
        detail=str(row.get("detail") or row.get("tier") or "")[:400],
        status="recovered",
        extra={
            "signature": sig[:160],
            "tier": str(row.get("tier") or "")[:80] or None,
        },
    )


def record_from_driver_decision(
    ctx: Any,
    *,
    severity: str,
    stage: str = "",
    action: str = "",
    reason: str = "",
    detail: Any = None,
) -> None:
    """Hook for full_auto_driver ``log_decision`` heal / continue events."""
    sev = str(severity or "").lower()
    act = str(action or "").lower()
    # Skip pure telemetry / stall escalations that are not rectifications.
    if act in {
        "forensics_escalate",
        "forensics_stall",
        "pause",
        "stop",
        "exit",
    }:
        return
    if sev not in {"minor", "major"}:
        return
    detail_s = detail if isinstance(detail, str) else (
        "" if detail is None else str(detail)[:400]
    )
    record_forensics_minor_fix(
        ctx,
        source="full_auto_driver",
        stage=stage,
        action=action or reason or "decision",
        detail=(reason + (" | " + detail_s if detail_s else "")).strip(" |")[:400],
        status="applied",
        extra={"severity": sev},
    )
