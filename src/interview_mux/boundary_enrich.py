"""Deterministic boundary enrichment for fine-grained segmentation."""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config
from interview_mux.segment_timeline_standard import segmentation_cfg


def _seg_cfg(cfg: dict[str, Any] | None) -> dict[str, Any]:
    if cfg is None:
        return segmentation_cfg()
    if isinstance(cfg.get("analysis"), dict):
        return segmentation_cfg(cfg)
    return {**segmentation_cfg(), **cfg}


def _words_from_transcript(transcript: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(transcript, dict):
        return []
    words = transcript.get("words") or []
    return [w for w in words if isinstance(w, dict) and w.get("start_ms") is not None and w.get("end_ms") is not None]


def _speaker_roles(speakers_doc: dict[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(speakers_doc, dict):
        return out
    for sp in speakers_doc.get("speakers") or []:
        if not isinstance(sp, dict):
            continue
        sid = str(sp.get("speaker_id") or sp.get("id") or "")
        if sid:
            out[sid] = str(sp.get("role") or "unknown")
    return out


def _words_in_span(words: list[dict[str, Any]], start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    return [
        w
        for w in words
        if int(w.get("start_ms", 0)) >= start_ms - 20
        and int(w.get("end_ms", 0)) <= end_ms + 20
    ]


def _word_count(span: list[dict[str, Any]]) -> int:
    return sum(1 for w in span if str(w.get("text") or "").strip())


def _split_points_from_backchannels(
    words: list[dict[str, Any]],
    *,
    start_ms: int,
    end_ms: int,
    roles: dict[str, str],
    backchannel_max_words: int,
) -> list[int]:
    span_words = _words_in_span(words, start_ms, end_ms)
    if len(span_words) < 2:
        return []

    splits: list[int] = []
    i = 0
    while i < len(span_words):
        w = span_words[i]
        sid = str(w.get("speaker_id") or "")
        role = roles.get(sid, "unknown")
        if role != "interviewer":
            i += 1
            continue
        turn_start = i
        while i < len(span_words) and str(span_words[i].get("speaker_id") or "") == sid:
            i += 1
        turn_words = span_words[turn_start:i]
        if _word_count(turn_words) <= backchannel_max_words:
            split_start = int(turn_words[0]["start_ms"])
            split_end = int(turn_words[-1]["end_ms"])
            if start_ms + 500 < split_start < end_ms - 500:
                splits.append(split_start)
            if start_ms + 500 < split_end < end_ms - 500:
                splits.append(split_end)
    return sorted(set(splits))


def _best_pause_split(
    words: list[dict[str, Any]],
    *,
    start_ms: int,
    end_ms: int,
    pause_split_ms: int,
    target_ms: int | None = None,
) -> int | None:
    span_words = _words_in_span(words, start_ms, end_ms)
    if len(span_words) < 2:
        return None

    best: tuple[int, int] | None = None
    for i in range(1, len(span_words)):
        prev = span_words[i - 1]
        cur = span_words[i]
        gap = int(cur["start_ms"]) - int(prev["end_ms"])
        if gap < pause_split_ms:
            continue
        split_at = int(cur["start_ms"])
        if split_at <= start_ms + 500 or split_at >= end_ms - 500:
            continue
        score = gap
        if target_ms is not None:
            score -= abs(split_at - target_ms) // 10
        if best is None or score > best[0]:
            best = (score, split_at)
    return best[1] if best else None


def _split_row_at_points(
    row: dict[str, Any],
    split_points: list[int],
    *,
    reason: str,
) -> list[dict[str, Any]]:
    start = int(row["start_ms"])
    end = int(row["end_ms"])
    speaker_id = row.get("speaker_id")
    points = sorted(p for p in split_points if start + 500 < p < end - 500)
    if not points:
        return [dict(row)]

    out: list[dict[str, Any]] = []
    cursor = start
    for point in points:
        out.append(
            {
                "start_ms": cursor,
                "end_ms": point,
                "speaker_id": speaker_id,
                "proposed_split_reason": reason,
            }
        )
        cursor = point
    out.append(
        {
            "start_ms": cursor,
            "end_ms": end,
            "speaker_id": speaker_id,
            "proposed_split_reason": reason,
        }
    )
    return out


def split_backchannel_turns(
    rows: list[dict[str, Any]],
    transcript: dict[str, Any] | None,
    speakers_doc: dict[str, Any] | None,
    *,
    cfg: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sc = _seg_cfg(cfg)
    if not sc.get("split_backchannels", True):
        return rows, []
    words = _words_from_transcript(transcript)
    roles = _speaker_roles(speakers_doc)
    max_words = int(sc.get("backchannel_max_words") or 8)
    min_ms = int(sc.get("min_segment_duration_ms") or 4000)

    applied: list[dict[str, Any]] = []
    result: list[dict[str, Any]] = []
    for row in rows:
        if row.get("start_ms") is None or row.get("end_ms") is None:
            result.append(dict(row))
            continue
        start = int(row["start_ms"])
        end = int(row["end_ms"])
        if end - start < min_ms * 2:
            result.append(dict(row))
            continue
        splits = _split_points_from_backchannels(
            words,
            start_ms=start,
            end_ms=end,
            roles=roles,
            backchannel_max_words=max_words,
        )
        if not splits:
            result.append(dict(row))
            continue
        pieces = _split_row_at_points(row, splits, reason="speaker_change")
        applied.append({"action": "split_backchannel", "segment_id": row.get("segment_id"), "splits": len(pieces) - 1})
        result.extend(pieces)
    return result, applied


def enforce_max_segment_duration(
    rows: list[dict[str, Any]],
    transcript: dict[str, Any] | None,
    *,
    cfg: dict[str, Any] | None = None,
    topic_split_times: list[int] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sc = _seg_cfg(cfg)
    max_ms = sc.get("max_segment_duration_ms")
    if max_ms is None:
        return rows, []
    max_ms = int(max_ms)
    min_ms = int(sc.get("min_segment_duration_ms") or 4000)
    pause_ms = int((merged_config().get("analysis") or {}).get("prompt_thresholds", {}).get("pause_split_ms") or 400)
    words = _words_from_transcript(transcript)
    topic_times = sorted(topic_split_times or [])

    applied: list[dict[str, Any]] = []
    queue = [dict(r) for r in rows if r.get("start_ms") is not None and r.get("end_ms") is not None]
    result: list[dict[str, Any]] = []

    while queue:
        row = queue.pop(0)
        start = int(row["start_ms"])
        end = int(row["end_ms"])
        span = end - start
        if span <= max_ms:
            result.append(row)
            continue

        target = start + span // 2
        topic_candidates = [t for t in topic_times if start + min_ms < t < end - min_ms]
        split_at: int | None = topic_candidates[len(topic_candidates) // 2] if topic_candidates else None
        reason = "topic_shift"
        if split_at is None:
            split_at = _best_pause_split(words, start_ms=start, end_ms=end, pause_split_ms=pause_ms, target_ms=target)
            reason = "pause"
        if split_at is None:
            split_at = target
            reason = "pause"
            applied.append({"action": "force_split_midpoint", "start_ms": start, "end_ms": end})

        left = {**row, "start_ms": start, "end_ms": split_at, "proposed_split_reason": reason}
        right = {**row, "start_ms": split_at, "end_ms": end, "proposed_split_reason": reason}
        applied.append({"action": "enforce_max_duration", "split_ms": split_at, "span_ms": span})
        queue.insert(0, right)
        queue.insert(0, left)

    return result, applied


def topic_split_times_from_brief(
    content_brief: dict[str, Any] | None,
    manifest: dict[str, Any] | None,
) -> list[int]:
    """Collect boundary times where reanchored topics change segment mapping."""
    if not isinstance(content_brief, dict) or not isinstance(manifest, dict):
        return []
    by_id = {
        str(s.get("segment_id")): s
        for s in (manifest.get("segments") or [])
        if isinstance(s, dict) and s.get("segment_id")
    }
    times: list[int] = []
    for topic in content_brief.get("topics") or []:
        if not isinstance(topic, dict):
            continue
        seg_ids = topic.get("segment_ids") or []
        if not isinstance(seg_ids, list) or len(seg_ids) < 2:
            continue
        ordered = sorted(str(s) for s in seg_ids)
        for sid in ordered[1:]:
            row = by_id.get(sid)
            if row and row.get("start_ms") is not None:
                times.append(int(row["start_ms"]))
    return sorted(set(times))


def detect_overloaded_segment_ids(
    boundaries_doc: dict[str, Any],
    *,
    content_brief: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
    cfg: dict[str, Any] | None = None,
) -> set[str]:
    sc = _seg_cfg(cfg)
    max_ms = sc.get("max_segment_duration_ms")
    max_ms = int(max_ms) if max_ms is not None else None
    overloaded: set[str] = set()

    topic_counts: dict[str, int] = {}
    if isinstance(content_brief, dict):
        for topic in content_brief.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            for sid in topic.get("segment_ids") or []:
                s = str(sid)
                topic_counts[s] = topic_counts.get(s, 0) + 1

    tag_counts: dict[str, set[str]] = {}
    if isinstance(manifest, dict):
        for seg in manifest.get("segments") or []:
            if not isinstance(seg, dict) or not seg.get("segment_id"):
                continue
            sid = str(seg["segment_id"])
            tags = {str(t) for t in (seg.get("topic_tags") or []) if t}
            if len(tags) > 1:
                tag_counts[sid] = tags

    for row in boundaries_doc.get("boundaries") or []:
        if not isinstance(row, dict) or not row.get("segment_id"):
            continue
        sid = str(row["segment_id"])
        if topic_counts.get(sid, 0) > 1:
            overloaded.add(sid)
        if sid in tag_counts:
            overloaded.add(sid)
        if max_ms and row.get("start_ms") is not None and row.get("end_ms") is not None:
            if int(row["end_ms"]) - int(row["start_ms"]) > max_ms:
                overloaded.add(sid)
    return overloaded


def enrich_boundary_rows(
    rows: list[dict[str, Any]],
    *,
    transcript: dict[str, Any] | None = None,
    speakers_doc: dict[str, Any] | None = None,
    content_brief: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
    cfg: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply deterministic fine-grain splits before timeline normalization."""
    applied: list[dict[str, Any]] = []
    current = [dict(r) for r in rows if isinstance(r, dict)]

    bc_rows, bc_actions = split_backchannel_turns(current, transcript, speakers_doc, cfg=cfg)
    applied.extend(bc_actions)
    current = bc_rows

    topic_times = topic_split_times_from_brief(content_brief, manifest)
    dur_rows, dur_actions = enforce_max_segment_duration(
        current,
        transcript,
        cfg=cfg,
        topic_split_times=topic_times,
    )
    applied.extend(dur_actions)
    return dur_rows, applied
