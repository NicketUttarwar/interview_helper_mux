"""Full autopilot UX configuration helpers."""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config


def full_autopilot_enabled(cfg: dict[str, Any] | None = None) -> bool:
    """True when in-run finalize and decision wizard replace manual ITR checkpoints."""
    cfg = cfg or merged_config()
    journey = cfg.get("journey_ui") or {}
    if journey.get("enabled") is False:
        return False
    return bool(journey.get("full_autopilot", True))
