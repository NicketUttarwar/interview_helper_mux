"""Optimizer state + Pareto archive under master/optimizer/."""

from __future__ import annotations

import copy
import time
from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext

STATE_REL = "master/optimizer/state.json"
ARCHIVE_REL = "master/optimizer/archive.json"
BEST_REL = "master/optimizer/best_candidate.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def empty_state() -> dict[str, Any]:
    return {
        "version": 1,
        "status": "idle",  # idle|running|paused|stopped|error
        "mode": "endless_daemon",
        "mutation_surface": "maximum",
        "generation": 0,
        "llm_proposals_used": 0,
        "best_score": None,
        "best_candidate_id": None,
        "plateau_streak": 0,
        "started_at": None,
        "updated_at": _now(),
        "stopped_at": None,
        "stop_requested": False,
        "last_error": None,
        "last_mutation": None,
        "promotions": [],
        "run_fingerprint": None,
    }


def load_optimizer_state(ctx: RunContext) -> dict[str, Any]:
    if ctx.artifact_exists(STATE_REL):
        try:
            doc = ctx.read_json(STATE_REL)
            if isinstance(doc, dict):
                return {**empty_state(), **doc}
        except Exception:
            pass
    return empty_state()


def save_optimizer_state(ctx: RunContext, state: dict[str, Any]) -> None:
    out = dict(state)
    out["updated_at"] = _now()
    ctx.write_json(STATE_REL, out)


def load_archive(ctx: RunContext) -> dict[str, Any]:
    if ctx.artifact_exists(ARCHIVE_REL):
        try:
            doc = ctx.read_json(ARCHIVE_REL)
            if isinstance(doc, dict):
                return doc
        except Exception:
            pass
    return {"version": 1, "candidates": []}


def save_archive(ctx: RunContext, archive: dict[str, Any]) -> None:
    ctx.write_json(ARCHIVE_REL, archive)


def load_best(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(BEST_REL):
        return None
    try:
        doc = ctx.read_json(BEST_REL)
        return doc if isinstance(doc, dict) else None
    except Exception:
        return None


def save_best(ctx: RunContext, candidate: dict[str, Any]) -> None:
    ctx.write_json(BEST_REL, candidate)


def seed_candidate_from_run(ctx: RunContext) -> dict[str, Any]:
    """Snapshot current selection (+ optional glue) as generation-0 candidate."""
    sel = (
        ctx.read_json("master/selection.json")
        if ctx.artifact_exists("master/selection.json")
        else {"ordered_segment_ids": []}
    )
    ordered = [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]
    excluded = [str(s) for s in (sel.get("excluded_segment_ids") or []) if s]
    considerable = [
        str(s)
        for s in (
            sel.get("considerable_segment_ids") or sel.get("admitted_story_segment_ids") or []
        )
        if s
    ]
    try:
        from interview_mux.media_ip_cta import admitted_story_segment_ids

        considerable = list(dict.fromkeys([*considerable, *sorted(admitted_story_segment_ids(ctx))]))
    except Exception:
        pass
    gap = (
        ctx.read_json("understanding/gap_report.json")
        if ctx.artifact_exists("understanding/gap_report.json")
        else None
    )
    tr = (
        ctx.read_json("master/transitions.json")
        if ctx.artifact_exists("master/transitions.json")
        else None
    )
    sdp = (
        ctx.read_json("understanding/sound_design_plan.json")
        if ctx.artifact_exists("understanding/sound_design_plan.json")
        else None
    )
    critic = (
        ctx.read_json("master/listen_critic.json")
        if ctx.artifact_exists("master/listen_critic.json")
        else None
    )
    health = (
        ctx.read_json("master/story_health.json")
        if ctx.artifact_exists("master/story_health.json")
        else None
    )
    return {
        "candidate_id": f"seed_{int(time.time())}",
        "generation": 0,
        "source": "seed_mix",
        "mutations": [],
        "ordered_segment_ids": ordered,
        "excluded_segment_ids": excluded,
        "admitted_story_segment_ids": list(considerable),
        "considerable_segment_ids": list(considerable),
        "gap_report": copy.deepcopy(gap) if isinstance(gap, dict) else None,
        "transitions": copy.deepcopy(tr) if isinstance(tr, dict) else None,
        "sound_design_plan": copy.deepcopy(sdp) if isinstance(sdp, dict) else None,
        "score": None,
        "listen_critic": critic if isinstance(critic, dict) else None,
        "story_health": health if isinstance(health, dict) else None,
        "created_at": _now(),
    }


def archive_add(
    archive: dict[str, Any],
    candidate: dict[str, Any],
    *,
    max_keep: int = 24,
) -> dict[str, Any]:
    rows = [c for c in (archive.get("candidates") or []) if isinstance(c, dict)]
    rows.append(candidate)
    rows.sort(key=lambda c: float(c.get("score") or -1e9), reverse=True)
    # Dedup by order fingerprint
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for c in rows:
        fp = "|".join(str(x) for x in (c.get("ordered_segment_ids") or []))
        if fp in seen:
            continue
        seen.add(fp)
        uniq.append(c)
    archive = dict(archive)
    archive["candidates"] = uniq[: max(1, max_keep)]
    archive["version"] = 1
    return archive


def optimizer_status_payload(ctx: RunContext) -> dict[str, Any]:
    state = load_optimizer_state(ctx)
    best = load_best(ctx)
    archive = load_archive(ctx)
    return {
        "status": state.get("status"),
        "mode": state.get("mode"),
        "mutation_surface": state.get("mutation_surface"),
        "generation": state.get("generation"),
        "best_score": state.get("best_score"),
        "best_candidate_id": state.get("best_candidate_id"),
        "plateau_streak": state.get("plateau_streak"),
        "stop_requested": bool(state.get("stop_requested")),
        "running": state.get("status") == "running",
        "archive_count": len(archive.get("candidates") or []),
        "best": {
            "candidate_id": (best or {}).get("candidate_id"),
            "score": (best or {}).get("score"),
            "ordered_segment_ids": (best or {}).get("ordered_segment_ids") or [],
            "mutations": (best or {}).get("mutations") or [],
        }
        if best
        else None,
        "last_mutation": state.get("last_mutation"),
        "last_error": state.get("last_error"),
        "updated_at": state.get("updated_at"),
        "promotions": state.get("promotions") or [],
    }
