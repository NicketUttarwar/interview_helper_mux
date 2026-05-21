from __future__ import annotations

from typing import Any


def chapter_metadata_for_segments(segments: list[dict[str, Any]], ordered_ids: list[str]) -> list[dict[str, Any]]:
    """Preset B: simple chapter titles from first words of each segment."""
    by_id = {s["segment_id"]: s for s in segments}
    chapters = []
    for i, sid in enumerate(ordered_ids):
        text = (by_id.get(sid, {}).get("text") or "").strip()
        title = " ".join(text.split()[:6]) or f"Chapter {i + 1}"
        chapters.append({"segment_id": sid, "chapter_index": i, "title": title})
    return chapters
