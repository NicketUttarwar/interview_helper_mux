from __future__ import annotations

import re
from typing import Any


def normalize_token(text: str) -> str:
    return re.sub(r"[^\w\s-]", "", text.strip().lower())


def is_filler_text(text: str, lexicon: frozenset[str]) -> bool:
    norm = normalize_token(text)
    if not norm:
        return False
    if norm in lexicon:
        return True
    tokens = norm.split()
    if len(tokens) == 1 and tokens[0] in lexicon:
        return True
    return len(tokens) <= 2 and all(t in lexicon for t in tokens)


def classify_transcript_words(
    words: list[dict[str, Any]],
    lexicon: frozenset[str],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for idx, word in enumerate(words):
        text = str(word.get("text") or word.get("word") or "").strip()
        if not is_filler_text(text, lexicon):
            continue
        start_ms = int(word.get("start_ms") or 0)
        end_ms = int(word.get("end_ms") or start_ms)
        if end_ms <= start_ms:
            end_ms = start_ms + 120
        events.append(
            {
                "start_ms": start_ms,
                "end_ms": end_ms,
                "speaker_id": str(word.get("speaker_id") or word.get("speaker_label") or ""),
                "text": text,
                "confidence": float(word.get("confidence") or 0.9),
                "source": "transcript_lexicon",
                "word_index": idx,
            }
        )
    return events
