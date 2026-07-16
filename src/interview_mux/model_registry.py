from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from interview_mux.config import merged_config

TIER_ORDER = ("economy", "standard", "flagship")

DEFAULT_TIER_MODELS: dict[str, str] = {
    "economy": "gpt-4o-mini",
    "standard": "gpt-4o",
    "flagship": "o3",
}

# OpenAI reasoning models reject non-default temperature (API error if set).
_REASONING_MODEL_PREFIXES = ("o1", "o3", "o4")

DEFAULT_STAGE_TIERS: dict[str, str] = {
    "speaker_roles": "economy",
    "content_context": "economy",
    "boundary_detection": "standard",
    "segment_classification": "standard",
    "sound_design_palettes": "economy",
    "missing_framing": "flagship",
    "optimal_questions": "flagship",
    "topic_coverage_audit": "flagship",
    "narrative_arc_plan": "flagship",
    "full_master_ranking": "flagship",
    "edl_narrative_audit": "flagship",
    "transitions": "economy",
    "podcast_sfx_brief": "economy",
    "sfx_brief": "economy",
    "_arbiter": "economy",
}

HIGH_SEVERITY_STAGES = {
    "content_context",
    "boundary_detection",
    "segment_classification",
    "content_brief_reanchor",
    "missing_framing",
    "optimal_questions",
    "topic_coverage_audit",
    "narrative_arc_plan",
    "full_master_ranking",
    "edl_narrative_audit",
    "sound_design_plan",
}

LOW_SEVERITY_STAGES = {
    "speaker_roles",
    "transitions",
    "podcast_sfx_brief",
    "sfx_brief",
    "sound_design_palettes",
    "sfx_prompt_craft",
    "sfx_prompt_refine",
}

def stage_severity(stage_key: str) -> str:
    """Editorial impact tier for local LLM escalation (low | medium | high)."""
    if stage_key in HIGH_SEVERITY_STAGES:
        return "high"
    if stage_key in LOW_SEVERITY_STAGES:
        return "low"
    return "medium"

@dataclass(frozen=True)
class ResolvedModel:
    stage_key: str
    task_kind: str
    tier: str
    model_id: str

def supports_custom_temperature(model_id: str) -> bool:
    """Whether chat.completions accepts an explicit temperature for this model."""
    mid = model_id.lower().strip()
    return not any(mid.startswith(prefix) for prefix in _REASONING_MODEL_PREFIXES)

def temperature_for_chat(model_id: str, task_kind: str) -> float | None:
    """Temperature for chat.completions, or None to omit (reasoning models use API default)."""
    if not supports_custom_temperature(model_id):
        return None
    return 0.0 if task_kind == "arbiter" else 0.2

def next_tier(tier: str) -> str:
    try:
        idx = TIER_ORDER.index(tier)
    except ValueError:
        return "standard"
    return TIER_ORDER[min(idx + 1, len(TIER_ORDER) - 1)]

def resolve_model(
    stage_key: str,
    task_kind: str = "primary",
    *,
    bump_tier: bool = False,
    explicit_tier: str | None = None,
) -> ResolvedModel:
    cfg = merged_config()
    models = cfg.get("models") or {}
    secrets = cfg.get("secrets") or {}

    stage_override = models.get(stage_key)
    if (
        isinstance(stage_override, str)
        and task_kind == "primary"
        and not explicit_tier
        and not bump_tier
    ):
        return ResolvedModel(stage_key=stage_key, task_kind=task_kind, tier="explicit", model_id=stage_override)

    tier = explicit_tier or _tier_for_task(stage_key, task_kind, cfg)
    if bump_tier:
        tier = next_tier(tier)
    tier_model = _resolve_tier_model(models, secrets, tier)
    return ResolvedModel(stage_key=stage_key, task_kind=task_kind, tier=tier, model_id=tier_model)

def _tier_for_task(stage_key: str, task_kind: str, cfg: dict[str, Any]) -> str:
    models = cfg.get("models") or {}
    if task_kind in ("arbiter", "shard", "specialist"):
        return "economy"
    stage_tier = _stage_default_tier(models, stage_key)
    if task_kind == "collate":
        if stage_key in HIGH_SEVERITY_STAGES and TIER_ORDER.index(stage_tier) < TIER_ORDER.index("standard"):
            return "standard"
        return stage_tier
    return stage_tier

def _stage_default_tier(models: dict[str, Any], stage_key: str) -> str:
    stages = models.get("stages") or {}
    if isinstance(stages.get(stage_key), dict):
        tier = str(stages[stage_key].get("tier") or "").strip()
        if tier in TIER_ORDER:
            return tier
    return DEFAULT_STAGE_TIERS.get(stage_key, "economy")

def _resolve_tier_model(models: dict[str, Any], secrets: dict[str, str], tier: str) -> str:
    tiers = models.get("tiers") or {}
    env_map = {
        "economy": "OPENAI_TIER_ECONOMY",
        "standard": "OPENAI_TIER_STANDARD",
        "flagship": "OPENAI_TIER_FLAGSHIP",
    }
    env_val = secrets.get(env_map.get(tier, ""), "")
    if env_val:
        return env_val
    if isinstance(tiers.get(tier), str) and tiers.get(tier):
        return str(tiers[tier])
    return DEFAULT_TIER_MODELS.get(tier, "gpt-4o-mini")
