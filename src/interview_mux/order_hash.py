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
    if sel_ids != edl_ids:
        return False
    sel_h = str(selection.get("order_content_hash") or "") or ordered_segment_ids_hash(sel_ids)
    edl_h = str(edl.get("order_content_hash") or "") or ordered_segment_ids_hash(edl_ids)
    return sel_h == edl_h
