"""Exact-edge refine for native cuts: word hinges + acoustic silence valleys.

Semantic stages choose *which* words belong in a keep window. This module owns
sample-accurate splice times: snap to word start/end, then micro-nudge into a
silence valley without crossing neighboring words. No large free shifts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _tok(w: dict[str, Any]) -> str:
    return str(w.get("text") or w.get("word") or "").strip()


def _norm(tok: str) -> str:
    return tok.lower().strip(".,!?;:\"'()[]")


def words_in_span(
    words: list[dict[str, Any]], start_ms: int, end_ms: int
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for w in words:
        if not isinstance(w, dict) or not _tok(w):
            continue
        try:
            w0 = int(float(w.get("start_ms") or 0))
            w1 = int(float(w.get("end_ms") or w0))
        except (TypeError, ValueError):
            continue
        if w1 < start_ms or w0 > end_ms:
            continue
        out.append(w)
    out.sort(key=lambda w: int(w.get("start_ms") or 0))
    return out


def resolve_ms_from_word_index(
    words: list[dict[str, Any]],
    index: int | None,
    *,
    prefer: str,
) -> int | None:
    if index is None or not words:
        return None
    try:
        i = int(index)
    except (TypeError, ValueError):
        return None
    if i < 0 or i >= len(words):
        return None
    w = words[i]
    if not isinstance(w, dict):
        return None
    if prefer == "start":
        return max(0, int(float(w.get("start_ms") or 0)))
    return max(0, int(float(w.get("end_ms") or w.get("start_ms") or 0)))


def resolve_ms_from_anchor_text(
    words: list[dict[str, Any]],
    anchor: str | None,
    *,
    approx_ms: int,
    prefer: str,
    window_ms: int = 8_000,
) -> int | None:
    """Match a short quoted phrase near ``approx_ms``; return word start or end."""
    phrase = " ".join(_norm(t) for t in (anchor or "").split() if _norm(t))
    if not phrase or not words:
        return None
    tokens = phrase.split()
    if not tokens:
        return None
    lo = max(0, int(approx_ms) - int(window_ms))
    hi = int(approx_ms) + int(window_ms)
    candidates = [
        w
        for w in words
        if isinstance(w, dict)
        and _tok(w)
        and lo <= int(float(w.get("start_ms") or 0)) <= hi
    ]
    candidates.sort(key=lambda w: int(w.get("start_ms") or 0))
    norms = [_norm(_tok(w)) for w in candidates]
    n = len(tokens)
    best_i: int | None = None
    best_dist = window_ms + 1
    for i in range(0, max(0, len(norms) - n + 1)):
        if norms[i : i + n] != tokens:
            continue
        if prefer == "start":
            edge = int(float(candidates[i].get("start_ms") or 0))
        else:
            edge = int(
                float(
                    candidates[i + n - 1].get("end_ms")
                    or candidates[i + n - 1].get("start_ms")
                    or 0
                )
            )
        dist = abs(edge - int(approx_ms))
        if dist < best_dist:
            best_dist = dist
            best_i = i
    if best_i is None:
        return None
    if prefer == "start":
        return max(0, int(float(candidates[best_i].get("start_ms") or 0)))
    last = candidates[best_i + n - 1]
    return max(0, int(float(last.get("end_ms") or last.get("start_ms") or 0)))


def exact_word_edges(
    words: list[dict[str, Any]], start_ms: int, end_ms: int
) -> tuple[int, int]:
    """Pin start/end to word boundaries without stealing earlier/later words.

    - If ``start_ms`` lands on a word start (±5ms), use that word start.
    - If ``start_ms`` is mid-word, keep ``start_ms`` (do not pull to the previous
      word start — that would violate ideal-window clamps).
    - Otherwise snap forward to the next word start in span.
    End snaps to the last word that ends at/before ``end_ms`` (+5ms slack).
    """
    span = words_in_span(words, start_ms, end_ms)
    if not span:
        return max(0, int(start_ms)), max(0, int(end_ms))
    start_i = int(start_ms)
    end_i = int(end_ms)

    containing = [
        w
        for w in span
        if int(float(w.get("start_ms") or 0))
        <= start_i
        <= int(float(w.get("end_ms") or w.get("start_ms") or 0))
    ]
    if containing:
        ws = int(float(containing[0].get("start_ms") or start_i))
        s = ws if abs(ws - start_i) <= 5 else start_i
    else:
        forward = [
            w
            for w in span
            if int(float(w.get("start_ms") or 0)) >= start_i - 5
        ]
        if forward:
            s0 = forward[0].get("start_ms")
            s = max(0, int(float(s0 if s0 is not None else start_i)))
        else:
            s = max(0, start_i)

    backward = [
        w
        for w in span
        if int(float(w.get("end_ms") or w.get("start_ms") or 0)) <= end_i + 5
    ]
    if backward:
        e1 = backward[-1].get("end_ms")
        if e1 is None:
            e1 = backward[-1].get("start_ms")
        e = max(s, int(float(e1 if e1 is not None else end_i)))
    else:
        e1 = span[-1].get("end_ms")
        if e1 is None:
            e1 = span[-1].get("start_ms")
        e = max(s, int(float(e1 if e1 is not None else end_i)))
    return s, e


def _neighbor_bounds(
    words: list[dict[str, Any]], start_ms: int, end_ms: int
) -> tuple[int, int]:
    """Return (prev_word_end_ms, next_word_start_ms) clamps for acoustic nudge."""
    prev_end = 0
    next_start = end_ms + 60_000
    for w in words:
        if not isinstance(w, dict) or not _tok(w):
            continue
        try:
            w0 = int(float(w.get("start_ms") or 0))
            w1 = int(float(w.get("end_ms") or w0))
        except (TypeError, ValueError):
            continue
        if w1 <= start_ms:
            prev_end = max(prev_end, w1)
        if w0 >= end_ms:
            next_start = min(next_start, w0)
    return prev_end, next_start


def acoustic_snap_edges(
    wav_path: Path | str | None,
    start_ms: int,
    end_ms: int,
    words: list[dict[str, Any]] | None = None,
    *,
    search_ms: int = 120,
) -> tuple[int, int, dict[str, Any]]:
    """Micro-nudge into silence valleys without eating neighboring speech.

    Start may move earlier into pre-roll silence (not past previous word end).
    End may move later into post-roll silence (not into next word start).
    Never moves start later or end earlier past the semantic word edges.
    """
    meta: dict[str, Any] = {
        "acoustic_applied": False,
        "before_start_ms": int(start_ms),
        "before_end_ms": int(end_ms),
    }
    start = max(0, int(start_ms))
    end = max(start, int(end_ms))
    if end <= start or search_ms <= 0:
        meta["after_start_ms"] = start
        meta["after_end_ms"] = end
        return start, end, meta

    path = Path(wav_path) if wav_path else None
    if path is None or not path.is_file():
        meta["after_start_ms"] = start
        meta["after_end_ms"] = end
        meta["skip_reason"] = "no_wav"
        return start, end, meta

    from interview_mux.audio_energy import find_silence_valley_ms, rms_at_ms

    prev_end, next_start = _neighbor_bounds(words or [], start, end)
    # Prefer valley just before first speech.
    start_floor = max(prev_end + 10, start - int(search_ms))
    start_ceil = start
    valley_s = find_silence_valley_ms(path, start, search_ms=int(search_ms))
    if start_floor <= valley_s <= start_ceil:
        # Only accept if the valley is quieter than on-word energy.
        on_word = rms_at_ms(path, min(start + 40, end))
        at_valley = rms_at_ms(path, valley_s)
        if at_valley is not None and on_word is not None and at_valley <= on_word * 0.85:
            start = valley_s
            meta["acoustic_applied"] = True
            meta["start_valley_ms"] = valley_s

    # Prefer valley just after last speech.
    end_floor = end
    end_ceil = min(next_start - 10, end + int(search_ms))
    if end_ceil > end_floor:
        valley_e = find_silence_valley_ms(path, end, search_ms=int(search_ms))
        if end_floor <= valley_e <= end_ceil:
            on_word = rms_at_ms(path, max(start, end - 40))
            at_valley = rms_at_ms(path, valley_e)
            if (
                at_valley is not None
                and on_word is not None
                and at_valley <= on_word * 0.85
            ):
                end = valley_e
                meta["acoustic_applied"] = True
                meta["end_valley_ms"] = valley_e

    if end <= start:
        start = int(meta["before_start_ms"])
        end = int(meta["before_end_ms"])
        meta["acoustic_applied"] = False
        meta["skip_reason"] = "degenerate_after_snap"

    meta["after_start_ms"] = start
    meta["after_end_ms"] = end
    return start, end, meta


def refine_cut_edges(
    *,
    start_ms: int,
    end_ms: int,
    words: list[dict[str, Any]] | None = None,
    wav_path: Path | str | None = None,
    search_ms: int = 120,
    apply_exact_words: bool = True,
    apply_acoustic: bool = True,
) -> tuple[int, int, dict[str, Any]]:
    """Full edge refine: exact word pins then optional acoustic valley nudge."""
    meta: dict[str, Any] = {"steps": []}
    start = max(0, int(start_ms))
    end = max(start, int(end_ms))
    word_list = [w for w in (words or []) if isinstance(w, dict)]
    if apply_exact_words and word_list:
        start, end = exact_word_edges(word_list, start, end)
        meta["steps"].append("exact_word_edges")
    if apply_acoustic:
        start, end, acoustic_meta = acoustic_snap_edges(
            wav_path,
            start,
            end,
            word_list,
            search_ms=search_ms,
        )
        meta["acoustic"] = acoustic_meta
        if acoustic_meta.get("acoustic_applied"):
            meta["steps"].append("acoustic_valley")
    meta["start_ms"] = start
    meta["end_ms"] = end
    return start, end, meta
