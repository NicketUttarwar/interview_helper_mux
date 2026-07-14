"""Workspace API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from interview_mux.pipeline import ANALYSIS_ORDER, DELIVERY_ORDER
from interview_mux.run_context import RunContext
from interview_mux.session_lineage import resolve_immediate_previous_run_id
from interview_mux.stage_execution_reuse import (
    apply_stage_reuse,
    find_reuse_candidates,
    get_reuse_decision,
    record_reuse_decision,
)

class BulkReuseBody(BaseModel):
    stage_ids: list[str] | None = None
    accept_all: bool = False

def register_workspace_routes(
    router: APIRouter,
    *,
    ctx_factory: Any,
    run_guard: Any,
) -> None:
    @router.get("/api/runs/{run_id}/workspace")
    def get_workspace(run_id: str) -> dict[str, Any]:
        ctx = ctx_factory(run_id)
        tree: list[dict[str, Any]] = []
        for p in sorted(ctx.run_dir.rglob("*")):
            if not p.is_file():
                continue
            rel = str(p.relative_to(ctx.run_dir)).replace("\\", "/")
            if rel.startswith(".pending_writes/"):
                continue
            tree.append({"path": rel, "size_bytes": p.stat().st_size})
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        return {
            "run_id": run_id,
            "working_dir": str(ctx.run_dir),
            "snapshot_version": meta.get("snapshot_version", 0),
            "files": tree[:500],
        }

    @router.post("/api/runs/{run_id}/reuse-from-previous")
    def reuse_from_previous(run_id: str, body: BulkReuseBody) -> dict[str, Any]:
        ctx = ctx_factory(run_id)
        prev_id = resolve_immediate_previous_run_id(ctx)
        if not prev_id:
            raise HTTPException(400, "No immediate previous execution.")
        stage_ids = body.stage_ids or []
        if body.accept_all:
            orders = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
            stage_ids = [
                sid
                for sid in orders
                if find_reuse_candidates(ctx, sid) and not get_reuse_decision(ctx, sid)
            ]
        results: list[dict[str, Any]] = []
        with run_guard(run_id):
            for sid in stage_ids:
                if get_reuse_decision(ctx, sid):
                    results.append({"stage_id": sid, "skipped": "already_decided"})
                    continue
                candidates = find_reuse_candidates(ctx, sid)
                if not candidates:
                    results.append({"stage_id": sid, "skipped": "not_eligible"})
                    continue
                record_reuse_decision(ctx, sid, action="accept", source_run_id=prev_id)
                try:
                    apply_stage_reuse(ctx, sid, prev_id)
                    results.append({"stage_id": sid, "ok": True, "source_run_id": prev_id})
                except Exception as exc:
                    results.append({"stage_id": sid, "error": str(exc)})
        ctx.bump_snapshot_version()
        return {"ok": True, "source_run_id": prev_id, "results": results}
