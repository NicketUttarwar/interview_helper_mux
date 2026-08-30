"""Product e2e-soft flags — gate auto-progress vs quality waivers.

``INTERVIEW_MUX_E2E_SOFT=1`` enables Full-auto gate auto-progress only (G0,
G-Framing, G-Publish). It does **not** waive listen-delight floors, junction
residuals, or listenability checks.

Quality ship waivers require a separate opt-in via
``INTERVIEW_MUX_E2E_QUALITY_WAIVERS=1`` (or run_meta ``e2e_quality_waivers``).
"""

from __future__ import annotations

import os
from typing import Any


def e2e_soft_enabled(*, meta: dict[str, Any] | None = None) -> bool:
    """True when Full-auto gate auto-progress is on (G0 / G-Framing / G-Publish)."""
    raw = str(os.environ.get("INTERVIEW_MUX_E2E_SOFT") or "").strip().lower()
    if raw in {"1", "true", "yes"}:
        return True
    _ = meta
    return False


def e2e_quality_waivers_enabled(*, meta: dict[str, Any] | None = None) -> bool:
    """Listen-delight / junction / listenability ship waivers — opt-in only.

    Full-auto sets INTERVIEW_MUX_E2E_SOFT=1 for gate auto-progress. Quality
    floors still halt unless INTERVIEW_MUX_E2E_QUALITY_WAIVERS=1.
    """
    raw = str(os.environ.get("INTERVIEW_MUX_E2E_QUALITY_WAIVERS") or "").strip().lower()
    if raw in {"1", "true", "yes"}:
        return True
    if isinstance(meta, dict) and meta.get("e2e_quality_waivers"):
        return True
    return False
