from __future__ import annotations

from typing import Any

from interview_mux.disfluency.config import restore_settings
from interview_mux.disfluency.extract import confirmed_events


def _events_in_range(events: list[dict[str, Any]], start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    inside: list[dict[str, Any]] = []
    for ev in events:
        es = int(ev.get("start_ms") or 0)
        ee = int(ev.get("end_ms") or es)
        if ee <= start_ms or es >= end_ms:
            continue
        inside.append(ev)
    return sorted(inside, key=lambda e: int(e.get("start_ms") or 0))


def _speech_already_contains(events: list[dict[str, Any]], seg_start: int, seg_end: int) -> bool:
    if not events:
        return False
    span = seg_end - seg_start
    if span <= 0:
        return False
    covered = 0
    for ev in events:
        es = max(seg_start, int(ev.get("start_ms") or 0))
        ee = min(seg_end, int(ev.get("end_ms") or es))
        covered += max(0, ee - es)
    return covered >= max(1, int(span * 0.85))


def split_speech_with_disfluencies(
    *,
    segment_id: str,
    seg_start_ms: int,
    seg_end_ms: int,
    events: list[dict[str, Any]],
    timeline_ms: int,
    settings: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    min_slice = int(settings.get("min_speech_slice_ms") or 200)
    clips: list[dict[str, Any]] = []
    cursor = timeline_ms
    seg_events = _events_in_range(events, seg_start_ms, seg_end_ms)

    if not seg_events or _speech_already_contains(seg_events, seg_start_ms, seg_end_ms):
        dur = seg_end_ms - seg_start_ms
        clips.append(
            {
                "type": "speech",
                "segment_id": segment_id,
                "source_start_ms": seg_start_ms,
                "source_end_ms": seg_end_ms,
                "timeline_start_ms": cursor,
                "duration_ms": dur,
            }
        )
        return clips, cursor + dur

    pos = seg_start_ms
    for ev in seg_events:
        es = max(seg_start_ms, int(ev.get("start_ms") or 0))
        ee = min(seg_end_ms, int(ev.get("end_ms") or es))
        if es > pos:
            speech_end = es
            speech_dur = speech_end - pos
            if speech_dur >= min_slice:
                clips.append(
                    {
                        "type": "speech",
                        "segment_id": segment_id,
                        "source_start_ms": pos,
                        "source_end_ms": speech_end,
                        "timeline_start_ms": cursor,
                        "duration_ms": speech_dur,
                    }
                )
                cursor += speech_dur
            pos = speech_end
        fill_dur = max(1, ee - max(pos, es))
        clips.append(
            {
                "type": "disfluency",
                "event_id": str(ev.get("event_id") or ""),
                "segment_id": segment_id,
                "source_path": ev.get("clip_path"),
                "source_start_ms": es,
                "source_end_ms": ee,
                "timeline_start_ms": cursor,
                "duration_ms": fill_dur,
                "text": str(ev.get("text") or ""),
            }
        )
        cursor += fill_dur
        pos = max(pos, ee)

    if seg_end_ms > pos:
        tail_dur = seg_end_ms - pos
        if tail_dur >= min_slice or not clips:
            clips.append(
                {
                    "type": "speech",
                    "segment_id": segment_id,
                    "source_start_ms": pos,
                    "source_end_ms": seg_end_ms,
                    "timeline_start_ms": cursor,
                    "duration_ms": tail_dur,
                }
            )
            cursor += tail_dur

    if not clips:
        dur = seg_end_ms - seg_start_ms
        clips.append(
            {
                "type": "speech",
                "segment_id": segment_id,
                "source_start_ms": seg_start_ms,
                "source_end_ms": seg_end_ms,
                "timeline_start_ms": timeline_ms,
                "duration_ms": dur,
            }
        )
        cursor = timeline_ms + dur
    return clips, cursor


def build_restore_plan(
    *,
    ordered_segment_ids: list[str],
    segments_by_id: dict[str, dict],
    disfluencies: dict[str, Any],
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg_settings = restore_settings()
    if settings:
        cfg_settings = {**cfg_settings, **settings}
    events = confirmed_events(disfluencies)
    pieces: list[dict[str, Any]] = []
    for sid in ordered_segment_ids:
        seg = segments_by_id.get(sid)
        if not seg:
            continue
        start_ms = int(seg.get("start_ms") or 0)
        end_ms = int(seg.get("end_ms") or start_ms)
        seg_events = _events_in_range(events, start_ms, end_ms)
        pieces.append(
            {
                "segment_id": sid,
                "segment_start_ms": start_ms,
                "segment_end_ms": end_ms,
                "event_ids": [str(e.get("event_id")) for e in seg_events],
                "restore_enabled": bool(seg_events) and not _speech_already_contains(seg_events, start_ms, end_ms),
            }
        )
    return {
        "schema_version": 1,
        "confirmed_event_count": len(events),
        "segment_pieces": pieces,
    }
