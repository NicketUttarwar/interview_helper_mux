"""Full-auto and partially-accelerated runs share one detached driver stack."""

from __future__ import annotations

import os
from typing import Any

_FULL_AUTO_MODES = frozenset({"full-auto", "fullauto", "auto", "e2e"})
_PARTIAL_AUTO_MODES = frozenset(
    {"partially-accelerated", "partial-auto", "partiallyaccelerated"}
)

# Partial-auto: reach G0 after ingest+STT only — defer DeepFilterNet until after operator review.
PARTIAL_AUTO_PREPARE_UNTIL_G0: tuple[str, ...] = (
    "ingest",
    "transcribe",
    "transcript_review_build",
)
_AUTOMATION_ENV_KEYS = (
    "MUX_FULL_AUTO",
    "MUX_BABA_E2E",
    "MUX_PARTIAL_AUTO",
    "INTERVIEW_MUX_AUTO_ACCEPT_GATES",
)


def _normalize_run_mode_token(raw: str | None) -> str:
    return str(raw or "").strip().lower().replace("_", "-").replace(" ", "")


def is_partially_accelerated_run(meta: dict[str, Any] | None) -> bool:
    if not isinstance(meta, dict):
        return False
    if meta.get("partial_auto"):
        return True
    return _normalize_run_mode_token(str(meta.get("run_mode") or "")) in _PARTIAL_AUTO_MODES


def is_full_auto_run(meta: dict[str, Any] | None) -> bool:
    if not isinstance(meta, dict):
        return False
    if meta.get("full_auto"):
        return True
    return _normalize_run_mode_token(str(meta.get("run_mode") or "")) in _FULL_AUTO_MODES


def automation_driver_run(meta: dict[str, Any] | None) -> bool:
    """True when the shared automation driver stack applies (full or partial)."""
    return is_full_auto_run(meta) or is_partially_accelerated_run(meta)


# Partial-auto operator gate SSOT (Cluster D / SYN-MODE) — mirror of
# frontend/src/utils/partialOperatorGates.ts
PARTIAL_MUST_ACT_GATES: tuple[str, ...] = ("transcript_review", "g_publish")
PARTIAL_MAY_PAUSE_GATES: tuple[str, ...] = (
    "gap_framing",
    "missing_framing",
    "g1_vo_pickup",
    "stage_reuse",
    "write_approval",
)


def automation_driver_env_enabled() -> bool:
    """True when the current process was launched by the automation driver."""
    for key in _AUTOMATION_ENV_KEYS:
        raw = str(os.environ.get(key) or "").strip().lower()
        if raw in {"1", "true", "yes"}:
            return True
    mode = _normalize_run_mode_token(os.environ.get("MUX_RUN_MODE"))
    return mode in _FULL_AUTO_MODES or mode in _PARTIAL_AUTO_MODES
