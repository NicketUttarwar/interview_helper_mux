"""Config for the per-run timeline optimizer daemon."""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config


def optimizer_cfg() -> dict[str, Any]:
    root = merged_config()
    mastering = root.get("mastering") if isinstance(root.get("mastering"), dict) else {}
    cfg = mastering.get("timeline_optimizer") if isinstance(mastering, dict) else None
    if not isinstance(cfg, dict):
        cfg = {}
    return {
        "enabled": bool(cfg.get("enabled", True)),
        # Mode C: keep going after shippable master; operator can stop / take best
        "mode": str(cfg.get("mode") or "endless_daemon"),
        # Mutation surface 4
        "mutation_surface": str(cfg.get("mutation_surface") or "maximum"),
        "auto_start_after_mix": bool(cfg.get("auto_start_after_mix", True)),
        "max_generations_soft": int(cfg.get("max_generations_soft") or 48),
        "max_llm_proposals": int(cfg.get("max_llm_proposals") or 8),
        "llm_every_n_gens": int(cfg.get("llm_every_n_gens") or 3),
        "sleep_ms": int(cfg.get("sleep_ms") or 750),
        "plateau_gens": int(cfg.get("plateau_gens") or 6),
        "min_score_delta": float(cfg.get("min_score_delta") or 0.75),
        "auto_promote_on_plateau": bool(cfg.get("auto_promote_on_plateau", True)),
        "auto_promote_remaster": bool(cfg.get("auto_promote_remaster", True)),
        "always_auto_apply_best": bool(cfg.get("always_auto_apply_best", True)),
        "beam_width": int(cfg.get("beam_width") or 4),
        "archive_max": int(cfg.get("archive_max") or 24),
        "block_finalize_until_take_or_skip": bool(
            cfg.get("block_finalize_until_take_or_skip", False)
        ),
        "use_llm_proposer": bool(cfg.get("use_llm_proposer", True)),
    }


def optimizer_live_mutate_blocked(ctx: Any) -> bool:
    """True when full-auto/operator skip forbids live selection rewrites after mix.

    Also blocks when air-order is frozen until named unlock_air_order_freeze.
    """
    if ctx is None:
        return False
    try:
        from interview_mux.delivery_guardrails import air_order_frozen

        if air_order_frozen(ctx):
            return True
    except Exception:
        pass
    try:
        if not ctx.artifact_exists("run_meta.json"):
            return False
        meta = ctx.read_json("run_meta.json") or {}
    except Exception:
        return False
    if not isinstance(meta, dict):
        return False
    return bool(
        meta.get("timeline_optimizer_skipped")
        or meta.get("e2e_skip_optimizer_remaster")
    )
