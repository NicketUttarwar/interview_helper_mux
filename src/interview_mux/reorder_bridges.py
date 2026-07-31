"""Detect master-adjacent pairs that are not source-adjacent (need VO glue)."""

from __future__ import annotations

from typing import Any


def _seg_times(
    segments_by_id: dict[str, dict[str, Any]], sid: str
) -> tuple[int, int] | None:
    seg = segments_by_id.get(sid)
    if not isinstance(seg, dict):
        return None
    try:
        start = int(seg.get("start_ms") or seg.get("source_start_ms") or 0)
        end = int(seg.get("end_ms") or seg.get("source_end_ms") or start)
    except (TypeError, ValueError):
        return None
    return start, end


def _same_split_family(a: str, b: str) -> bool:
    """Letter-suffixed children of the same parent, e.g. seg_001a / seg_001b."""
    import re

    m1 = re.match(r"^(seg_\d+)([a-z]+)?$", a)
    m2 = re.match(r"^(seg_\d+)([a-z]+)?$", b)
    if not m1 or not m2:
        return False
    return m1.group(1) == m2.group(1) and bool(m1.group(2) or m2.group(2))


def build_reorder_bridges(
    ordered: list[str],
    segments_by_id: dict[str, dict[str, Any]],
    *,
    contiguous_gap_ms: int = 1500,
    chapter_ends: set[str] | None = None,
) -> dict[str, Any]:
    """Emit pairs where consecutive air order is a source jump or split sibling."""
    chapter_ends = chapter_ends or set()
    pairs: list[dict[str, Any]] = []
    ids = [str(s) for s in ordered if s]
    for i in range(len(ids) - 1):
        a, b = ids[i], ids[i + 1]
        ta = _seg_times(segments_by_id, a)
        tb = _seg_times(segments_by_id, b)
        kind = "reorder"
        source_gap_ms = None
        if _same_split_family(a, b):
            kind = "split_sibling"
            if ta and tb:
                source_gap_ms = abs(tb[0] - ta[1])
                # Contiguous split children usually need no bridge
                if source_gap_ms <= contiguous_gap_ms:
                    continue
        elif ta and tb:
            source_gap_ms = tb[0] - ta[1]
            # Forward contiguous in source → natural; skip
            if 0 <= source_gap_ms <= contiguous_gap_ms:
                continue
            if source_gap_ms < 0:
                kind = "reorder"
            else:
                kind = "reorder"
        if a in chapter_ends:
            kind = "chapter_jump"
        pairs.append(
            {
                "after_id": a,
                "before_id": b,
                "after_segment_id": a,
                "before_segment_id": b,
                "kind": kind,
                "source_gap_ms": source_gap_ms,
            }
        )
    return {"version": 1, "pairs": pairs, "count": len(pairs)}
