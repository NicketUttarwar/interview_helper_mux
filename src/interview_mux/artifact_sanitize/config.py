"""Config budgets for artifact sanitizers."""

from __future__ import annotations

from typing import Any


_DEFAULTS: dict[str, Any] = {
    "max_same_family_on_air": 8,
    "max_fragment_depth": 3,
    "max_cta_readmit": 0,
    "max_order_growth_pct": 15.0,
    "block_consumers": True,
    "halt_after": 3,
    "min_layup_coverage": 0.70,
}


def sanitize_root_cfg() -> dict[str, Any]:
    from interview_mux.config import merged_config

    root = merged_config().get("artifact_sanitize") or {}
    return root if isinstance(root, dict) else {}


def sanitize_section(name: str) -> dict[str, Any]:
    root = sanitize_root_cfg()
    sec = root.get(name)
    return sec if isinstance(sec, dict) else {}


def sanitize_selection_cfg() -> dict[str, Any]:
    from interview_mux.config import merged_config

    root = merged_config().get("artifact_sanitize") or {}
    if not isinstance(root, dict):
        root = {}
    sel = root.get("selection") if isinstance(root.get("selection"), dict) else {}
    out = dict(_DEFAULTS)
    for key, default in _DEFAULTS.items():
        if key in sel:
            try:
                if isinstance(default, float):
                    out[key] = float(sel[key])
                elif isinstance(default, bool):
                    out[key] = bool(sel[key])
                elif isinstance(default, int):
                    out[key] = int(sel[key])
                else:
                    out[key] = sel[key]
            except (TypeError, ValueError):
                out[key] = default
    if "block_consumers" in root and "block_consumers" not in sel:
        out["block_consumers"] = bool(root.get("block_consumers"))
    return out


def block_consumers_on_unsanitary() -> bool:
    from interview_mux.config import merged_config

    root = merged_config().get("artifact_sanitize") or {}
    if isinstance(root, dict) and "block_consumers" in root:
        return bool(root.get("block_consumers"))
    return bool(sanitize_selection_cfg().get("block_consumers", True))
