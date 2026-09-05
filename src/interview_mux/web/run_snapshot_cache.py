"""Per-run stage/journey snapshot cache for GET /api/runs/{id}."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from interview_mux.run_context import RunContext


@dataclass
class _CachedRunSnapshot:
    key: tuple[str, int, float]
    stages: list[dict[str, Any]]
    journey: dict[str, Any]
    cached_at: float


_CACHE: dict[str, _CachedRunSnapshot] = {}
_TTL_SEC = 30.0


def _stage_done_mtime(ctx: RunContext) -> float:
    sd = ctx.run_dir / ".stage_done"
    if not sd.is_dir():
        return 0.0
    try:
        return max((p.stat().st_mtime for p in sd.iterdir() if p.is_file()), default=0.0)
    except OSError:
        return 0.0


def _cache_key(ctx: RunContext) -> tuple[str, int, float]:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    version = int(meta.get("snapshot_version") or 0)
    return (ctx.run_id, version, _stage_done_mtime(ctx))


def invalidate_run_snapshot(run_id: str) -> None:
    _CACHE.pop(run_id, None)


def get_or_build_run_snapshot(
    ctx: RunContext,
    *,
    job: dict[str, Any],
    build_stages: Any,
    build_journey: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return cached (stages, journey) or build and store."""
    key = _cache_key(ctx)
    now = time.monotonic()
    hit = _CACHE.get(ctx.run_id)
    # Idle / gate waits: keep snapshot longer to avoid pegging CPU on get_run.
    status = str((job or {}).get("status") or "").lower()
    ttl = 90.0 if status in {"idle", "complete", "gate", "needs_operator"} else _TTL_SEC
    if hit and hit.key == key and (now - hit.cached_at) < ttl:
        return hit.stages, hit.journey

    stages = build_stages()
    journey = build_journey(stages)
    _CACHE[ctx.run_id] = _CachedRunSnapshot(
        key=key,
        stages=stages,
        journey=journey,
        cached_at=now,
    )
    return stages, journey


def clear_run_snapshot_cache() -> None:
    _CACHE.clear()
