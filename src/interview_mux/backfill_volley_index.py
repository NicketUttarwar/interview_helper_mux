"""Backfill volley memory index from stage_runs and analysis_state."""

from __future__ import annotations

import json
from typing import Any

from interview_mux.analysis_memory import (
    ANALYSIS_STATE_PATH,
    INVESTIGATION_QUEUE_PATH,
    should_merge_envelope,
)
from interview_mux.context_resolver import (
    append_stage_conclusion,
    deterministic_entry_id,
    load_context_index,
    save_context_index,
    sync_investigation_entries_from_queue,
    sync_stage_plans,
)
from interview_mux.run_context import RunContext


def backfill_volley_index(ctx: RunContext, *, dry_run: bool = False) -> dict[str, int]:
    stats = {"conclusions": 0, "investigations": 0, "skipped": 0}
    idx = load_context_index(ctx, write=False)
    existing_ids = {e.get("entry_id") for e in idx.get("volley_entries") or []}

    stage_runs = ctx.path("understanding", "stage_runs")
    if stage_runs.is_dir():
        for stage_dir in sorted(stage_runs.iterdir()):
            if not stage_dir.is_dir():
                continue
            stage_key = stage_dir.name
            for attempt_path in sorted(stage_dir.glob("attempt_*.json")):
                name = attempt_path.name
                if "shard_" in name or name.endswith("_collate.json") or name.endswith("_arbiter.json"):
                    continue
                try:
                    doc = json.loads(attempt_path.read_text(encoding="utf-8"))
                except Exception:
                    stats["skipped"] += 1
                    continue
                env = doc.get("envelope") or {}
                arbiter = doc.get("arbiter_result") or {}
                routed = bool(doc.get("routed_via_collate"))
                if not should_merge_envelope(arbiter, env, routed_via_collate=routed):
                    continue
                summary = (env.get("reasoning_summary") or "").strip()
                if not summary:
                    continue
                attempt_n = int(doc.get("attempt") or 1)
                eid = deterministic_entry_id(
                    kind="stage_conclusion", stage_key=stage_key, attempt=attempt_n
                )
                if eid in existing_ids:
                    continue
                if dry_run:
                    stats["conclusions"] += 1
                    continue
                append_stage_conclusion(
                    ctx,
                    stage_key=stage_key,
                    attempt=attempt_n,
                    reasoning_summary=summary,
                )
                existing_ids.add(eid)
                stats["conclusions"] += 1

    if ctx.artifact_exists(ANALYSIS_STATE_PATH):
        state = ctx.read_json(ANALYSIS_STATE_PATH)
        summaries = (state.get("meta") or {}).get("stage_summaries") or {}
        for stage_key, summary in summaries.items():
            if not summary:
                continue
            eid = deterministic_entry_id(
                kind="stage_conclusion", stage_key=str(stage_key), attempt=0, suffix="summary"
            )
            if eid in existing_ids:
                continue
            if dry_run:
                stats["conclusions"] += 1
                continue
            append_stage_conclusion(
                ctx,
                stage_key=str(stage_key),
                attempt=0,
                reasoning_summary=str(summary),
            )
            existing_ids.add(eid)
            stats["conclusions"] += 1

    if ctx.artifact_exists(INVESTIGATION_QUEUE_PATH):
        if dry_run:
            queue = ctx.read_json(INVESTIGATION_QUEUE_PATH)
            stats["investigations"] = sum(
                1 for it in queue.get("items") or [] if it.get("status") == "open"
            )
        else:
            stats["investigations"] = sync_investigation_entries_from_queue(ctx)

    if not dry_run:
        idx = load_context_index(ctx, write=False)
        idx = sync_stage_plans(ctx, idx)
        save_context_index(ctx, idx)

    return stats
