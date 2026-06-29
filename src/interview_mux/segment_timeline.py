"""Shared segment timeline validation and normalization."""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config


def segment_timeline_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis = (cfg or merged_config()).get("analysis") or {}
    defaults = {
        "allow_overlap_ms": 0,
        "require_speaker_id": True,
        "sort_on_write": True,
    }
    raw = analysis.get("segment_timeline") or {}
    return {**defaults, **raw}


def sort_segments_by_start_ms(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable sort by start_ms; tie-break by segment_id."""

    def _key(row: dict[str, Any]) -> tuple[int, str]:
        start = row.get("start_ms")
        if start is None:
            return (2**31 - 1, str(row.get("segment_id") or ""))
        return (int(start), str(row.get("segment_id") or ""))

    return sorted([r for r in rows if isinstance(r, dict)], key=_key)


def validate_timeline_monotonic(
    rows: list[dict[str, Any]],
    *,
    allow_overlap_ms: int = 0,
) -> list[str]:
    """Return errors for non-monotonic or overlapping timeline (sorted first)."""
    errors: list[str] = []
    sorted_rows = sort_segments_by_start_ms(rows)
    prev_end: int | None = None
    for row in sorted_rows:
        seg_id = str(row.get("segment_id") or "?")
        if row.get("start_ms") is None:
            errors.append(f"missing start_ms at {seg_id}")
            continue
        if row.get("end_ms") is None:
            errors.append(f"missing end_ms at {seg_id}")
            continue
        start = int(row["start_ms"])
        end = int(row["end_ms"])
        if end <= start:
            errors.append(f"zero-length segment at {seg_id}")
            continue
        if prev_end is not None and start < prev_end - allow_overlap_ms:
            errors.append(f"manifest times not monotonic at {seg_id}")
        prev_end = max(prev_end or 0, end)
    return errors


def validate_boundary_rows(
    rows: list[dict[str, Any]],
    *,
    require_speaker_id: bool = True,
    allow_overlap_ms: int = 0,
) -> list[str]:
    """Validate boundary segment rows."""
    errors: list[str] = []
    seen_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        seg_id = str(row.get("segment_id") or "")
        if not seg_id:
            errors.append("boundary missing segment_id")
            continue
        if seg_id in seen_ids:
            errors.append(f"duplicate segment_id {seg_id}")
        seen_ids.add(seg_id)
        if row.get("start_ms") is None or row.get("end_ms") is None:
            errors.append(f"boundary {seg_id} missing start_ms or end_ms")
            continue
        start = int(row["start_ms"])
        end = int(row["end_ms"])
        if end <= start:
            errors.append(f"zero-length boundary {seg_id}")
        if require_speaker_id and not row.get("speaker_id"):
            errors.append(f"boundary {seg_id} missing speaker_id")
    errors.extend(
        validate_timeline_monotonic(rows, allow_overlap_ms=allow_overlap_ms)
    )
    return errors


def normalize_boundary_document(
    doc: dict[str, Any],
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Sort boundaries and return a copy."""
    if not isinstance(doc, dict):
        return doc
    st_cfg = segment_timeline_cfg(cfg)
    boundaries = doc.get("boundaries") or []
    if not isinstance(boundaries, list):
        return doc
    sorted_b = sort_segments_by_start_ms([b for b in boundaries if isinstance(b, dict)])
    if not st_cfg.get("sort_on_write", True):
        return {**doc, "boundaries": boundaries}
    return {**doc, "boundaries": sorted_b}


def boundary_by_id(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    boundaries = doc.get("boundaries") or [] if isinstance(doc, dict) else []
    return {
        str(b["segment_id"]): b
        for b in boundaries
        if isinstance(b, dict) and b.get("segment_id")
    }


def normalize_manifest_document(
    doc: dict[str, Any],
    boundary_doc: dict[str, Any] | None,
    *,
    cfg: dict[str, Any] | None = None,
    overwrite_times: bool = True,
) -> dict[str, Any]:
    """Sort manifest segments; optionally overwrite times from boundaries."""
    if not isinstance(doc, dict):
        return doc
    st_cfg = segment_timeline_cfg(cfg)
    segs = doc.get("segments") or []
    if not isinstance(segs, list):
        return doc
    bmap = boundary_by_id(boundary_doc) if boundary_doc else {}
    hydrated: list[dict[str, Any]] = []
    for seg in segs:
        if not isinstance(seg, dict):
            continue
        out = dict(seg)
        sid = str(out.get("segment_id") or "")
        boundary = bmap.get(sid) if sid else None
        if boundary and overwrite_times:
            if boundary.get("start_ms") is not None:
                out["start_ms"] = int(boundary["start_ms"])
            if boundary.get("end_ms") is not None:
                out["end_ms"] = int(boundary["end_ms"])
            if not out.get("speaker_id") and boundary.get("speaker_id"):
                out["speaker_id"] = str(boundary["speaker_id"])
        hydrated.append(out)
    if st_cfg.get("sort_on_write", True):
        hydrated = sort_segments_by_start_ms(hydrated)
    return {**doc, "segments": hydrated}
