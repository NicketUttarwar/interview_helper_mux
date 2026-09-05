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

# Classified artifact blocks — homunculus/driver should ladder-recover, not stamp needs_operator.
AUTOMATED_CLASSIFIED_MARKERS: tuple[str, ...] = (
    "vo contract",
    "missing from gap_report",
    "vo coverage not rendered",
    "stale upstream",
    "marked stale",
    "seed order",
    "invalidated_by",
    "transitions.json",
    "layup plan stale",
    "nugget_layup_plan_stale",
    "selection_edl_order_drift",
    "opening_slot_conflict",
    "air_script",
)


def is_automated_classified_block(reason: str | None) -> bool:
    low = str(reason or "").lower()
    return any(marker in low for marker in AUTOMATED_CLASSIFIED_MARKERS)


def is_operator_must_act(stage: str | None, reason: str | None = None) -> bool:
    """True for gates that require human operator (G0, G-Publish, unlock, voice ref)."""
    return is_operator_gate(stage, reason)


def is_automated_classified(stage: str | None, reason: str | None = None) -> bool:
    """True when block should be handled by remediation ladder, not operator pause."""
    if is_operator_gate(stage, reason):
        return False
    return is_automated_classified_block(reason)


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
    if is_automated_classified_block(reason):
        return False
    return is_operator_gate(stage, reason)
