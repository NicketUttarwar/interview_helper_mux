"""Stratified transcript excerpts for speaker-role and understanding stages."""

from __future__ import annotations

from typing import Any


def stratified_transcript_samples(
    text: str,
    *,
    total_chars: int,
    windows: int = 3,
) -> dict[str, str]:
    """
    Return opening / middle / closing excerpts totaling <= total_chars.

    For short transcripts, returns a single opening sample. For longer text,
    splits budget across windows (default: opening, middle, closing).
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return {"opening": ""}

    if len(cleaned) <= total_chars:
        return {"opening": cleaned}

    if windows <= 1:
        return {"opening": cleaned[:total_chars]}

    per_window = max(1, total_chars // windows)
    n = len(cleaned)
    mid_start = max(0, (n // 2) - (per_window // 2))
    samples: dict[str, str] = {
        "opening": cleaned[:per_window],
        "middle": cleaned[mid_start : mid_start + per_window],
        "closing": cleaned[max(0, n - per_window) :],
    }
    return samples


def _speaker_labeled_span(chunk: list[dict[str, Any]]) -> str:
    """Join words, prefixing each turn with [speaker_id] when diarization exists.

    Unlabeled windows made speaker_roles guess at 0.5 confidence because the
    LLM saw only bare text ("turn-level attribution is absent").
    """
    has_speaker = any(
        isinstance(w, dict) and (w.get("speaker_id") or w.get("speaker"))
        for w in chunk
    )
    if not has_speaker:
        return " ".join(
            str(w.get("text") or w.get("word") or "")
            for w in chunk
            if isinstance(w, dict) and (w.get("text") or w.get("word"))
        ).strip()
    parts: list[str] = []
    cur: str | None = None
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        parts.append(f"[{cur or 'unk'}] " + " ".join(buf))

    for w in chunk:
        if not isinstance(w, dict):
            continue
        tok = str(w.get("text") or w.get("word") or "").strip()
        if not tok:
            continue
        sid = str(w.get("speaker_id") or w.get("speaker") or "") or None
        if sid != cur and buf:
            flush()
            buf = []
        cur = sid
        buf.append(tok)
    flush()
    return "\n".join(parts)


def stratified_transcript_samples_from_words(
    words: list[dict[str, Any]],
    *,
    total_chars: int,
    windows: int = 3,
) -> dict[str, str]:
    """Build stratified samples from word-level transcript, biasing middle toward questions."""
    text = " ".join(str(w.get("text", "")) for w in words if w.get("text"))
    if not words:
        return stratified_transcript_samples(text, total_chars=total_chars, windows=windows)
    labeled_all = _speaker_labeled_span(list(words))
    if labeled_all.startswith("["):
        if len(labeled_all) <= total_chars:
            return {"opening": labeled_all}
    elif len(text) <= total_chars:
        return stratified_transcript_samples(text, total_chars=total_chars, windows=windows)

    per_window = max(1, total_chars // max(windows, 1))
    n = len(words)
    third = max(1, n // 3)

    def _span(start: int, end: int) -> str:
        chunk = words[max(0, start) : min(n, end)]
        return _speaker_labeled_span(chunk)

    question_idx = _best_question_window_start(words, start=third, end=2 * third)
    mid_start = question_idx if question_idx is not None else max(0, (n // 2) - third // 2)
    mid_end = min(n, mid_start + third)

    opening = _span(0, third)[:per_window]
    middle = _span(mid_start, mid_end)[:per_window]
    closing = _span(max(0, n - third), n)[:per_window]

    return {"opening": opening, "middle": middle, "closing": closing}


def _best_question_window_start(
    words: list[dict[str, Any]],
    *,
    start: int,
    end: int,
    window: int = 40,
) -> int | None:
    """Pick start index in [start, end) with highest question-mark density."""
    if end <= start:
        return None
    best_idx: int | None = None
    best_score = -1
    for idx in range(start, min(end, len(words) - window + 1)):
        chunk = words[idx : idx + window]
        score = sum(1 for w in chunk if "?" in str(w.get("text", "")))
        if score > best_score:
            best_score = score
            best_idx = idx
    return best_idx if best_score > 0 else None
