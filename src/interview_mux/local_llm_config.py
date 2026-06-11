"""Configuration helpers for the on-device MLX local LLM tier."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config, repo_root

DEFAULT_MODEL_ID = "mlx-community/Llama-3.2-3B-Instruct-4bit"
LOCAL_FRAMER_PROMPT = "_shared/local-volley-framer.system.txt"
DEFAULT_MODELS_DIR_REL = "ASSETS/local_llm/models"


def local_llm_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    return (cfg or merged_config()).get("local_llm") or {}


def local_llm_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(local_llm_cfg(cfg).get("enabled", True))


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
    """Model HF repo id: secrets > selection.json > config > default."""
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


# P0–P2 stages always escalate to OpenAI (quality-first; see llm-guidance-program.md).
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
        "sound_design_plan_flow1",
        "sound_design_plan_flow2",
        "elevenlabs_prompt_craft",
        "highlight_selection",
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
