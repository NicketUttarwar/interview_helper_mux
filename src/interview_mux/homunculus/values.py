"""Perspective registry (seed: direct_listener_monetization)."""

from interview_mux.homunculus.persona import PERSPECTIVES

__all__ = ["PERSPECTIVES", "should_hard_omit_cta"]


def should_hard_omit_cta(text: str) -> bool:
    """True when native speech is a direct listener CTA / buy-now."""
    lower = (text or "").lower()
    phrases = PERSPECTIVES["direct_listener_monetization"]["hard_omit"]
    return any(p in lower for p in phrases)
