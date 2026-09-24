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
    retried_vo: list[str] | None = None,
) -> None:
    """Hard-fail blocking VO / empty speech; soft-fail SFX placeholders under first_try."""
    if not completeness_gate_enabled():
        return

    from interview_mux.first_try import allow_placeholder_mix, first_try_mode_enabled

    cfg = _completeness_cfg()
    hard_vo = bool(cfg.get("hard_fail_missing_blocking_vo", True))
    hard_speech = bool(cfg.get("hard_fail_empty_speech", True))
    soft_sfx = bool(cfg.get("soft_fail_sfx_placeholder", True)) or allow_placeholder_mix()
    last_chance = bool((merged_config().get("mix") or {}).get("missing_vo_retry_once", True))

    def _id_list(raw: Any) -> list[str]:
        """Accept id sequences; ignore int counts / other non-iterables (DEEP-MIX)."""
        if raw is None or isinstance(raw, bool):
            return []
        if isinstance(raw, (int, float)):
            return []
        if isinstance(raw, str):
            return [raw] if raw.strip() else []
        try:
            return [str(x) for x in raw if x]
        except TypeError:
            return []

    vo = sorted({str(x) for x in _id_list(missing_vo) if x})
    sfx = sorted({str(x) for x in _id_list(missing_sfx) if x})
    retried = sorted({str(x) for x in _id_list(retried_vo) if x})
    qa_missing = _missing_sfx_from_mmaudio_qa(ctx)
    if qa_missing:
        sfx = sorted(set(sfx) | qa_missing)
    omitted = _music_omitted_asset_ids(ctx)
    if omitted:
        sfx = sorted(a for a in sfx if a not in omitted)

    if empty_speech and hard_speech:
        msg = f"{stage}: mix completeness — empty speech assembly (hard fail)"
        ctx.log(msg, level="error", stage=stage, detail=f"flow={flow}")
        raise RuntimeError(msg)

    if not vo and not sfx:
        return

    parts: list[str] = []
    if vo:
        parts.append(f"missing VO: {vo}")
    if retried:
        parts.append(f"retried_once: {retried}")
    if sfx:
        parts.append(f"missing/placeholder SFX: {sfx}")

    message = f"{stage}: mix completeness — {'; '.join(parts)}"
    mode = completeness_gate_mode()

    # HAU speech-first: beds/SFX deferred until MusicGen admit + remaster —
    # never block seating assembly on missing theme/SFX (exec_13170).
    beds_deferred = False
    try:
        from interview_mux.mix_junction_seat import beds_deferred_for_mix

        beds_deferred = bool(beds_deferred_for_mix(ctx))
        if beds_deferred:
            soft_sfx = True
    except Exception:
        pass

    # R3-A: full-auto / production refuse placeholder music once beds are owed
    # (speech-first deferred seating stays soft).
    if not beds_deferred:
        try:
            from interview_mux.automation_run import is_full_auto_run

            meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
            if isinstance(meta, dict) and (
                is_full_auto_run(meta)
                or meta.get("production")
                or meta.get("full_auto_production_parity")
            ):
                soft_sfx = False
        except Exception:
            pass

    # Last-chance mix retry already ran (or is the policy): warn, do not hard-block ship.
    block_for_vo = (
        bool(vo)
        and hard_vo
        and not last_chance
        and (mode == "block" or first_try_mode_enabled())
    )
    block_for_sfx = bool(sfx) and mode == "block" and not soft_sfx

    if block_for_vo or block_for_sfx:
        ctx.log(message, level="error", stage=stage, detail=f"flow={flow} mode=block")
        raise RuntimeError(
            f"{stage}: cannot continue with missing mix assets ({'; '.join(parts)}). "
            "Record VO, regenerate SFX, or adjust mix.completeness_gate."
        )

    ctx.log(message, level="warning", stage=stage, detail=f"flow={flow} mode=warn soft_sfx={soft_sfx} retried_once={bool(retried)}")


def _music_omitted_asset_ids(ctx: RunContext) -> set[str]:
    """Honest limbo / fail-closed music omits are not completeness blockers."""
    out: set[str] = set()
    try:
        if ctx.artifact_exists("operator/music_omitted.json"):
            doc = ctx.read_json("operator/music_omitted.json")
            for row in (doc.get("omitted") or []) if isinstance(doc, dict) else []:
                if isinstance(row, dict) and row.get("asset_id"):
                    out.add(str(row["asset_id"]))
    except Exception:
        pass
    try:
        if ctx.artifact_exists("run_meta.json"):
            meta = ctx.read_json("run_meta.json")
            if isinstance(meta, dict):
                for aid in meta.get("music_omitted_asset_ids") or []:
                    if aid:
                        out.add(str(aid))
    except Exception:
        pass
    return out


def _missing_sfx_from_mmaudio_qa(ctx: RunContext) -> set[str]:
    rel = "sound_design/mmaudio_qa.json"
    if not ctx.artifact_exists(rel):
        return set()
    doc = ctx.read_json(rel)
    rows = doc.get("assets") if isinstance(doc, dict) else []
    out: set[str] = set()
    omitted = _music_omitted_asset_ids(ctx)
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        aid = str(row.get("asset_id") or "").strip()
        if not aid or aid in omitted:
            continue
        status = str(row.get("generation_status") or "").lower()
        if status in {"failed", "placeholder"}:
            out.add(aid)
            continue
        if row.get("silence_detected") is True:
            out.add(aid)
    return out
