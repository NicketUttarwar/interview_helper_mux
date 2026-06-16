from __future__ import annotations

from typing import Any


def coherence_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    from interview_mux.config import merged_config

    resolved = cfg if cfg is not None else merged_config()
    block = resolved.get("coherence")
    return block if isinstance(block, dict) else {}


def value_analysis_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    from interview_mux.config import merged_config

    resolved = cfg if cfg is not None else merged_config()
    block = resolved.get("value_analysis")
    return block if isinstance(block, dict) else {}


def coherence_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(coherence_cfg(cfg).get("enabled", True))


def orc03_enabled(cfg: dict[str, Any] | None = None) -> bool:
    va = value_analysis_cfg(cfg)
    if not va.get("enabled", True):
        return False
    return bool(va.get("orc03_enabled", True))


def coherence_active(cfg: dict[str, Any] | None = None) -> bool:
    return coherence_enabled(cfg) and orc03_enabled(cfg)


def replace_stub_topic_shift_hints(cfg: dict[str, Any] | None = None) -> bool:
    return bool(coherence_cfg(cfg).get("replace_stub_topic_shift_hints", True))


def threshold(cfg: dict[str, Any] | None, key: str, default: float) -> float:
    return float(coherence_cfg(cfg).get(key, default))


def int_threshold(cfg: dict[str, Any] | None, key: str, default: int) -> int:
    return int(coherence_cfg(cfg).get(key, default))
