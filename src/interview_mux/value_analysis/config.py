from __future__ import annotations

from typing import Any


def _resolved_cfg(cfg: dict[str, Any] | None) -> dict[str, Any]:
    from interview_mux.config import merged_config

    return cfg if cfg is not None else merged_config()


def _va_block(cfg: dict[str, Any]) -> dict[str, Any]:
    block = cfg.get("value_analysis")
    return block if isinstance(block, dict) else {}


def value_analysis_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(_va_block(_resolved_cfg(cfg)).get("enabled", False))


def value_analysis_flag(cfg: dict[str, Any] | None, name: str) -> bool:
    """True when master enabled and sub-flag is true (missing sub-flags default false)."""
    resolved = _resolved_cfg(cfg)
    if not value_analysis_enabled(resolved):
        return False
    return bool(_va_block(resolved).get(name, False))


def require_value_analysis_flag(cfg: dict[str, Any] | None, name: str) -> None:
    c = _resolved_cfg(cfg)
    if not value_analysis_enabled(c):
        raise RuntimeError(
            "value_analysis.enabled is false. Set it in config/app.defaults.json to use value-analysis tools."
        )
    if not value_analysis_flag(c, name):
        raise RuntimeError(f"value_analysis.{name} is false.")
