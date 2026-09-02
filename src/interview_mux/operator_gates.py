"""Operator journey gates — human-required pauses vs homunculus recovery (H0/R14)."""

from __future__ import annotations

OPERATOR_GATE_STAGES: frozenset[str] = frozenset(
    {
        "transcript_review",
        "transcript_review_build",
        "topic_coverage_audit",
        "delivery_epoch_unlock",
        "podcast_publish",
    }
)

_OPERATOR_REASON_MARKERS: tuple[str, ...] = (
    "voice reference pending",
    "transcript review",
    "delivery epoch unlock",
    "delivery_epoch_unlock",
    "g-publish",
    "operator publish",
)


def is_operator_gate(stage: str | None, reason: str | None = None) -> bool:
    """True when the pause requires a human operator (not homunculus recovery)."""
    sid = str(stage or "").strip()
    if sid in OPERATOR_GATE_STAGES:
        if sid == "topic_coverage_audit":
            low = str(reason or "").lower()
            return "voice reference" in low or "chatterbox" in low
        return True
    low = str(reason or "").lower()
    return any(marker in low for marker in _OPERATOR_REASON_MARKERS)


def is_unattended_run(meta: dict | None) -> bool:
    if not isinstance(meta, dict):
        return False
    return bool(meta.get("partial_auto") or meta.get("full_auto"))


def should_stamp_needs_operator(
    stage: str,
    reason: str,
    *,
    meta: dict | None = None,
) -> bool:
    """Homunculus 0.1.0 unattended: only stamp needs_operator for operator gates."""
    if not is_unattended_run(meta):
        return True
    homunculus = str((meta or {}).get("homunculus_version") or "").strip()
    if homunculus and not homunculus.startswith("0.1"):
        return True
    return is_operator_gate(stage, reason)
