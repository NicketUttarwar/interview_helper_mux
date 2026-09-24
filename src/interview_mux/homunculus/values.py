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
    re.compile(
        r"\bsubscribe\s+to\s+(?:the\s+)?(?:[\w'’.-]+\s+){0,6}"
        r"(show|channel|podcast|newsletter)\b"
    ),
    re.compile(r"\bdon'?t\s+forget\s+to\s+subscribe\b"),
    re.compile(r"\bhit(ting)?\s+(the\s+)?(like|subscribe)(\s+button)?\b"),
    re.compile(r"\b(leave|drop)\s+(a\s+)?comment"),
    re.compile(r"\bcomments?\s+section\b"),
    re.compile(r"\bour\s+sponsor\b"),
    re.compile(r"\bthanks?\s+(again\s+)?to\s+our\s+sponsor\b"),
    re.compile(r"\baudio[-\s]only\s+version\s+of\s+the\s+show\b"),
    re.compile(r"\bvisit\s+(them|us)\s+at\b"),
    re.compile(r"\bfollow\s+us\s+on\b"),
    re.compile(r"\bpreferred\s+podcast\s+platform\b"),
    re.compile(r"\bwe'?d\s+love\s+to\s+hear\s+from\s+you\b"),
    re.compile(r"\bpop\s+us\s+a\s+note\b"),
    re.compile(r"\bpodcast produced by\b"),
    re.compile(r"\bproduction support from\b"),
    re.compile(r"\bmusic for this podcast\b"),
    re.compile(r"\bmusic\b.+\bprovided courtesy\b"),
    # Deterministic media-IP / pitch classifiers (§7A).
    re.compile(r"https?://"),
    re.compile(r"\bwww\.\w+\.\w+"),
    re.compile(r"\buse\s+(code|promo)\b"),
    re.compile(r"\bpromo\s+code\b"),
    re.compile(r"\blink\s+in\s+(the\s+)?(description|bio|show\s+notes)\b"),
    re.compile(r"\bpatreon\.com\b"),
    re.compile(r"\bbuy\s+my\s+(course|book|program)\b"),
    re.compile(r"\bcheck\s+out\s+(my|our)\s+(course|program|newsletter)\b"),
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
    if any(rx.search(raw) for rx in _SPEECH_ACT_RES):
        return True
    words = lower.split()
    if words and len(words) <= 4 and words[-1] in {"com", "net", "org"}:
        return True
    # Short pitch islands: mostly CTA tokens, little story content.
    if len(words) <= 12:
        pitch_hits = sum(
            1
            for w in words
            if w
            in {
                "subscribe",
                "sponsor",
                "patreon",
                "promo",
                "discount",
                "coupon",
                "newsletter",
                "follow",
                "like",
                "comment",
                "sponsor",
            }
        )
        if pitch_hits >= 2:
            return True
    return False
