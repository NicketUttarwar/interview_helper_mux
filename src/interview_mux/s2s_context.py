"""Segment-adjacent context clips for S2S prosody (case 3)."""

from __future__ import annotations

from pathlib import Path

from interview_mux.run_context import RunContext
from interview_mux.s2s_runner import context_clip_for_line, load_speaker_ref, write_speaker_ref_sidecar

__all__ = [
    "context_clip_for_line",
    "load_speaker_ref",
    "write_speaker_ref_sidecar",
    "resolve_context_window_ms",
]


def resolve_context_window_ms(ctx: RunContext, line: dict) -> tuple[int, int] | None:
    """Return start/end ms for the context window used by S2S, if computable."""
    clip = context_clip_for_line(ctx, line)
    if clip is None:
        return None
    from interview_mux.config import merged_config

    block = merged_config().get("local_speech") or {}
    seg_id = str(line.get("targets_segment_id") or "")
    if not seg_id or not ctx.artifact_exists("segments/segments.json"):
        return None
    segments = ctx.read_json("segments/segments.json")
    seg = next(
        (s for s in (segments.get("segments") or []) if str(s.get("segment_id")) == seg_id),
        None,
    )
    if not isinstance(seg, dict):
        return None
    placement = str(line.get("placement") or "before").lower()
    anchor_ms = int(seg.get("end_ms") if placement == "after" else seg.get("start_ms") or 0)
    max_ms = int(block.get("context_clip_max_ms", 8000))
    start_ms = max(0, anchor_ms - max_ms // 2)
    end_ms = start_ms + max_ms
    return start_ms, end_ms
