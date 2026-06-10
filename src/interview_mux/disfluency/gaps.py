from __future__ import annotations

from typing import Any


def build_gap_candidates(
    words: list[dict[str, Any]],
    *,
    gap_min_ms: int,
    gap_max_ms: int,
    pad_ms: int,
) -> list[dict[str, Any]]:
    if len(words) < 2:
        return []
    out: list[dict[str, Any]] = []
    for i in range(1, len(words)):
        prev_w = words[i - 1]
        cur_w = words[i]
        prev_end = int(prev_w.get("end_ms") or 0)
        cur_start = int(cur_w.get("start_ms") or 0)
        gap = cur_start - prev_end
        if gap < gap_min_ms or gap > gap_max_ms:
            continue
        speaker = str(
            prev_w.get("speaker_id")
            or prev_w.get("speaker_label")
            or cur_w.get("speaker_id")
            or cur_w.get("speaker_label")
            or ""
        )
        out.append(
            {
                "gap_index": i,
                "start_ms": max(0, prev_end - pad_ms),
                "end_ms": cur_start + pad_ms,
                "gap_ms": gap,
                "speaker_id": speaker,
            }
        )
    return out
