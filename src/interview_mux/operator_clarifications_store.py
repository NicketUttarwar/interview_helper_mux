"""Read/write understanding/operator_clarifications.json for ITR."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

CLARIFICATIONS_REL = "understanding/operator_clarifications.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_clarifications(ctx: Any) -> dict[str, Any]:
    if not ctx.artifact_exists(CLARIFICATIONS_REL):
        return {"schema_version": 1, "items": []}
    raw = ctx.read_json(CLARIFICATIONS_REL)
    if not isinstance(raw, dict):
        return {"schema_version": 1, "items": []}
    items = raw.get("items")
    if not isinstance(items, list):
        raw["items"] = []
    raw.setdefault("schema_version", 1)
    return raw


def save_clarifications(ctx: Any, doc: dict[str, Any]) -> None:
    doc = dict(doc)
    doc.setdefault("schema_version", 1)
    doc.setdefault("items", [])
    ctx.write_json(CLARIFICATIONS_REL, doc)


def issue_id_for(stage_key: str, message: str, segment_id: str | None = None) -> str:
    base = f"{stage_key}:{segment_id or ''}:{message[:120]}"
    digest = hashlib.sha256(base.encode()).hexdigest()[:12]
    return f"itr_{digest}"


def upsert_items(ctx: Any, items: list[dict[str, Any]]) -> None:
    doc = load_clarifications(ctx)
    by_id = {str(it["id"]): it for it in doc.get("items") or [] if isinstance(it, dict) and it.get("id")}
    for item in items:
        iid = str(item.get("id") or "")
        if not iid:
            continue
        existing = by_id.get(iid)
        if existing and existing.get("status") in ("resolved", "dismissed", "auto_fixed"):
            if item.get("status") == "open":
                continue
        by_id[iid] = item
    doc["items"] = list(by_id.values())
    save_clarifications(ctx, doc)


def items_for_stage(ctx: Any, stage_key: str) -> list[dict[str, Any]]:
    doc = load_clarifications(ctx)
    return [
        it
        for it in doc.get("items") or []
        if isinstance(it, dict) and str(it.get("stage_key") or "") == stage_key
    ]


def open_blocking_count(ctx: Any, stage_key: str) -> int:
    return sum(
        1
        for it in items_for_stage(ctx, stage_key)
        if it.get("status") == "open" and it.get("blocking") is not False
    )


def mark_resolved(ctx: Any, issue_id: str, *, chosen: Any = None, auto_applied: Any = None) -> bool:
    doc = load_clarifications(ctx)
    found = False
    for it in doc.get("items") or []:
        if not isinstance(it, dict) or str(it.get("id")) != issue_id:
            continue
        it["status"] = "auto_fixed" if auto_applied is not None else "resolved"
        it["resolved_at"] = _now_iso()
        if chosen is not None:
            it["chosen"] = chosen
        if auto_applied is not None:
            it["auto_applied"] = auto_applied
        found = True
        break
    if found:
        save_clarifications(ctx, doc)
    return found


def clear_resolved_for_stage(ctx: Any, stage_key: str) -> None:
    doc = load_clarifications(ctx)
    kept = [
        it
        for it in doc.get("items") or []
        if not (
            isinstance(it, dict)
            and str(it.get("stage_key") or "") == stage_key
            and it.get("status") in ("resolved", "dismissed", "auto_fixed")
        )
    ]
    doc["items"] = kept
    save_clarifications(ctx, doc)
