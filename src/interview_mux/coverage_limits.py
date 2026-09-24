"""Ratio-based limits for analysis integrity vs delivery compression."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

T = TypeVar("T")

_DEFAULTS: dict[str, float | int] = {
    "analysis_timeline_min_coverage_ratio": 0.85,
    "reanchor_min_coverage_ratio": 0.55,
    "reanchor_min_coverage_ratio_max": 0.85,
    "delivery_output_min_ratio_of_source": 0.10,
    "delivery_output_ideal_ratio_of_source": 0.65,
    "delivery_output_max_ratio_of_source": 1.5,
    "volley_spread_quartile_min_ratio": 0.25,
    "volley_hydrate_max_ratio_of_budget": 0.20,
    "volley_spine_event_max_ratio": 1.0,
    "gap_fill_max_ratio": 0.20,
    "fabricate_max_ratio_per_call": 0.20,
    "fabricate_max_ratio_per_stage": 0.20,
    "synthetic_edit_max_ratio": 0.20,
    "listenability_strict_below_output_ratio": 0.40,
    "coherence_risk_max_ratio": 1.0,
    "investigation_drain_max_ratio": 1.0,
    "disfluency_event_max_ratio": 1.0,
    "shard_target_duration_ms": 120_000,
    "shard_batch_max_ratio": 1.0,
    "segments_in_context_max_ratio": 1.0,
    "stage_data_max_ratio_of_model_context": 0.35,
    "transcript_max_ratio_of_stage_data": 0.60,
    "boundary_timeline_coverage_min_ratio": 0.85,
    "delivery_timeline_min_ratio": 0.10,
    "max_chapters_ratio": 0.15,
    "max_highlight_clips_ratio": 0.08,
    "gap_evaluations_max_ratio": 1.0,
    "gap_pass_segments_max_ratio": 1.0,
    "context_selector_enabled": 0,
}

_SOFT_PROGRESSION_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "lint_coverage_floor_ratio": 0.15,
    "segment_coverage_adaptive": True,
    "shard_min_success_floor_ratio": 0.35,
    "pre_master_soft_fail": True,
    "non_blocking_lint_substrings": [
        "segment_coverage_ratio",
        "cross_artifact_refs_valid",
        "truncation_requires_decompose",
        "confidence_gte_min",
        "generic_theme",
        "topic without evidence",
        "key_claim without evidence",
        "post_listen failed",
        "mmaudio_qa placeholder",
        "missing wav for asset_id",
        "time gap",
        "no boundaries",
        "time gaps",
        "boundary timeline coverage",
    ],
}


def coverage_limits_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved = cfg or merged_config()
    analysis = resolved.get("analysis") or {}
    block = dict(_DEFAULTS)
    block.update(analysis.get("coverage_limits") or {})
    ctx_legacy = analysis.get("context") or {}
    if "max_shard_batches" in ctx_legacy and "shard_batch_ceiling" not in block:
        block["shard_batch_ceiling"] = int(ctx_legacy["max_shard_batches"])
    if "content_brief_reanchor_min_coverage_ratio" in ctx_legacy:
        block.setdefault(
            "reanchor_min_coverage_ratio",
            float(ctx_legacy["content_brief_reanchor_min_coverage_ratio"]),
        )
    delivery = analysis.get("delivery_brief") or {}
    if "ideal_fraction_of_source" in delivery:
        block.setdefault("delivery_output_ideal_ratio_of_source", float(delivery["ideal_fraction_of_source"]))
    if "max_ratio_of_source" in delivery:
        block.setdefault("delivery_output_max_ratio_of_source", float(delivery["max_ratio_of_source"]))
    if "min_ratio_of_source" in delivery:
        block.setdefault("delivery_output_min_ratio_of_source", float(delivery["min_ratio_of_source"]))
    selector = analysis.get("context_selector") or {}
    if "enabled" in selector:
        block["context_selector_enabled"] = 1 if selector.get("enabled") else 0
    return block


def _float(cfg: dict[str, Any], key: str, default: float) -> float:
    val = cfg.get(key, default)
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _int(cfg: dict[str, Any], key: str, default: int) -> int:
    val = cfg.get(key, default)
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def ratio_cap(count: int, ratio: float, *, ceiling: int | None = None, floor: int = 1) -> int:
    if count <= 0:
        return 0
    if ratio >= 1.0:
        cap = count
    else:
        cap = max(floor, int(round(count * max(0.0, ratio))))
    if ceiling is not None:
        cap = min(cap, ceiling)
    return min(cap, count)


def spread_sample(
    items: list[T],
    cap: int,
    *,
    time_key: Callable[[T], int] | None = None,
) -> list[T]:
    """Evenly spread sample across timeline (or list order when no time_key)."""
    if cap <= 0 or not items:
        return []
    if len(items) <= cap:
        return list(items)
    if time_key is None:
        step = len(items) / cap
        return [items[int(i * step)] for i in range(cap)]

    keyed = sorted(items, key=time_key)
    max_t = max(time_key(x) for x in keyed) or 1
    buckets = max(4, min(12, cap))
    bin_size = max(max_t // buckets, 1)
    per_bin: dict[int, list[T]] = {}
    for item in keyed:
        b = min(time_key(item) // bin_size, buckets - 1)
        per_bin.setdefault(b, []).append(item)

    picked: list[T] = []
    while len(picked) < cap:
        progressed = False
        for b in sorted(per_bin.keys()):
            if not per_bin[b]:
                continue
            picked.append(per_bin[b].pop(0))
            progressed = True
            if len(picked) >= cap:
                break
        if not progressed:
            break
    if len(picked) < cap:
        seen = {id(x) for x in picked}
        for item in keyed:
            if id(item) in seen:
                continue
            picked.append(item)
            if len(picked) >= cap:
                break
    return picked[:cap]


def spread_quartile_coverage(items: list[Any], cap: int, *, time_key: Callable[[Any], int]) -> list[Any]:
    if cap <= 0 or not items:
        return []
    if len(items) <= cap:
        return list(items)
    quartiles = 4
    per_q = max(1, cap // quartiles)
    max_t = max(time_key(x) for x in items) or 1
    q_size = max(max_t // quartiles, 1)
    buckets: dict[int, list[Any]] = {i: [] for i in range(quartiles)}
    for item in items:
        q = min(time_key(item) // q_size, quartiles - 1)
        buckets[q].append(item)
    picked: list[Any] = []
    for q in range(quartiles):
        chunk = buckets[q][:per_q]
        picked.extend(chunk)
        if len(picked) >= cap:
            return picked[:cap]
    return spread_sample(items, cap, time_key=time_key)


def duration_scaled(base: int, duration_ms: int, *, ref_ms: int = 3_600_000) -> int:
    if duration_ms <= 0 or ref_ms <= 0:
        return base
    scale = max(0.25, min(4.0, duration_ms / ref_ms))
    return max(1, int(round(base * scale)))


def output_ratio_of_source(output_ms: int, source_ms: int) -> float:
    if source_ms <= 0:
        return 1.0 if output_ms > 0 else 0.0
    return min(1.0, max(0.0, output_ms / source_ms))


def listenability_tier(output_ratio: float, cfg: dict[str, Any] | None = None) -> str:
    limits = coverage_limits_cfg(cfg)
    strict_below = _float(limits, "listenability_strict_below_output_ratio", 0.40)
    if output_ratio < strict_below:
        return "strict"
    if output_ratio < _float(limits, "delivery_output_ideal_ratio_of_source", 0.65):
        return "normal"
    return "relaxed"


def max_shard_batches(cfg: dict[str, Any] | None = None) -> int:
    limits = coverage_limits_cfg(cfg)
    ctx = (merged_config().get("analysis") or {}).get("context") or {}
    ceiling = _int(limits, "shard_batch_ceiling", int(ctx.get("max_shard_batches", ctx.get("max_transcript_shards", 12))))
    return max(1, ceiling)


def shard_batch_cap(plan_len: int, cfg: dict[str, Any] | None = None) -> int:
    limits = coverage_limits_cfg(cfg)
    ratio = _float(limits, "shard_batch_max_ratio", 1.0)
    ceiling = max_shard_batches(cfg)
    return ratio_cap(plan_len, ratio, ceiling=ceiling)


def volley_spine_event_cap(total_events: int, cfg: dict[str, Any] | None = None) -> int:
    limits = coverage_limits_cfg(cfg)
    ratio = _float(limits, "volley_spine_event_max_ratio", 1.0)
    if ratio >= 1.0:
        return total_events
    legacy = 40
    cap = ratio_cap(total_events, ratio, ceiling=legacy * 3, floor=legacy // 2)
    return max(cap, min(total_events, legacy))


def gap_fill_cap(total: int, cfg: dict[str, Any] | None = None) -> int:
    limits = coverage_limits_cfg(cfg)
    ratio = _float(limits, "gap_fill_max_ratio", 1.0)
    if ratio >= 1.0:
        return max(total, 1)
    return ratio_cap(total, ratio, floor=1)


def fabricate_cap(total: int, cfg: dict[str, Any] | None = None, *, per_call: bool = True) -> int:
    limits = coverage_limits_cfg(cfg)
    key = "fabricate_max_ratio_per_call" if per_call else "fabricate_max_ratio_per_stage"
    return ratio_cap(total, _float(limits, key, 0.20), floor=1)


def coherence_risk_cap(total: int, cfg: dict[str, Any] | None = None) -> int:
    limits = coverage_limits_cfg(cfg)
    return ratio_cap(total, _float(limits, "coherence_risk_max_ratio", 1.0), floor=1)


def segments_in_context_cap(total: int, cfg: dict[str, Any] | None = None) -> int:
    limits = coverage_limits_cfg(cfg)
    ctx = (merged_config().get("analysis") or {}).get("context") or {}
    ceiling = int(ctx.get("max_segments_in_context", 100))
    return ratio_cap(total, _float(limits, "segments_in_context_max_ratio", 1.0), ceiling=ceiling)


def reanchor_coverage_denominator(manifest_ids: set[str], ctx: RunContext) -> set[str]:
    if not manifest_ids or not ctx.artifact_exists("segments/manifest.json"):
        return manifest_ids
    manifest = ctx.read_json("segments/manifest.json")
    denom: set[str] = set()
    skip_types = {"interviewer_reaction"}
    for seg in manifest.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        sid = str(seg.get("segment_id") or "")
        if sid not in manifest_ids:
            continue
        seg_type = str(seg.get("type") or "").lower()
        tags = seg.get("topic_tags") or []
        if seg_type in skip_types and not tags:
            continue
        denom.add(sid)
    return denom or manifest_ids


def reanchor_min_coverage_ratio(
    manifest_ids: set[str],
    ctx: RunContext,
    rubric: dict[str, Any],
    cfg: dict[str, Any] | None = None,
) -> float:
    limits = coverage_limits_cfg(cfg)
    configured = rubric.get("min_segment_coverage_ratio")
    if configured is not None:
        return float(configured)
    fallback = _float(limits, "reanchor_min_coverage_ratio", 0.55)
    max_ratio = _float(limits, "reanchor_min_coverage_ratio_max", 0.85)
    if len(manifest_ids) < 5:
        return 1.0
    tagged = 0
    if ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")
        for seg in manifest.get("segments") or []:
            if isinstance(seg, dict) and seg.get("topic_tags"):
                tagged += 1
    total = len(manifest_ids)
    if total <= 0:
        return fallback
    tag_ratio = tagged / total
    return min(max_ratio, max(fallback, 0.4 + tag_ratio * 0.35))


def analysis_timeline_min_ratio(cfg: dict[str, Any] | None = None) -> float:
    return _float(coverage_limits_cfg(cfg), "analysis_timeline_min_coverage_ratio", 0.85)


def delivery_output_min_ratio(cfg: dict[str, Any] | None = None) -> float:
    return _float(coverage_limits_cfg(cfg), "delivery_output_min_ratio_of_source", 0.10)


def delivery_output_ideal_ratio(cfg: dict[str, Any] | None = None) -> float:
    return _float(coverage_limits_cfg(cfg), "delivery_output_ideal_ratio_of_source", 0.65)


def delivery_output_max_ratio(cfg: dict[str, Any] | None = None) -> float:
    return _float(coverage_limits_cfg(cfg), "delivery_output_max_ratio_of_source", 1.5)


def soft_progression_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    limits = coverage_limits_cfg(cfg)
    block = dict(_SOFT_PROGRESSION_DEFAULTS)
    raw = limits.get("soft_progression")
    if isinstance(raw, dict):
        block.update(raw)
    return block


def soft_progression_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(soft_progression_cfg(cfg).get("enabled", True))


def is_non_blocking_lint(error: str, cfg: dict[str, Any] | None = None) -> bool:
    if not soft_progression_enabled(cfg):
        return False
    low = str(error or "").lower()
    for pat in soft_progression_cfg(cfg).get("non_blocking_lint_substrings") or []:
        if str(pat).lower() in low:
            return True
    return False


def partition_lint_errors(
    errors: list[str],
    cfg: dict[str, Any] | None = None,
) -> tuple[list[str], list[str]]:
    blocking: list[str] = []
    warnings: list[str] = []
    for err in errors:
        if is_non_blocking_lint(err, cfg):
            warnings.append(err)
        else:
            blocking.append(err)
    return blocking, warnings


def segment_coverage_min_ratio(
    stage_key: str,
    manifest_ids: set[str],
    ctx: RunContext,
    rubric: dict[str, Any],
    *,
    cfg: dict[str, Any] | None = None,
) -> float:
    """Adaptive moving minimum — scales down on long interviews, never below floor."""
    manifest_count = len(manifest_ids)
    soft = soft_progression_cfg(cfg)
    floor = _float(soft, "lint_coverage_floor_ratio", 0.15)
    if manifest_count < 5:
        return 1.0
    if stage_key == "content_brief_reanchor":
        base = reanchor_min_coverage_ratio(manifest_ids, ctx, rubric, cfg)
    else:
        configured = rubric.get("min_segment_coverage_ratio")
        base = float(configured) if configured is not None else analysis_timeline_min_ratio(cfg)
    if soft.get("segment_coverage_adaptive", True):
        ref = 40.0
        scale = min(1.0, ref / max(float(manifest_count), ref))
        base = max(floor, base * (0.45 + 0.55 * scale))
    return max(floor, base)


def effective_shard_min_success_ratio(plan_len: int, cfg: dict[str, Any] | None = None) -> float:
    from interview_mux.llm_flow_hardening import flow_hardening_cfg

    configured = float(flow_hardening_cfg(cfg).get("shard_min_success_ratio", 0.75))
    if not soft_progression_enabled(cfg):
        return configured
    soft = soft_progression_cfg(cfg)
    floor = _float(soft, "shard_min_success_floor_ratio", 0.35)
    if plan_len <= 1:
        return 1.0
    if plan_len <= 4:
        return min(configured, max(floor, 0.5))
    adaptive = max(floor, configured * (4.0 / float(plan_len)) ** 0.3)
    return min(configured, adaptive)


def ratio_cap_from_context_key(
    total: int,
    context_key: str,
    *,
    default_ceiling: int,
    ratio_key: str,
    cfg: dict[str, Any] | None = None,
) -> int:
    """Map legacy fixed context caps to moving ratio caps."""
    limits = coverage_limits_cfg(cfg)
    ctx_cfg = (merged_config().get("analysis") or {}).get("context") or {}
    ceiling = int(ctx_cfg.get(context_key, default_ceiling))
    ratio = _float(limits, ratio_key, 1.0)
    if ratio >= 1.0 and total <= ceiling:
        return min(total, ceiling) if total else 0
    return ratio_cap(total, ratio, ceiling=ceiling, floor=min(4, ceiling))


def pre_master_soft_fail_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return soft_progression_enabled(cfg) and bool(
        soft_progression_cfg(cfg).get("pre_master_soft_fail", True)
    )


def context_selector_enabled(cfg: dict[str, Any] | None = None) -> bool:
    limits = coverage_limits_cfg(cfg)
    analysis = (merged_config().get("analysis") or {})
    selector = analysis.get("context_selector") or {}
    if "enabled" in selector:
        return bool(selector.get("enabled"))
    return bool(_int(limits, "context_selector_enabled", 0))


__all__ = [
    "analysis_timeline_min_ratio",
    "context_selector_enabled",
    "coverage_limits_cfg",
    "delivery_output_ideal_ratio",
    "delivery_output_max_ratio",
    "delivery_output_min_ratio",
    "duration_scaled",
    "effective_shard_min_success_ratio",
    "fabricate_cap",
    "gap_fill_cap",
    "is_non_blocking_lint",
    "listenability_tier",
    "max_shard_batches",
    "output_ratio_of_source",
    "partition_lint_errors",
    "pre_master_soft_fail_enabled",
    "ratio_cap",
    "ratio_cap_from_context_key",
    "reanchor_coverage_denominator",
    "reanchor_min_coverage_ratio",
    "segment_coverage_min_ratio",
    "segments_in_context_cap",
    "shard_batch_cap",
    "soft_progression_cfg",
    "soft_progression_enabled",
    "spread_quartile_coverage",
    "spread_sample",
    "volley_spine_event_cap",
    "coherence_risk_cap",
]
