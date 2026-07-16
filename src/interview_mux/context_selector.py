"""Economy context selector — catalog → select chunk IDs → hydrate within ratio budget."""

from __future__ import annotations

import json
from typing import Any

from interview_mux.config import merged_config
from interview_mux.coverage_limits import (
    context_selector_enabled,
    coverage_limits_cfg,
    spread_sample,
)
from interview_mux.run_context import RunContext


def _selector_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis = (cfg or merged_config()).get("analysis") or {}
    defaults = {"enabled": False, "shadow_log": True, "min_catalog_items": 4}
    return {**defaults, **(analysis.get("context_selector") or {})}


def catalog_from_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for seg in segments:
        if not isinstance(seg, dict) or not seg.get("segment_id"):
            continue
        catalog.append(
            {
                "id": str(seg["segment_id"]),
                "kind": "segment",
                "start_ms": int(seg.get("start_ms") or 0),
                "end_ms": int(seg.get("end_ms") or 0),
                "topic_tags": seg.get("topic_tags") or [],
                "text_preview": str(seg.get("text") or "")[:120],
            }
        )
    return catalog


def select_chunk_ids(
    catalog: list[dict[str, Any]],
    *,
    cap: int,
    stage_key: str | None = None,
) -> list[str]:
    """Deterministic spread selection (v1 — no extra OpenAI call when selector disabled)."""
    if not catalog or cap <= 0:
        return []
    if len(catalog) <= cap:
        return [str(c["id"]) for c in catalog if c.get("id")]
    sampled = spread_sample(catalog, cap, time_key=lambda c: int(c.get("start_ms") or 0))
    return [str(c["id"]) for c in sampled if c.get("id")]


def hydrate_segments(
    segments: list[dict[str, Any]],
    selected_ids: list[str],
) -> list[dict[str, Any]]:
    wanted = set(selected_ids)
    if not wanted:
        return list(segments)
    return [s for s in segments if isinstance(s, dict) and str(s.get("segment_id")) in wanted]


def maybe_select_context_segments(
    ctx: RunContext | None,
    segments: list[dict[str, Any]],
    *,
    cap: int,
    stage_key: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Return (segments, meta). When selector disabled, spread-sample to cap.
    When enabled with shadow_log, log selection without changing behavior until rollout.
    """
    cfg = _selector_cfg()
    limits = coverage_limits_cfg()
    hydrate_ratio = float(limits.get("volley_hydrate_max_ratio_of_budget", 0.20))
    effective_cap = max(1, int(cap * hydrate_ratio)) if hydrate_ratio < 1.0 else cap
    catalog = catalog_from_segments(segments)
    meta: dict[str, Any] = {
        "catalog_size": len(catalog),
        "cap": cap,
        "effective_cap": effective_cap,
        "selector_enabled": context_selector_enabled(),
    }
    if len(catalog) <= effective_cap:
        return segments, meta

    selected_ids = select_chunk_ids(catalog, cap=effective_cap, stage_key=stage_key)
    meta["selected_ids"] = selected_ids
    meta["selection"] = "spread_sample"

    if context_selector_enabled() and not cfg.get("shadow_log", True):
        hydrated = hydrate_segments(segments, selected_ids)
        meta["hydrated_count"] = len(hydrated)
        return hydrated, meta

    if ctx is not None and cfg.get("shadow_log", True) and len(catalog) > effective_cap:
        ctx.log(
            f"context_selector shadow: would select {len(selected_ids)}/{len(catalog)} segments "
            f"for {stage_key or 'stage'}",
            level="info",
            stage=stage_key,
            detail={"selected_ids": selected_ids[:12], "catalog_size": len(catalog)},
        )

    sampled = hydrate_segments(segments, selected_ids)
    return sampled if sampled else spread_sample(segments, effective_cap, time_key=lambda s: int(s.get("start_ms") or 0)), meta


def compact_catalog_json(catalog: list[dict[str, Any]], *, max_items: int = 40) -> str:
    slim = catalog[:max_items]
    return json.dumps(slim, ensure_ascii=False)


__all__ = [
    "catalog_from_segments",
    "compact_catalog_json",
    "hydrate_segments",
    "maybe_select_context_segments",
    "select_chunk_ids",
]
