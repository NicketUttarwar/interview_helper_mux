from __future__ import annotations

from typing import Any


def spine_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    from interview_mux.config import merged_config

    resolved = cfg if cfg is not None else merged_config()
    block = resolved.get("interview_spine")
    return block if isinstance(block, dict) else {}


def spine_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(spine_cfg(cfg).get("enabled", True))


def spine_flow2_quotability_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(spine_cfg(cfg).get("flow2_quotability_enabled", False))
