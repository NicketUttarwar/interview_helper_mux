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
        "beam_width": int(cfg.get("beam_width") or 4),
        "archive_max": int(cfg.get("archive_max") or 24),
        "block_finalize_until_take_or_skip": bool(
            cfg.get("block_finalize_until_take_or_skip", False)
        ),
        "use_llm_proposer": bool(cfg.get("use_llm_proposer", True)),
    }
