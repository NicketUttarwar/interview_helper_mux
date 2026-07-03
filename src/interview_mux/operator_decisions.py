"""Persisted operator decision queue for Stage Decision Wizard."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

DecisionKind = Literal["issue_choice", "propagation", "upstream_rerun", "acknowledge_warning"]

_STORE_PATH = "understanding/operator_decisions.json"


@dataclass
class DecisionOption:
    label: str
    value: Any
    confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "value": self.value,
            **({"confidence": self.confidence} if self.confidence is not None else {}),
        }


@dataclass
class OperatorDecision:
    id: str
    kind: DecisionKind
    headline: str
    detail: str
    context: dict[str, Any] = field(default_factory=dict)
    options: list[DecisionOption] = field(default_factory=list)
    recommended: Any | None = None
    status: str = "open"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "headline": self.headline,
            "detail": self.detail,
            "context": self.context,
            "options": [o.to_dict() for o in self.options],
            "recommended": self.recommended,
            "status": self.status,
        }


def _load_doc(ctx: Any) -> dict[str, Any]:
    if not ctx.artifact_exists(_STORE_PATH):
        return {"by_stage": {}}
    raw = ctx.read_json(_STORE_PATH)
    return raw if isinstance(raw, dict) else {"by_stage": {}}


def _decisions_staging_overlay(ctx: Any, stage_key: str | None = None) -> str | None:
    """Stage whose pending write root holds operator_decisions during write approval."""
    from interview_mux.write_staging import has_pending_writes, pending_stage_for_path

    overlay = pending_stage_for_path(ctx, _STORE_PATH)
    if overlay:
        return overlay
    if stage_key and has_pending_writes(ctx, stage_key):
        return stage_key
    return None


def _write_doc(ctx: Any, doc: dict[str, Any], *, stage_key: str | None = None) -> None:
    """Persist decisions to committed disk and mirror into active staging when present."""
    from interview_mux.file_store import write_json as fs_write_json
    from interview_mux.write_staging import staged_path

    committed = ctx.final_path(*_STORE_PATH.split("/"))
    committed.parent.mkdir(parents=True, exist_ok=True)
    fs_write_json(committed, doc)

    overlay = _decisions_staging_overlay(ctx, stage_key)
    if overlay:
        staged = staged_path(ctx, _STORE_PATH, stage_id=overlay)
        staged.parent.mkdir(parents=True, exist_ok=True)
        fs_write_json(staged, doc)


def _stage_bucket(doc: dict[str, Any], stage_key: str) -> dict[str, Any]:
    by_stage = doc.setdefault("by_stage", {})
    bucket = by_stage.get(stage_key)
    if not isinstance(bucket, dict):
        bucket = {"decisions": [], "cursor": 0, "warnings": [], "updated_at": None}
        by_stage[stage_key] = bucket
    return bucket


def new_decision_id() -> str:
    return f"dec_{uuid.uuid4().hex[:12]}"


def set_stage_decisions(
    ctx: Any,
    stage_key: str,
    decisions: list[OperatorDecision],
    *,
    warnings: list[str] | None = None,
) -> None:
    doc = _load_doc(ctx)
    bucket = _stage_bucket(doc, stage_key)
    bucket["decisions"] = [d.to_dict() for d in decisions if d.status == "open"]
    bucket["cursor"] = 0
    bucket["warnings"] = list(warnings or [])
    bucket["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_doc(ctx, doc, stage_key=stage_key)


def append_stage_decisions(ctx: Any, stage_key: str, decisions: list[OperatorDecision]) -> None:
    if not decisions:
        return
    doc = _load_doc(ctx)
    bucket = _stage_bucket(doc, stage_key)
    existing_ids = {str(d.get("id")) for d in bucket.get("decisions") or [] if isinstance(d, dict)}
    for dec in decisions:
        if dec.id in existing_ids:
            continue
        rows = bucket.setdefault("decisions", [])
        if isinstance(rows, list):
            rows.append(dec.to_dict())
    bucket["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_doc(ctx, doc, stage_key=stage_key)


def clear_stage_decisions(ctx: Any, stage_key: str) -> None:
    doc = _load_doc(ctx)
    by_stage = doc.get("by_stage")
    if isinstance(by_stage, dict) and stage_key in by_stage:
        del by_stage[stage_key]
        _write_doc(ctx, doc, stage_key=stage_key)


def pending_decision_count(ctx: Any, stage_key: str) -> int:
    return len(list_open_decisions(ctx, stage_key))


def list_open_decisions(ctx: Any, stage_key: str) -> list[dict[str, Any]]:
    doc = _load_doc(ctx)
    bucket = (doc.get("by_stage") or {}).get(stage_key) or {}
    rows = bucket.get("decisions") or []
    return [r for r in rows if isinstance(r, dict) and str(r.get("status") or "open") == "open"]


def current_decision(ctx: Any, stage_key: str) -> dict[str, Any] | None:
    open_rows = list_open_decisions(ctx, stage_key)
    if not open_rows:
        return None
    doc = _load_doc(ctx)
    bucket = (doc.get("by_stage") or {}).get(stage_key) or {}
    cursor = int(bucket.get("cursor") or 0)
    if cursor >= len(open_rows):
        return open_rows[0]
    return open_rows[cursor]


def mark_decision_resolved(ctx: Any, stage_key: str, decision_id: str) -> None:
    doc = _load_doc(ctx)
    bucket = _stage_bucket(doc, stage_key)
    rows = bucket.get("decisions") or []
    for row in rows:
        if isinstance(row, dict) and str(row.get("id")) == decision_id:
            row["status"] = "resolved"
    open_left = [r for r in rows if isinstance(r, dict) and str(r.get("status") or "open") == "open"]
    bucket["cursor"] = 0
    if not open_left:
        bucket["decisions"] = []
    bucket["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_doc(ctx, doc, stage_key=stage_key)


def stage_decisions_summary(ctx: Any, stage_key: str) -> dict[str, Any]:
    open_rows = list_open_decisions(ctx, stage_key)
    doc = _load_doc(ctx)
    bucket = (doc.get("by_stage") or {}).get(stage_key) or {}
    current = current_decision(ctx, stage_key)
    return {
        "stage_key": stage_key,
        "open_count": len(open_rows),
        "cursor": int(bucket.get("cursor") or 0),
        "current": current,
        "decisions": open_rows,
        "warnings": list(bucket.get("warnings") or [])[:6],
        "ready_for_review": len(open_rows) == 0,
    }
