"""Perspective registry (seed: direct_listener_monetization)."""

from __future__ import annotations

import re

from interview_mux.homunculus.persona import PERSPECTIVES

__all__ = ["PERSPECTIVES", "normalize_omit_text", "should_hard_omit_cta"]


_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]+", flags=re.UNICODE)


def normalize_omit_text(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation for phrase matching."""
    raw = (text or "").lower().replace("\u2019", "'").replace("\u2018", "'")
    raw = _PUNCT_RE.sub(" ", raw)
    return _SPACE_RE.sub(" ", raw).strip()


# Listener-directed speech-acts. Bare "subscribe" is not enough (story: "hospitals subscribe to").
_SPEECH_ACT_RES = (
    re.compile(r"\blike\s+(and|&)\s+subscribe\b"),
    re.compile(r"\bgo\s+subscribe\b"),
    re.compile(r"\bplease\s+subscribe\b"),
    re.compile(r"\bsubscribe\s+to\s+(my|our|this)\b"),
    re.compile(r"\bsubscribe\s+to\s+(the\s+)?(show|channel|podcast|newsletter)\b"),
    re.compile(r"\bdon'?t\s+forget\s+to\s+subscribe\b"),
    re.compile(r"\bhit\s+(the\s+)?(like|subscribe)(\s+button)?\b"),
    re.compile(r"\b(leave|drop)\s+(a\s+)?comment"),
    re.compile(r"\bcomments?\s+section\b"),
    re.compile(r"\bour\s+sponsor\b"),
    re.compile(r"\bthanks?\s+(again\s+)?to\s+our\s+sponsor\b"),
    re.compile(r"\baudio[-\s]only\s+version\s+of\s+the\s+show\b"),
)


def should_hard_omit_cta(text: str) -> bool:
    """True when native speech is a direct listener CTA / sponsor bumper."""
    lower = normalize_omit_text(text)
    if not lower:
        return False
    phrases = PERSPECTIVES["direct_listener_monetization"]["hard_omit"]
    if any(normalize_omit_text(p) in lower for p in phrases):
        return True
    raw = (text or "").lower().replace("\u2019", "'").replace("\u2018", "'")
    return any(rx.search(raw) for rx in _SPEECH_ACT_RES)
