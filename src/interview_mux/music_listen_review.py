"""G1.5-adjacent music listen gate — approve cold open + one underscore bed before mix."""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

MUSIC_LISTEN_BLOCK = (
    "Music listen approval required before mix. "
    "Listen to the cold open and one underscore bed, then approve in the GUI."
)


def music_listen_required(cfg: dict[str, Any] | None = None) -> bool:
    c = cfg if cfg is not None else merged_config()
    return bool(c.get("g1_5_require_music_listen", False))


def _pick_listen_assets(ctx: RunContext) -> dict[str, str | None]:
    cold: str | None = None
    bed: str | None = None
    assets_dir = ctx.final_path("sound_design", "assets")
    if not assets_dir.is_dir():
        return {"cold_open": None, "underscore": None}
    for path in sorted(assets_dir.glob("*.wav")):
        name = path.stem.lower()
        if path.stat().st_size < 1000:
            continue
        if cold is None and "cold_open" in name:
            cold = path.name
        if bed is None and ("underscore" in name or name.startswith("theme_") and "bed" in name):
            bed = path.name
    # Prefer any theme_underscore-named asset; do not fall back to arbitrary SFX.
    if bed is None:
        for path in sorted(assets_dir.glob("*.wav")):
            name = path.stem.lower()
            if path.stat().st_size >= 1000 and "underscore" in name:
                bed = path.name
                break
    return {"cold_open": cold, "underscore": bed}


def can_run_mix_after_music_listen(ctx: RunContext) -> tuple[bool, str]:
    if not music_listen_required():
        return True, ""
    assets = _pick_listen_assets(ctx)
    # Nothing to listen to yet (e.g. dry mix / tests without theme WAVs) — do not block.
    if not assets.get("cold_open") and not assets.get("underscore"):
        return True, ""
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    review = meta.get("music_listen_review") if isinstance(meta, dict) else None
    if isinstance(review, dict) and review.get("approved"):
        return True, ""
    return False, MUSIC_LISTEN_BLOCK


def require_music_listen_for_mix(ctx: RunContext) -> None:
    ok, message = can_run_mix_after_music_listen(ctx)
    if not ok:
        raise RuntimeError(message)


def set_music_listen_approved(
    ctx: RunContext,
    *,
    approved: bool,
    approved_by: str = "operator",
) -> dict[str, Any]:
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    assets = _pick_listen_assets(ctx)

    def patch(meta: dict[str, Any]) -> None:
        meta["music_listen_review"] = {
            "approved": bool(approved),
            "approved_at": now if approved else None,
            "approved_by": approved_by if approved else None,
            "cold_open_asset": assets.get("cold_open"),
            "underscore_asset": assets.get("underscore"),
        }

    ctx.mutate_run_meta(patch)
    return {
        "approved": bool(approved),
        "cold_open_asset": assets.get("cold_open"),
        "underscore_asset": assets.get("underscore"),
    }


def music_listen_status(ctx: RunContext) -> dict[str, Any]:
    assets = _pick_listen_assets(ctx)
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    review = meta.get("music_listen_review") if isinstance(meta, dict) else {}
    if not isinstance(review, dict):
        review = {}
    required = music_listen_required()
    return {
        "required": required,
        "approved": bool(review.get("approved")),
        "cold_open_asset": review.get("cold_open_asset") or assets.get("cold_open"),
        "underscore_asset": review.get("underscore_asset") or assets.get("underscore"),
        "can_mix": (not required) or bool(review.get("approved")),
    }
