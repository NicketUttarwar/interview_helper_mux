"""Session API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from interview_mux.application_session import (
    VALID_ACTIVE_TABS,
    VALID_ACTIVITY_LOG_TABS,
    VALID_PIPELINE_SUB_TABS,
    active_run_id,
    assert_session_allows_run_switch,
    build_session_payload,
    clear_active_execution,
    merge_active_execution,
    set_active_execution,
)
from interview_mux.gates import get_selected_flow
from interview_mux.run_context import RunContext
from interview_mux.session_lineage import (
    hash_match_with_previous,
    previous_run_summary,
    resolve_immediate_previous_run_id,
)
from interview_mux.stage_execution_reuse import find_reuse_candidates, prior_run_has_reusable_stage
from interview_mux.web.stages import STAGE_BY_ID, all_stages_for_run


class ActiveBody(BaseModel):
    run_id: str | None = None
    selected_stage_id: str | None = None
    active_tab: str | None = None
    pipeline_sub_tab: str | None = None
    activity_log_tab: str | None = None
    activity_log_collapsed: bool | None = None
    pipeline_collapsed_stages: list[str] | None = None
    pipeline_expanded_done_stages: list[str] | None = None
    pipeline_filter_needs_you: bool | None = None
    source_locked: bool | None = None
    input_audio_path: str | None = None


def register_session_routes(router: APIRouter, *, ctx_factory: Any) -> None:
    @router.get("/api/session")
    def get_session() -> dict[str, Any]:
        return build_session_payload()

    @router.put("/api/session/active")
    def put_active(body: ActiveBody) -> dict[str, Any]:
        updates = body.model_dump(exclude_unset=True)
        if "run_id" in updates and updates["run_id"] is None:
            clear_active_execution()
            return {"ok": True, "active": None}
        run_id = updates.get("run_id") or active_run_id()
        if not run_id:
            raise HTTPException(400, "run_id required")
        if "active_tab" in updates and updates["active_tab"] not in VALID_ACTIVE_TABS:
            raise HTTPException(400, f"Invalid active_tab: {updates['active_tab']}")
        if "pipeline_sub_tab" in updates and updates["pipeline_sub_tab"] not in VALID_PIPELINE_SUB_TABS:
            raise HTTPException(400, f"Invalid pipeline_sub_tab: {updates['pipeline_sub_tab']}")
        if "activity_log_tab" in updates and updates["activity_log_tab"] not in VALID_ACTIVITY_LOG_TABS:
            raise HTTPException(400, f"Invalid activity_log_tab: {updates['activity_log_tab']}")
        try:
            assert_session_allows_run_switch(run_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        ctx_factory(run_id)
        if updates.get("run_id") and len(updates) == 1:
            return set_active_execution(run_id)
        try:
            payload = merge_active_execution(
                updates if "run_id" in updates else {**updates, "run_id": run_id}
            )
            return payload
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.delete("/api/session/active")
    def delete_active() -> dict[str, Any]:
        clear_active_execution()
        return {"ok": True, "active": None}

    @router.get("/api/session/lineage")
    def get_session_lineage() -> dict[str, Any]:
        rid = active_run_id()
        if not rid or not RunContext.exists(rid):
            return {"active_run_id": None, "immediate_previous_run_id": None, "stages": []}
        ctx = RunContext(rid, create=False)
        prev_id = resolve_immediate_previous_run_id(ctx)
        hash_match = hash_match_with_previous(ctx) if prev_id else False
        prev_summary = previous_run_summary(prev_id) if prev_id else None
        flow = get_selected_flow(ctx)
        stages_out: list[dict[str, Any]] = []
        if prev_id and hash_match:
            prev_ctx = RunContext(prev_id, create=False)
            for stage in all_stages_for_run(flow):
                sid = stage["id"]
                if sid not in STAGE_BY_ID:
                    continue
                eligible = prior_run_has_reusable_stage(prev_ctx, sid)
                candidates = find_reuse_candidates(ctx, sid) if eligible else []
                stages_out.append(
                    {
                        "stage_id": sid,
                        "title": STAGE_BY_ID[sid].title,
                        "eligible": eligible and bool(candidates),
                        "previous_done": prev_ctx.is_done(sid),
                    }
                )
        return {
            "active_run_id": rid,
            "immediate_previous_run_id": prev_id,
            "hash_match_with_previous": hash_match,
            "previous_run_summary": prev_summary,
            "stages": stages_out,
        }
