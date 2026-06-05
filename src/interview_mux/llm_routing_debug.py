"""Read-only summaries of LLM stage routing attempts for GUI/debug."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from interview_mux.run_context import RunContext


def list_stage_routing_attempts(ctx: RunContext) -> list[dict[str, Any]]:
    base = ctx.path("understanding", "stage_runs")
    if not base.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for stage_dir in sorted(base.iterdir()):
        if not stage_dir.is_dir():
            continue
        stage_key = stage_dir.name
        for path in sorted(stage_dir.glob("*.json")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            arb = doc.get("arbiter_result") or {}
            out.append(
                {
                    "stage": stage_key,
                    "file": str(path.relative_to(ctx.run_dir)),
                    "task_kind": doc.get("task_kind"),
                    "attempt": doc.get("attempt"),
                    "verdict": arb.get("verdict"),
                    "arbiter_reason": arb.get("reasoning_summary") or arb.get("reason"),
                    "shard_count": doc.get("shard_count", 0),
                    "truncation_flags": doc.get("truncation_flags") or [],
                    "shard_plan_source": doc.get("shard_plan_source"),
                    "routed_via_collate": doc.get("routed_via_collate"),
                    "model_tier": doc.get("model_tier"),
                    "model_id": doc.get("model_id"),
                    "context_chars": doc.get("context_chars"),
                    "schema_errors": doc.get("schema_errors") or [],
                }
            )
    return out
