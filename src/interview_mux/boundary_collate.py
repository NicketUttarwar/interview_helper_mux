"""Deterministic boundary shard merge and timeline normalization."""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config
from interview_mux.segment_timeline import sort_segments_by_start_ms


def boundary_collate_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis = (cfg or merged_config()).get("analysis") or {}
    itr = analysis.get("artifact_issue_triage") or {}
    return {
        "snap_tolerance_ms": int(itr.get("boundary_snap_tolerance_ms") or 500),
        "merge_threshold_ms": int(itr.get("boundary_merge_threshold_ms") or 500),
        "coarse_partition_min_children": int(itr.get("boundary_coarse_partition_min_children") or 2),
        "coarse_coverage_ratio": float(itr.get("boundary_coarse_coverage_ratio") or 0.85),
    }


def _row_span(row: dict[str, Any]) -> int:
    start = row.get("start_ms")
    end = row.get("end_ms")
    if start is None or end is None:
        return 0
    return max(0, int(end) - int(start))


def _interval_union(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not intervals:
        return []
    merged: list[tuple[int, int]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            prev_s, prev_e = merged[-1]
            merged[-1] = (prev_s, max(prev_e, end))
    return merged


def _coverage_ratio(parent_start: int, parent_end: int, child_intervals: list[tuple[int, int]]) -> float:
    parent_span = parent_end - parent_start
    if parent_span <= 0:
        return 0.0
    clipped: list[tuple[int, int]] = []
    for start, end in child_intervals:
        clip_start = max(start, parent_start)
        clip_end = min(end, parent_end)
        if clip_end > clip_start:
            clipped.append((clip_start, clip_end))
    covered = sum(end - start for start, end in _interval_union(clipped))
    return covered / parent_span


def _snap_bucket(value: int, tolerance: int) -> int:
    if tolerance <= 0:
        return value
    return int(round(value / tolerance) * tolerance)


def _rows_equivalent_within_tolerance(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    snap_tolerance_ms: int,
) -> bool:
    if left.get("start_ms") is None or left.get("end_ms") is None:
        return False
    if right.get("start_ms") is None or right.get("end_ms") is None:
        return False
    ls, le = int(left["start_ms"]), int(left["end_ms"])
    rs, re = int(right["start_ms"]), int(right["end_ms"])
    return (
        _snap_bucket(ls, snap_tolerance_ms) == _snap_bucket(rs, snap_tolerance_ms)
        and _snap_bucket(le, snap_tolerance_ms) == _snap_bucket(re, snap_tolerance_ms)
    )


def _prefer_boundary_row(candidate: dict[str, Any], incumbent: dict[str, Any]) -> dict[str, Any]:
    cand_span = _row_span(candidate)
    inc_span = _row_span(incumbent)
    if cand_span and inc_span:
        if cand_span < inc_span:
            return candidate
        if cand_span > inc_span:
            return incumbent
    if candidate.get("proposed_split_reason") and not incumbent.get("proposed_split_reason"):
        return candidate
    return incumbent


def _dedupe_rows_within_tolerance(
    rows: list[dict[str, Any]],
    *,
    snap_tolerance_ms: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    applied: list[dict[str, Any]] = []
    for row in sort_segments_by_start_ms(rows):
        duplicate_idx = None
        for idx, existing in enumerate(kept):
            if _rows_equivalent_within_tolerance(row, existing, snap_tolerance_ms=snap_tolerance_ms):
                duplicate_idx = idx
                break
        if duplicate_idx is None:
            kept.append(dict(row))
            continue
        preferred = _prefer_boundary_row(row, kept[duplicate_idx])
        if preferred is row:
            kept[duplicate_idx] = dict(row)
        applied.append(
            {
                "action": "dedupe_snap_tolerance",
                "segment_id": row.get("segment_id"),
                "start_ms": row.get("start_ms"),
                "end_ms": row.get("end_ms"),
            }
        )
    return kept, applied


def _drop_coarse_dominated_rows(
    rows: list[dict[str, Any]],
    *,
    snap_tolerance_ms: int,
    coarse_partition_min_children: int,
    coarse_coverage_ratio: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    applied: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for row in rows:
        if row.get("start_ms") is None or row.get("end_ms") is None:
            continue
        start = int(row["start_ms"])
        end = int(row["end_ms"])
        span = end - start
        if span <= 0:
            continue
        children: list[tuple[int, int]] = []
        for other in rows:
            if other is row:
                continue
            if other.get("start_ms") is None or other.get("end_ms") is None:
                continue
            other_start = int(other["start_ms"])
            other_end = int(other["end_ms"])
            other_span = other_end - other_start
            if other_span <= 0 or other_span >= span:
                continue
            if other_start >= start - snap_tolerance_ms and other_end <= end + snap_tolerance_ms:
                children.append((other_start, other_end))
        if len(children) < coarse_partition_min_children:
            kept.append(row)
            continue
        if _coverage_ratio(start, end, children) >= coarse_coverage_ratio:
            applied.append(
                {
                    "action": "drop_coarse_dominated",
                    "segment_id": row.get("segment_id"),
                    "start_ms": start,
                    "end_ms": end,
                }
            )
            continue
        kept.append(row)
    return kept, applied


def _snap_monotonic_timeline(
    rows: list[dict[str, Any]],
    *,
    snap_tolerance_ms: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    applied: list[dict[str, Any]] = []
    result: list[dict[str, Any]] = []
    prev_end = 0
    for row in sort_segments_by_start_ms(rows):
        if row.get("start_ms") is None or row.get("end_ms") is None:
            continue
        start = int(row["start_ms"])
        end = int(row["end_ms"])
        if end <= start:
            applied.append({"action": "drop_zero_length", "segment_id": row.get("segment_id")})
            continue
        if result:
            if abs(start - prev_end) <= snap_tolerance_ms:
                if start != prev_end:
                    applied.append(
                        {
                            "action": "snap_start_to_prev_end",
                            "segment_id": row.get("segment_id"),
                            "from_ms": start,
                            "to_ms": prev_end,
                        }
                    )
                start = prev_end
            elif start < prev_end:
                applied.append(
                    {
                        "action": "trim_overlap_to_prev_end",
                        "segment_id": row.get("segment_id"),
                        "from_ms": start,
                        "to_ms": prev_end,
                    }
                )
                start = prev_end
        if end <= start:
            applied.append({"action": "drop_zero_length_after_snap", "segment_id": row.get("segment_id")})
            continue
        normalized = dict(row)
        normalized["start_ms"] = start
        normalized["end_ms"] = end
        result.append(normalized)
        prev_end = end
    return result, applied


def _merge_micro_boundaries(
    rows: list[dict[str, Any]],
    *,
    merge_threshold_ms: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    applied: list[dict[str, Any]] = []
    if not rows:
        return [], applied
    merged: list[dict[str, Any]] = [dict(rows[0])]
    for row in rows[1:]:
        span = _row_span(row)
        if span < merge_threshold_ms and merged:
            prev = merged[-1]
            prev["end_ms"] = max(int(prev.get("end_ms", 0)), int(row.get("end_ms", 0)))
            applied.append({"action": "merge_micro_boundary", "segment_id": row.get("segment_id")})
            continue
        merged.append(dict(row))
    return merged, applied


def _renumber_segment_ids(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    renumbered: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        normalized = dict(row)
        normalized["segment_id"] = f"seg_{idx:03d}"
        renumbered.append(normalized)
    return renumbered


def collect_boundary_rows(
    *,
    shard_outputs: list[dict[str, Any]] | None = None,
    collate_artifacts: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for shard in shard_outputs or []:
        env = shard.get("envelope") if isinstance(shard, dict) else None
        artifacts = env.get("artifacts") if isinstance(env, dict) else {}
        boundaries = artifacts.get("boundaries") if isinstance(artifacts, dict) else []
        if isinstance(boundaries, list):
            rows.extend(dict(row) for row in boundaries if isinstance(row, dict))
    if isinstance(collate_artifacts, dict):
        boundaries = collate_artifacts.get("boundaries") or []
        if isinstance(boundaries, list):
            rows.extend(dict(row) for row in boundaries if isinstance(row, dict))
    return rows


def normalize_boundary_timeline(
    rows: list[dict[str, Any]],
    *,
    cfg: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Force a monotonic boundary timeline, tolerating small timestamp drift."""
    settings = boundary_collate_cfg(cfg)
    snap_tol = int(settings["snap_tolerance_ms"])
    merge_threshold = int(settings["merge_threshold_ms"])
    min_children = int(settings["coarse_partition_min_children"])
    coverage_ratio = float(settings["coarse_coverage_ratio"])

    valid = [
        dict(row)
        for row in rows
        if isinstance(row, dict)
        and row.get("start_ms") is not None
        and row.get("end_ms") is not None
        and int(row["end_ms"]) > int(row["start_ms"])
    ]
    if not valid:
        return [], []

    applied: list[dict[str, Any]] = []
    deduped, dedupe_actions = _dedupe_rows_within_tolerance(valid, snap_tolerance_ms=snap_tol)
    applied.extend(dedupe_actions)

    filtered, dominated_actions = _drop_coarse_dominated_rows(
        deduped,
        snap_tolerance_ms=snap_tol,
        coarse_partition_min_children=min_children,
        coarse_coverage_ratio=coverage_ratio,
    )
    applied.extend(dominated_actions)

    snapped, snap_actions = _snap_monotonic_timeline(filtered, snap_tolerance_ms=snap_tol)
    applied.extend(snap_actions)

    merged, merge_actions = _merge_micro_boundaries(snapped, merge_threshold_ms=merge_threshold)
    applied.extend(merge_actions)

    return _renumber_segment_ids(merged), applied


def merge_shard_boundaries(
    shard_outputs: list[dict[str, Any]],
    *,
    collate_artifacts: dict[str, Any] | None = None,
    cfg: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Union shard (and optional collate) boundaries into one monotonic timeline."""
    rows = collect_boundary_rows(shard_outputs=shard_outputs, collate_artifacts=collate_artifacts)
    return normalize_boundary_timeline(rows, cfg=cfg)
