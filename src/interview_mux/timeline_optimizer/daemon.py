"""Endless (mode C) timeline optimizer daemon — per-run search loop."""

from __future__ import annotations

import threading
import time
import traceback
from typing import Any

from interview_mux.run_context import RunContext
from interview_mux.timeline_optimizer.apply import take_best_candidate
from interview_mux.timeline_optimizer.config import optimizer_cfg
from interview_mux.timeline_optimizer.eval import score_candidate
from interview_mux.timeline_optimizer.mutations import apply_mutation
from interview_mux.timeline_optimizer.proposer import propose_batch
from interview_mux.timeline_optimizer.state import (
    archive_add,
    empty_state,
    load_archive,
    load_best,
    load_optimizer_state,
    save_archive,
    save_best,
    save_optimizer_state,
    seed_candidate_from_run,
)

_lock = threading.Lock()
_threads: dict[str, threading.Thread] = {}
_stop_flags: dict[str, threading.Event] = {}


def is_optimizer_running(run_id: str) -> bool:
    t = _threads.get(run_id)
    return bool(t and t.is_alive())


def stop_optimizer_daemon(ctx: RunContext) -> dict[str, Any]:
    run_id = ctx.run_id
    ev = _stop_flags.get(run_id)
    if ev:
        ev.set()
    state = load_optimizer_state(ctx)
    state["stop_requested"] = True
    state["status"] = "stopped" if not is_optimizer_running(run_id) else "stopping"
    save_optimizer_state(ctx, state)
    ctx.log("timeline_optimizer stop requested", level="info", stage="timeline_optimizer")
    return {"ok": True, "status": state["status"]}


def start_optimizer_daemon(
    ctx: RunContext,
    *,
    force: bool = False,
) -> dict[str, Any]:
    cfg = optimizer_cfg()
    if not cfg.get("enabled") and not force:
        return {"ok": False, "error": "disabled"}
    run_id = ctx.run_id
    with _lock:
        if is_optimizer_running(run_id) and not force:
            return {"ok": True, "already_running": True}
        stop_ev = threading.Event()
        _stop_flags[run_id] = stop_ev

        def _target() -> None:
            try:
                _run_loop(run_id, stop_ev)
            except Exception:
                try:
                    c = RunContext(run_id, create=False)
                    state = load_optimizer_state(c)
                    state["status"] = "error"
                    state["last_error"] = traceback.format_exc()[-800:]
                    save_optimizer_state(c, state)
                except Exception:
                    pass

        t = threading.Thread(
            target=_target,
            name=f"timeline-opt-{run_id}",
            daemon=True,
        )
        _threads[run_id] = t
        t.start()
    return {"ok": True, "started": True, "run_id": run_id}


def _run_loop(run_id: str, stop_ev: threading.Event) -> None:
    ctx = RunContext(run_id, create=False)
    cfg = optimizer_cfg()
    state = load_optimizer_state(ctx)
    if state.get("status") not in {"running", "stopping"}:
        state = empty_state()
    state["status"] = "running"
    state["mode"] = "endless_daemon"
    state["mutation_surface"] = "maximum"
    state["stop_requested"] = False
    state["started_at"] = state.get("started_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_optimizer_state(ctx, state)

    archive = load_archive(ctx)
    best = load_best(ctx)
    if not best:
        seed = seed_candidate_from_run(ctx)
        scored = score_candidate(ctx, seed)
        seed["score"] = scored["score"]
        seed["story_health"] = scored.get("story_health")
        seed["listen_critic"] = scored.get("listen_critic")
        seed["score_breakdown"] = scored
        archive = archive_add(archive, seed, max_keep=int(cfg.get("archive_max") or 24))
        save_archive(ctx, archive)
        save_best(ctx, seed)
        best = seed
        state["best_score"] = seed["score"]
        state["best_candidate_id"] = seed["candidate_id"]
        save_optimizer_state(ctx, state)
        ctx.log(
            f"timeline_optimizer seeded score={seed['score']}",
            level="info",
            stage="timeline_optimizer",
        )

    gen = int(state.get("generation") or 0)
    llm_used = int(state.get("llm_proposals_used") or 0)
    plateau = int(state.get("plateau_streak") or 0)
    soft_max = int(cfg.get("max_generations_soft") or 48)
    sleep_s = max(0.05, float(cfg.get("sleep_ms") or 750) / 1000.0)
    plateau_limit = max(2, int(cfg.get("plateau_gens") or 6))
    min_delta = float(cfg.get("min_score_delta") or 0.75)
    max_llm = int(cfg.get("max_llm_proposals") or 8)

    # Endless: soft_max only triggers auto-promote + continue (does not stop)
    while not stop_ev.is_set():
        state = load_optimizer_state(ctx)
        if state.get("stop_requested"):
            break

        current = load_best(ctx) or best
        breakdown = current.get("score_breakdown") if isinstance(current.get("score_breakdown"), dict) else None
        if not breakdown:
            breakdown = score_candidate(ctx, current)

        allow_llm = llm_used < max_llm
        batch = propose_batch(
            ctx,
            current,
            generation=gen + 1,
            score_breakdown=breakdown,
            allow_llm=allow_llm,
        )
        improved = False
        last_mut = None
        for mut in batch:
            if stop_ev.is_set():
                break
            if mut.get("source") == "llm" or mut.get("source") == "llm_order":
                llm_used += 1
            child = apply_mutation(current, mut)
            child["candidate_id"] = f"g{gen + 1}_{mut.get('op')}_{int(time.time() * 1000) % 100000}"
            child["generation"] = gen + 1
            child["source"] = str(mut.get("source") or "heuristic")
            scored = score_candidate(ctx, child)
            child["score"] = scored["score"]
            child["story_health"] = scored.get("story_health")
            child["listen_critic"] = scored.get("listen_critic")
            child["score_breakdown"] = scored
            last_mut = {"op": mut.get("op"), "score": child["score"], "source": child["source"]}

            archive = archive_add(
                load_archive(ctx), child, max_keep=int(cfg.get("archive_max") or 24)
            )
            save_archive(ctx, archive)

            prev_best = float((load_best(ctx) or {}).get("score") or -1e9)
            if float(child["score"]) > prev_best + 1e-6:
                save_best(ctx, child)
                best = child
                if float(child["score"]) >= prev_best + min_delta:
                    improved = True
                    plateau = 0
                state = load_optimizer_state(ctx)
                state["best_score"] = child["score"]
                state["best_candidate_id"] = child["candidate_id"]
                save_optimizer_state(ctx, state)
                ctx.log(
                    f"timeline_optimizer new best gen={gen + 1} "
                    f"score={child['score']} via {mut.get('op')}",
                    level="info",
                    stage="timeline_optimizer",
                    detail=last_mut,
                )

        gen += 1
        if not improved:
            plateau += 1

        state = load_optimizer_state(ctx)
        state["generation"] = gen
        state["llm_proposals_used"] = llm_used
        state["plateau_streak"] = plateau
        state["last_mutation"] = last_mut
        state["status"] = "running"
        save_optimizer_state(ctx, state)

        # Plateau / soft budget → auto-promote (still endless afterward)
        if (
            cfg.get("auto_promote_on_plateau")
            and (plateau >= plateau_limit or gen >= soft_max)
            and not state.get("auto_promoted_once")
        ):
            try:
                # A promoted order is not live until its EDL and mix agree.
                # The daemon has no JobRunner, so remaster synchronously.
                result = take_best_candidate(
                    ctx,
                    remaster=bool(cfg.get("auto_promote_remaster", True)),
                    sync_remaster=bool(cfg.get("always_auto_apply_best", True)),
                    runner=None,
                )
                if not result.get("ok"):
                    raise RuntimeError(str(result.get("error") or "take-best failed"))
                if result.get("order_changed") and not result.get("remaster_started"):
                    raise RuntimeError("promoted order was not remastered")
                state = load_optimizer_state(ctx)
                state["auto_promoted_once"] = True
                # Reset soft counters so endless search continues exploring
                if gen >= soft_max:
                    # Keep going; bump soft window
                    soft_max = gen + int(cfg.get("max_generations_soft") or 48)
                plateau = 0
                state["plateau_streak"] = 0
                save_optimizer_state(ctx, state)
                ctx.log(
                    "timeline_optimizer auto-promoted and remastered best on plateau "
                    "(daemon continues)",
                    level="info",
                    stage="timeline_optimizer",
                )
            except Exception as exc:
                ctx.log(f"auto-promote failed: {exc}", level="warning", stage="timeline_optimizer")

        time.sleep(sleep_s)

    state = load_optimizer_state(ctx)
    state["status"] = "stopped"
    state["stopped_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    state["stop_requested"] = True
    save_optimizer_state(ctx, state)
    ctx.log(
        f"timeline_optimizer stopped after gen={state.get('generation')} "
        f"best={state.get('best_score')}",
        level="info",
        stage="timeline_optimizer",
    )
