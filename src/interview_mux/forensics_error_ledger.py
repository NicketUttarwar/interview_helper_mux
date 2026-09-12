"""Forensic-run ledger of *all* errors / predicates (not only successful heals).

When ``MUX_FORENSICS`` is on, every recorded failure is appended under
``operator/forensics_errors.json`` and mirrored to
``operator/forensics_errors.md`` for later family analysis / ledger updates.

Companion to ``forensics_minor_fixes`` (successful rectifications only).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

FORENSICS_ERRORS_JSON = "operator/forensics_errors.json"
FORENSICS_ERRORS_MD = "operator/forensics_errors.md"
_MAX_ENTRIES = 2000
_DETAIL_CAP = 2000


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
        "summary": {},
    }
    if not ctx.artifact_exists(FORENSICS_ERRORS_JSON):
        return doc
    try:
        raw = ctx.read_json(FORENSICS_ERRORS_JSON)
    except Exception:
        return doc
    if isinstance(raw, dict):
        for k in ("version", "run_id", "entries", "updated_at", "summary"):
            if k in raw:
                doc[k] = raw[k]
        if not isinstance(doc.get("entries"), list):
            doc["entries"] = []
    return doc


def _count_by(entries: list[Any], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in entries:
        if not isinstance(row, dict):
            continue
        k = str(row.get(key) or "") or "(none)"
        out[k] = int(out.get(k) or 0) + 1
    return out


def _render_md(doc: dict[str, Any]) -> str:
    entries = [e for e in (doc.get("entries") or []) if isinstance(e, dict)]
    summary = doc.get("summary") if isinstance(doc.get("summary"), dict) else {}
    lines = [
        f"# Forensics errors — `{doc.get('run_id') or ''}`",
        "",
        "Full failure / predicate ledger for this forensic execution. Use for",
        "post-run family analysis (see `docs/cross-cutting/predicate-families.md`).",
        "",
        f"- Updated: `{doc.get('updated_at') or ''}`",
        f"- Entry count: **{len(entries)}**",
        f"- Unique predicates: **{int(summary.get('unique_predicates') or 0)}**",
        "",
        "| # | When (UTC) | Source | Stage | Predicate / class | Count | Detail |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, row in enumerate(entries, start=1):
        ts = str(row.get("at") or "")[:26]
        source = str(row.get("source") or "").replace("|", "/")
        stage = str(row.get("stage") or "").replace("|", "/")
        pred = str(
            row.get("predicate") or row.get("error_class") or row.get("signature") or ""
        ).replace("|", "/")[:80]
        count = row.get("identical_count")
        count_s = "" if count is None else str(count)
        detail = str(row.get("detail") or "").replace("|", "/")[:120]
        lines.append(
            f"| {i} | {ts} | {source} | {stage} | {pred} | {count_s} | {detail} |"
        )
    lines.append("")
    by_stage = summary.get("by_stage") if isinstance(summary.get("by_stage"), dict) else {}
    if by_stage:
        lines.extend(["## By stage", ""])
        for k, v in sorted(by_stage.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- `{k}`: {v}")
        lines.append("")
    by_pred = (
        summary.get("by_predicate")
        if isinstance(summary.get("by_predicate"), dict)
        else {}
    )
    if by_pred:
        lines.extend(["## By predicate (top)", ""])
        top = sorted(by_pred.items(), key=lambda kv: (-kv[1], kv[0]))[:40]
        for k, v in top:
            lines.append(f"- `{k}`: {v}")
        lines.append("")
    return "\n".join(lines)


def record_forensics_error(
    ctx: Any,
    *,
    source: str,
    stage: str = "",
    detail: str = "",
    error_class: str = "",
    predicate: str = "",
    signature: str = "",
    identical_count: int | None = None,
    halt: bool | None = None,
    severity: str = "error",
    extra: dict[str, Any] | None = None,
) -> None:
    """Append one forensic error event (no-op unless forensics mode)."""
    if not _forensics_on():
        return
    try:
        doc = _load(ctx)
        pred = str(predicate or error_class or signature or detail or "")[:240]
        entry: dict[str, Any] = {
            "at": _utc_now(),
            "source": str(source or "")[:80],
            "stage": str(stage or "")[:120],
            "severity": str(severity or "error")[:40],
            "error_class": str(error_class or "")[:160],
            "predicate": pred,
            "signature": str(signature or "")[:80],
            "detail": str(detail or "")[:_DETAIL_CAP],
        }
        if identical_count is not None:
            entry["identical_count"] = int(identical_count)
        if halt is not None:
            entry["halt"] = bool(halt)
        if extra and isinstance(extra, dict):
            slim: dict[str, Any] = {}
            for k, v in extra.items():
                if isinstance(v, (str, int, float, bool)) or v is None:
                    slim[k] = v if not isinstance(v, str) else v[:400]
                elif isinstance(v, (list, dict)):
                    # Compact JSON-ish for analysis without blowing the ledger.
                    text = str(v)
                    slim[k] = text[:400]
            if slim:
                entry["extra"] = slim
        entries = list(doc.get("entries") or [])
        entries.append(entry)
        doc["entries"] = entries[-_MAX_ENTRIES:]
        doc["version"] = 1
        doc["run_id"] = str(getattr(ctx, "run_id", "") or doc.get("run_id") or "")
        doc["updated_at"] = _utc_now()
        by_pred = _count_by(doc["entries"], "predicate")
        doc["summary"] = {
            "count": len(doc["entries"]),
            "unique_predicates": len([k for k in by_pred if k != "(none)"]),
            "by_source": _count_by(doc["entries"], "source"),
            "by_stage": _count_by(doc["entries"], "stage"),
            "by_predicate": by_pred,
            "by_error_class": _count_by(doc["entries"], "error_class"),
        }
        ctx.write_json(FORENSICS_ERRORS_JSON, doc, skip_handoff=True)
        md_path = ctx.path(FORENSICS_ERRORS_MD)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_render_md(doc), encoding="utf-8")
    except Exception:
        pass


def record_from_identical_failure_row(ctx: Any, row: dict[str, Any]) -> None:
    """Hook from ``identical_failures.record_failure`` (every ledger write)."""
    if not isinstance(row, dict):
        return
    stage = str(row.get("failed_stage") or "")
    detail = str(
        row.get("raw_reason")
        or row.get("reason")
        or row.get("fail_key")
        or row.get("error_class")
        or ""
    )
    record_forensics_error(
        ctx,
        source="identical_failures",
        stage=stage,
        detail=detail,
        error_class=str(row.get("error_class") or row.get("producer") or ""),
        predicate=str(
            row.get("fail_key")
            or row.get("error_class")
            or row.get("reason")
            or row.get("signature")
            or ""
        ),
        signature=str(row.get("signature") or ""),
        identical_count=int(row.get("count") or 0) or None,
        halt=bool(row.get("halt")) if "halt" in row else None,
        severity="halt" if row.get("halt") else "error",
        extra={
            "kind": str(row.get("kind") or "") or None,
            "cascade_suppressed": bool(row["cascade_suppressed"])
            if "cascade_suppressed" in row
            else None,
            "resume_attempted": str(row.get("resume_attempted") or "") or None,
            "predicate_token": str(row.get("predicate_token") or "") or None,
            "esr_softened": bool(row["esr_softened"]) if "esr_softened" in row else None,
        },
    )


def record_from_recovery_action(ctx: Any, row: dict[str, Any]) -> None:
    """Hook for recovery_controller — record non-success and success attempts."""
    if not isinstance(row, dict):
        return
    status = str(row.get("status") or "").lower()
    sig = str(row.get("signature") or "")
    stage = sig.split(":", 1)[0] if ":" in sig else str(row.get("resume_stage") or "")
    record_forensics_error(
        ctx,
        source="recovery_controller",
        stage=stage,
        detail=str(row.get("detail") or row.get("tier") or status)[:_DETAIL_CAP],
        error_class=str(row.get("error_class") or ""),
        predicate=str(row.get("playbook_id") or sig or status),
        signature=sig[:80],
        severity="recovered" if status == "recovered" else "error",
        extra={
            "status": status or None,
            "playbook_id": str(row.get("playbook_id") or "") or None,
            "tier": str(row.get("tier") or "") or None,
            "resume_stage": str(row.get("resume_stage") or "") or None,
        },
    )


def record_from_driver_event(
    ctx: Any,
    *,
    stage: str = "",
    detail: str = "",
    action: str = "",
    severity: str = "error",
    extra: dict[str, Any] | None = None,
) -> None:
    """Hook for full_auto_driver ERROR / job-error lines."""
    record_forensics_error(
        ctx,
        source="full_auto_driver",
        stage=stage,
        detail=detail,
        predicate=str(action or detail or "")[:240],
        error_class=str(action or "")[:160],
        severity=severity,
        extra=extra,
    )
