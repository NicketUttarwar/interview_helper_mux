from __future__ import annotations

from typing import Any

from interview_mux.interview_spine.constants import PAUSE_SPLIT_MS


def _words_in_span(words: list[dict[str, Any]], start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    return [
        w
        for w in words
        if int(w.get("start_ms", 0)) >= start_ms - 50 and int(w.get("end_ms", 0)) <= end_ms + 50
    ]


def _text_for_words(span: list[dict[str, Any]]) -> str:
    return " ".join(str(w.get("text") or "") for w in span if w.get("text"))


def _pace_window_sec(pace_class: str, cfg: dict[str, Any]) -> float:
    if pace_class == "dense":
        return float(cfg.get("window_sec_dense", 6))
    if pace_class == "calm":
        return float(cfg.get("window_sec_calm", 12))
    return float(cfg.get("window_sec_default", 10))


def build_windows(
    words: list[dict[str, Any]],
    *,
    pace_class: str = "conversational",
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Word-aligned sliding windows; split on speaker change and long pauses."""
    from interview_mux.interview_spine.config import spine_cfg

    resolved = cfg if cfg is not None else spine_cfg()
    if not words:
        return []

    window_ms = int(_pace_window_sec(pace_class, resolved) * 1000)
    hop_ms = int(float(resolved.get("hop_sec", 5)) * 1000)
    sorted_words = sorted(words, key=lambda w: float(w.get("start_ms", 0)))
    from interview_mux.diarization_suspicion import absorbable_micro_word_indexes

    micro_idxs = absorbable_micro_word_indexes(sorted_words)

    raw_spans: list[tuple[int, int, list[dict[str, Any]]]] = []
    bucket: list[dict[str, Any]] = []
    bucket_start = int(sorted_words[0]["start_ms"])
    bucket_speaker = sorted_words[0].get("speaker_id")

    for i, w in enumerate(sorted_words):
        bucket.append(w)
        pause_after = False
        speaker_change = False
        if i + 1 < len(sorted_words):
            nxt = sorted_words[i + 1]
            pause_after = int(nxt["start_ms"]) - int(w["end_ms"]) >= PAUSE_SPLIT_MS
            speaker_change = nxt.get("speaker_id") != w.get("speaker_id")
            if speaker_change and (i in micro_idxs or (i + 1) in micro_idxs):
                speaker_change = False
        duration = int(w["end_ms"]) - bucket_start
        if pause_after or speaker_change or duration >= window_ms or i == len(sorted_words) - 1:
            raw_spans.append((bucket_start, int(w["end_ms"]), list(bucket)))
            bucket = []
            if i + 1 < len(sorted_words):
                bucket_start = int(sorted_words[i + 1]["start_ms"])
                bucket_speaker = sorted_words[i + 1].get("speaker_id")
        elif bucket_speaker is None and w.get("speaker_id"):
            bucket_speaker = w.get("speaker_id")

    # Optional hop subdivision for long spans
    spans: list[tuple[int, int, list[dict[str, Any]]]] = []
    for start_ms, end_ms, span_words in raw_spans:
        if end_ms - start_ms <= window_ms or hop_ms <= 0:
            if end_ms > start_ms:
                spans.append((start_ms, end_ms, span_words))
            continue
        cursor = start_ms
        while cursor < end_ms:
            sub_end = min(end_ms, cursor + window_ms)
            sub_words = _words_in_span(span_words, cursor, sub_end)
            if sub_words and sub_end > cursor:
                spans.append((cursor, sub_end, sub_words))
            cursor += hop_ms

    out: list[dict[str, Any]] = []
    for idx, (start_ms, end_ms, span_words) in enumerate(spans, start=1):
        speaker_ids = {w.get("speaker_id") for w in span_words if w.get("speaker_id")}
        speaker_id = next(iter(speaker_ids)) if len(speaker_ids) == 1 else None
        out.append(
            {
                "window_id": f"win_{idx:04d}",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "speaker_id": speaker_id,
                "text_span": _text_for_words(span_words),
                "features": {},
                "embedding_ref": None,
                "_words": span_words,
            }
        )
    return out
