"""Keep transcript speech covered by the source segmentation across rewrites.

``segments/boundaries.json`` is the source map: boundary quality is measured
on it, and delivery refuses the run when it stops covering the tape. Several
stages rewrite it after boundary detection (connector fuse, resplit, the
chapter-close hitch, overlap repair). A rewrite that drops a row or narrows a
row to an on-air window takes speech out of the map, and nothing downstream
can put it back: re-running segmentation starts from the damaged file
(ISSUES 142, exec_007: nine minutes uncovered, every delivery stage refused).

``preserve_speech_coverage`` compares the incoming document with the one on
disk. Where the new map leaves real speech uncovered that the old map
covered, a row that still exists is widened back over it, or a dropped row is
restored clipped to the gap. The fresh map from boundary detection is the
model's own output and is not compared with anything, and the chapter-close
hitch's keeper map leaves editorial cuts out on purpose.
"""

from __future__ import annotations

from typing import Any

FRESH_MAP_WRITERS = frozenset({"boundary_detection"})
# The hitch writes its keeper map: editorial cuts are left out on purpose and
# the map it replaced is archived as its pre_keepers (ISSUES 143).
EDITORIAL_MAP_WRITERS = frozenset({"chapter_close_hitch"})
MIN_LOST_WORDS = 8
MIN_LOST_SPEECH_MS = 3000


def _span(row: dict[str, Any]) -> tuple[int, int] | None:
    try:
        start, end = int(row.get("start_ms")), int(row.get("end_ms"))
    except (TypeError, ValueError):
        return None
    return (start, end) if end > start else None


def _rows(doc: Any) -> list[dict[str, Any]]:
    if not isinstance(doc, dict):
        return []
    return [r for r in (doc.get("boundaries") or []) if isinstance(r, dict) and _span(r)]


def _words(ctx: Any) -> list[tuple[int, int]]:
    try:
        doc = ctx.read_json("transcript/full.json") if ctx.artifact_exists("transcript/full.json") else None
    except Exception:
        return []
    out: list[tuple[int, int]] = []
    for w in (doc.get("words") or []) if isinstance(doc, dict) else []:
        if not isinstance(w, dict):
            continue
        try:
            out.append((int(w["start_ms"]), int(w["end_ms"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _covered(mid: int, spans: list[tuple[int, int]]) -> bool:
    return any(a <= mid < b for a, b in spans)


def _lost_runs(
    words: list[tuple[int, int]],
    old: list[tuple[int, int]],
    new: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Contiguous stretches of speech the old map covered and the new one does not."""
    runs: list[tuple[int, int, int]] = []
    cur: list[int] | None = None
    for a, b in sorted(words):
        mid = (a + b) // 2
        lost = _covered(mid, old) and not _covered(mid, new)
        if lost:
            if cur is None:
                cur = [a, b, 1]
            else:
                cur[1], cur[2] = b, cur[2] + 1
        elif cur is not None and _covered(mid, new):
            runs.append((cur[0], cur[1], cur[2]))
            cur = None
    if cur is not None:
        runs.append((cur[0], cur[1], cur[2]))
    return [
        (a, b) for a, b, n in runs if n >= MIN_LOST_WORDS and (b - a) >= MIN_LOST_SPEECH_MS
    ]


def preserve_speech_coverage(
    ctx: Any, doc: dict[str, Any], *, writer: str
) -> dict[str, Any]:
    if str(writer or "").strip() in FRESH_MAP_WRITERS | EDITORIAL_MAP_WRITERS or not isinstance(doc, dict):
        return doc
    try:
        prior = ctx.read_json("segments/boundaries.json") if ctx.artifact_exists("segments/boundaries.json") else None
    except Exception:
        return doc
    old_rows, new_rows = _rows(prior), _rows(doc)
    if not old_rows or not new_rows:
        return doc
    words = _words(ctx)
    if not words:
        return doc
    old_spans = [_span(r) for r in old_rows]
    new_spans = [_span(r) for r in new_rows]
    lost = _lost_runs(words, old_spans, new_spans)  # type: ignore[arg-type]
    if not lost:
        return doc

    rows = [dict(r) for r in (doc.get("boundaries") or []) if isinstance(r, dict)]
    restored: list[dict[str, Any]] = []
    for run_start, run_end in lost:
        spans = [(_span(r), r) for r in rows if _span(r)]
        before = [(sp, r) for sp, r in spans if sp[1] <= run_start]
        after = [(sp, r) for sp, r in spans if sp[0] >= run_end]
        prev = max(before, key=lambda x: x[0][1]) if before else None
        nxt = min(after, key=lambda x: x[0][0]) if after else None
        gap_lo = prev[0][1] if prev else 0
        gap_hi = nxt[0][0] if nxt else run_end
        # Only a row that borders the gap may grow, and only inside the gap, so
        # order and non-overlap hold whatever the writer renumbered. Ids are not
        # matched across the rewrite: a resplit reuses them for other tape
        # (exec_009: matching by id widened seg_032 over eleven rows).
        covered_before = {
            str(o.get("segment_id") or "")
            for o in old_rows
            if (_span(o) or (0, 0))[1] > run_start and (_span(o) or (0, 0))[0] < run_end
        }
        pick = None
        if nxt and str(nxt[1].get("segment_id") or "") in covered_before:
            pick = ("start", nxt[1])
        elif prev and str(prev[1].get("segment_id") or "") in covered_before:
            pick = ("end", prev[1])
        elif prev:
            pick = ("end", prev[1])
        elif nxt:
            pick = ("start", nxt[1])
        if pick is None:
            continue
        side, row = pick
        if side == "start":
            row["start_ms"] = max(gap_lo, min(int(row["start_ms"]), run_start))
        else:
            later_starts = [
                sp[0] for sp, _row in spans if sp[0] > int(row.get("start_ms") or 0)
            ]
            cap = (min(later_starts) - 80) if later_starts else gap_hi
            proposed = min(cap, gap_hi, max(int(row["end_ms"]), run_end))
            if proposed > int(row.get("start_ms") or 0):
                row["end_ms"] = proposed
        restored.append(
            {
                "segment_id": row.get("segment_id"),
                "action": f"extended_{side}",
                "start_ms": row["start_ms"],
                "end_ms": row["end_ms"],
            }
        )
    if not restored:
        return doc
    rows.sort(key=lambda r: int(r.get("start_ms") or 0))
    out = dict(doc)
    out["boundaries"] = rows
    try:
        ctx.log(
            f"segments/boundaries.json: {writer or 'a writer'} would have left "
            f"{len(lost)} stretch(es) of speech uncovered; kept them in the source map",
            level="warning",
            stage=str(writer or "") or None,
            detail={
                "event": "boundary_speech_coverage_preserved",
                "lost_runs_ms": lost,
                "restored": restored[:20],
            },
        )
    except Exception:
        pass
    return out
