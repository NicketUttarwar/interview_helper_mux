"""v2 compatibility shims for legacy first-try operator mode helpers."""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config


def _first_try_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = (cfg or merged_config()).get("first_try") or {}
    return raw if isinstance(raw, dict) else {}


def first_try_mode_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(_first_try_cfg(cfg).get("enabled", True))


def allow_placeholder_mix(cfg: dict[str, Any] | None = None) -> bool:
    return bool(_first_try_cfg(cfg).get("allow_placeholder_mix", True))


def write_approval_deferred(cfg: dict[str, Any] | None = None) -> bool:
    return bool(_first_try_cfg(cfg).get("write_approval_deferred", False))


def preclean_auto_dismiss_when_green(cfg: dict[str, Any] | None = None) -> bool:
    return bool(_first_try_cfg(cfg).get("preclean_auto_dismiss_when_green", True))
