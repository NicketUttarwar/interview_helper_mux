from __future__ import annotations

from typing import Any

from interview_mux.coherence.config import coherence_cfg, int_threshold


def interview_duration_ms(ctx) -> int:
    """Best-effort duration from transcript words or spine windows."""
    if ctx.artifact_exists("transcript/full.json"):
        transcript = ctx.read_json("transcript/full.json")
        words = transcript.get("words") or []
        if words:
            return int(max(float(w.get("end_ms", 0)) for w in words if isinstance(w, dict)))

    from interview_mux.interview_spine.paths import SPINE_PATH

    if ctx.artifact_exists(SPINE_PATH):
        spine = ctx.read_json(SPINE_PATH)
        windows = spine.get("windows") or []
        if windows:
            return int(max(int(w.get("end_ms", 0)) for w in windows if isinstance(w, dict)))

    if ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")
        segs = manifest.get("segments") or []
        if segs:
            return int(max(int(s.get("end_ms", 0)) for s in segs if isinstance(s, dict)))

    return 0


def build_gate(ctx, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    block = coherence_cfg(cfg)
    min_ms = int_threshold(cfg, "min_duration_ms", 1_800_000)
    duration = interview_duration_ms(ctx)
    return {
        "min_duration_ms": min_ms,
        "duration_ms": duration,
        "activated": duration >= min_ms,
    }


def coherence_activated(ctx, cfg: dict[str, Any] | None = None) -> bool:
    return bool(build_gate(ctx, cfg).get("activated"))
