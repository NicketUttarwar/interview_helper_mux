from __future__ import annotations

from typing import Any

from pipeline.transcription.schema import TranscriptDocument


def segment_transcript(
    doc: TranscriptDocument,
    *,
    min_gap_ms: int = 800,
    min_duration_ms: int = 3000,
    max_duration_ms: int = 120_000,
) -> list[dict[str, Any]]:
    """
    Merge transcript STT segments on short gaps; split long spans at silence gaps.
    Returns segment dicts ready for mux_store.upsert_segment.
    """
    if not doc.segments:
        return []

    merged: list[tuple[int, int, str]] = []
    cur_start = doc.segments[0].start_ms
    cur_end = doc.segments[0].end_ms
    cur_text = [doc.segments[0].text]

    for seg in doc.segments[1:]:
        gap = seg.start_ms - cur_end
        span = cur_end - cur_start
        if gap <= min_gap_ms and span < max_duration_ms:
            cur_end = seg.end_ms
            if seg.text:
                cur_text.append(seg.text)
        else:
            merged.append((cur_start, cur_end, " ".join(cur_text).strip()))
            cur_start, cur_end, cur_text = seg.start_ms, seg.end_ms, [seg.text]
    merged.append((cur_start, cur_end, " ".join(cur_text).strip()))

    out: list[dict[str, Any]] = []
    for i, (t0, t1, text) in enumerate(merged):
        if t1 - t0 < min_duration_ms or not text:
            continue
        out.append(
            {
                "segment_id": f"seg-{i:04d}",
                "t_start_ms": t0,
                "t_end_ms": t1,
                "text": text,
                "transcript_revision_id": doc.revision_id,
                "provenance": {
                    "segmenter_id": "silence_merge_v1",
                    "stt_model_id": doc.model_id,
                    "transcript_revision": doc.revision_id,
                },
            }
        )
    return out


def persist_segments(conn: Any, interview_id: str, segments: list[dict[str, Any]]) -> int:
    from mux_store import upsert_segment

    for s in segments:
        upsert_segment(
            conn,
            interview_id=interview_id,
            segment_id=s["segment_id"],
            t_start_ms=s["t_start_ms"],
            t_end_ms=s["t_end_ms"],
            text=s.get("text"),
            transcript_revision_id=s.get("transcript_revision_id"),
            provenance=s.get("provenance"),
        )
    return len(segments)
