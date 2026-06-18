"""Shared constants for pause ladder (H-SEG-02) and spine window splitting."""

from __future__ import annotations

from typing import Final

# H-SEG-02 — ranked pause tiers for boundary hints and spine fusion (single source)
PAUSE_LADDER_MS: Final[tuple[int, ...]] = (400, 700, 1200)

# Internal window span split (separate from ladder tiers — see windows.build_windows)
PAUSE_SPLIT_MS: Final[int] = 700

# Log warning when 400 ms tier exceeds this count (fireside over-split guardrail)
PAUSE_LADDER_OVERSPLIT_400MS_COUNT: Final[int] = 50

# Volley compact cap for boundary_detection spine events
BOUNDARY_VOLLEY_MAX_SPINE_EVENTS: Final[int] = 40
