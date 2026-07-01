"""Downstream risk classification for autopilot force-advance."""

from __future__ import annotations

from enum import Enum
from typing import Any


class IssueRisk(str, Enum):
    GUARANTEED_BREAKAGE = "guaranteed_breakage"
    REPAIRABLE = "repairable"
    PASSABLE = "passable"


_GUARANTEED_PATTERNS = (
    "duplicate segment_id",
    "not monotonic",
    "zero-length segment",
    "zero-length boundary",
    "boundary segment_id",
    "not in manifest",
    "timeline invalid",
    "boundary timeline",
    "overlap",
    "has no segment_ids",
)

_PASSABLE_STRATEGIES = frozenset({"infer_segment_types", "llm_pick"})
_PASSABLE_SEVERITIES = frozenset({"minor", "noise"})


def assess_issue_risk(item: dict[str, Any]) -> IssueRisk:
    """Classify an open blocking clarification item for autopilot remediation."""
    msg = str(item.get("message") or "").lower()
    strategy = str(item.get("repair_strategy") or "")
    kind = str(item.get("kind") or "")
    severity = str(item.get("severity") or "")

    if kind == "cross_validate" or kind == "overlap":
        for pat in _GUARANTEED_PATTERNS:
            if pat in msg:
                return IssueRisk.GUARANTEED_BREAKAGE

    for pat in _GUARANTEED_PATTERNS:
        if pat in msg:
            return IssueRisk.GUARANTEED_BREAKAGE

    if strategy in ("merge_overlap", "fabricate_missing_segments", "default_value", "drop_row", "drop_orphan_ref", "infer_enum"):
        return IssueRisk.REPAIRABLE

    if strategy in _PASSABLE_STRATEGIES or severity in _PASSABLE_SEVERITIES:
        return IssueRisk.PASSABLE

    if item.get("options") and not item.get("recommended_choice"):
        return IssueRisk.PASSABLE

    if severity == "critical" and not strategy:
        return IssueRisk.GUARANTEED_BREAKAGE

    return IssueRisk.REPAIRABLE


def cross_validate_is_hard(message: str) -> bool:
  low = message.lower()
  return any(pat in low for pat in _GUARANTEED_PATTERNS)
