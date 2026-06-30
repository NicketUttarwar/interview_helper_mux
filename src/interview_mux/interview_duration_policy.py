"""Interview length tiers and duration-scaled loop budgets.

Tiers (operator model):
  short  — under 15 minutes
  medium — 15 minutes to 1 hour
  long   — over 1 hour (very long: 2h+ gets higher shard cap)
"""

from __future__ import annotations

from typing import Any

import interview_mux.config as config
from interview_mux.run_context import RunContext

MS_PER_MINUTE = 60_000
THIRTY_MIN_MS = 30 * MS_PER_MINUTE
DEFAULT_SHORT_MAX_MS = 15 * MS_PER_MINUTE
DEFAULT_MEDIUM_MAX_MS = 60 * MS_PER_MINUTE
DEFAULT_VERY_LONG_MIN_MS = 2 * 60 * MS_PER_MINUTE


def duration_policy_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis = (cfg or config.merged_config()).get("analysis") or {}
    defaults = {
        "short_max_ms": DEFAULT_SHORT_MAX_MS,
        "medium_max_ms": DEFAULT_MEDIUM_MAX_MS,
        "very_long_min_ms": DEFAULT_VERY_LONG_MIN_MS,
        "primary_attempts_base": 6,
        "primary_attempts_per_30min_above_short": 1,
        "primary_attempts_cap": 16,
        "shard_calls_base": 24,
        "shard_calls_very_long": 48,
        "boundary_micro_segment_min_ms": DEFAULT_SHORT_MAX_MS,
    }
    raw = analysis.get("duration_policy") or {}
    return {**defaults, **raw}


def transcript_duration_ms(ctx: RunContext | None) -> int:
    if ctx is None:
        return 0
    if ctx.artifact_exists("transcript/full.json"):
        doc = ctx.read_json("transcript/full.json")
        if isinstance(doc, dict) and doc.get("duration_ms"):
            return int(doc["duration_ms"])
    return 0


def duration_tier(duration_ms: int, cfg: dict[str, Any] | None = None) -> str:
    pol = duration_policy_cfg(cfg)
    short_max = int(pol["short_max_ms"])
    medium_max = int(pol["medium_max_ms"])
    if duration_ms < short_max:
        return "short"
    if duration_ms < medium_max:
        return "medium"
    return "long"


def primary_attempt_cap(ctx: RunContext | None = None, cfg: dict[str, Any] | None = None) -> int:
    """Dynamic primary routing budget: base + 1 per 30m above short tier, capped."""
    pol = duration_policy_cfg(cfg)
    base = int(pol["primary_attempts_base"])
    cap = int(pol["primary_attempts_cap"])
    per_block = int(pol["primary_attempts_per_30min_above_short"])
    short_max = int(pol["short_max_ms"])

    fh = ((cfg or config.merged_config()).get("analysis") or {}).get("flow_hardening") or {}
    static_fallback = fh.get("max_primary_attempts_per_stage")

    duration = transcript_duration_ms(ctx)
    if duration <= 0:
        if static_fallback is not None:
            return int(static_fallback)
        return base

    if duration <= short_max:
        dynamic = base
    else:
        blocks = (duration - short_max) // THIRTY_MIN_MS
        dynamic = base + int(blocks) * per_block

    dynamic = min(cap, dynamic)
    if static_fallback is not None:
        return max(int(static_fallback), dynamic)
    return dynamic


def max_per_segment_shard_calls(ctx: RunContext | None = None, cfg: dict[str, Any] | None = None) -> int:
    pol = duration_policy_cfg(cfg)
    base = int(pol["shard_calls_base"])
    boosted = int(pol["shard_calls_very_long"])
    very_long_min = int(pol["very_long_min_ms"])
    duration = transcript_duration_ms(ctx)
    if duration >= very_long_min:
        return boosted
    return base


def boundary_micro_segment_min_ms(cfg: dict[str, Any] | None = None) -> int:
    return int(duration_policy_cfg(cfg).get("boundary_micro_segment_min_ms", DEFAULT_SHORT_MAX_MS))


def content_context_long_interview_ms(cfg: dict[str, Any] | None = None) -> int:
    analysis = (cfg or config.merged_config()).get("analysis") or {}
    thresholds = analysis.get("prompt_thresholds") or {}
    return int(
        thresholds.get("content_context_topic_anchor_min_duration_ms", DEFAULT_SHORT_MAX_MS)
    )
