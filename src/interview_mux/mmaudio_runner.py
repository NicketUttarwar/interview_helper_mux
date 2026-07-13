"""MMAudio text-to-audio generation via isolated local venv."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.local_install import mmaudio_repo_dir
from interview_mux.local_runtime import LocalRuntimeUnavailable, run_runtime_script
from interview_mux.run_context import RunContext
from interview_mux.sonic_context import load_sonic_context

DEFAULT_CFG_BY_ROLE: dict[str, float] = {
    "ambient_bed": 3.8,
    "chapter_stinger": 4.8,
    "transition_stinger": 4.6,
    "cold_open": 5.0,
    "vo_bridge": 4.2,
    "accent_foley": 4.5,
}

ALLOWED_VARIANTS = frozenset(
    {"small_16k", "small_44k", "medium_44k", "large_44k", "large_44k_v2"},
)


class MMAudioUnavailable(LocalRuntimeUnavailable):
    """Raised when MMAudio local stack is missing or generation fails."""


def mmaudio_cfg() -> dict[str, Any]:
    return merged_config().get("mmaudio") or {}


def _duration_band_for_role(role: str | None, *, ctx: RunContext | None = None) -> tuple[float, float] | None:
    key = str(role or "").strip()
    if not key:
        return None
    if ctx is not None:
        sonic = load_sonic_context(ctx) or {}
        mix_policy = sonic.get("mix_policy") if isinstance(sonic.get("mix_policy"), dict) else {}
        by_role = mix_policy.get("duration_bands_by_role") if isinstance(mix_policy.get("duration_bands_by_role"), dict) else {}
        band = by_role.get(key)
        if isinstance(band, list) and len(band) == 2:
            return float(band[0]), float(band[1])
    by_role_cfg = mmaudio_cfg().get("duration_bands_by_role")
    if isinstance(by_role_cfg, dict):
        band = by_role_cfg.get(key)
        if isinstance(band, list) and len(band) == 2:
            return float(band[0]), float(band[1])
    return None


def clamp_duration_seconds(
    duration_seconds: float,
    *,
    role: str | None = None,
    ctx: RunContext | None = None,
) -> float:
    cfg = mmaudio_cfg()
    min_s = float(cfg.get("min_duration_sec", 3.0))
    max_s = float(cfg.get("max_duration_sec", 8.0))
    duration = float(duration_seconds)
    band = _duration_band_for_role(role, ctx=ctx)
    if band:
        min_s = max(min_s, float(band[0]))
        max_s = min(max_s, float(band[1]))
        if max_s < min_s:
            max_s = min_s
    return max(min_s, min(max_s, duration))


def apply_prompt_influence_to_text(text: str, prompt_influence: float | None) -> str:
    """Deprecated prose append — use resolve_cfg_strength instead unless legacy_influence_prose."""
    if prompt_influence is None:
        return text
    if prompt_influence >= 0.4:
        return (
            f"{text}\n\nFollow the description precisely with minimal improvisation; "
            "stay close to the specified texture, length, and mix role."
        )
    if prompt_influence <= 0.25:
        return (
            f"{text}\n\nAllow subtle variation while preserving the overall character "
            "and podcast-safe mix role."
        )
    return text


def resolve_cfg_strength(
    *,
    role: str | None = None,
    prompt_influence: float | None = None,
    explicit_cfg: float | None = None,
    cfg: dict[str, Any] | None = None,
) -> float:
    mcfg = cfg if cfg is not None else mmaudio_cfg()
    if explicit_cfg is not None:
        return max(2.0, min(8.0, float(explicit_cfg)))

    role_map = mcfg.get("cfg_strength_by_role") or {}
    base = float(role_map.get(role or "", mcfg.get("cfg_strength_default", 4.5)))
    if role and role in role_map:
        base = float(role_map[role])
    elif role and role in DEFAULT_CFG_BY_ROLE:
        base = DEFAULT_CFG_BY_ROLE[role]

    if prompt_influence is None:
        return base
    influence = float(prompt_influence)
    if influence <= 0.25:
        return max(2.0, base - 0.6)
    if influence >= 0.4:
        return min(8.0, base + 0.5)
    return base


def resolve_num_steps(explicit: int | None = None, cfg: dict[str, Any] | None = None) -> int:
    mcfg = cfg if cfg is not None else mmaudio_cfg()
    if explicit is not None:
        return max(10, min(50, int(explicit)))
    return max(10, min(50, int(mcfg.get("num_steps", 25))))


def resolve_seed(
    *,
    asset_id: str | None = None,
    run_id: str | None = None,
    explicit_seed: int | None = None,
    cfg: dict[str, Any] | None = None,
) -> int:
    mcfg = cfg if cfg is not None else mmaudio_cfg()
    if explicit_seed is not None:
        return int(explicit_seed) & 0x7FFFFFFF

    strategy = str(mcfg.get("seed_strategy", "asset_id_hash"))
    if strategy == "random":
        import random

        return random.randint(0, 0x7FFFFFFF)
    if strategy == "fixed":
        return int(mcfg.get("fixed_seed", 42)) & 0x7FFFFFFF

    key = f"{run_id or ''}:{asset_id or ''}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    return int(digest[:8], 16) & 0x7FFFFFFF


def resolve_variant(explicit: str | None = None, cfg: dict[str, Any] | None = None) -> str:
    mcfg = cfg if cfg is not None else mmaudio_cfg()
    variant = explicit or str(mcfg.get("model_id", "large_44k_v2"))
    if variant not in ALLOWED_VARIANTS:
        return str(mcfg.get("model_id", "large_44k_v2"))
    return variant


def generate_text_to_audio(
    *,
    prompt: str,
    duration_seconds: float,
    output_wav: Path,
    negative_prompt: str = "",
    prompt_influence: float | None = None,
    cfg_strength: float | None = None,
    num_steps: int | None = None,
    seed: int | None = None,
    variant: str | None = None,
    role: str | None = None,
    asset_id: str | None = None,
    run_id: str | None = None,
    ctx: RunContext | None = None,
) -> dict[str, Any]:
    mcfg = mmaudio_cfg()
    duration = clamp_duration_seconds(duration_seconds, role=role, ctx=ctx)
    resolved_variant = resolve_variant(variant, mcfg)
    resolved_cfg = resolve_cfg_strength(
        role=role,
        prompt_influence=prompt_influence,
        explicit_cfg=cfg_strength,
        cfg=mcfg,
    )
    resolved_steps = resolve_num_steps(num_steps, mcfg)
    resolved_seed = resolve_seed(
        asset_id=asset_id,
        run_id=run_id or (ctx.run_id if ctx else None),
        explicit_seed=seed,
        cfg=mcfg,
    )
    device = str(mcfg.get("device", "auto"))

    positive = prompt
    if bool(mcfg.get("legacy_influence_prose", False)):
        positive = apply_prompt_influence_to_text(prompt, prompt_influence)

    repo = mmaudio_repo_dir()
    if not repo.is_dir():
        raise MMAudioUnavailable(f"MMAudio repo missing at {repo}")

    stage_key = "mmaudio_sfx"
    if ctx:
        from interview_mux.operator_trace import log_api_call

        log_api_call(
            "MMAudio",
            f"generate ({resolved_variant}, {duration:.1f}s)",
            ctx=ctx,
            stage=stage_key,
            detail={
                "asset_id": asset_id,
                "role": role,
                "variant": resolved_variant,
                "duration_seconds": duration,
            },
        )

    with tempfile.TemporaryDirectory(prefix="mmaudio_out_") as tmp:
        proc = run_runtime_script(
            "mmaudio",
            "tools/mmaudio_generate.py",
            [
                "--variant",
                resolved_variant,
                "--prompt",
                positive,
                "--negative-prompt",
                negative_prompt or "no vocals, no speech, no lyrics",
                "--duration",
                str(duration),
                "--cfg-strength",
                str(resolved_cfg),
                "--num-steps",
                str(resolved_steps),
                "--seed",
                str(resolved_seed),
                "--device",
                device,
                "--output-wav",
                str(output_wav),
                "--repo",
                str(repo),
                "--work-dir",
                tmp,
            ],
            ctx=ctx,
            stage=stage_key,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()[:500]
            raise MMAudioUnavailable(f"MMAudio generation failed: {err}")

    meta = {
        "provider": "mmaudio",
        "model_id": resolved_variant,
        "variant": resolved_variant,
        "duration_seconds": duration,
        "cfg_strength": resolved_cfg,
        "num_steps": resolved_steps,
        "seed": resolved_seed,
        "sample_rate_hz": 48000,
        "negative_prompt_passed": bool(negative_prompt),
        "repo_dir": str(repo),
        "asset_id": asset_id,
    }
    if ctx:
        ctx.log(
            f"MMAudio generated {output_wav.name}",
            level="success",
            stage=stage_key,
            detail={**meta, "journey_kind": "execute"},
        )
    return meta
