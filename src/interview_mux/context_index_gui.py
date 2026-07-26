"""GUI/API helpers for understanding/context_index.json volley memory."""

from __future__ import annotations

from typing import Any

from interview_mux.context_resolver import (
    append_volley_entry,
    invalidate_entry,
    load_context_index,
    new_entry_id,
    save_context_index,
    update_volley_entry,
)
from interview_mux.prompt_validation import validate_context_index
from interview_mux.run_context import RunContext


def get_context_index_summary(ctx: RunContext) -> dict[str, Any]:
    idx = load_context_index(ctx, write=False)
    entries = idx.get("volley_entries") or []
    by_kind: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for e in entries:
        k = str(e.get("kind") or "unknown")
        by_kind[k] = by_kind.get(k, 0) + 1
        s = str(e.get("status") or "active")
        by_status[s] = by_status.get(s, 0) + 1
    return {
        "index": idx,
        "stats": {
            "total": len(entries),
            "by_kind": by_kind,
            "by_status": by_status,
        },
    }


def create_volley_entry(ctx: RunContext, body: dict[str, Any]) -> dict[str, Any]:
    entry_id = append_volley_entry(
        ctx,
        {
            "entry_id": body.get("entry_id") or new_entry_id(),
            "kind": body.get("kind", "stage_conclusion"),
            "role": body.get("role", "assistant"),
            "content": body.get("content", ""),
            "source": body.get("source") or {"stage_key": "operator", "task_kind": "manual"},
            "tags": body.get("tags") or [],
            "scope": body.get("scope") or {},
            "operator_edited": True,
        },
        supersede_same_source=False,
    )
    idx = load_context_index(ctx, write=False)
    for e in idx.get("volley_entries") or []:
        if e.get("entry_id") == entry_id:
            return e
    return {"entry_id": entry_id}


def put_volley_entry(ctx: RunContext, entry_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    updated = update_volley_entry(ctx, entry_id, patch)
    if not updated:
        raise FileNotFoundError(f"volley entry not found: {entry_id}")
    _maybe_invalidate_downstream_acks(ctx, updated)
    return updated


def invalidate_volley_entry(ctx: RunContext, entry_id: str) -> dict[str, Any]:
    if not invalidate_entry(ctx, entry_id):
        raise FileNotFoundError(f"volley entry not found: {entry_id}")
    idx = load_context_index(ctx, write=False)
    for e in idx.get("volley_entries") or []:
        if e.get("entry_id") == entry_id:
            return e
    return {"entry_id": entry_id, "status": "invalidated"}


def rebuild_context_index(ctx: RunContext) -> dict[str, Any]:
    """v2: volley backfill removed — the index is now append-only from live stage runs."""
    return get_context_index_summary(ctx) | {"rebuild_stats": {}}


def save_full_context_index(ctx: RunContext, doc: dict[str, Any]) -> dict[str, Any]:
    errors = validate_context_index(doc)
    if errors:
        raise ValueError("; ".join(errors[:5]))
    save_context_index(ctx, doc)
    return doc


def _maybe_invalidate_downstream_acks(ctx: RunContext, entry: dict[str, Any]) -> None:
    """v2: handoff acks removed — no downstream invalidation."""
    return
