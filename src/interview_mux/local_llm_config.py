"""Configuration helpers for the on-device MLX local LLM tier."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config, repo_root

DEFAULT_MODEL_ID = "mlx-community/Llama-3.2-3B-Instruct-4bit"
LOCAL_FRAMER_PROMPT = "_shared/local-volley-framer.system.txt"
LOCAL_COMPRESSOR_PROMPT = "_shared/local-digest-compressor.system.txt"
LOCAL_ESCALATE_ADVISORY_PROMPT = "_shared/local-escalate-advisory.system.txt"
LOCAL_SHARD_PREP_PROMPT = "_shared/local-shard-packet-prep.system.txt"
DEFAULT_MODELS_DIR_REL = "ASSETS/local_llm/models"

# Quality-defining schema LLM stages only (P0–P2 + critical transitions).
# Housekeeping / compute / deterministic substrate must stay off this set.
QUALITY_LOCAL_ALLOWLIST: frozenset[str] = frozenset(
    {
        # W1 P0
        "speaker_roles",
        "content_context",
        "boundary_detection",
        "segment_classification",
        "content_brief_reanchor",
        # W2 P1
        "missing_framing",
        "optimal_questions",
        "topic_coverage_audit",
        "narrative_arc_plan",
        "full_master_ranking",
        "edl_narrative_audit",
        # W3 P2 + critical polish
        "sound_design_palettes",
        "sound_design_plan",
        "sfx_prompt_craft",
        "transitions",
    }
)

def local_llm_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    return (cfg or merged_config()).get("local_llm") or {}

def local_llm_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(local_llm_cfg(cfg).get("enabled", True))

def capability_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(local_llm_cfg(cfg).get("capability") or {})

def capability_router_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(capability_cfg(cfg).get("enabled", True))

def quality_local_allowlist(cfg: dict[str, Any] | None = None) -> frozenset[str]:
    """Allowlist SoT: code constant unless config override list is non-empty."""
    override = capability_cfg(cfg).get("allowlist") or []
    if isinstance(override, list) and override:
        return frozenset(str(x).strip() for x in override if str(x).strip())
    return QUALITY_LOCAL_ALLOWLIST

def stage_on_quality_allowlist(stage_key: str, cfg: dict[str, Any] | None = None) -> bool:
    return stage_key in quality_local_allowlist(cfg)

def max_local_steps(cfg: dict[str, Any] | None = None) -> int:
    return max(1, int(capability_cfg(cfg).get("max_local_steps", 3)))

def max_local_retries_per_cap(cfg: dict[str, Any] | None = None) -> int:
    # Plan locks retries at 0; clamp any misconfig to zero.
    _ = cfg
    return 0

def planner_fanout_k(cfg: dict[str, Any] | None = None) -> int:
    return max(1, int(capability_cfg(cfg).get("planner_fanout_k", 3)))

def max_enabled_caps(cfg: dict[str, Any] | None = None) -> int:
    return max(1, int(capability_cfg(cfg).get("max_enabled_caps", 4)))

def lx03_min_verify_rate(cfg: dict[str, Any] | None = None) -> float:
    return float(capability_cfg(cfg).get("lx03_min_verify_rate", 0.85))

def lx04_min_agreement(cfg: dict[str, Any] | None = None) -> float:
    return float(capability_cfg(cfg).get("lx04_min_agreement", 0.95))

def lx05_min_verify_rate(cfg: dict[str, Any] | None = None) -> float:
    return float(capability_cfg(cfg).get("lx05_min_verify_rate", 0.85))

def capability_manifest_path() -> Path:
    return repo_root() / "ASSETS" / "local_llm" / "capability_manifest.json"

def overlays_dir() -> Path:
    return repo_root() / "ASSETS" / "local_llm" / "overlays"

def repo_slug(repo_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", repo_id)

def default_models_dir() -> Path:
    return repo_root() / "ASSETS" / "local_llm" / "models"

def default_hf_cache_dir() -> Path:
    return repo_root() / "ASSETS" / "local_llm" / "hf_cache"

def selection_manifest_path() -> Path:
    return repo_root() / "ASSETS" / "local_llm" / "selection.json"

def _resolve_models_dir(cfg: dict[str, Any] | None = None) -> Path:
    llm = local_llm_cfg(cfg)
    custom_dir = str(llm.get("models_dir") or "").strip()
    if custom_dir:
        path = Path(custom_dir)
        if not path.is_absolute():
            path = repo_root() / path
        return path
    env_override = __import__("os").environ.get("LOCAL_LLM_MODELS_DIR", "").strip()
    if env_override:
        return Path(env_override)
    return default_models_dir()

def resolve_model_id(cfg: dict[str, Any] | None = None) -> str:
    """Model HF repo id: selection.json (bootstrap/llmfit) > config > default.

    Optional advanced override: ``LOCAL_LLM_MODEL_ID`` in secrets (not in the
    shipped template — prefer bootstrap so operators need not pin a model).
    """
    secrets = (cfg or merged_config()).get("secrets") or {}
    override = str(secrets.get("LOCAL_LLM_MODEL_ID") or "").strip()
    if override:
        return override

    from interview_mux.local_llm_selection import load_selection_manifest

    manifest = load_selection_manifest()
    if manifest:
        mid = str(manifest.get("model_id") or "").strip()
        if mid:
            return mid

    llm = local_llm_cfg(cfg)
    return str(llm.get("model_id") or DEFAULT_MODEL_ID).strip()

def resolve_model_path(cfg: dict[str, Any] | None = None) -> Path:
    """Resolved directory containing MLX weights."""
    model_id = resolve_model_id(cfg)
    models_dir = _resolve_models_dir(cfg)
    slug_path = models_dir / repo_slug(model_id)
    if slug_path.is_dir():
        return slug_path
    if Path(model_id).is_dir():
        return Path(model_id)
    return slug_path

def max_volley_turns(cfg: dict[str, Any] | None = None) -> int:
    return max(1, int(local_llm_cfg(cfg).get("max_volley_turns", 2)))

def max_tokens(cfg: dict[str, Any] | None = None) -> int:
    return max(64, int(local_llm_cfg(cfg).get("max_tokens", 768)))

def min_confidence(cfg: dict[str, Any] | None = None) -> float:
    return float(local_llm_cfg(cfg).get("min_confidence", 0.6))

def escalate_on_parse_error(cfg: dict[str, Any] | None = None) -> bool:
    return bool(local_llm_cfg(cfg).get("escalate_on_parse_error", True))

def skip_openai_when_local_satisfied(cfg: dict[str, Any] | None = None) -> bool:
    return bool(local_llm_cfg(cfg).get("skip_openai_primary_when_local_satisfied", False))

def apply_to_specialists(cfg: dict[str, Any] | None = None) -> bool:
    return bool(local_llm_cfg(cfg).get("apply_to_specialists", True))

def apply_to_shards(cfg: dict[str, Any] | None = None) -> bool:
    return bool(local_llm_cfg(cfg).get("apply_to_shards", True))

def apply_to_collate(cfg: dict[str, Any] | None = None) -> bool:
    return bool(local_llm_cfg(cfg).get("apply_to_collate", True))

# P0–P2 + critical polish always escalate to OpenAI (quality-first).
# Includes transitions to match ALL_CRITICAL_LLM_STAGES / flow hardening.
ALWAYS_ESCALATE_STAGES = frozenset(
    {
        "speaker_roles",
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
        "sound_design_palettes",
        "sound_design_plan",
        "sfx_prompt_craft",
        "transitions",
    }
)

def force_escalate_stage(stage_key: str) -> bool:
    return stage_key in ALWAYS_ESCALATE_STAGES

def should_frame_task_kind(task_kind: str, profile: str, cfg: dict[str, Any] | None = None) -> bool:
    if not local_llm_enabled(cfg):
        return False
    if task_kind in ("arbiter",):
        return False
    if task_kind == "specialist" and not apply_to_specialists(cfg):
        return False
    if task_kind == "shard" and not apply_to_shards(cfg):
        return False
    if task_kind == "collate" and not apply_to_collate(cfg):
        return False
    return task_kind in ("primary", "shard", "collate", "specialist")
