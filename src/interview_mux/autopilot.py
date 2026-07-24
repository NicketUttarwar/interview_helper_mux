"""Optional autopilot progression (default off).

Never auto-completes G0. Stops when speaker-volley integrity would fail.
See docs/cross-cutting/volley-glossary.md.
"""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config


def autopilot_enabled() -> bool:
    cfg = merged_config()
    op = cfg.get("operator") if isinstance(cfg.get("operator"), dict) else {}
    if "autopilot_enabled" in op:
        return bool(op.get("autopilot_enabled"))
    return bool(cfg.get("autopilot_enabled", False))


def soft_gates_auto_continue() -> bool:
    """When autopilot is on, soft structure/preview gates may auto-continue with log."""
    return autopilot_enabled()


def autopilot_blocks_on_speaker_volley(flags: list[str]) -> dict[str, Any] | None:
    """Return a blocker dict if speaker-volley integrity flags are present."""
    bad = [f for f in flags if str(f).startswith("speaker_volley_")]
    if not bad:
        return None
    return {
        "layer": "speaker_volley",
        "message": "Autopilot stopped: speaker volley integrity failed",
        "flags": bad[:12],
        "id": "autopilot.speaker_volley_integrity",
    }
