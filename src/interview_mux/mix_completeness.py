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
    empty_speech: bool = False,
) -> None:
    """Hard-fail blocking VO / empty speech; soft-fail SFX placeholders under first_try."""
    if not completeness_gate_enabled():
        return

    from interview_mux.first_try import allow_placeholder_mix, first_try_mode_enabled

    cfg = _completeness_cfg()
    hard_vo = bool(cfg.get("hard_fail_missing_blocking_vo", True))
    hard_speech = bool(cfg.get("hard_fail_empty_speech", True))
    soft_sfx = bool(cfg.get("soft_fail_sfx_placeholder", True)) or allow_placeholder_mix()

    vo = sorted({str(x) for x in (missing_vo or []) if x})
    sfx = sorted({str(x) for x in (missing_sfx or []) if x})
    qa_missing = _missing_sfx_from_mmaudio_qa(ctx)
    if qa_missing:
        sfx = sorted(set(sfx) | qa_missing)

    if empty_speech and hard_speech:
        msg = f"{stage}: mix completeness — empty speech assembly (hard fail)"
        ctx.log(msg, level="error", stage=stage, detail=f"flow={flow}")
        raise RuntimeError(msg)

    if not vo and not sfx:
        return

    parts: list[str] = []
    if vo:
        parts.append(f"missing VO: {vo}")
    if sfx:
        parts.append(f"missing/placeholder SFX: {sfx}")

    message = f"{stage}: mix completeness — {'; '.join(parts)}"
    mode = completeness_gate_mode()

    block_for_vo = bool(vo) and hard_vo and (mode == "block" or first_try_mode_enabled())
    block_for_sfx = bool(sfx) and mode == "block" and not soft_sfx

    if block_for_vo or block_for_sfx:
        ctx.log(message, level="error", stage=stage, detail=f"flow={flow} mode=block")
        raise RuntimeError(
            f"{stage}: cannot continue with missing mix assets ({'; '.join(parts)}). "
            "Record VO, regenerate SFX, or adjust mix.completeness_gate."
        )

    ctx.log(message, level="warning", stage=stage, detail=f"flow={flow} mode=warn soft_sfx={soft_sfx}")


def _missing_sfx_from_mmaudio_qa(ctx: RunContext) -> set[str]:
    rel = "sound_design/mmaudio_qa.json"
    if not ctx.artifact_exists(rel):
        return set()
    doc = ctx.read_json(rel)
    rows = doc.get("assets") if isinstance(doc, dict) else []
    out: set[str] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        aid = str(row.get("asset_id") or "").strip()
        if not aid:
            continue
        status = str(row.get("generation_status") or "").lower()
        if status in {"failed", "placeholder"}:
            out.add(aid)
            continue
        if row.get("silence_detected") is True:
            out.add(aid)
    return out
