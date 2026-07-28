"""N-way vernacular sanitize / sub-segmentation from protected zones."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _child_suffix(i: int) -> str:
    """0 -> a, 25 -> z, 26 -> aa, ..."""
    if i < 26:
        return chr(ord("a") + i)
    return _child_suffix(i // 26 - 1) + chr(ord("a") + (i % 26))


def _overlap(a0: int, a1: int, b0: int, b1: int) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def _merge_cuts(cuts: list[int], *, min_child_ms: int) -> list[int]:
    if not cuts:
        return []
    cuts = sorted(set(cuts))
    out = [cuts[0]]
    for c in cuts[1:]:
        if c - out[-1] < min_child_ms:
            continue
        out.append(c)
    return out


def _intervals_from_spans(
    parent_start: int,
    parent_end: int,
    spans: list[dict[str, Any]],
    *,
    min_child_ms: int,
) -> list[tuple[int, int, bool]]:
    """Return ordered (start, end, is_special) covering parent fully."""
    specials: list[tuple[int, int]] = []
    for sp in spans:
        try:
            a = max(parent_start, int(sp.get("start_ms") or 0))
            b = min(parent_end, int(sp.get("end_ms") or 0))
        except (TypeError, ValueError):
            continue
        if b - a >= max(50, min_child_ms // 4):
            specials.append((a, b))
    specials.sort()
    # merge overlapping specials
    merged: list[tuple[int, int]] = []
    for a, b in specials:
        if not merged or a > merged[-1][1]:
            merged.append((a, b))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))

    cuts = [parent_start, parent_end]
    for a, b in merged:
        cuts.extend([a, b])
    cuts = _merge_cuts(cuts, min_child_ms=min_child_ms)
    if parent_start not in cuts:
        cuts = [parent_start] + cuts
    if parent_end not in cuts:
        cuts = cuts + [parent_end]
    cuts = sorted(set(cuts))

    children: list[tuple[int, int, bool]] = []
    for i in range(len(cuts) - 1):
        a, b = cuts[i], cuts[i + 1]
        if b <= a:
            continue
        mid = (a + b) // 2
        is_special = any(sa <= mid < sb for sa, sb in merged)
        # also if majority overlap
        if not is_special:
            for sa, sb in merged:
                if _overlap(a, b, sa, sb) >= (b - a) * 0.5:
                    is_special = True
                    break
        children.append((a, b, is_special))
    if not children:
        children = [(parent_start, parent_end, bool(merged))]
    return children


def sanitize_manifest_with_zones(
    manifest: dict[str, Any],
    zones: dict[str, Any],
    *,
    min_child_ms: int = 800,
) -> dict[str, Any]:
    """
    Split parent segments that intersect vernacular zones into N children.

    Returns {manifest, resplit_report, must_keep_segment_ids}.
    """
    segs = [s for s in (manifest.get("segments") or []) if isinstance(s, dict)]
    zone_list = [z for z in (zones.get("zones") or []) if isinstance(z, dict)]
    new_segs: list[dict[str, Any]] = []
    report_rows: list[dict[str, Any]] = []
    must_keep: list[str] = []
    used_ids: set[str] = set()

    def _alloc_id(base: str, i: int) -> str:
        # base seg_014 -> seg_014a
        sid = f"{base}{_child_suffix(i)}"
        n = 0
        while sid in used_ids:
            n += 1
            sid = f"{base}{_child_suffix(i + n)}"
        used_ids.add(sid)
        return sid

    for seg in segs:
        parent_id = str(seg.get("segment_id") or seg.get("id") or "")
        try:
            ps = int(seg.get("start_ms") or 0)
            pe = int(seg.get("end_ms") or 0)
        except (TypeError, ValueError):
            new_segs.append(seg)
            if parent_id:
                used_ids.add(parent_id)
            continue

        hit_zones = [
            z
            for z in zone_list
            if _overlap(ps, pe, int(z.get("start_ms") or 0), int(z.get("end_ms") or 0)) > 0
        ]
        if not hit_zones:
            new_segs.append(seg)
            if parent_id:
                used_ids.add(parent_id)
            continue

        spans: list[dict[str, Any]] = []
        keywords: list[str] = []
        for z in hit_zones:
            spans.extend(z.get("spans") or [{"start_ms": z.get("start_ms"), "end_ms": z.get("end_ms")}])
            keywords.extend(str(k) for k in (z.get("keywords") or []))

        intervals = _intervals_from_spans(ps, pe, spans, min_child_ms=min_child_ms)
        # If only one interval and not special, keep parent
        if len(intervals) == 1 and not intervals[0][2]:
            tagged = dict(seg)
            tagged["audio_tags"] = dict(tagged.get("audio_tags") or {})
            tagged["audio_tags"]["near_vernacular_zone"] = True
            new_segs.append(tagged)
            if parent_id:
                used_ids.add(parent_id)
            continue

        children_meta: list[dict[str, Any]] = []
        base = parent_id or "seg_x"
        for i, (a, b, special) in enumerate(intervals):
            cid = _alloc_id(base, i)
            child = dict(seg)
            child["segment_id"] = cid
            child["start_ms"] = a
            child["end_ms"] = b
            child["duration_ms"] = max(0, b - a)
            child["parent_segment_id"] = parent_id
            # crude text slice by proportion if no word timings on segment
            text = str(seg.get("text") or "")
            if text and pe > ps:
                # keep full text on special/primary proportionally marked
                child["text"] = text if special else text
                child["text_pre_sanitize"] = text
            tags = dict(child.get("audio_tags") or {})
            tags["is_special"] = special
            if special:
                tags["vernacular"] = True
                tags["keywords"] = sorted(set(keywords))[:12]
                child["retention"] = "must_keep"
                must_keep.append(cid)
            child["audio_tags"] = tags
            new_segs.append(child)
            children_meta.append(
                {
                    "segment_id": cid,
                    "start_ms": a,
                    "end_ms": b,
                    "is_special": special,
                }
            )

        pattern = "|".join("SW" if c["is_special"] else "EN" for c in children_meta)
        report_rows.append(
            {
                "parent": parent_id,
                "children": children_meta,
                "pattern": pattern,
                "zone_ids": [z.get("zone_id") for z in hit_zones],
            }
        )

    out_manifest = dict(manifest)
    out_manifest["segments"] = new_segs
    report = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": report_rows,
        "must_keep_segment_ids": must_keep,
    }
    return {
        "manifest": out_manifest,
        "resplit_report": report,
        "must_keep_segment_ids": must_keep,
    }
