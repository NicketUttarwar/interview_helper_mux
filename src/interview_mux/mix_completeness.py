"""Mix asset completeness gates — warn or block before master export."""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext


def _completeness_cfg() -> dict[str, Any]:
    mix = merged_config().get("mix") or {}
    row = mix.get("completeness_gate")
    return row if isinstance(row, dict) else {}


def completeness_gate_enabled() -> bool:
    return bool(_completeness_cfg().get("enabled", True))


def completeness_gate_mode() -> str:
    """warn | block"""
    mode = str(_completeness_cfg().get("mode", "warn")).lower()
    return mode if mode in {"warn", "block"} else "warn"


def enforce_mix_completeness(
    ctx: RunContext,
    *,
    flow: str,
    stage: str,
    missing_vo: list[str] | None = None,
    missing_sfx: list[str] | None = None,
) -> None:
    """Raise on block mode when required VO/SFX assets are missing; always log."""
    if not completeness_gate_enabled():
        return

    vo = sorted({str(x) for x in (missing_vo or []) if x})
    sfx = sorted({str(x) for x in (missing_sfx or []) if x})
    if not vo and not sfx:
        return

    parts: list[str] = []
    if vo:
        parts.append(f"missing VO: {vo}")
    if sfx:
        parts.append(f"missing SFX: {sfx}")

    message = f"{stage}: mix completeness — {'; '.join(parts)}"
    mode = completeness_gate_mode()
    level = "error" if mode == "block" else "warning"
    ctx.log(message, level=level, stage=stage, detail=f"flow={flow} mode={mode}")

    if mode == "block":
        raise RuntimeError(
            f"{stage}: cannot continue with missing mix assets ({'; '.join(parts)}). "
            "Record VO, regenerate SFX, or set mix.completeness_gate.mode to warn."
        )
