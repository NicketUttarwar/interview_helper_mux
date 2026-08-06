"""Stable content hash for air-order authority (selection ↔ EDL lock)."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def ordered_segment_ids_hash(ordered: list[Any] | None) -> str:
    """Return a short sha256 of the ordered segment id list."""
    ids = [str(s) for s in (ordered or []) if s]
    payload = json.dumps(ids, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def stamp_order_hash(doc: dict[str, Any], *, ordered_key: str = "ordered_segment_ids") -> dict[str, Any]:
    """Return a copy of doc with ``order_content_hash`` set from ordered ids."""
    out = dict(doc)
    out["order_content_hash"] = ordered_segment_ids_hash(out.get(ordered_key) or [])
    return out


def order_hashes_match(
    selection: dict[str, Any] | None,
    edl: dict[str, Any] | None,
) -> bool:
    """True when selection and EDL agree on air order (hash or list equality)."""
    if not isinstance(selection, dict) or not isinstance(edl, dict):
        return False
    sel_ids = [str(s) for s in (selection.get("ordered_segment_ids") or []) if s]
    edl_ids = [str(s) for s in (edl.get("ordered_segment_ids") or []) if s]
    # Air-order list equality is authoritative. Recompute hashes so a stale
    # order_content_hash field cannot false-fail commitment checks.
    if sel_ids != edl_ids:
        return False
    return ordered_segment_ids_hash(sel_ids) == ordered_segment_ids_hash(edl_ids)


def sync_selection_order_to_edl(selection: dict[str, Any], edl: dict[str, Any]) -> dict[str, Any]:
    """Return selection copy whose ordered_segment_ids match EDL air order."""
    edl_ids = [str(s) for s in (edl.get("ordered_segment_ids") or []) if s]
    out = dict(selection) if isinstance(selection, dict) else {"version": 1}
    prev = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    dropped = [s for s in prev if s not in set(edl_ids)]
    if dropped:
        excl_list = list(out.get("excluded_segment_ids") or [])
        existing = {
            (e if isinstance(e, str) else str((e or {}).get("segment_id") or ""))
            for e in excl_list
        }
        for sid in dropped:
            if sid in existing:
                continue
            excl_list.append(
                {"segment_id": sid, "reason": "sync_selection_order_to_edl"}
            )
        out["excluded_segment_ids"] = excl_list
    out["ordered_segment_ids"] = list(edl_ids)
    return stamp_order_hash(out)
