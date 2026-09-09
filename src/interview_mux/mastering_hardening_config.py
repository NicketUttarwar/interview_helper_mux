"""Config access for the Mastering quality-hardening gates.

Canon: docs/cross-cutting/mastering-quality-hardening.md
"""

from __future__ import annotations

from typing import Any, Literal

from interview_mux.config import merged_config

GateMode = Literal["off", "advisory", "authoritative"]

_VALID_MODES = ("off", "advisory", "authoritative")

GATE_DEFAULTS: dict[str, dict[str, Any]] = {
    "context": {
        "mode": "advisory",
        "default_max_tokens": 24000,
        "truncation_policy": "drop_lowest_salience",
        "inline_max_chars": 4000,
    },
    "diversity": {
        "mode": "advisory",
        "min_pairwise_distance": 0.35,
        "max_remint_rounds": 1,
    },
    "feasibility": {
        "mode": "authoritative",
        "duration_slack_pct": 0.15,
    },
    "semantic_integrity": {
        "mode": "authoritative",
        "adjacency_max_turns": 3,
        "llm_confirm": True,
    },
    "voice_clone": {
        "mode": "advisory",
        "default_scopes": [],
        "require_disclosure": False,
    },
    "rubric": {"mode": "advisory"},
    "auditions": {
        "mode": "advisory",
        "max_auditions": 3,
        "window_ms": {"opening": 20000, "hinge": 20000, "dense": 30000},
        "total_max_ms": 90000,
    },
    "critics": {
        "mode": "advisory",
        "enabled_critics": [
            "narrative_editor",
            "engagement_listener",
            "audio_intelligibility",
            "integrity",
            "pacing_repetition",
            "style_fit",
        ],
        "max_deepen_rounds": 1,
    },
    "pareto": {"mode": "advisory", "min_frontier_size": 1},
    "polish": {"mode": "advisory", "audio_grounded": True, "max_remux_rounds": 2},
}

ROUTING_DEFAULTS: dict[str, Any] = {
    "mode": "advisory",
    "default_disposition": "required",
    "max_deep_fields": 12,
}

PROMPT_EDIT_DEFAULTS: dict[str, Any] = {
    "allow_global_promotion": False,
    "require_operator_approval": True,
}


def mastering_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = (cfg or merged_config()).get("mastering")
    return raw if isinstance(raw, dict) else {}


def hardening_enabled(cfg: dict[str, Any] | None = None) -> bool:
    block = mastering_cfg(cfg).get("quality_hardening")
    if not isinstance(block, dict):
        return True
    return bool(block.get("enabled", True))


def gate_cfg(gate: str, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merged defaults + overrides for one hardening gate."""
    defaults = GATE_DEFAULTS.get(gate)
    if defaults is None:
        raise KeyError(f"unknown hardening gate: {gate}")
    block = mastering_cfg(cfg).get("quality_hardening")
    raw = block.get(gate) if isinstance(block, dict) else None
    if not isinstance(raw, dict):
        return dict(defaults)
    return {**defaults, **raw}


def gate_mode(gate: str, cfg: dict[str, Any] | None = None) -> GateMode:
    """Effective mode; `off` whenever the whole layer is disabled."""
    if not hardening_enabled(cfg):
        return "off"
    mode = str(gate_cfg(gate, cfg).get("mode") or "advisory").lower()
    return mode if mode in _VALID_MODES else "advisory"  # type: ignore[return-value]


def gate_blocks(gate: str, cfg: dict[str, Any] | None = None) -> bool:
    """True when this gate may fail the run."""
    return gate_mode(gate, cfg) == "authoritative"


def gate_runs(gate: str, cfg: dict[str, Any] | None = None) -> bool:
    return gate_mode(gate, cfg) != "off"


def routing_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    research = mastering_cfg(cfg).get("research")
    raw = research.get("routing") if isinstance(research, dict) else None
    if not isinstance(raw, dict):
        return dict(ROUTING_DEFAULTS)
    return {**ROUTING_DEFAULTS, **raw}


def prompt_edit_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = mastering_cfg(cfg).get("prompt_edit")
    if not isinstance(raw, dict):
        return dict(PROMPT_EDIT_DEFAULTS)
    return {**PROMPT_EDIT_DEFAULTS, **raw}


def global_prompt_promotion_allowed(cfg: dict[str, Any] | None = None) -> bool:
    return bool(prompt_edit_cfg(cfg).get("allow_global_promotion", False))
