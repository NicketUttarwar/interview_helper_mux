"""Duration-scaled air-order integrity caps and per-run resolved policy."""

from __future__ import annotations

import math
from typing import Any

from interview_mux.config import merged_config
from interview_mux.interview_duration_policy import duration_tier, transcript_duration_ms
from interview_mux.run_context import RunContext
from interview_mux.selection_order_repair import _parent_seg_id

DEFAULT_OPENING_WINDOW_MS = 180_000
DEFAULT_OPENING_AIR_SLOTS = 6
DEFAULT_OPENING_BODY_START_INDEX = 3
DEFAULT_REVERSE_JUMP_MARGIN_MS = 300_000


def air_order_integrity_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    mastering = (cfg or merged_config()).get("mastering") or {}
    raw = mastering.get("air_order_integrity") if isinstance(mastering, dict) else None
    return dict(raw) if isinstance(raw, dict) else {}


def _cfg_int(cfg: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(cfg.get(key, default))
    except (TypeError, ValueError):
        return default


def _cfg_float(cfg: dict[str, Any], key: str, default: float | None) -> float | None:
    val = cfg.get(key, default)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _cfg_bool(cfg: dict[str, Any], key: str, default: bool) -> bool:
    val = cfg.get(key, default)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(value)))


def _resolve_scaled_ms(
    cfg: dict[str, Any],
    *,
    static_key: str,
    static_default: int,
    ratio_key: str,
    min_key: str,
    min_default: int,
    max_key: str,
    max_default: int,
    source_duration_ms: int,
) -> int:
    static = _cfg_int(cfg, static_key, static_default)
    lo = _cfg_int(cfg, min_key, min_default)
    hi = _cfg_int(cfg, max_key, max_default)
    ratio = _cfg_float(cfg, ratio_key, None)
    if ratio is not None and source_duration_ms > 0:
        scaled = int(math.ceil(source_duration_ms * ratio))
        return _clamp_int(scaled, lo, hi)
    return _clamp_int(static, lo, hi)


def _opening_stats(
    selection: dict[str, Any] | None,
    *,
    opening_window_ms: int,
    starts: dict[str, int] | None,
) -> tuple[int, int]:
    """Return (opening_families_on_air, opening_fragments_on_air)."""
    if not selection or not starts:
        return 0, 0
    from interview_mux.selection_order_repair import resolved_source_start_ms

    ordered = [str(s) for s in (selection.get("ordered_segment_ids") or []) if s]
    opening_ids: set[str] = set()
    for sid in ordered:
        start = resolved_source_start_ms(sid, starts)
        if start is not None and int(start) < opening_window_ms:
            opening_ids.add(sid)
    if not opening_ids:
        return 0, 0
    families = {_parent_seg_id(s) for s in ordered if s in opening_ids}
    fragments = sum(1 for s in ordered if s in opening_ids)
    return len(families), fragments


def resolve_air_order_policy(
    ctx: RunContext | None,
    *,
    selection: dict[str, Any] | None = None,
    cfg: dict[str, Any] | None = None,
    starts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Return resolved caps + metadata for this run."""
    pol_cfg = air_order_integrity_cfg(cfg)
    source_ms = transcript_duration_ms(ctx) if ctx is not None else 0
    tier = duration_tier(source_ms, cfg) if source_ms > 0 else "unknown"

    opening_window = _resolve_scaled_ms(
        pol_cfg,
        static_key="opening_window_ms",
        static_default=DEFAULT_OPENING_WINDOW_MS,
        ratio_key="opening_window_ratio",
        min_key="opening_window_min_ms",
        min_default=90_000,
        max_key="opening_window_max_ms",
        max_default=300_000,
        source_duration_ms=source_ms,
    )
    reverse_jump_margin = _resolve_scaled_ms(
        pol_cfg,
        static_key="reverse_jump_margin_ms",
        static_default=DEFAULT_REVERSE_JUMP_MARGIN_MS,
        ratio_key="reverse_jump_margin_ratio",
        min_key="reverse_jump_margin_min_ms",
        min_default=120_000,
        max_key="reverse_jump_margin_max_ms",
        max_default=600_000,
        source_duration_ms=source_ms,
    )

    slots_static = _cfg_int(pol_cfg, "opening_air_slots", DEFAULT_OPENING_AIR_SLOTS)
    slots_min = _cfg_int(pol_cfg, "opening_air_slots_min", 4)
    slots_max = _cfg_int(pol_cfg, "opening_air_slots_max", 12)
    opening_air_slots = _clamp_int(slots_static, slots_min, slots_max)

    body_static = _cfg_int(
        pol_cfg, "opening_body_start_index", DEFAULT_OPENING_BODY_START_INDEX
    )
    body_min = _cfg_int(pol_cfg, "opening_body_start_index_min", 2)
    body_max = _cfg_int(pol_cfg, "opening_body_start_index_max", 6)
    body_tier_bump = _cfg_int(pol_cfg, "opening_body_start_index_long_tier_bump", 0)
    if tier == "long" and body_tier_bump:
        body_static += body_tier_bump
    opening_body_start = _clamp_int(body_static, body_min, body_max)

    count_by_family = _cfg_bool(pol_cfg, "count_opening_by_family", True)
    frag_extra_cap = _cfg_int(pol_cfg, "fragmentation_extra_slots", 2)

    if selection is None and ctx is not None and ctx.artifact_exists("master/selection.json"):
        try:
            raw = ctx.read_json("master/selection.json")
            selection = raw if isinstance(raw, dict) else None
        except Exception:
            selection = None

    if starts is None and ctx is not None:
        from interview_mux.air_order_integrity import resolved_segment_starts

        starts = resolved_segment_starts(ctx)

    families_on_air, fragments_on_air = _opening_stats(
        selection, opening_window_ms=opening_window, starts=starts
    )
    if families_on_air and fragments_on_air > families_on_air and frag_extra_cap > 0:
        extra = min(frag_extra_cap, fragments_on_air - families_on_air)
        opening_air_slots = _clamp_int(opening_air_slots + extra, slots_min, slots_max)

    return {
        "source_duration_ms": source_ms,
        "duration_tier": tier,
        "opening_window_ms": opening_window,
        "opening_air_slots": opening_air_slots,
        "reverse_jump_margin_ms": reverse_jump_margin,
        "opening_body_start_index": opening_body_start,
        "count_opening_by_family": count_by_family,
        "opening_families_on_air": families_on_air,
        "opening_fragments_on_air": fragments_on_air,
    }


def policy_value(policy: dict[str, Any] | None, key: str, default: int) -> int:
    if not policy:
        return default
    try:
        return int(policy.get(key, default))
    except (TypeError, ValueError):
        return default
