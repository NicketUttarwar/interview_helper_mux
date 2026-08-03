"""Build Podcasting 2.0 timed chapters JSON from selection + master EDL timeline."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

CHAPTERS_VERSION = "1.2.0"


def _speech_timeline_lookup(ctx: RunContext) -> dict[str, float]:
    """Map segment_id → start seconds on the master/EDL timeline."""
    if not ctx.artifact_exists("master/edl.json"):
        return {}
    edl = ctx.read_json("master/edl.json") or {}
    out: dict[str, float] = {}
    for clip in edl.get("clips") or []:
        if not isinstance(clip, dict):
            continue
        if clip.get("type") != "speech":
            continue
        sid = str(clip.get("segment_id") or "").strip()
        if not sid:
            continue
        start_ms = clip.get("timeline_start_ms")
        if start_ms is None:
            continue
        out[sid] = float(start_ms) / 1000.0
    return out


def _chapter_anchor_ids(chapter: dict[str, Any]) -> list[str]:
    keys = (
        "anchor_segment_id",
        "opens_with_segment_id",
        "suggested_open_segment_id",
        "open_segment_id",
    )
    out: list[str] = []
    for key in keys:
        val = chapter.get(key)
        if val:
            out.append(str(val).strip())
    for sid in chapter.get("segment_ids") or []:
        if sid:
            out.append(str(sid).strip())
    # preserve order, unique
    seen: set[str] = set()
    uniq: list[str] = []
    for sid in out:
        if sid and sid not in seen:
            seen.add(sid)
            uniq.append(sid)
    return uniq


def _chapter_title(chapter: dict[str, Any], *, index: int) -> str:
    for key in ("title", "chapter_title", "label", "name"):
        val = chapter.get(key)
        if val:
            return str(val).strip()[:200]
    return f"Chapter {index + 1}"


def build_timed_chapters(ctx: RunContext) -> dict[str, Any]:
    """Return Podcasting 2.0 chapters document (always valid; may be empty)."""
    lookup = _speech_timeline_lookup(ctx)
    raw_chapters: list[dict[str, Any]] = []

    if ctx.artifact_exists("master/selection.json"):
        sel = ctx.read_json("master/selection.json") or {}
        for ch in sel.get("chapters") or []:
            if isinstance(ch, dict):
                raw_chapters.append(ch)

    if not raw_chapters and ctx.artifact_exists("master/narrative_plan.json"):
        plan = ctx.read_json("master/narrative_plan.json") or {}
        for ch in plan.get("chapters") or []:
            if isinstance(ch, dict):
                raw_chapters.append(ch)

    timed: list[dict[str, Any]] = []
    used_starts: set[float] = set()
    for i, ch in enumerate(raw_chapters):
        start: float | None = None
        for sid in _chapter_anchor_ids(ch):
            if sid in lookup:
                start = lookup[sid]
                break
        if start is None and ch.get("timeline_start_ms") is not None:
            try:
                start = float(ch["timeline_start_ms"]) / 1000.0
            except (TypeError, ValueError):
                start = None
        if start is None and ch.get("startTime") is not None:
            try:
                start = float(ch["startTime"])
            except (TypeError, ValueError):
                start = None
        if start is None:
            continue
        # Round lightly for stable JSON; skip exact duplicate starts
        start_r = round(float(start), 3)
        if start_r in used_starts:
            continue
        used_starts.add(start_r)
        timed.append({"startTime": start_r, "title": _chapter_title(ch, index=i)})

    timed.sort(key=lambda row: float(row["startTime"]))
    # Podcasting 2.0: first chapter should start at 0 when any chapters exist
    if timed and float(timed[0]["startTime"]) > 0:
        timed.insert(0, {"startTime": 0, "title": str(timed[0]["title"])})

    return {"version": CHAPTERS_VERSION, "chapters": timed}
