"""Product e2e-soft waivers — off unless INTERVIEW_MUX_E2E_SOFT=1."""

from __future__ import annotations

import os
from typing import Any


def e2e_soft_enabled(*, meta: dict[str, Any] | None = None) -> bool:
    """True only when the operator explicitly opts into e2e QC waivers."""
    raw = str(os.environ.get("INTERVIEW_MUX_E2E_SOFT") or "").strip().lower()
    if raw in {"1", "true", "yes"}:
        return True
    _ = meta
    return False
