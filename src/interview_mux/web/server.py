from __future__ import annotations

import json
import re
import traceback
from contextlib import contextmanager
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from interview_mux.analysis_memory import (
    ANALYSIS_STATE_PATH,
    EDITABLE_PROFILE_PATHS,
    ensure_analysis_workspace,
    load_analysis_state,
    mark_operator_verified,
    save_analysis_state,
)
from interview_mux.config import merged_config, repo_root
from interview_mux.value_analysis.config import value_analysis_enabled
from interview_mux.sfx_prompt_review import (
    prompt_completeness_warnings,
    validate_prompts_payload,
)
from interview_mux.prompt_validation import validate_artifact_write
from interview_mux.file_store import read_json, write_json
from interview_mux.disfluency.config import disfluency_enabled, disfluency_restore_enabled
from interview_mux.gates import (
    check_disfluency_review_pending,
    check_g1_vo,
    check_profile_gate_pending,
    check_transcript_review_pending,
    get_selected_flow,
    is_operator_profile_verified,
    set_selected_flow,
)
from interview_mux.stages import disfluency
from interview_mux.stages import transcript_review
from interview_mux.api_providers import list_providers, all_provider_grants
from interview_mux.gui_api_consent import load_persisted_consents, merge_consents, save_persisted_consent
from interview_mux.gui_session import (
    VALID_ACTIVE_TABS,
    VALID_ACTIVITY_LOG_TABS,
    VALID_PIPELINE_SUB_TABS,
    active_run_id,
    assert_session_allows_run_switch,
    clear_active_execution,
    get_active_execution,
    get_server_session,
    merge_active_execution,
    set_active_execution,
    source_audio_locked_for_session,
)
from interview_mux.assembly_timeline import build_assembly_timeline
from interview_mux.nle_state import (
    apply_segments_with_nle,
    load_nle,
    save_nle,
    snap_boundary_for_segment,
    split_segment_at,
)
from interview_mux.waveform_peaks import load_or_generate_peaks
from interview_mux.pipeline import ANALYSIS_ORDER, FLOW1_ORDER, FLOW2_ORDER, FLOW3_ORDER
from interview_mux.run_context import RunContext
from interview_mux.session_log import append_log, read_log
from interview_mux.journey_orchestrator import (
    build_journey_snapshot,
    mark_preview_listened,
    refresh_journey_meta,
    set_flow_intent,
)
from interview_mux.journey_state import get_flow_intent, stage_operator_phase
from interview_mux.operator_quality import preclean_acknowledged
from interview_mux.web.runner import RunBusyError, runner
from interview_mux.web.session_routes import ActiveBody, register_session_routes
from interview_mux.web.workspace_routes import register_workspace_routes
from interview_mux.web.stages import LLM_ROUTING_STAGE_IDS, STAGE_BY_ID, all_stages_for_run
from interview_mux.operator_snapshots import (
    append_operator_stage_reuse,
    mirror_artifact_to_operator,
    persist_operator_acoustic_overrides,
    persist_operator_analysis_profile,
    persist_operator_sfx_listen_results,
    persist_operator_sfx_prompts,
    persist_operator_flow_selection,
    persist_operator_investigation_queue,
    persist_operator_preclean,
)
from interview_mux.sonic_context import compact_for_volley as compact_sonic_context, load_sonic_context

STATIC_DIR = Path(__file__).resolve().parent / "static"

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".webm"}


@contextmanager
def _guarded_run(run_id: str):
    """Serialize mutating API calls with background jobs (HTTP 409 on busy)."""
    try:
        with runner.operator_guard(run_id):
            yield
    except RunBusyError as exc:
        raise HTTPException(409, {"error": "run_busy", "message": str(exc)}) from exc
SKIP_ASSET_PARTS = {"executions", ".gui"}

_RUN_ID_IN_API_PATH = re.compile(r"^/api/runs/(?P<run_id>[^/]+)")


def _run_id_from_request(request: Request) -> str | None:
    match = _RUN_ID_IN_API_PATH.match(request.url.path)
    return match.group("run_id") if match else None


def _append_api_error_log(
    run_id: str,
    request: Request,
    exc: BaseException,
    *,
    status_code: int,
) -> None:
    """Mirror unhandled run-scoped API failures to gui_log.jsonl."""
    if not RunContext.exists(run_id):
        return
    ctx = RunContext(run_id, create=False)
    tb = traceback.format_exc()
    detail: dict[str, Any] = {
        "path": request.url.path,
        "method": request.method,
        "status_code": status_code,
        "error_class": type(exc).__name__,
        "journey_kind": "api",
    }
    if tb and tb.strip() != "NoneType: None":
        detail["traceback"] = tb
    append_log(
        ctx.run_dir,
        f"API {status_code}: {exc}",
        level="error" if status_code >= 500 else "warning",
        stage="api",
        detail=detail,
    )


class CreateRunBody(BaseModel):
    input_audio_path: str
    run_id: str | None = None
    flow_intent: str | None = Field(default=None, pattern="^(flow1|flow2|flow3)$")


class FlowBody(BaseModel):
    flow: str = Field(pattern="^(flow1|flow2|flow3)$")


class InvestigationPatchBody(BaseModel):
    status: str = "resolved"


class ExecuteBody(BaseModel):
    mode: str = Field(
        description=(
            "stage | analysis | analysis_until_g0 | flow1 | flow1_until_preview | "
            "flow1_polish | flow2 | flow3 | nle_apply"
        )
    )
    stage: str | None = None
    from_stage: str | None = None
    until_stage: str | None = None
    nle_full_refresh: bool = False
    nle_apply_mode: str = "structural"
    api_consents: dict[str, bool] | None = None


class FillArtifactGapsBody(BaseModel):
    path: str
    api_consents: dict[str, bool] | None = None


class ApiConsentBody(BaseModel):
    provider: str
    granted: bool


class ArtifactBody(BaseModel):
    path: str
    data: Any
    invalidate_from: str | None = None


class ArtifactTextBody(BaseModel):
    path: str
    text: str
    invalidate_from: str | None = None


class HandoffAckBody(BaseModel):
    stage_id: str


class PendingWriteContentBody(BaseModel):
    path: str
    data: Any | None = None
    text: str | None = None


class ResetBody(BaseModel):
    from_stage: str | None = None
    new_input_audio_path: str | None = None


class NleBody(BaseModel):
    data: dict[str, Any]


class NleSegmentBody(BaseModel):
    segment_id: str
    patch: dict[str, Any]


class SplitBody(BaseModel):
    segment_id: str
    at_ms: int


class SnapBoundaryBody(BaseModel):
    segment_id: str
    ms: int
    edge: str = "end"


class NleBatchOperation(BaseModel):
    segment_id: str
    patch: dict[str, Any]


class NleBatchBody(BaseModel):
    operations: list[NleBatchOperation]


class LogBody(BaseModel):
    message: str
    level: str = "info"
    stage: str | None = None
    action_id: str | None = None


class LlmCallVolleyTurn(BaseModel):
    role: str
    content: str = ""


class LlmCallVolleyBody(BaseModel):
    system_prompt: str = ""
    turns: list[LlmCallVolleyTurn] = Field(default_factory=list)


class LlmCallRecordUpdateBody(BaseModel):
    path: str
    volley: LlmCallVolleyBody | None = None
    raw_response: str | None = None


class VolleyEntryBody(BaseModel):
    kind: str = "stage_conclusion"
    role: str = "assistant"
    content: str = ""
    source: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)
    scope: dict[str, Any] | None = None


class VolleyEntryPatchBody(BaseModel):
    content: str | None = None
    tags: list[str] | None = None
    scope: dict[str, Any] | None = None


class TranscriptChunkBody(BaseModel):
    text: str
    reviewed: bool = True


class TranscriptReviewCompleteBody(BaseModel):
    accept_unreviewed: bool = False


class DisfluencyEventBody(BaseModel):
    review_status: str = Field(pattern="^(pending|confirmed|rejected)$")
    text: str | None = None
    include_in_restore: bool | None = None


class DisfluencyReviewCompleteBody(BaseModel):
    accept_unreviewed: bool = False


class DisfluencyRestoreBody(BaseModel):
    enabled: bool


class TranscriptWordPatch(BaseModel):
    index: int
    text: str


class TranscriptWordsPatchBody(BaseModel):
    updates: list[TranscriptWordPatch] = Field(default_factory=list)


class AnalysisProfileBody(BaseModel):
    data: dict[str, Any]
    operator_verified: bool | None = None
    invalidate_from: str | None = None


class AcousticProfileOverridesBody(BaseModel):
    overrides: dict[str, Any] = Field(default_factory=dict)
    invalidate_from: str | None = None


class PrecleanOfferBody(BaseModel):
    checkpoint: str
    action: str = Field(pattern="^(offer|accept|dismiss)$")
    scope: str | None = None


class StageReuseBody(BaseModel):
    action: str = Field(pattern="^(accept|decline|decline_and_run)$")
    source_run_id: str | None = None
    api_consents: dict[str, bool] | None = None


class SfxPromptApproveBody(BaseModel):
    approved_by: str | None = None


class SfxListenResultBody(BaseModel):
    asset_id: str = Field(min_length=1)
    result: str = Field(pattern="^(pass|fail)$")
    note: str | None = None
    mode: str = Field(default="post_listen", pattern="^(post_listen|under_speech)$")


class SfxPromptRefineBody(BaseModel):
    asset_ids: list[str] | None = None
    force: bool = False


class SfxPromptRegenBody(BaseModel):
    asset_ids: list[str] = Field(min_length=1)


from contextlib import asynccontextmanager


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    yield
    from interview_mux.gui_job_reconcile import reconcile_stale_jobs
    from interview_mux.process_cleanup import kill_mux_workers_for_shutdown

    kill_mux_workers_for_shutdown()
    reconcile_stale_jobs()


def create_app() -> FastAPI:
    app = FastAPI(title="Interview Helper Mux", version="0.2.0", lifespan=_app_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    from interview_mux.web.action_trace_middleware import ActionTraceMiddleware

    app.add_middleware(ActionTraceMiddleware)

    @app.middleware("http")
    async def gui_client_leader_middleware(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            path = request.url.path
            if path.startswith("/api/runs/") and not path.endswith("/job"):
                from interview_mux.application_session import assert_client_controls_session

                client_id = request.headers.get("X-GUI-Client-Id")
                try:
                    assert_client_controls_session(client_id)
                except ValueError as exc:
                    return JSONResponse(
                        status_code=409,
                        content={"detail": str(exc), "error": "session_superseded"},
                    )
        return await call_next(request)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        cfg = merged_config()
        root = repo_root()
        return {
            "assets_root": cfg.get("assets_root", "ASSETS"),
            "executions_root": cfg.get("executions_root", "ASSETS/executions"),
            "data_root": cfg.get("data_root", "data"),
            "web_port": cfg.get("web_port", 8765),
            "repo_root": str(root),
            "value_analysis_enabled": value_analysis_enabled(cfg),
            "disfluency_extract_enabled": disfluency_enabled(cfg),
            "disfluency_restore_enabled": disfluency_restore_enabled(cfg),
            "api_consent_persist": (cfg.get("web") or {}).get("api_consent_persist", True),
            "journey_ui": (cfg.get("journey_ui") or {"enabled": True}),
            "llm_routing_stage_ids": sorted(LLM_ROUTING_STAGE_IDS),
        }

    @app.get("/api/session/api-consent")
    def get_api_consent() -> dict[str, Any]:
        grants = merge_consents(all_provider_grants(), load_persisted_consents())
        return {
            "providers": list_providers(),
            "grants": grants,
        }

    @app.post("/api/session/api-consent")
    def post_api_consent(body: ApiConsentBody) -> dict[str, Any]:
        cfg = merged_config()
        persist = (cfg.get("web") or {}).get("api_consent_persist", True)
        grants = persisted = load_persisted_consents()
        if persist:
            grants = save_persisted_consent(body.provider, body.granted)
        else:
            grants = dict(persisted)
            grants[body.provider] = body.granted
        return {"ok": True, "provider": body.provider, "granted": body.granted, "grants": grants}

    @app.get("/api/assets")
    def list_assets(recursive: bool = False) -> dict[str, Any]:
        cfg = merged_config()
        assets = repo_root() / cfg.get("assets_root", "ASSETS")
        assets.mkdir(parents=True, exist_ok=True)
        files: list[dict[str, Any]] = []
        iterator = assets.rglob("*") if recursive else assets.iterdir()
        for p in sorted(iterator):
            if not p.is_file():
                continue
            rel_parts = p.relative_to(assets).parts
            if not recursive and len(rel_parts) != 1:
                continue
            if any(part in SKIP_ASSET_PARTS for part in rel_parts):
                continue
            if p.suffix.lower() not in AUDIO_EXTS:
                continue
            rel = p.relative_to(repo_root()).as_posix()
            stat = p.stat()
            files.append(
                {
                    "path": rel,
                    "name": p.name,
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                }
            )
        return {"assets_root": assets.relative_to(repo_root()).as_posix(), "files": files}

    @app.get("/api/runs")
    def list_runs(enrich: bool = False, enrich_limit: int = 50) -> dict[str, Any]:
        runs: list[dict[str, Any]] = []
        for rid in RunContext.list_runs():
            try:
                runs.append(RunContext.summarize_run(rid))
            except Exception:
                runs.append({"run_id": rid, "progress": {"done": 0, "total": 0}})
        runs.sort(key=lambda r: r.get("execution_number") or 0, reverse=True)
        if enrich:
            for r in runs[: max(enrich_limit, 0)]:
                try:
                    ctx = RunContext(r["run_id"], create=False)
                    flow = get_selected_flow(ctx)
                    stages = _build_stage_list(
                        ctx,
                        flow,
                        check_g1_vo(ctx),
                        check_transcript_review_pending(ctx),
                        is_operator_profile_verified(ctx),
                        check_profile_gate_pending(ctx),
                    )
                    done = sum(1 for s in stages if s["status"] == "done")
                    r["progress"] = {"done": done, "total": len(stages)}
                    r["last_stage"] = next(
                        (s["title"] for s in reversed(stages) if s["status"] == "done"),
                        None,
                    )
                    log_entries = read_log(ctx.run_dir, tail=1)
                    if log_entries:
                        r["last_log"] = log_entries[-1]
                    job = runner.get_job(r["run_id"])
                    if job.get("status"):
                        r["job_status"] = job.get("status")
                    journey = build_journey_snapshot(ctx, job=job, stages=stages)
                    r["operator_phase"] = journey.get("phase")
                    next_action = str(journey.get("next_action") or "")
                    r["next_action"] = next_action[:80] if next_action else None
                    blocking = journey.get("blocking") or {}
                    r["blocking_message"] = (
                        blocking.get("message") if blocking.get("blocked") else None
                    )
                    attention = sum(
                        1 for s in stages if s.get("status") == "action_required"
                    )
                    if job.get("status") in (
                        "gate",
                        "awaiting_write_approval",
                        "needs_operator",
                    ) or job.get("needs_stage_reuse"):
                        attention += 1
                    if blocking.get("blocked"):
                        attention = max(attention, 1)
                    r["attention_count"] = attention
                except Exception:
                    r["progress"] = {"done": 0, "total": 0}
        return {"runs": runs}

    @app.post("/api/runs")
    def create_run(body: CreateRunBody) -> dict[str, Any]:
        if active_run_id():
            raise HTTPException(
                409,
                "An execution is already active in this session. "
                "Clear session (Menu) before starting with a different source.",
            )
        src = _resolve_repo_path(body.input_audio_path)
        if not src.is_file():
            raise HTTPException(404, f"Audio file not found: {body.input_audio_path}")
        _assert_asset_input_path(body.input_audio_path)
        if body.run_id and RunContext.exists(body.run_id):
            raise HTTPException(409, f"Execution already exists: {body.run_id}")
        from interview_mux.source_audio_hash import pipeline_wav_path, source_audio_hash_pair

        wav_src = pipeline_wav_path(src)
        full_hash, short_hash = source_audio_hash_pair(wav_src)
        run_id = body.run_id or RunContext.allocate_run_id(source_hash=short_hash)
        ctx = RunContext(run_id, create=True)
        ctx.init_run_meta(
            body.input_audio_path,
            source_audio_hash=full_hash,
            source_audio_hash_short=short_hash,
        )
        if body.flow_intent:
            set_flow_intent(ctx, body.flow_intent)
        ensure_analysis_workspace(ctx)
        refresh_journey_meta(ctx)
        from interview_mux.session_lineage import record_immediate_previous_on_create

        record_immediate_previous_on_create(ctx)
        meta = ctx.read_json("run_meta.json")
        set_active_execution(
            ctx.run_id,
            input_audio_path=meta.get("input_audio_path"),
            source_locked=True,
        )
        return {
            "run_id": ctx.run_id,
            "run_dir": str(ctx.run_dir.relative_to(ctx.root)),
            "execution_number": meta.get("execution_number"),
            "input_audio_path": meta.get("input_audio_path"),
            "source_audio_hash": meta.get("source_audio_hash"),
            "source_audio_hash_short": meta.get("source_audio_hash_short"),
        }

    @app.get("/api/runs/{run_id}/summary")
    def get_run_summary(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        summary = RunContext.summarize_run(run_id)
        flow = get_selected_flow(ctx)
        stages = _build_stage_list(
            ctx,
            flow,
            check_g1_vo(ctx),
            check_transcript_review_pending(ctx),
            is_operator_profile_verified(ctx),
            check_profile_gate_pending(ctx),
        )
        done = sum(1 for s in stages if s["status"] == "done")
        log_entries = read_log(ctx.run_dir, tail=1)
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        return {
            **summary,
            "progress": {"done": done, "total": len(stages)},
            "last_log": log_entries[-1] if log_entries else None,
            "handoff_ack": meta.get("handoff_ack") or {},
        }

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        g1_missing = check_g1_vo(ctx)
        from interview_mux.gates_tbiy import check_g1_5_preview_pickup_pending

        g1_5_pending = check_g1_5_preview_pickup_pending(ctx)
        from interview_mux.source_topology import check_pickup_speaker_pending

        pickup_speaker_pending = check_pickup_speaker_pending(ctx)
        flow = get_selected_flow(ctx)
        tr_pending = check_transcript_review_pending(ctx)
        profile_verified = is_operator_profile_verified(ctx)
        profile_gate_pending = check_profile_gate_pending(ctx)
        df_pending = check_disfluency_review_pending(ctx)
        from interview_mux.artifact_completeness import (
            analysis_profile_ready_for_review,
            story_board_ready_for_gui,
            timeline_ready_for_gui,
        )

        profile_ready = analysis_profile_ready_for_review(ctx)
        story_board_ready = story_board_ready_for_gui(ctx)
        timeline_ready = timeline_ready_for_gui(ctx)
        stages = _build_stage_list(
            ctx, flow, g1_missing, tr_pending, profile_verified, profile_gate_pending, df_pending
        )
        handoff_ack = meta.get("handoff_ack") or {}
        job = runner.get_job(run_id)
        job = _enrich_job_autopilot(ctx, job if isinstance(job, dict) else {}, stages)
        if job.get("status") == "error":
            tb = job.get("traceback") or ""
            existing = job.get("last_error") if isinstance(job.get("last_error"), dict) else {}
            job = {
                **job,
                "last_error": {
                    "message": existing.get("message")
                    or job.get("message")
                    or job.get("error")
                    or "Job failed",
                    "stage": existing.get("stage")
                    or job.get("stage")
                    or job.get("current_stage"),
                    "error_class": existing.get("error_class"),
                    "traceback_excerpt": existing.get("traceback_excerpt")
                    or (str(tb)[:2000] if tb else None),
                },
            }
        journey = build_journey_snapshot(ctx, job=job, stages=stages)
        intent = get_flow_intent(ctx)
        display_flow = flow or intent
        from interview_mux.legacy_stage_warnings import legacy_sfx_warnings

        llm_verification_alerts: list[dict[str, Any]] = []
        try:
            from interview_mux.llm_calls_gui import list_verification_alerts

            llm_verification_alerts = list_verification_alerts(ctx)
        except Exception:
            pass

        return {
            "run_id": run_id,
            "meta": meta,
            "working_dir": str(ctx.run_dir),
            "snapshot_version": meta.get("snapshot_version", 0),
            "execution_number": meta.get("execution_number"),
            "immediate_previous_run_id": meta.get("immediate_previous_run_id"),
            "handoff_ack": handoff_ack,
            "sfx_generated_assets": _discover_generated_sfx_assets(ctx),
            "legacy_migration_warnings": legacy_sfx_warnings(ctx),
            "selected_flow": flow,
            "flow_intent": intent,
            "flow_adaptation": (
                ctx.read_json("understanding/flow_adaptation.json")
                if ctx.artifact_exists("understanding/flow_adaptation.json")
                else None
            ),
            "source_topology": (
                ctx.read_json("understanding/source_topology.json")
                if ctx.artifact_exists("understanding/source_topology.json")
                else None
            ),
            "transcript_review_pending": tr_pending,
            "transcript_review_clear": not tr_pending,
            "disfluency_review_pending": df_pending,
            "disfluency_review_clear": not df_pending,
            "profile_verified": profile_verified,
            "profile_gate_pending": profile_gate_pending,
            "profile_ready_for_review": profile_ready,
            "story_board_ready": story_board_ready,
            "timeline_ready": timeline_ready,
            "g1_missing": g1_missing,
            "g1_clear": not g1_missing,
            "g1_5_preview_pickup_pending": g1_5_pending,
            "g1_5_preview_pickup_clear": not g1_5_pending,
            "pickup_speaker_pending": pickup_speaker_pending,
            "analysis_complete": ctx.artifact_exists("analysis_complete.json"),
            "job": job,
            "journey": journey,
            "blocking": journey.get("blocking"),
            "stages": stages,
            "log_tail": read_log(ctx.run_dir, tail=100),
            "display_flow": display_flow,
            "llm_verification_alerts": llm_verification_alerts,
        }

    @app.get("/api/runs/{run_id}/flow1-readiness")
    def get_flow1_readiness(
        run_id: str,
        target_stage: str = "topic_coverage_audit",
        scope: str = "flow1",
    ) -> dict[str, Any]:
        ctx = _ctx(run_id)
        from interview_mux.progression_readiness import (
            build_flow1_readiness_report,
            build_pre_audio_readiness_report,
        )

        if scope == "pre_audio":
            return build_pre_audio_readiness_report(ctx)
        return build_flow1_readiness_report(
            ctx,
            target_stage=target_stage or None,
            include_flow1_spine=target_stage not in (None, "", "topic_coverage_audit"),
        )

    @app.get("/api/runs/{run_id}/log")
    def get_log(
        run_id: str,
        tail: int = 200,
        stage: str | None = None,
        since_ts: str | None = None,
    ) -> dict[str, Any]:
        ctx = _ctx(run_id)
        return {
            "entries": read_log(
                ctx.run_dir,
                tail=tail,
                stage=stage or None,
                since_ts=since_ts or None,
            )
        }

    @app.post("/api/runs/{run_id}/log")
    def post_log(run_id: str, body: LogBody) -> dict[str, Any]:
        ctx = _ctx(run_id)
        detail: dict[str, Any] = {"journey_kind": "execute", "origin": "gui"}
        if body.action_id:
            detail["action_id"] = body.action_id
        from interview_mux.operator_log import operator_log

        entry = operator_log(
            body.message,
            run_dir=ctx.run_dir,
            level=body.level,
            stage=body.stage,
            action_id=body.action_id,
            origin="gui",
            detail=detail,
        )
        return {"ok": True, "entry": entry}

    @app.get("/api/runs/{run_id}/action-trace")
    def get_action_trace(run_id: str, tail: int = 50) -> dict[str, Any]:
        ctx = _ctx(run_id)
        from interview_mux.operator_action_trace import read_action_trace

        return {"entries": read_action_trace(ctx.run_dir, tail=max(1, min(tail, 500)))}

    @app.post("/api/runs/{run_id}/action-trace/dump-last")
    def dump_last_action_trace(run_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            from interview_mux.operator_action_catalog import load_catalog
            from interview_mux.operator_action_trace import format_dump_text, read_action_trace
            from interview_mux.operator_log import operator_log

            entries = read_action_trace(ctx.run_dir, tail=100)
            text = format_dump_text(entries, catalog=load_catalog())
            operator_log(
                "Action trace dump",
                run_dir=ctx.run_dir,
                level="info",
                stage="api",
                action_id="gui.activity.dump_last",
                origin="api",
                detail={"dump": text, "journey_kind": "execute"},
            )
            return {"ok": True, "text": text, "entries_used": len(entries)}

    @app.get("/api/runs/{run_id}/timeline")
    def get_timeline(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        nle = load_nle(ctx)
        segments: list[dict[str, Any]] = []
        duration_ms = 0
        manifest_by_id: dict[str, dict[str, Any]] = {}
        if ctx.artifact_exists("segments/manifest.json"):
            manifest = ctx.read_json("segments/manifest.json")
            raw = manifest.get("segments") or []
            manifest_by_id = {
                s["segment_id"]: s for s in raw if s.get("segment_id")
            }
            segments = apply_segments_with_nle(raw, nle)
            for seg in segments:
                sid = seg.get("segment_id")
                if sid and sid in manifest_by_id:
                    m = manifest_by_id[sid]
                    if m.get("start_ms") is not None:
                        seg["_manifest_start_ms"] = int(m["start_ms"])
                    if m.get("end_ms") is not None:
                        seg["_manifest_end_ms"] = int(m["end_ms"])
            if segments:
                duration_ms = max(s.get("end_ms", 0) for s in segments)
        vo_lines: list[dict[str, Any]] = []
        if ctx.artifact_exists("understanding/gap_report.json"):
            from interview_mux.gates_tbiy import post_preview_vo_satisfied

            report = ctx.read_json("understanding/gap_report.json")
            pickup = ctx.path("vo_pickup")
            for line in report.get("interviewer_lines") or []:
                lid = line.get("line_id", "")
                seg = line.get("targets_segment_id", "")
                candidates = [pickup / f"{lid}.wav", pickup / f"{seg}.wav"]
                recorded = next((p.name for p in candidates if p.is_file()), None)
                row = {**line, "recorded_file": recorded}
                if line.get("post_preview"):
                    row["post_preview_satisfied"] = bool(
                        recorded and post_preview_vo_satisfied(ctx, str(lid))
                    )
                vo_lines.append(row)
        return {
            "duration_ms": duration_ms,
            "segments": segments,
            "vo_lines": vo_lines,
            "nle": nle,
            "normalized_audio": "ingest/normalized.wav" if ctx.artifact_exists("ingest/normalized.wav") else None,
        }

    @app.get("/api/runs/{run_id}/nle")
    def get_nle(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        return load_nle(ctx)

    @app.put("/api/runs/{run_id}/nle")
    def put_nle(run_id: str, body: NleBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            try:
                save_nle(ctx, body.data)
            except ValueError as exc:
                raise HTTPException(400, {"errors": [str(exc)]}) from exc
            ctx.log("NLE timeline state saved to disk.", level="info", stage="nle")
            return {"ok": True}

    @app.post("/api/runs/{run_id}/recompute-acoustic-profile")
    def recompute_acoustic_profile(run_id: str) -> dict[str, Any]:
        from interview_mux.stages.understanding import run_source_acoustic_profile

        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            prior = ctx.read_json("understanding/source_acoustic_profile.json") if ctx.artifact_exists(
                "understanding/source_acoustic_profile.json"
            ) else {}
            prior_pace = (prior.get("pacing") or {}).get("pace_class") if isinstance(prior, dict) else None
            run_source_acoustic_profile(ctx)
            profile = ctx.read_json("understanding/source_acoustic_profile.json")
            new_pace = (profile.get("pacing") or {}).get("pace_class") if isinstance(profile, dict) else None
            ctx.log(
                "Acoustic profile recomputed from current ingest/transcript.",
                level="success",
                stage="source_acoustic_profile",
                detail="acoustic_profile_recomputed",
            )
            out: dict[str, Any] = {
                "ok": True,
                "profile": profile,
                "derived_from": profile.get("derived_from"),
                "prior_pace": prior_pace,
                "new_pace": new_pace,
            }
            if prior_pace and new_pace and prior_pace != new_pace:
                cleared = _invalidate_sound_design_for_pace_change(ctx)
                ctx.log(
                    f"pace_class changed {prior_pace} → {new_pace}; invalidated downstream sound design.",
                    level="warning",
                    stage="source_acoustic_profile",
                    detail=f"acoustic_profile_invalidation: {json.dumps(cleared)}",
                )
                out["invalidated_from"] = "sound_design_palettes"
            return out

    @app.get("/api/runs/{run_id}/interview-spine")
    def get_interview_spine(run_id: str, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx = _ctx(run_id)
        path = "understanding/interview_spine.json"
        if not ctx.artifact_exists(path):
            raise HTTPException(404, "Interview spine not found — run interview_spine_build first.")
        doc = ctx.read_json(path)
        windows = doc.get("windows") or []
        if not isinstance(windows, list):
            windows = []
        start = max(0, offset)
        end = start + max(1, min(limit, 200))
        page = windows[start:end]
        from interview_mux.interview_spine.lineage import derived_from_matches

        derived = doc.get("derived_from")
        stale = bool(derived) and not derived_from_matches(ctx, derived or {})
        return {
            "schema_version": doc.get("schema_version"),
            "derived_from": derived,
            "derived_from_stale": stale,
            "window_policy": doc.get("window_policy"),
            "retrieval": doc.get("retrieval"),
            "speaker_stats": doc.get("speaker_stats"),
            "boundary_events": doc.get("boundary_events"),
            "windows": page,
            "window_total": len(windows),
            "offset": start,
            "limit": end - start,
        }

    @app.post("/api/runs/{run_id}/recompute-interview-spine")
    def recompute_interview_spine(run_id: str) -> dict[str, Any]:
        from interview_mux.stages.interview_spine_stage import run_interview_spine_build

        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            try:
                prior = (
                    ctx.read_json("understanding/interview_spine.json")
                    if ctx.artifact_exists("understanding/interview_spine.json")
                    else {}
                )
                run_interview_spine_build(ctx)
            except FileNotFoundError as exc:
                ctx.log(
                    f"Interview spine recompute failed: {exc}. "
                    "Complete G0 transcript review and source_acoustic_profile first.",
                    level="error",
                    stage="interview_spine_build",
                    detail="interview_spine_recompute_failed",
                )
                raise HTTPException(500, {"error": "interview_spine_recompute_failed", "message": str(exc)}) from exc
            doc = ctx.read_json("understanding/interview_spine.json")
            ctx.log(
                "Interview spine recomputed from current ingest/transcript/SAP.",
                level="success",
                stage="interview_spine_build",
                detail="interview_spine_recomputed",
            )
            return {
                "ok": True,
                "spine": doc,
                "derived_from": doc.get("derived_from"),
                "prior_window_count": len((prior.get("windows") or []) if isinstance(prior, dict) else []),
                "new_window_count": len(doc.get("windows") or []),
            }

    @app.post("/api/runs/{run_id}/interview-spine/query")
    def query_interview_spine(run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        from interview_mux.interview_spine.retrieval import query_spine

        ctx = _ctx(run_id)
        query = str(body.get("query") or "").strip()
        if not query:
            raise HTTPException(400, "query is required")
        top_k = int(body.get("top_k") or 5)
        hits = query_spine(ctx, query, top_k=max(1, min(top_k, 20)))
        return {"ok": True, "query": query, "hits": hits}

    @app.get("/api/runs/{run_id}/coherence-report")
    def get_coherence_report(run_id: str) -> dict[str, Any]:
        from interview_mux.coherence.analyze import _inactive_report
        from interview_mux.coherence.duration_gate import build_gate

        ctx = _ctx(run_id)
        path = "understanding/coherence_report.json"
        if not ctx.artifact_exists(path):
            gate = build_gate(ctx)
            return _inactive_report(gate, "pre_analysis")
        doc = ctx.read_json(path)
        return doc

    @app.post("/api/runs/{run_id}/recompute-coherence")
    def recompute_coherence(run_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        from interview_mux.coherence import build_coherence_report, COHERENCE_REPORT_PATH
        from interview_mux.coherence.memory_sync import sync_coherence_to_state
        from interview_mux.prompt_validation import validate_coherence_report

        phase = str((body or {}).get("phase") or "post_reanchor")
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            report = build_coherence_report(ctx, phase=phase)
            errors = validate_coherence_report(report)
            if errors and report.get("gate", {}).get("activated"):
                raise HTTPException(400, f"Coherence report invalid: {errors[:3]}")
            ctx.write_json(COHERENCE_REPORT_PATH, report)
            sync_coherence_to_state(ctx, report)
            ctx.log(
                "Coherence report recomputed.",
                level="success",
                stage="coherence",
                detail=f"coherence_recomputed:{phase}",
            )
            return {"ok": True, "report": report}

    @app.patch("/api/runs/{run_id}/acoustic-profile/overrides")
    def patch_acoustic_profile_overrides(run_id: str, body: AcousticProfileOverridesBody) -> dict[str, Any]:
        from interview_mux.acoustic_profile import SAP_PATH, load_profile, save_operator_overrides

        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            if not ctx.artifact_exists(SAP_PATH):
                raise HTTPException(404, "Source acoustic profile not found — run source_acoustic_profile first.")
            try:
                merged = save_operator_overrides(ctx, body.overrides)
            except FileNotFoundError as exc:
                raise HTTPException(404, str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(400, {"errors": [str(exc)]}) from exc
            persist_operator_acoustic_overrides(ctx, merged.get("operator_overrides") or {}, source="gui_override")
            ctx.log(
                "Acoustic profile operator overrides saved.",
                level="success",
                stage="source_acoustic_profile",
                detail="acoustic_profile_override_saved",
            )
            if body.invalidate_from:
                runner.invalidate_from(run_id, body.invalidate_from)
            return {
                "ok": True,
                "operator_overrides": merged.get("operator_overrides", {}),
                "effective": {
                    "pace_class": (merged.get("pacing") or {}).get("pace_class"),
                    "underscore_policy": (merged.get("mix_contract") or {}).get("underscore_policy"),
                },
                "profile": load_profile(ctx),
            }

    @app.patch("/api/runs/{run_id}/nle/segment")
    def patch_nle_segment(run_id: str, body: NleSegmentBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            nle = load_nle(ctx)
            overrides = nle.setdefault("segment_overrides", {})
            overrides[body.segment_id] = {**overrides.get(body.segment_id, {}), **body.patch}
            save_nle(ctx, nle)
            label = body.patch.get("mark_redo") and "marked for redo" or body.patch.get("excluded") and "excluded" or "updated"
            ctx.log(f"Segment {body.segment_id} {label} in NLE.", level="info", stage="nle")
            return {"ok": True, "nle": nle}

    @app.post("/api/runs/{run_id}/nle/split")
    def nle_split(run_id: str, body: SplitBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            nle = split_segment_at(ctx, body.segment_id, body.at_ms)
            ctx.log(f"Split segment {body.segment_id} at {body.at_ms}ms.", level="info", stage="nle")
            return {"ok": True, "nle": nle}

    @app.post("/api/runs/{run_id}/nle/batch")
    def nle_batch(run_id: str, body: NleBatchBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            nle = load_nle(ctx)
            overrides = nle.setdefault("segment_overrides", {})
            count = 0
            for op in body.operations:
                if not op.segment_id:
                    continue
                overrides[op.segment_id] = {**overrides.get(op.segment_id, {}), **op.patch}
                count += 1
            try:
                save_nle(ctx, nle)
            except ValueError as exc:
                raise HTTPException(400, {"errors": [str(exc)]}) from exc
            ctx.log(f"NLE batch update: {count} segment(s).", level="info", stage="nle")
            return {"ok": True, "updated": count, "nle": nle}

    @app.post("/api/runs/{run_id}/nle/snap-boundary")
    def nle_snap_boundary(run_id: str, body: SnapBoundaryBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            if body.edge not in ("start", "end"):
                raise HTTPException(400, "edge must be 'start' or 'end'")
            try:
                snapped = snap_boundary_for_segment(
                    ctx,
                    segment_id=body.segment_id,
                    ms=body.ms,
                    edge=body.edge,
                )
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return {"ok": True, "snapped_ms": snapped}

    @app.get("/api/runs/{run_id}/assembly-timeline")
    def get_assembly_timeline(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        return build_assembly_timeline(ctx)

    @app.get("/api/runs/{run_id}/waveform")
    def get_waveform(run_id: str, path: str = "ingest/normalized.wav") -> dict[str, Any]:
        ctx = _ctx(run_id)
        _assert_artifact_path(path)
        try:
            return load_or_generate_peaks(ctx, path)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/runs/{run_id}/llm-routing")
    def get_llm_routing(run_id: str) -> dict[str, Any]:
        from interview_mux.llm_routing_debug import list_stage_routing_attempts

        ctx = _ctx(run_id)
        return {"attempts": list_stage_routing_attempts(ctx)}

    @app.get("/api/runs/{run_id}/llm-calls")
    def get_llm_calls(run_id: str) -> dict[str, Any]:
        from interview_mux.llm_calls_gui import list_llm_calls_summary

        ctx = _ctx(run_id)
        return list_llm_calls_summary(ctx)

    @app.get("/api/runs/{run_id}/llm-calls/record")
    def get_llm_call_record(run_id: str, path: str) -> dict[str, Any]:
        from interview_mux.llm_calls_gui import get_llm_call_record as load_record

        ctx = _ctx(run_id)
        try:
            return load_record(ctx, path)
        except FileNotFoundError:
            raise HTTPException(404, f"LLM call record not found: {path}") from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.put("/api/runs/{run_id}/llm-calls/record")
    def put_llm_call_record(run_id: str, body: LlmCallRecordUpdateBody) -> dict[str, Any]:
        from interview_mux.llm_calls_gui import update_llm_call_record

        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            volley_dict: dict[str, Any] | None = None
            if body.volley is not None:
                volley_dict = {
                    "system_prompt": body.volley.system_prompt,
                    "turns": [t.model_dump() for t in body.volley.turns],
                }
            try:
                doc = update_llm_call_record(
                    ctx,
                    body.path,
                    volley=volley_dict,
                    raw_response=body.raw_response,
                )
            except FileNotFoundError:
                raise HTTPException(404, f"LLM call record not found: {body.path}") from None
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            ctx.log(
                f"Updated LLM call record {body.path} from GUI.",
                level="info",
                stage="llm_calls_editor",
                detail=json.dumps({"path": body.path}),
            )
            return {"ok": True, "record": doc}

    @app.get("/api/runs/{run_id}/context-index")
    def get_context_index(run_id: str) -> dict[str, Any]:
        from interview_mux.context_index_gui import get_context_index_summary

        ctx = _ctx(run_id)
        return get_context_index_summary(ctx)

    @app.post("/api/runs/{run_id}/context-index/entries")
    def post_context_index_entry(run_id: str, body: VolleyEntryBody) -> dict[str, Any]:
        from interview_mux.context_index_gui import create_volley_entry

        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            try:
                entry = create_volley_entry(ctx, body.model_dump())
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            ctx.log("Created volley memory entry from GUI.", level="info", stage="volley_memory")
            return {"ok": True, "entry": entry}

    @app.put("/api/runs/{run_id}/context-index/entries/{entry_id}")
    def put_context_index_entry(run_id: str, entry_id: str, body: VolleyEntryPatchBody) -> dict[str, Any]:
        from interview_mux.context_index_gui import put_volley_entry

        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            try:
                entry = put_volley_entry(ctx, entry_id, body.model_dump(exclude_unset=True))
            except FileNotFoundError:
                raise HTTPException(404, f"Volley entry not found: {entry_id}") from None
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            ctx.log(f"Updated volley entry {entry_id} from GUI.", level="info", stage="volley_memory")
            return {"ok": True, "entry": entry}

    @app.post("/api/runs/{run_id}/context-index/entries/{entry_id}/invalidate")
    def invalidate_context_index_entry(run_id: str, entry_id: str) -> dict[str, Any]:
        from interview_mux.context_index_gui import invalidate_volley_entry

        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            try:
                entry = invalidate_volley_entry(ctx, entry_id)
            except FileNotFoundError:
                raise HTTPException(404, f"Volley entry not found: {entry_id}") from None
            ctx.log(f"Invalidated volley entry {entry_id}.", level="info", stage="volley_memory")
            return {"ok": True, "entry": entry}

    @app.post("/api/runs/{run_id}/context-index/rebuild")
    def rebuild_context_index_route(run_id: str) -> dict[str, Any]:
        from interview_mux.context_index_gui import rebuild_context_index

        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            result = rebuild_context_index(ctx)
            ctx.log("Rebuilt volley memory index from disk.", level="info", stage="volley_memory")
            return {"ok": True, **result}

    @app.get("/api/runs/{run_id}/artifact")
    def get_artifact(run_id: str, path: str) -> Any:
        ctx = _ctx(run_id)
        _assert_artifact_path(path)
        full = ctx.read_path(path)
        if not full.is_file():
            raise HTTPException(404, f"Artifact not found: {path}")
        if path.endswith(".json"):
            return read_json(full)
        return {"path": path, "text": full.read_text(encoding="utf-8")}

    @app.put("/api/runs/{run_id}/artifact/text")
    def put_artifact_text(run_id: str, body: ArtifactTextBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            _assert_artifact_path(body.path)
            if body.path.endswith(".json"):
                raise HTTPException(400, "Use PUT /artifact with JSON body for .json files.")
            if not _is_editable_text_path(body.path):
                raise HTTPException(400, f"Path not editable via GUI: {body.path}")
            full = ctx.path(body.path)
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(body.text, encoding="utf-8")
            mirror_artifact_to_operator(ctx, body.path, body.text, source="artifact_text_editor")
            ctx.log(f"Saved artifact {body.path} from GUI editor.", level="info", stage="artifact_editor")
            if body.invalidate_from:
                runner.invalidate_from(run_id, body.invalidate_from)
            return {"ok": True, "path": body.path}

    @app.put("/api/runs/{run_id}/artifact")
    def put_artifact(run_id: str, body: ArtifactBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            _assert_artifact_path(body.path)
            if not body.path.endswith(".json"):
                raise HTTPException(400, "Use PUT /artifact/text for non-JSON text files.")
            if isinstance(body.data, dict):
                schema_errors = validate_artifact_write(body.path, body.data)
                if schema_errors:
                    raise HTTPException(
                        400,
                        {
                            "error": "schema_validation_failed",
                            "path": body.path,
                            "errors": schema_errors,
                        },
                    )
            from interview_mux.custom_run_handoff import stage_for_custom_run_path

            stage_key = body.invalidate_from or stage_for_custom_run_path(body.path) or "artifact_editor"
            ctx.write_json(body.path, body.data, stage_key=stage_key)
            stage = stage_key
            mirror_artifact_to_operator(ctx, body.path, body.data, source="artifact_json_editor")
            ctx.log(f"Saved artifact {body.path} from GUI editor.", level="info", stage=stage)
            if body.path == "understanding/analysis_state.json":
                persist_operator_analysis_profile(ctx, source="artifact_json_editor")
            if body.path == "understanding/source_acoustic_profile.json" and isinstance(body.data, dict):
                overrides = body.data.get("operator_overrides")
                if isinstance(overrides, dict) and overrides:
                    ctx.log(
                        "Acoustic profile operator overrides saved.",
                        level="success",
                        stage="source_acoustic_profile",
                        detail="acoustic_profile_override_saved",
                    )
            if body.invalidate_from:
                runner.invalidate_from(run_id, body.invalidate_from)
            return {"ok": True, "path": body.path}

    @app.post("/api/runs/{run_id}/flow")
    def set_flow(run_id: str, body: FlowBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            set_selected_flow(ctx, body.flow)
            persist_operator_flow_selection(ctx, body.flow, source="g2_flow_select")
            ctx.log(f"Output flow selected: {body.flow}", level="success", stage="g2_flow_select")
            refresh_journey_meta(ctx)
            return {"ok": True, "selected_flow": body.flow}

    @app.post("/api/runs/{run_id}/preclean-offer")
    def preclean_offer(run_id: str, body: PrecleanOfferBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            allowed_checkpoints = {
                "before_ingest",
                "g1_vo_pickup",
            }
            if body.checkpoint not in allowed_checkpoints:
                raise HTTPException(400, f"Unknown pre-clean checkpoint: {body.checkpoint}")
            if body.scope and body.scope not in {"full_source", "vo_pickup", "normalized_rebuild"}:
                raise HTTPException(400, f"Invalid pre-clean scope: {body.scope}")
            changed, payload = _record_preclean_offer(
                ctx,
                checkpoint=body.checkpoint,
                action=body.action,
                scope=body.scope,
            )
            if body.action == "accept" and changed:
                from interview_mux.stages.audio_preclean import invalidate_after_preclean_accept

                scope = str(payload.get("scope") or "full_source")
                invalidate_after_preclean_accept(ctx, scope)
            if changed:
                persist_operator_preclean(ctx, source=f"preclean_{body.action}")
            return {"ok": True, "changed": changed, "audio_preclean": payload}

    @app.get("/api/runs/{run_id}/pending-writes")
    def list_pending_writes(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        from interview_mux.write_staging import all_pending_stages, list_pending_paths

        stages = all_pending_stages(ctx)
        return {
            "stages": [
                {"stage_id": sid, "paths": list_pending_paths(ctx, sid)} for sid in stages
            ]
        }

    @app.get("/api/runs/{run_id}/pending-writes/{stage_id}")
    def get_pending_writes_stage(run_id: str, stage_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        from interview_mux.write_staging import list_pending_paths

        paths = list_pending_paths(ctx, stage_id)
        if not paths and ctx.artifact_exists("run_meta.json"):
            meta = ctx.read_json("run_meta.json")
            pending = meta.get("pending_write_approval") if isinstance(meta, dict) else {}
            if isinstance(pending, dict):
                info = pending.get(stage_id)
                if isinstance(info, dict):
                    raw = info.get("paths")
                    if isinstance(raw, list):
                        paths = [str(p) for p in raw if p]
        if not paths:
            raise HTTPException(404, f"No pending writes for stage: {stage_id}")
        return {"stage_id": stage_id, "paths": paths}

    @app.get("/api/runs/{run_id}/pending-writes/{stage_id}/content")
    def get_pending_write_content(run_id: str, stage_id: str, path: str) -> Any:
        ctx = _ctx(run_id)
        _assert_artifact_path(path)
        from interview_mux.write_staging import read_pending_content, read_pending_json, read_pending_text

        rel_path = path
        try:
            if path.endswith(".json"):
                return read_pending_json(ctx, stage_id, rel_path)
            if path.endswith((".md", ".txt")):
                return {"text": read_pending_text(ctx, stage_id, rel_path)}
            raw = read_pending_content(ctx, stage_id, rel_path)
            return {"bytes_b64": None, "size": len(raw)}
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.put("/api/runs/{run_id}/pending-writes/{stage_id}/content")
    def put_pending_write_content(
        run_id: str, stage_id: str, body: PendingWriteContentBody
    ) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            _assert_artifact_path(body.path)
            from interview_mux.write_staging import write_pending_content

            if body.data is not None:
                write_pending_content(ctx, stage_id, body.path, data=body.data)
            elif body.text is not None:
                write_pending_content(ctx, stage_id, body.path, text=body.text)
            else:
                raise HTTPException(400, "Provide data or text")
            return {"ok": True, "path": body.path}

    def _approve_staged_writes_locked(
        run_id: str,
        ctx: RunContext,
        stage_id: str,
    ) -> list[str]:
        from interview_mux.write_staging import approve_stage_writes, list_pending_paths

        with runner.operator_guard(run_id):
            paths = list_pending_paths(ctx, stage_id)
            if not paths:
                raise HTTPException(404, f"No pending writes for stage: {stage_id}")
            runner.mark_write_approval_saving(ctx, stage_id, paths)
            try:
                return approve_stage_writes(ctx, stage_id)
            except Exception:
                if list_pending_paths(ctx, stage_id):
                    runner.restore_write_approval_pause(ctx, stage_id, paths)
                raise

    @app.post("/api/runs/{run_id}/pending-writes/{stage_id}/approve")
    async def approve_pending_writes(run_id: str, stage_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)

            def _approve_locked() -> list[str]:
                from interview_mux.write_staging import assert_write_approval_allowed

                assert_write_approval_allowed(ctx, stage_id)
                return _approve_staged_writes_locked(run_id, ctx, stage_id)

            try:
                flushed = await run_in_threadpool(_approve_locked)
            except RunBusyError as exc:
                raise HTTPException(409, {"error": "run_busy", "message": str(exc)}) from exc
            except HTTPException:
                raise
            except Exception as exc:
                from interview_mux.write_staging import WriteApprovalBlockedError

                if isinstance(exc, WriteApprovalBlockedError):
                    raise HTTPException(409, str(exc)) from exc
                raise
            title = STAGE_BY_ID.get(stage_id)
            stage_label = title.title if title else stage_id.replace("_", " ")
            runner.clear_operator_pause(
                ctx,
                stage_id,
                message=(
                    f"{stage_label}: saved {len(flushed)} file(s) to disk — advancing pipeline."
                ),
            )
            ctx.log(
                f"Saved {len(flushed)} file(s) for {stage_label} — advancing pipeline.",
                level="success",
                stage=stage_id,
                action_id="api.write_approval.approve",
                origin="api",
                detail={
                    "journey_kind": "milestone",
                    "event": "write_approval_complete",
                    "paths": flushed,
                    "stage_id": stage_id,
                },
            )
            refresh_journey_meta(ctx)
            return {"ok": True, "flushed": flushed, "stage_id": stage_id}

    @app.post("/api/runs/{run_id}/continue-after-checkpoint")
    async def continue_after_checkpoint(
        run_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Approve staged writes and release the run lock without auto-starting the next stage."""
        kind = str(body.get("kind") or "write_approval")
        stage_id = str(body.get("stage_id") or "")
        if kind == "artifact_clarification":
            if not stage_id:
                raise HTTPException(400, "stage_id required")
            ctx = _ctx(run_id)

            def _itr_continue() -> dict[str, Any]:
                from interview_mux.artifact_auto_resolve import auto_resolve_stage

                result = auto_resolve_stage(ctx, stage_id, runner=runner, run_id=run_id)
                refresh_journey_meta(ctx)
                return result.to_dict()

            try:
                with runner.operator_guard(run_id):
                    return _itr_continue()
            except RunBusyError as exc:
                raise HTTPException(409, str(exc)) from exc

        if kind != "write_approval" or not stage_id:
            raise HTTPException(400, "kind=write_approval and stage_id required")

        def _approve_and_next() -> dict[str, Any]:
            return runner.approve_write_and_continue(run_id, stage_id)

        try:
            return await run_in_threadpool(_approve_and_next)
        except RunBusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except Exception as exc:
            from interview_mux.write_staging import WriteApprovalBlockedError

            if isinstance(exc, WriteApprovalBlockedError):
                raise HTTPException(409, str(exc)) from exc
            raise

    @app.post("/api/runs/{run_id}/pending-writes/{stage_id}/discard")
    def discard_pending_writes(run_id: str, stage_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        from interview_mux.write_staging import discard_stage_writes

        try:
            with runner.operator_guard(run_id):
                discard_stage_writes(ctx, stage_id)
                runner.invalidate_from(run_id, stage_id)
        except RunBusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        title = STAGE_BY_ID.get(stage_id)
        stage_label = title.title if title else stage_id.replace("_", " ")
        runner.clear_operator_pause(
            ctx,
            stage_id,
            message=f"{stage_label}: discarded staged outputs — re-run when ready.",
            level="info",
        )
        refresh_journey_meta(ctx)
        return {"ok": True, "stage_id": stage_id}

    @app.get("/api/runs/{run_id}/stages/{stage_id}/issues")
    def get_stage_issues(run_id: str, stage_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        if stage_id not in STAGE_BY_ID:
            raise HTTPException(404, f"Unknown stage: {stage_id}")
        from interview_mux.artifact_auto_resolve import auto_resolve_stage, get_stage_issues_summary, stage_capabilities
        from interview_mux.artifact_issue_triage import (
            blocking_issues_remaining,
            list_stage_issues,
            triage_enabled,
        )

        items = list_stage_issues(ctx, stage_id) if triage_enabled() else []
        summary = get_stage_issues_summary(ctx, stage_id) if triage_enabled() else {}
        caps = stage_capabilities(stage_id)
        return {
            "stage_id": stage_id,
            "items": items,
            "open_blocking": blocking_issues_remaining(ctx, stage_id),
            "summary": summary,
            "capabilities": caps,
        }

    @app.post("/api/runs/{run_id}/stages/{stage_id}/issues/auto-resolve")
    async def post_stage_issues_auto_resolve(
        run_id: str,
        stage_id: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ctx = _ctx(run_id)
        if stage_id not in STAGE_BY_ID:
            raise HTTPException(404, f"Unknown stage: {stage_id}")
        from interview_mux.artifact_auto_resolve import auto_resolve_stage
        from interview_mux.artifact_issue_triage import triage_enabled

        if not triage_enabled():
            return {"outcome": "success", "stage_key": stage_id, "open_blocking": 0, "can_advance_pipeline": True}

        autopilot = bool((body or {}).get("autopilot"))

        def _resolve() -> dict[str, Any]:
            ctx.log(
                f"api.itr.auto_resolve stage={stage_id} autopilot={autopilot}",
                level="action",
                stage=stage_id,
                action_id="api.itr.auto_resolve",
            )
            result = auto_resolve_stage(
                ctx,
                stage_id,
                runner=runner,
                run_id=run_id,
                autopilot=autopilot,
            )
            return result.to_dict()

        try:
            with runner.operator_guard(run_id):
                out = _resolve()
        except RunBusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        refresh_journey_meta(ctx)
        return out

    @app.post("/api/runs/{run_id}/stages/{stage_id}/issues/auto-repair")
    def post_stage_issues_auto_repair(run_id: str, stage_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        if stage_id not in STAGE_BY_ID:
            raise HTTPException(404, f"Unknown stage: {stage_id}")
        from interview_mux.artifact_issue_triage import run_triage_pipeline, triage_enabled

        if not triage_enabled():
            return {"ok": True, "summary": {}, "open_blocking": 0}
        try:
            with runner.operator_guard(run_id):
                result = run_triage_pipeline(ctx, stage_id, staged=True)
        except RunBusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        refresh_journey_meta(ctx)
        return {"ok": True, "summary": result.summary(), "open_blocking": result.open_blocking}

    @app.post("/api/runs/{run_id}/stages/{stage_id}/issues/{issue_id}/resolve")
    async def post_stage_issue_resolve(
        run_id: str,
        stage_id: str,
        issue_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        ctx = _ctx(run_id)
        if stage_id not in STAGE_BY_ID:
            raise HTTPException(404, f"Unknown stage: {stage_id}")
        from interview_mux.artifact_issue_triage import blocking_issues_remaining, resolve_issue

        choice = body.get("choice")
        if choice is None:
            raise HTTPException(400, "choice required")

        def _resolve() -> dict[str, Any]:
            ctx.log(
                f"api.itr.issue_resolve stage={stage_id} issue={issue_id}",
                level="action",
                stage=stage_id,
                action_id="api.itr.issue_resolve",
            )
            ok, errors = resolve_issue(ctx, stage_id, issue_id, choice)
            return {
                "ok": ok,
                "errors": errors,
                "open_blocking": blocking_issues_remaining(ctx, stage_id),
            }

        try:
            with runner.operator_guard(run_id):
                out = _resolve()
        except RunBusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        refresh_journey_meta(ctx)
        return out

    @app.post("/api/runs/{run_id}/stages/{stage_id}/issues/revalidate")
    def post_stage_issues_revalidate(run_id: str, stage_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            if stage_id not in STAGE_BY_ID:
                raise HTTPException(404, f"Unknown stage: {stage_id}")
            from interview_mux.artifact_issue_triage import (
                blocking_issues_remaining,
                clear_clarification_gate,
                get_propagation_plan,
                revalidate_after_repair,
                revalidate_downstream_on_segment_fix,
                triage_enabled,
            )

            if not triage_enabled():
                return {"ok": True, "errors": [], "open_blocking": 0}
            ctx.log(
                f"api.itr.revalidate stage={stage_id}",
                level="action",
                stage=stage_id,
                action_id="api.itr.revalidate",
            )
            ok, errors = revalidate_after_repair(ctx, stage_id, staged=True)
            downstream_errors = revalidate_downstream_on_segment_fix(ctx, stage_id)
            propagation_plan = get_propagation_plan(ctx, stage_id)
            open_blocking = blocking_issues_remaining(ctx, stage_id)
            all_ok = ok and not downstream_errors and not propagation_plan.get("has_blocking")
            if all_ok and open_blocking == 0:
                clear_clarification_gate(ctx, stage_id)
            refresh_journey_meta(ctx)
            return {
                "ok": all_ok,
                "errors": errors,
                "downstream_errors": downstream_errors,
                "propagation_plan": propagation_plan,
                "open_blocking": open_blocking,
            }

    @app.get("/api/runs/{run_id}/stages/{stage_id}/propagation-plan")
    def get_stage_propagation_plan(run_id: str, stage_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        if stage_id not in STAGE_BY_ID:
            raise HTTPException(404, f"Unknown stage: {stage_id}")
        from interview_mux.artifact_issue_triage import get_propagation_plan, triage_enabled

        if not triage_enabled():
            return {"stage_id": stage_id, "propagation_plan": {}}
        return {"stage_id": stage_id, "propagation_plan": get_propagation_plan(ctx, stage_id)}

    @app.get("/api/runs/{run_id}/stages/{stage_id}/decisions")
    def get_stage_decisions(run_id: str, stage_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        if stage_id not in STAGE_BY_ID:
            raise HTTPException(404, f"Unknown stage: {stage_id}")
        from interview_mux.operator_decisions import stage_decisions_summary

        return stage_decisions_summary(ctx, stage_id)

    @app.post("/api/runs/{run_id}/stages/{stage_id}/decisions/{decision_id}/resolve")
    async def post_stage_decision_resolve(
        run_id: str,
        stage_id: str,
        decision_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        ctx = _ctx(run_id)
        if stage_id not in STAGE_BY_ID:
            raise HTTPException(404, f"Unknown stage: {stage_id}")
        choice = body.get("choice")
        if choice is None:
            raise HTTPException(400, "choice required")
        from interview_mux.stage_finalize import resolve_operator_decision

        def _run() -> dict[str, Any]:
            ctx.log(
                f"api.decision.resolve stage={stage_id} decision={decision_id}",
                level="action",
                stage=stage_id,
                action_id="api.decision.resolve",
            )
            return resolve_operator_decision(
                ctx,
                stage_id,
                decision_id,
                choice,
                runner=runner,
                run_id=run_id,
            )

        try:
            with runner.operator_guard(run_id):
                out = _run()
        except RunBusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        refresh_journey_meta(ctx)
        return out

    @app.post("/api/runs/{run_id}/stages/{stage_id}/propagation/execute")
    async def post_stage_propagation_execute(
        run_id: str,
        stage_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        ctx = _ctx(run_id)
        if stage_id not in STAGE_BY_ID:
            raise HTTPException(404, f"Unknown stage: {stage_id}")
        invalidate_from = str(body.get("invalidate_from") or "")
        if not invalidate_from:
            raise HTTPException(400, "invalidate_from required")
        rerun_stages = body.get("rerun_stages")
        from interview_mux.artifact_issue_triage import execute_propagation

        def _run() -> dict[str, Any]:
            ctx.log(
                f"api.itr.propagation stage={stage_id} from={invalidate_from}",
                level="action",
                stage=stage_id,
                action_id="api.itr.propagation",
            )
            result = execute_propagation(
                ctx,
                stage_id,
                invalidate_from=invalidate_from,
                rerun_stages=rerun_stages if isinstance(rerun_stages, list) else None,
                runner=runner,
                run_id=run_id,
            )
            return {
                "ok": result.ok,
                "errors": result.errors,
                "job": result.job,
                "invalidated_from": result.invalidated_from,
                "upstream_stage": result.upstream_stage,
            }

        try:
            with runner.operator_guard(run_id):
                out = _run()
        except RunBusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        refresh_journey_meta(ctx)
        return out

    @app.post("/api/runs/{run_id}/stages/{stage_id}/issues/{issue_id}/execute-action")
    async def post_stage_issue_execute_action(
        run_id: str,
        stage_id: str,
        issue_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        ctx = _ctx(run_id)
        if stage_id not in STAGE_BY_ID:
            raise HTTPException(404, f"Unknown stage: {stage_id}")
        action = str(body.get("action") or "")
        if not action:
            raise HTTPException(400, "action required")
        from interview_mux.artifact_issue_triage import blocking_issues_remaining, execute_recovery_action

        def _run() -> dict[str, Any]:
            result = execute_recovery_action(
                ctx,
                stage_id,
                issue_id,
                action,
                upstream_stage=body.get("upstream_stage"),
                runner=runner,
                run_id=run_id,
            )
            return {
                "ok": result.ok,
                "errors": result.errors,
                "job": result.job,
                "upstream_stage": result.upstream_stage,
                "invalidated_from": result.invalidated_from,
                "open_blocking": blocking_issues_remaining(ctx, stage_id),
            }

        try:
            with runner.operator_guard(run_id):
                out = _run()
        except RunBusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        refresh_journey_meta(ctx)
        return out

    @app.get("/api/runs/{run_id}/stages/{stage_id}/reuse-offers")
    def get_stage_reuse_offers(run_id: str, stage_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        if stage_id not in STAGE_BY_ID:
            raise HTTPException(404, f"Unknown stage: {stage_id}")
        from interview_mux.stage_execution_reuse import reuse_offer_payload

        return reuse_offer_payload(ctx, stage_id)

    @app.post("/api/runs/{run_id}/stages/{stage_id}/reuse")
    def post_stage_reuse(run_id: str, stage_id: str, body: StageReuseBody) -> dict[str, Any]:
        ctx = _ctx(run_id)
        if stage_id not in STAGE_BY_ID:
            raise HTTPException(404, f"Unknown stage: {stage_id}")
        from interview_mux.stage_execution_reuse import (
            apply_stage_reuse,
            get_reuse_decision,
            prior_run_has_reusable_stage,
            record_reuse_decision,
            reuse_already_applied,
            reuse_candidates_if_undecided,
        )

        title = STAGE_BY_ID.get(stage_id)
        stage_label = title.title if title else stage_id.replace("_", " ")
        entry: dict[str, Any] = {}
        copied: list[str] = []
        action = body.action

        if body.action == "decline_and_run":
            return runner.decline_reuse_and_run(
                run_id,
                stage_id,
                api_consents=body.api_consents,
            )

        try:
            with runner.operator_guard(run_id):
                if body.action == "decline":
                    existing = get_reuse_decision(ctx, stage_id)
                    if existing and existing.get("action") == "decline":
                        refresh_journey_meta(ctx)
                        runner.clear_operator_pause(
                            ctx,
                            stage_id,
                            message=f"{stage_label}: reuse decision recorded — ready for next step.",
                            level="info",
                        )
                        return {"ok": True, "action": "decline", "stage_reuse": existing}
                    entry = record_reuse_decision(ctx, stage_id, action="decline")
                    append_operator_stage_reuse(ctx, stage_id, entry, source="gui_decline")
                elif reuse_already_applied(ctx, stage_id):
                    entry = get_reuse_decision(ctx, stage_id) or {}
                    refresh_journey_meta(ctx)
                    runner.clear_operator_pause(
                        ctx,
                        stage_id,
                        message=f"{stage_label}: reuse already applied — ready for next step.",
                        level="info",
                    )
                    return {
                        "ok": True,
                        "action": "accept",
                        "stage_reuse": entry,
                        "copied": [],
                        "stage_done": ctx.is_done(stage_id),
                    }
                else:
                    source_id = body.source_run_id
                    if not source_id:
                        raise HTTPException(400, "source_run_id is required when action is accept")
                    if not RunContext.exists(source_id):
                        raise HTTPException(404, f"Source run not found: {source_id}")
                    source = RunContext(source_id, create=False)
                    if not prior_run_has_reusable_stage(source, stage_id):
                        raise HTTPException(
                            400,
                            f"Run {source_id} does not have complete reusable outputs for {stage_id}",
                        )
                    allowed = {c.run_id for c in reuse_candidates_if_undecided(ctx, stage_id)}
                    if source_id not in allowed:
                        raise HTTPException(
                            400,
                            f"Run {source_id} is not an eligible reuse source for this stage",
                        )
                    entry = record_reuse_decision(
                        ctx, stage_id, action="accept", source_run_id=source_id
                    )
                    copied = apply_stage_reuse(ctx, stage_id, source_id)
                    append_operator_stage_reuse(
                        ctx,
                        stage_id,
                        {**entry, "copied": copied},
                        source="gui_accept",
                    )
                    action = "accept"
        except RunBusyError as exc:
            raise HTTPException(409, str(exc)) from exc

        refresh_journey_meta(ctx)
        from interview_mux.write_staging import has_pending_writes, list_pending_paths

        if action == "accept" and copied and has_pending_writes(ctx, stage_id):
            paths = list_pending_paths(ctx, stage_id)
            runner.restore_write_approval_pause(ctx, stage_id, paths)
            ctx.log(
                f"{stage_label}: reused {len(copied)} file(s) — review outputs before saving.",
                level="action",
                stage=stage_id,
                action_id="api.stage_reuse.accept",
                origin="api",
            )
        else:
            runner.clear_operator_pause(
                ctx,
                stage_id,
                message=(
                    f"{stage_label}: reused {len(copied)} file(s) from prior execution."
                    if action == "accept" and copied
                    else f"{stage_label}: reuse decision recorded — ready for next step."
                ),
                level="success" if action == "accept" and copied else "info",
            )
        return {
            "ok": True,
            "action": action,
            "stage_reuse": entry,
            "copied": copied,
            "stage_done": ctx.is_done(stage_id),
        }

    @app.get("/api/runs/{run_id}/sfx-prompts")
    def get_sfx_prompts(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        path = "sound_design/sfx_prompts.json"
        if not ctx.artifact_exists(path):
            raise HTTPException(404, f"Artifact not found: {path}")
        data = ctx.read_json(path)
        rows = data.get("prompts") if isinstance(data, dict) and isinstance(data.get("prompts"), list) else []
        review = _read_prompt_review_meta(ctx)
        review_required = bool(merged_config().get("g1_5_require_prompt_approval", False))
        approved = bool(review.get("approved"))
        warnings = prompt_completeness_warnings(ctx, rows)
        listen_results = _read_sfx_listen_results(ctx)
        mmaudio_qa = _read_mmaudio_qa(ctx)
        generation_meta = _read_sfx_generation_meta(ctx)
        sonic_context = load_sonic_context(ctx)
        return {
            "path": path,
            "prompts": rows,
            "review": review,
            "review_required": review_required,
            "can_generate": (not review_required) or approved,
            "warnings": warnings,
            "listen_results": listen_results,
            "generated_assets": _discover_generated_sfx_assets(ctx),
            "mmaudio_qa": mmaudio_qa,
            "generation_meta": generation_meta,
            "sonic_context": compact_sonic_context(sonic_context) if sonic_context else None,
        }

    @app.put("/api/runs/{run_id}/sfx-prompts")
    def put_sfx_prompts(run_id: str, body: ArtifactBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            if body.path != "sound_design/sfx_prompts.json":
                raise HTTPException(400, "This endpoint only supports sound_design/sfx_prompts.json")
            if not isinstance(body.data, dict):
                raise HTTPException(400, "Prompt payload must be a JSON object with prompts[].")
            rows = body.data.get("prompts")
            if not isinstance(rows, list):
                raise HTTPException(400, "Prompt payload must include prompts[] array.")
            schema_errors = validate_prompts_payload({"prompts": rows})
            if schema_errors:
                raise HTTPException(400, "; ".join(schema_errors[:5]))
            write_json(ctx.path(body.path), {"prompts": rows})
            review = _set_prompt_review_meta(
                ctx,
                approved=False,
                approved_by=None,
                approved_at=None,
            )
            ctx.log(
                "SFX prompts edited in review panel; approval reset.",
                level="info",
                stage="sfx_prompt_craft",
                detail=f"rows={len(rows)}",
            )
            if body.invalidate_from:
                runner.invalidate_from(run_id, body.invalidate_from)
            warnings = prompt_completeness_warnings(ctx, rows)
            persist_operator_sfx_prompts(
                ctx,
                {"prompts": rows, "review": review},
                source="sfx_prompts_put",
            )
            return {"ok": True, "path": body.path, "review": review, "warnings": warnings}

    @app.post("/api/runs/{run_id}/sfx-prompts/approve")
    def approve_sfx_prompts(run_id: str, body: SfxPromptApproveBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            path = "sound_design/sfx_prompts.json"
            if not ctx.artifact_exists(path):
                raise HTTPException(404, f"Artifact not found: {path}")
            data = ctx.read_json(path)
            rows = data.get("prompts") if isinstance(data, dict) and isinstance(data.get("prompts"), list) else []
            review = _set_prompt_review_meta(
                ctx,
                approved=True,
                approved_by=body.approved_by or "operator",
                approved_at=datetime.now(timezone.utc).isoformat(),
            )
            asset_ids = [str(row.get("asset_id")) for row in rows if isinstance(row, dict) and row.get("asset_id")]
            detail = {"approved_by": review.get("approved_by"), "asset_ids": asset_ids}
            ctx.log(
                "sfx_prompts_approved",
                level="success",
                stage="sfx_prompt_craft",
                detail=str(detail),
            )
            warnings = prompt_completeness_warnings(ctx, rows)
            for w in warnings:
                ctx.log(w, level="warning", stage="sfx_prompt_craft")
            persist_operator_sfx_prompts(
                ctx,
                {"prompts": rows, "review": review},
                source="sfx_prompts_approve",
            )
            return {"ok": True, "review": review, "asset_ids": asset_ids, "warnings": warnings}

    @app.post("/api/runs/{run_id}/sfx-prompts/listen-result")
    def post_sfx_listen_result(run_id: str, body: SfxListenResultBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            asset_id = body.asset_id.strip()
            if not asset_id:
                raise HTTPException(400, "asset_id is required")
            if body.mode == "under_speech":
                entry, results = _append_speech_under_listen_result(
                    ctx,
                    asset_id=asset_id,
                    result=body.result,
                    note=body.note,
                )
                ctx.log(
                    "speech_under_listen_result_recorded",
                    level="info",
                    stage="mix_flow1",
                    detail=entry,
                )
                return {"ok": True, "entry": entry, "speech_under_listen_results": results}

            entry, results = _append_sfx_listen_result(
                ctx,
                asset_id=asset_id,
                result=body.result,
                note=body.note,
            )
            event = (
                "sfx_post_listen_pass"
                if body.result == "pass"
                else "sfx_post_listen_fail"
            )
            detail: dict[str, str] = {"asset_id": asset_id}
            if body.note:
                detail["note"] = body.note
            ctx.log(
                event,
                level="success" if body.result == "pass" else "warning",
                detail=str(detail),
            )
            persist_operator_sfx_listen_results(ctx, source="sfx_listen_result")
            from interview_mux.gates import sync_post_listen_gate_state
            from interview_mux.stages.sfx_mmaudio import maybe_auto_refine

            gate_state = sync_post_listen_gate_state(ctx)
            auto_refined: list[str] = []
            if body.result == "fail":
                flow = get_selected_flow(ctx)
                stage = "mmaudio_sfx_flow1" if flow == "flow1" else "mmaudio_sfx_flow2"
                auto_refined = maybe_auto_refine(ctx, stage)
            return {
                "ok": True,
                "entry": entry,
                "sfx_listen_results": results,
                "post_listen_gate_state": gate_state,
                "auto_refined_asset_ids": auto_refined,
            }

    @app.post("/api/runs/{run_id}/sfx-prompts/refine")
    def post_sfx_prompt_refine(run_id: str, body: SfxPromptRefineBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            from interview_mux.stages.sfx_mmaudio import grant_auto_refine_override
            from interview_mux.stages.sound_design_stages import run_sfx_prompt_refine

            asset_ids = [a.strip() for a in (body.asset_ids or []) if a.strip()]
            if body.force or asset_ids:
                grant_auto_refine_override(ctx, asset_ids)
            run_sfx_prompt_refine(ctx, asset_ids=body.asset_ids)
            data = ctx.read_json("sound_design/sfx_prompts.json")
            rows = data.get("prompts") if isinstance(data, dict) else []
            review = _read_prompt_review_meta(ctx)
            return {
                "ok": True,
                "prompts": rows,
                "review": review,
                "refined_asset_ids": body.asset_ids or [],
            }

    @app.post("/api/runs/{run_id}/sfx-prompts/regenerate")
    def post_sfx_prompt_regenerate(run_id: str, body: SfxPromptRegenBody) -> dict[str, Any]:
        if runner.is_running(run_id):
            raise HTTPException(409, "A job is already running for this run.")
        stage: str
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            asset_ids = [a.strip() for a in body.asset_ids if a.strip()]
            if not asset_ids:
                raise HTTPException(400, "asset_ids required")

            def patch(m: dict[str, Any]) -> None:
                m["sfx_regen_asset_ids"] = sorted(set(asset_ids))

            ctx.mutate_run_meta(patch)
            flow = get_selected_flow(ctx)
            stage = "mmaudio_sfx_flow1" if flow == "flow1" else "mmaudio_sfx_flow2"
            marker = ctx.final_path(".stage_done", stage)
            if marker.is_file():
                marker.unlink()
            ctx.log(
                "sfx_regen_requested",
                level="info",
                stage=stage,
                detail={"asset_ids": asset_ids},
            )
            set_active_execution(run_id)
        return runner.start(run_id, mode="stage", stage=stage, from_stage=stage)

    @app.get("/api/runs/{run_id}/sfx-qa")
    def get_sfx_qa(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        return _read_mmaudio_qa(ctx)

    @app.post("/api/runs/{run_id}/handoff-ack")
    def handoff_ack(run_id: str, body: HandoffAckBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            now = datetime.now(timezone.utc).isoformat()

            def _patch(meta: dict[str, Any]) -> None:
                ack = dict(meta.get("handoff_ack") or {})
                ack[body.stage_id] = now
                meta["handoff_ack"] = ack
                pending = dict(meta.get("handoff_pending_writes") or {})
                pending.pop(body.stage_id, None)
                meta["handoff_pending_writes"] = pending

            meta = ctx.mutate_run_meta(_patch)
            title = STAGE_BY_ID.get(body.stage_id)
            stage_label = title.title if title else body.stage_id.replace("_", " ")
            ctx.log(
                f"Handoff acknowledged for {body.stage_id} — ready for next step.",
                level="success",
                stage=body.stage_id,
            )
            runner.clear_operator_pause(
                ctx,
                body.stage_id,
                message=f"{stage_label}: AI outputs reviewed — ready for next step.",
            )
            return {"ok": True, "handoff_ack": meta.get("handoff_ack") or {}}

    @app.post("/api/runs/{run_id}/execute")
    def execute(run_id: str, body: ExecuteBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            stage = body.stage or body.from_stage
            stage_label = (
                STAGE_BY_ID[stage].title
                if stage and stage in STAGE_BY_ID
                else (stage or body.mode).replace("_", " ")
            )
            ctx.log(
                f"Operator requested: run {stage_label} (mode={body.mode})",
                level="action",
                stage=stage or "gui",
            )
            set_active_execution(run_id)
        flow_modes = ("flow1", "flow2", "flow3", "flow1_until_preview", "flow1_polish")
        return runner.start(
            run_id,
            mode=body.mode,
            stage=body.stage,
            flow=body.mode if body.mode in flow_modes else None,
            from_stage=body.from_stage or body.stage,
            until_stage=body.until_stage,
            nle_full_refresh=body.nle_full_refresh,
            nle_apply_mode=body.nle_apply_mode,
            api_consents=body.api_consents,
        )

    @app.post("/api/runs/{run_id}/fill-artifact-gaps")
    def fill_artifact_gaps(run_id: str, body: FillArtifactGapsBody) -> dict[str, Any]:
        from interview_mux.artifact_completeness import stage_keys_for_artifact_path

        stage: str
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            _assert_artifact_path(body.path)
            stage_ids = stage_keys_for_artifact_path(body.path)
            if not stage_ids:
                raise HTTPException(400, f"No LLM stage registered for artifact path: {body.path}")
            set_active_execution(run_id)
            stage = stage_ids[0]
            ctx.log(
                f"Fill gaps requested for {body.path} — re-running stage {stage}",
                level="info",
                stage=stage,
            )
        return runner.start(
            run_id,
            mode="stage",
            stage=stage,
            from_stage=stage,
            api_consents=body.api_consents,
        )

    @app.post("/api/runs/{run_id}/extract-value-features")
    def extract_value_features(run_id: str) -> dict[str, Any]:
        from interview_mux.value_analysis.extract import extract_and_write_value_features

        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            cfg = merged_config()
            if not value_analysis_enabled(cfg):
                raise HTTPException(400, "value_analysis is disabled in config")
            written = extract_and_write_value_features(ctx, cfg=cfg)
            ctx.log(
                f"Value features extracted: {', '.join(written) if written else 'none'}",
                level="info",
                stage="content_context",
            )
            return {"ok": True, "profiles_written": written or []}

    @app.get("/api/runs/{run_id}/job")
    def get_job(run_id: str) -> dict[str, Any]:
        return runner.get_job(run_id)

    @app.get("/api/runs/{run_id}/transcript")
    def get_transcript(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        return transcript_review.get_transcript_state(ctx)

    @app.patch("/api/runs/{run_id}/transcript/words")
    def patch_transcript_words(run_id: str, body: TranscriptWordsPatchBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            if not ctx.artifact_exists("transcript/full.json"):
                raise HTTPException(404, "Transcript not found — run transcribe first.")
            updates = [{"index": u.index, "text": u.text} for u in body.updates]
            return transcript_review.patch_transcript_words(ctx, updates)

    @app.get("/api/runs/{run_id}/transcript-review")
    def get_transcript_review(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        return transcript_review.get_review_state(ctx)

    @app.put("/api/runs/{run_id}/transcript-review/{chunk_id}")
    def put_transcript_chunk(run_id: str, chunk_id: str, body: TranscriptChunkBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            if not ctx.artifact_exists("transcript/review_queue.json"):
                raise HTTPException(404, "Review queue not built — run transcript_review_build first.")
            return transcript_review.save_chunk_correction(
                ctx, chunk_id, body.text, reviewed=body.reviewed
            )

    @app.get("/api/runs/{run_id}/analysis-profile")
    def get_analysis_profile(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        ensure_analysis_workspace(ctx)
        state = load_analysis_state(ctx)
        queue = ctx.read_json("understanding/investigation_queue.json")
        return {
            "analysis_state": state,
            "investigation_queue": queue,
            "editable_paths": list(EDITABLE_PROFILE_PATHS),
            "operator_verified": (state.get("meta") or {}).get("operator_verified", False),
            "completion": state.get("completion"),
        }

    @app.put("/api/runs/{run_id}/analysis-profile")
    def put_analysis_profile(run_id: str, body: AnalysisProfileBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            ensure_analysis_workspace(ctx)
            if isinstance(body.data, dict):
                schema_errors = validate_artifact_write(ANALYSIS_STATE_PATH, body.data)
                if schema_errors:
                    raise HTTPException(
                        400,
                        {
                            "error": "schema_validation_failed",
                            "path": ANALYSIS_STATE_PATH,
                            "errors": schema_errors,
                        },
                    )
            save_analysis_state(ctx, body.data, stage="operator_gui")
            _sync_tbiy_operator_profile(ctx, body.data if isinstance(body.data, dict) else {})
            if body.operator_verified is not None:
                mark_operator_verified(ctx, body.operator_verified)
            persist_operator_analysis_profile(ctx, source="analysis_profile_put")
            ctx.log(
                "Interview profile saved from GUI."
                + (" Verified." if body.operator_verified else ""),
                level="success",
                stage="analysis_profile",
            )
            if body.invalidate_from:
                runner.invalidate_from(run_id, body.invalidate_from)
            state = load_analysis_state(ctx)
            return {
                "ok": True,
                "operator_verified": (state.get("meta") or {}).get("operator_verified"),
                "completion": state.get("completion"),
            }

    @app.post("/api/runs/{run_id}/analysis-profile/verify")
    def verify_analysis_profile(run_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            ensure_analysis_workspace(ctx)
            mark_operator_verified(ctx, True)
            persist_operator_analysis_profile(ctx, source="analysis_profile_verify")
            ctx.log("Interview profile marked verified.", level="success", stage="analysis_profile")
            refresh_journey_meta(ctx)
            return {"ok": True, "operator_verified": True}

    @app.get("/api/runs/{run_id}/story-board")
    def get_story_board(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        ensure_analysis_workspace(ctx)
        state = load_analysis_state(ctx)
        queue = (
            ctx.read_json("understanding/investigation_queue.json")
            if ctx.artifact_exists("understanding/investigation_queue.json")
            else {}
        )
        brief = (
            ctx.read_json("understanding/content_brief.json")
            if ctx.artifact_exists("understanding/content_brief.json")
            else {}
        )
        narrative = (
            ctx.read_json("flow_1_master/narrative_plan.json")
            if ctx.artifact_exists("flow_1_master/narrative_plan.json")
            else None
        )
        sap = (
            ctx.read_json("understanding/source_acoustic_profile.json")
            if ctx.artifact_exists("understanding/source_acoustic_profile.json")
            else None
        )
        value_features = (
            ctx.read_json("understanding/value_features.json")
            if ctx.artifact_exists("understanding/value_features.json")
            else None
        )
        interview_spine = (
            ctx.read_json("understanding/interview_spine.json")
            if ctx.artifact_exists("understanding/interview_spine.json")
            else None
        )
        coherence_report = (
            ctx.read_json("understanding/coherence_report.json")
            if ctx.artifact_exists("understanding/coherence_report.json")
            else None
        )
        return {
            "analysis_state": state,
            "investigation_queue": queue,
            "content_brief": brief,
            "narrative_plan": narrative,
            "source_acoustic_profile": sap,
            "value_features": value_features,
            "interview_spine": interview_spine,
            "coherence_report": coherence_report,
            "operator_verified": (state.get("meta") or {}).get("operator_verified", False),
        }

    @app.patch("/api/runs/{run_id}/investigation-queue/{item_id}")
    def patch_investigation_item(
        run_id: str, item_id: str, body: InvestigationPatchBody
    ) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            path = "understanding/investigation_queue.json"
            if not ctx.artifact_exists(path):
                raise HTTPException(404, "Investigation queue not found")
            queue = ctx.read_json(path)
            items = queue.get("items") or queue.get("investigations") or []
            if not isinstance(items, list):
                raise HTTPException(400, "Invalid investigation queue")
            found = False
            for it in items:
                if isinstance(it, dict) and str(it.get("id")) == item_id:
                    it["status"] = body.status
                    found = True
                    break
            if not found:
                raise HTTPException(404, f"Investigation item not found: {item_id}")
            queue["items"] = items
            ctx.write_json(path, queue)
            persist_operator_investigation_queue(ctx, source="investigation_patch")
            ctx.log(
                f"Investigation {item_id} marked {body.status}.",
                level="success",
                stage="analysis_profile",
            )
            refresh_journey_meta(ctx)
            return {"ok": True, "investigation_queue": queue}

    @app.post("/api/runs/{run_id}/milestones/preview-listened")
    def post_preview_listened(run_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            mark_preview_listened(ctx)
            return {"ok": True, "journey": build_journey_snapshot(ctx)}

    @app.post("/api/runs/{run_id}/transcript-review/complete")
    def complete_transcript_review(run_id: str, body: TranscriptReviewCompleteBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            state = transcript_review.get_review_state(ctx)
            if not state.get("ready"):
                raise HTTPException(400, "Review queue not ready.")
            pending = state.get("pending_count", 0)
            if pending and not body.accept_unreviewed:
                raise HTTPException(
                    400,
                    f"{pending} clip(s) not marked reviewed. Save each chunk or pass accept_unreviewed=true.",
                )
            transcript_review.mark_transcript_review_complete(ctx)
            from interview_mux.gui_job_reconcile import reconcile_operator_gate_job
            from interview_mux.write_staging import read_gui_job

            job = read_gui_job(ctx) or {}
            reconciled = reconcile_operator_gate_job(ctx, job)
            if reconciled is not job:
                ctx.write_json("gui_job.json", reconciled, skip_handoff=True)
            refresh_journey_meta(ctx)
            return {"ok": True, "transcript_review_clear": True}

    @app.get("/api/runs/{run_id}/disfluency-review")
    def get_disfluency_review(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        return disfluency.get_review_state(ctx)

    @app.put("/api/runs/{run_id}/disfluency-review/{event_id}")
    def put_disfluency_event(run_id: str, event_id: str, body: DisfluencyEventBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            if not ctx.artifact_exists("transcript/disfluencies.json"):
                raise HTTPException(404, "Disfluency catalog not built — run disfluency_extract first.")
            try:
                return disfluency.update_event_review(
                    ctx,
                    event_id,
                    review_status=body.review_status,
                    text=body.text,
                    include_in_restore=body.include_in_restore,
                )
            except KeyError:
                raise HTTPException(404, f"Unknown event: {event_id}") from None
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc

    @app.post("/api/runs/{run_id}/disfluency-review/complete")
    def complete_disfluency_review(
        run_id: str,
        body: DisfluencyReviewCompleteBody = DisfluencyReviewCompleteBody(),
    ) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            state = disfluency.get_review_state(ctx)
            if not state.get("ready"):
                raise HTTPException(400, "Disfluency catalog not ready.")
            pending = state.get("pending_count", 0)
            if pending and not body.accept_unreviewed:
                raise HTTPException(
                    400,
                    f"{pending} event(s) still pending review. Confirm each or pass accept_unreviewed=true.",
                )
            try:
                disfluency.mark_disfluency_review_complete(ctx, accept_unreviewed=body.accept_unreviewed)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            from interview_mux.gui_job_reconcile import reconcile_operator_gate_job
            from interview_mux.write_staging import read_gui_job

            job = read_gui_job(ctx) or {}
            reconciled = reconcile_operator_gate_job(ctx, job)
            if reconciled is not job:
                ctx.write_json("gui_job.json", reconciled, skip_handoff=True)
            refresh_journey_meta(ctx)
            return {"ok": True, "disfluency_review_clear": True}

    @app.patch("/api/runs/{run_id}/disfluency-restore")
    def patch_disfluency_restore(run_id: str, body: DisfluencyRestoreBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
            block = meta.get("disfluency_restore")
            if not isinstance(block, dict):
                block = {}
            block["enabled"] = body.enabled
            meta["disfluency_restore"] = block
            ctx.write_json("run_meta.json", meta)
            return {"ok": True, "disfluency_restore_enabled": body.enabled}

    @app.post("/api/runs/{run_id}/vo/{line_id}")
    async def upload_vo(run_id: str, line_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.file_store import write_bytes as fs_write_bytes
            from interview_mux.source_topology import pickup_eligible_speaker_id

            ctx = _ctx(run_id)
            eligible = pickup_eligible_speaker_id(ctx)
            if eligible and ctx.artifact_exists("understanding/gap_report.json"):
                report = ctx.read_json("understanding/gap_report.json")
                for ln in report.get("interviewer_lines") or []:
                    if isinstance(ln, dict) and str(ln.get("line_id")) == line_id:
                        expected = str(ln.get("voice_speaker_id") or eligible)
                        if expected != eligible:
                            raise HTTPException(
                                400,
                                f"Line {line_id} is locked to speaker {expected}; pickup must use the confirmed gap pickup speaker.",
                            )
                        break
            pickup = ctx.path("vo_pickup")
            pickup.mkdir(parents=True, exist_ok=True)
            dest = pickup / f"{line_id}.wav"
            content = await file.read()
            fs_write_bytes(dest, content)
            if ctx.artifact_exists("run_meta.json"):
                run_meta = ctx.read_json("run_meta.json")
                if run_meta.get("preview_listened_at") and ctx.artifact_exists("understanding/gap_report.json"):
                    report = ctx.read_json("understanding/gap_report.json")
                    for ln in report.get("interviewer_lines") or []:
                        if (
                            isinstance(ln, dict)
                            and str(ln.get("line_id")) == line_id
                            and ln.get("post_preview")
                        ):
                            from interview_mux.gates_tbiy import mark_post_preview_vo_recorded

                            mark_post_preview_vo_recorded(ctx, line_id)
                            break
            ctx.log(
                f"VO pickup saved: vo_pickup/{line_id}.wav",
                level="success",
                stage="g1_vo_pickup",
                detail={"kind": "gate", "line_id": line_id, "pickup_eligible_speaker_id": eligible},
            )
            return {"ok": True, "path": f"vo_pickup/{dest.name}", "g1_missing": check_g1_vo(ctx)}

    @app.get("/api/runs/{run_id}/source-topology")
    def get_source_topology(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        out: dict[str, Any] = {}
        if ctx.artifact_exists("understanding/source_topology.json"):
            out["topology"] = ctx.read_json("understanding/source_topology.json")
        if ctx.artifact_exists("understanding/flow_adaptation.json"):
            out["adaptation"] = ctx.read_json("understanding/flow_adaptation.json")
        return out

    @app.patch("/api/runs/{run_id}/flow-adaptation")
    def patch_flow_adaptation(run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.source_topology import apply_flow_adaptation_patch

            ctx = _ctx(run_id)
            adapt = apply_flow_adaptation_patch(ctx, body)
            return {"ok": True, "adaptation": adapt}

    @app.post("/api/runs/{run_id}/flow-adaptation/confirm")
    def confirm_flow_adaptation(run_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.source_topology import apply_flow_adaptation_patch

            ctx = _ctx(run_id)
            adapt = apply_flow_adaptation_patch(
                ctx, {"operator_overrides": {"topology_confirmed": True}}
            )
            ctx.log(
                "Topology confirmed by operator",
                level="action",
                stage="source_topology_build",
                detail={"kind": "adaptation", "journey_kind": "adaptation", "action_id": "gui.adaptation.confirm"},
            )
            return {"ok": True, "adaptation": adapt}

    @app.get("/api/runs/{run_id}/pickup-speaker")
    def get_pickup_speaker(run_id: str) -> dict[str, Any]:
        from interview_mux.source_topology import pickup_speaker_payload

        ctx = _ctx(run_id)
        return pickup_speaker_payload(ctx)

    @app.patch("/api/runs/{run_id}/pickup-speaker")
    def patch_pickup_speaker(run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.source_topology import apply_flow_adaptation_patch, pickup_speaker_payload

            ctx = _ctx(run_id)
            speaker_id = body.get("pickup_eligible_speaker_id")
            if not speaker_id:
                raise HTTPException(400, "pickup_eligible_speaker_id is required")
            try:
                apply_flow_adaptation_patch(ctx, {"pickup_eligible_speaker_id": str(speaker_id)})
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return {"ok": True, **pickup_speaker_payload(ctx)}

    @app.post("/api/runs/{run_id}/pickup-speaker/confirm")
    def confirm_pickup_speaker_endpoint(run_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.source_topology import confirm_pickup_speaker, pickup_speaker_payload

            ctx = _ctx(run_id)
            payload = body or {}
            try:
                confirm_pickup_speaker(
                    ctx,
                    speaker_id=str(payload["pickup_eligible_speaker_id"])
                    if payload.get("pickup_eligible_speaker_id")
                    else None,
                )
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return {"ok": True, **pickup_speaker_payload(ctx)}

    @app.get("/api/runs/{run_id}/gap-report/lines")
    def list_gap_report_lines(run_id: str) -> dict[str, Any]:
        from interview_mux.gap_report_api import list_lines

        ctx = _ctx(run_id)
        return {"lines": list_lines(ctx)}

    @app.post("/api/runs/{run_id}/gap-report/lines")
    async def add_gap_report_line(run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.gap_report_api import add_line

            ctx = _ctx(run_id)
            try:
                line = add_line(ctx, body)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            ctx.log(
                f"Gap report line added: {line.get('line_id')}",
                level="action",
                stage="optimal_questions",
                detail={"kind": "gap_report", "action_id": "gui.gap_report.add_line", "line_id": line.get("line_id")},
            )
            return {"ok": True, "line": line}

    @app.patch("/api/runs/{run_id}/gap-report/lines/{line_id}")
    def patch_gap_report_line(run_id: str, line_id: str, body: dict[str, Any]) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.gap_report_api import update_line

            ctx = _ctx(run_id)
            try:
                line = update_line(ctx, line_id, body)
            except KeyError as exc:
                raise HTTPException(404, str(exc)) from exc
            return {"ok": True, "line": line}

    @app.delete("/api/runs/{run_id}/gap-report/lines/{line_id}")
    def delete_gap_report_line(run_id: str, line_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.gap_report_api import delete_line

            ctx = _ctx(run_id)
            try:
                delete_line(ctx, line_id)
            except KeyError as exc:
                raise HTTPException(404, str(exc)) from exc
            ctx.log(
                f"Gap report line removed: {line_id}",
                level="action",
                stage="optimal_questions",
                detail={"kind": "gap_report", "action_id": "gui.gap_report.remove_line", "line_id": line_id},
            )
            return {"ok": True}

    @app.get("/api/runs/{run_id}/vo/{line_id}/boundary-suggest")
    def vo_boundary_suggest(run_id: str, line_id: str) -> dict[str, Any]:
        from interview_mux.vo_boundary_detect import suggest_line_boundary

        ctx = _ctx(run_id)
        return suggest_line_boundary(ctx, line_id)

    @app.post("/api/runs/{run_id}/vo/{line_id}/trim")
    def vo_apply_trim(run_id: str, line_id: str, body: dict[str, Any]) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.vo_pickup_trim import apply_vo_trim

            ctx = _ctx(run_id)
            row = apply_vo_trim(
                ctx,
                line_id,
                trim_in_ms=float(body.get("trim_in_ms", 0)),
                trim_out_ms=float(body["trim_out_ms"]) if body.get("trim_out_ms") is not None else None,
            )
            return {"ok": True, "metadata": row}

    @app.post("/api/runs/{run_id}/reset")
    def reset_run(run_id: str, body: ResetBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            if body.new_input_audio_path:
                if source_audio_locked_for_session() and active_run_id() == run_id:
                    raise HTTPException(
                        409,
                        "Source audio is locked for this session. "
                        "Clear session to start over with different audio.",
                    )
                src = _resolve_repo_path(body.new_input_audio_path)
                if not src.is_file():
                    raise HTTPException(404, f"Audio file not found: {body.new_input_audio_path}")
                _assert_asset_input_path(body.new_input_audio_path)
                ctx.init_run_meta(body.new_input_audio_path)
                for order in (ANALYSIS_ORDER, FLOW1_ORDER, FLOW2_ORDER, FLOW3_ORDER):
                    if order:
                        ctx.clear_from(order[0], order)
            elif body.from_stage:
                runner.invalidate_from(run_id, body.from_stage)
            else:
                raise HTTPException(400, "Provide from_stage or new_input_audio_path.")
            return {"ok": True}

    @app.get("/api/runs/{run_id}/audio/sfx-under-speech")
    def serve_sfx_under_speech(run_id: str, asset_id: str) -> FileResponse:
        ctx = _ctx(run_id)
        aid = asset_id.strip()
        if not aid:
            raise HTTPException(400, "asset_id required")
        from interview_mux.sound_design import render_sfx_under_speech_preview

        try:
            preview = render_sfx_under_speech_preview(ctx, aid)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(404, f"Preview unavailable: {exc}") from exc
        return FileResponse(preview, media_type="audio/wav", filename=preview.name)

    @app.get("/api/runs/{run_id}/audio")
    def serve_audio(
        run_id: str,
        path: str,
        pending: int = 0,
        pending_stage: str | None = None,
    ) -> FileResponse:
        ctx = _ctx(run_id)
        _assert_artifact_path(path)
        if pending and pending_stage:
            from interview_mux.write_staging import staged_path

            full = staged_path(ctx, path, stage_id=pending_stage)
        else:
            full = ctx.final_path(*path.split("/"))
        if not full.is_file():
            full = ctx.path(path)
        if not full.is_file():
            raise HTTPException(404, f"Audio not found: {path}")
        media = mimetypes.guess_type(full.name)[0] or "application/octet-stream"
        return FileResponse(full, media_type=media, filename=full.name)

    @app.get("/api/runs/{run_id}/source-audio")
    def serve_source_audio(run_id: str) -> FileResponse:
        ctx = _ctx(run_id)
        src = ctx.input_audio()
        if not src.is_file():
            raise HTTPException(404, "Source audio not found.")
        media = mimetypes.guess_type(src.name)[0] or "application/octet-stream"
        return FileResponse(src, media_type=media, filename=src.name)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        run_id = _run_id_from_request(request)
        if run_id and exc.status_code >= 500:
            try:
                _append_api_error_log(run_id, request, exc, status_code=exc.status_code)
            except Exception:
                pass
        detail = exc.detail
        if isinstance(detail, dict):
            content = detail
        else:
            content = {"detail": detail}
        return JSONResponse(status_code=exc.status_code, content=content)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        run_id = _run_id_from_request(request)
        if run_id:
            try:
                _append_api_error_log(run_id, request, exc, status_code=500)
            except Exception:
                pass
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    from fastapi import APIRouter

    _session_router = APIRouter()
    register_session_routes(_session_router, ctx_factory=_ctx)
    app.include_router(_session_router)
    _workspace_router = APIRouter()
    register_workspace_routes(
        _workspace_router,
        ctx_factory=_ctx,
        run_guard=runner.operator_guard,
    )
    app.include_router(_workspace_router)

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app


def _done_markers_from(ctx: RunContext, order: list[str], from_stage: str) -> list[str]:
    if from_stage not in order:
        return []
    idx = order.index(from_stage)
    return [s for s in order[idx:] if ctx.is_done(s)]


def _invalidate_sound_design_for_pace_change(ctx: RunContext) -> list[str]:
    """Clear analysis + flow sound-design markers after pace_class change."""
    from_stage = "sound_design_palettes"
    cleared = _done_markers_from(ctx, ANALYSIS_ORDER, from_stage)
    flow = get_selected_flow(ctx)
    if flow == "flow1":
        cleared.extend(_done_markers_from(ctx, FLOW1_ORDER, "sound_design_plan_flow1"))
    elif flow == "flow2":
        cleared.extend(_done_markers_from(ctx, FLOW2_ORDER, "sound_design_plan_flow2"))
    ctx.clear_from(from_stage, ANALYSIS_ORDER)
    if flow == "flow1":
        ctx.clear_from("sound_design_plan_flow1", FLOW1_ORDER)
    elif flow == "flow2":
        ctx.clear_from("sound_design_plan_flow2", FLOW2_ORDER)
    from interview_mux.analysis_memory import invalidate_sonic_context

    invalidate_sonic_context(ctx, reason="pace_class_changed", stage="source_acoustic_profile")
    return cleared


def _count_sufficiency_blocking(ctx: RunContext, stages: list[dict[str, Any]]) -> int:
    """Count committed artifacts with blocking sufficiency findings across done stages."""
    from interview_mux.sufficiency_engine import evaluate, sufficiency_enabled

    if not sufficiency_enabled():
        return 0
    total = 0
    for s in stages:
        if s.get("status") != "done":
            continue
        for row in s.get("outputs_view") or []:
            if row.get("sufficiency_status") != "blocking":
                continue
            rel = str(row.get("path") or "")
            if not rel or not ctx.artifact_exists(rel):
                continue
            try:
                doc = ctx.read_json(rel)
                if isinstance(doc, dict):
                    total += len([f for f in evaluate(str(s.get("id") or ""), doc, ctx) if f.blocking])
            except Exception:
                total += 1
    return total


def _enrich_job_autopilot(
    ctx: RunContext, job: dict[str, Any], stages: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Attach ITR autopilot hints so the GUI can auto fix-all without an extra round trip."""
    if not isinstance(job, dict):
        return job
    suff_count = _count_sufficiency_blocking(ctx, stages or [])
    if suff_count:
        job = {**job, "sufficiency_blocking": suff_count}
    stage = job.get("pending_write_stage") or job.get("stage")
    status = str(job.get("status") or "")
    if not stage or status not in ("needs_clarification", "gate", "awaiting_write_approval"):
        return job
    try:
        from interview_mux.artifact_auto_resolve import get_stage_issues_summary
        from interview_mux.artifact_issue_triage import blocking_issues_remaining, triage_enabled

        if not triage_enabled():
            return job
        stage_key = str(stage)
        summary = get_stage_issues_summary(ctx, stage_key)
        open_blocking = int(summary.get("open_blocking") or blocking_issues_remaining(ctx, stage_key))
        return {
            **job,
            "can_fix_all": bool(summary.get("can_fix_all")),
            "bridge_eligible": bool(summary.get("bridge_eligible")),
            "itr_open_blocking": open_blocking,
            "itr_blocking_count": job.get("itr_blocking_count") or open_blocking,
        }
    except Exception:
        return job


def _sync_tbiy_operator_profile(ctx: RunContext, state: dict[str, Any]) -> None:
    """Mirror operator profile fields into content_brief and flow_adaptation."""
    if not state:
        return
    meta = state.get("meta") if isinstance(state.get("meta"), dict) else {}
    style = meta.get("production_style")
    if style:
        if ctx.artifact_exists("understanding/flow_adaptation.json"):
            from interview_mux.source_topology import apply_flow_adaptation_patch

            apply_flow_adaptation_patch(ctx, {"production_style": str(style)})
        if ctx.artifact_exists("run_meta.json"):
            run_meta = ctx.read_json("run_meta.json")
            if isinstance(run_meta, dict):
                run_meta["production_style"] = str(style)
                ctx.write_json("run_meta.json", run_meta)
    narrative = state.get("narrative") if isinstance(state.get("narrative"), dict) else {}
    moat = narrative.get("strategic_moat_concept")
    if moat and ctx.artifact_exists("understanding/content_brief.json"):
        from interview_mux.artifact_writes import write_validated_artifact

        brief = ctx.read_json("understanding/content_brief.json")
        if isinstance(brief, dict):
            brief["strategic_moat_concept"] = str(moat).strip()
            write_validated_artifact(
                ctx,
                "understanding/content_brief.json",
                brief,
                merge_from_disk=True,
                stage_key="content_context",
            )


def _ctx(run_id: str) -> RunContext:
    if not RunContext.exists(run_id):
        raise HTTPException(404, f"Run not found: {run_id}")
    return RunContext(run_id, create=False)


def _assert_asset_input_path(rel: str) -> None:
    """Source audio for a new execution must live under assets_root (not executions/.gui)."""
    cfg = merged_config()
    assets = (repo_root() / cfg.get("assets_root", "ASSETS")).resolve()
    resolved = _resolve_repo_path(rel)
    try:
        resolved.relative_to(assets)
    except ValueError as exc:
        raise HTTPException(
            400,
            f"input_audio_path must be under {assets.relative_to(repo_root()).as_posix()}/",
        ) from exc
    rel_parts = resolved.relative_to(assets).parts
    if len(rel_parts) != 1:
        raise HTTPException(
            400,
            f"input_audio_path must be a file directly under "
            f"{assets.relative_to(repo_root()).as_posix()}/ (not in subfolders)",
        )
    if any(part in SKIP_ASSET_PARTS for part in rel_parts):
        raise HTTPException(400, "input_audio_path cannot be under executions/ or .gui/")


def _resolve_repo_path(rel: str) -> Path:
    p = Path(rel)
    if not p.is_absolute():
        p = repo_root() / p
    return p.resolve()


def _artifact_path_allowed(normalized: str, allowed: set[str]) -> bool:
    import fnmatch

    if normalized in allowed:
        return True
    for spec in allowed:
        if spec.endswith("/"):
            prefix = spec.rstrip("/") + "/"
            if normalized.startswith(prefix) or normalized == spec.rstrip("/"):
                return True
        elif spec.startswith("glob:"):
            if fnmatch.fnmatch(normalized, spec[5:]):
                return True
    return False


def _assert_artifact_path(path: str) -> None:
    normalized = path.replace("\\", "/").strip()
    if not normalized or ".." in normalized.split("/") or normalized.startswith("/"):
        raise HTTPException(400, "Invalid artifact path.")
    from interview_mux.prompt_validation import ARTIFACT_WRITE_VALIDATORS

    allowed = set(ARTIFACT_WRITE_VALIDATORS.keys())
    for info in STAGE_BY_ID.values():
        allowed.update(info.artifacts)
        allowed.update(info.editable)
        allowed.update(info.audio_outputs)
    allowed.update(
        {
            "run_meta.json",
            "gui_job.json",
            "gui_log.jsonl",
            "analysis_complete.json",
            "understanding/gap_report.json",
            "understanding/interviewer_script.txt",
            "transcript/review_queue.json",
            "transcript/disfluencies.json",
            "segments/nle_edits.json",
            "operator/manifest.json",
        }
    )
    if not _artifact_path_allowed(normalized, allowed):
        raise HTTPException(400, f"Artifact path not in allowlist: {normalized}")


def _is_editable_text_path(path: str) -> bool:
    if path.endswith(".json"):
        return True
    if not (path.endswith(".md") or path.endswith(".txt")):
        return False
    for info in STAGE_BY_ID.values():
        if path in info.editable or path in info.artifacts:
            return True
    return False


def _g0_locked_analysis_stages() -> frozenset[str]:
    from interview_mux.stage_guidance import G0_LOCKED_ANALYSIS_STAGES

    return G0_LOCKED_ANALYSIS_STAGES


def _disfluency_locked_analysis_stages() -> frozenset[str]:
    from interview_mux.stage_guidance import DISFLUENCY_LOCKED_ANALYSIS_STAGES

    return DISFLUENCY_LOCKED_ANALYSIS_STAGES


def _build_stage_list(
    ctx: RunContext,
    flow: str | None,
    g1_missing: list[str],
    transcript_review_pending: bool,
    profile_verified: bool,
    profile_gate_pending: bool,
    disfluency_review_pending: bool | None = None,
) -> list[dict[str, Any]]:
    from interview_mux.write_staging import all_pending_stages

    df_pending = (
        disfluency_review_pending
        if disfluency_review_pending is not None
        else check_disfluency_review_pending(ctx)
    )
    stages = all_stages_for_run(flow)
    pending_write_stages = set(all_pending_stages(ctx))
    from interview_mux.stage_completion import reconcile_stage_done_marker

    for s in stages:
        reconcile_stage_done_marker(ctx, s["id"])
    for s in stages:
        sid = s["id"]
        if sid == "transcript_review":
            if not ctx.artifact_exists("transcript/review_queue.json"):
                s["status"] = "locked"
            elif transcript_review_pending:
                s["status"] = "action_required"
            else:
                s["status"] = "done"
        elif sid == "disfluency_review":
            if not disfluency_enabled():
                s["status"] = "done"
            elif not ctx.artifact_exists("transcript/disfluencies.json"):
                s["status"] = "locked"
            elif df_pending:
                s["status"] = "action_required"
            else:
                s["status"] = "done"
        elif sid == "missing_framing":
            from interview_mux.source_topology import check_pickup_speaker_pending

            if check_pickup_speaker_pending(ctx):
                s["status"] = "action_required"
            elif ctx.is_done(sid):
                s["status"] = "done"
            else:
                s["status"] = "pending"
        elif sid == "analysis_profile":
            ensure_analysis_workspace(ctx)
            from interview_mux.artifact_completeness import analysis_profile_ready_for_review

            if profile_verified:
                s["status"] = "done"
            elif not analysis_profile_ready_for_review(ctx):
                s["status"] = "locked"
            else:
                s["status"] = "action_required"
        elif sid == "g1_vo_pickup":
            if not ctx.artifact_exists("understanding/gap_report.json"):
                s["status"] = "locked"
            elif g1_missing:
                s["status"] = "action_required"
            else:
                s["status"] = "done"
        elif sid == "g1_5_preview_pickup":
            from interview_mux.gates_tbiy import (
                check_g1_5_preview_pickup_pending,
                g1_5_preview_pickup_enabled,
            )
            from interview_mux.production_profile import is_tbiy

            meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
            g1_5_pending = check_g1_5_preview_pickup_pending(ctx)
            if not g1_5_preview_pickup_enabled() or not is_tbiy(ctx):
                s["status"] = "done"
            elif not ctx.artifact_exists("flow_1_master/assembly_preview.wav"):
                s["status"] = "locked"
            elif not meta.get("preview_listened_at"):
                s["status"] = "locked"
            elif g1_5_pending:
                s["status"] = "action_required"
            else:
                s["status"] = "done"
        elif sid == "g2_flow_select":
            if g1_missing:
                s["status"] = "locked"
            elif flow:
                s["status"] = "done"
            elif ctx.artifact_exists("analysis_complete.json"):
                s["status"] = "action_required"
            elif get_flow_intent(ctx):
                s["status"] = "pending"
            else:
                s["status"] = "locked"
        elif sid in STAGE_BY_ID and STAGE_BY_ID[sid].phase in ("flow1", "flow2", "flow3"):
            if not flow:
                s["status"] = "locked"
            elif profile_gate_pending and STAGE_BY_ID[sid].phase == "flow1":
                s["status"] = "locked"
            else:
                s["status"] = "done" if ctx.is_done(sid) else "pending"
        elif transcript_review_pending and sid in _g0_locked_analysis_stages():
            s["status"] = "locked"
        elif df_pending and sid in _disfluency_locked_analysis_stages():
            s["status"] = "locked"
        else:
            s["status"] = "done" if ctx.is_done(sid) else "pending"
        from interview_mux.write_staging import gate_blocked_stage

        gate_stage = gate_blocked_stage(ctx)
        if sid in pending_write_stages:
            if gate_stage == sid:
                s["status"] = "action_required"
            else:
                s["status"] = "awaiting_write_approval"
        info = STAGE_BY_ID.get(sid)
        if info:
            from interview_mux.artifact_completeness import artifact_status
            from interview_mux.artifact_lifecycle import (
                build_outputs_view,
                split_artifact_lists,
                stage_output_mode,
            )
            from interview_mux.custom_run_handoff import handoff_paths_for_stage

            committed, staged, lifecycle = split_artifact_lists(ctx, sid, info.artifacts)
            s["artifacts_committed"] = committed
            s["artifacts_staged"] = staged
            s["artifacts_lifecycle"] = lifecycle
            s["artifacts_present"] = committed
            s["artifacts_status"] = {
                a: artifact_status(a, ctx) for a in info.artifacts if a and not a.endswith("/")
            }
            s["outputs_view"] = build_outputs_view(ctx, sid)
            s["stage_output_mode"] = stage_output_mode(ctx, sid)
            from interview_mux.web.stages import reuse_policy_for

            s["reuse_policy"] = reuse_policy_for(sid)
            if s["stage_output_mode"] == "optional_skipped":
                for a in info.artifacts:
                    if a and not a.endswith("/"):
                        s["artifacts_lifecycle"][a] = "n_a"
                        s["artifacts_status"][a] = "complete"
            s["audio_outputs_present"] = [a for a in info.audio_outputs if ctx.artifact_exists(a)]
            if ctx.is_done(sid):
                handoff = handoff_paths_for_stage(ctx, sid)
                if handoff:
                    s["handoff_paths"] = handoff
            from interview_mux.ui_truth import reconcile_stage_status

            reconcile_stage_status(s)
        s["operator_phase"] = stage_operator_phase(sid)
    filtered = _filter_stages_for_intent(ctx, stages, flow or get_flow_intent(ctx))
    from interview_mux.stage_guidance import attach_guidance_to_stages

    attach_guidance_to_stages(
        ctx,
        filtered,
        flow=flow,
        g1_missing=g1_missing,
        transcript_review_pending=transcript_review_pending,
        profile_gate_pending=profile_gate_pending,
        profile_verified=profile_verified,
    )
    return filtered


def _filter_stages_for_intent(
    ctx: RunContext,
    stages: list[dict[str, Any]],
    flow: str | None,
) -> list[dict[str, Any]]:
    """Collapse irrelevant flow stages when flow_intent is set early."""
    if not flow:
        return stages
    if flow != "flow3":
        return stages
    hide_phases = {"flow1", "flow2"}
    out: list[dict[str, Any]] = []
    for s in stages:
        sid = s.get("id") or ""
        info = STAGE_BY_ID.get(sid)
        if info and info.phase in hide_phases:
            continue
        out.append(s)
    return out


def _record_preclean_offer(
    ctx: RunContext,
    *,
    checkpoint: str,
    action: str,
    scope: str | None,
) -> tuple[bool, dict[str, Any]]:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    now = datetime.now(timezone.utc).isoformat()
    preclean = meta.get("audio_preclean")
    if not isinstance(preclean, dict):
        preclean = {}
    offered_at = preclean.get("offered_at")
    if not isinstance(offered_at, list):
        offered_at = []
    decisions = preclean.get("decisions")
    if not isinstance(decisions, list):
        decisions = []
    changed = False
    if action == "offer":
        if checkpoint not in offered_at:
            offered_at.append(checkpoint)
            changed = True
            if checkpoint == "g1_vo_pickup":
                ctx.log("g1_pickup_preclean_offered", level="info", stage="g1_vo_pickup")
            else:
                ctx.log(
                    f"Quality offer shown: background noise removal ({checkpoint}).",
                    level="info",
                    stage="audio_preclean",
                )
    elif action in {"accept", "dismiss"}:
        requested_scope = scope or preclean.get("scope") or _default_scope_for_checkpoint(checkpoint)
        if checkpoint not in offered_at:
            offered_at.append(checkpoint)
            changed = True
        preclean["enabled"] = action == "accept"
        preclean["scope"] = requested_scope
        preclean["provider"] = "deepfilternet"
        preclean["requested_at"] = now
        decisions.append(
            {
                "checkpoint": checkpoint,
                "action": action,
                "scope": requested_scope,
                "at": now,
            }
        )
        changed = True
        if action == "accept" and checkpoint == "g1_vo_pickup":
            ctx.log("g1_pickup_preclean_accepted", level="success", stage="g1_vo_pickup")
        elif action == "dismiss":
            from interview_mux.stages.audio_preclean import ensure_preclean_skipped

            ensure_preclean_skipped(
                ctx,
                checkpoint=checkpoint,
                scope=str(requested_scope),
                reason="operator_dismissed",
            )
            ctx.log(
                f"Quality offer dismissed: background noise removal ({checkpoint}, scope={requested_scope}).",
                level="info",
                stage="audio_preclean",
            )
        else:
            verb = "accepted" if action == "accept" else "dismissed"
            ctx.log(
                f"Quality offer {verb}: background noise removal ({checkpoint}, scope={requested_scope}).",
                level="success" if action == "accept" else "info",
                stage="audio_preclean",
            )
    else:
        raise HTTPException(400, f"Unsupported offer action: {action}")
    preclean["offered_at"] = offered_at
    preclean["decisions"] = decisions
    meta["audio_preclean"] = preclean
    if changed:
        ctx.write_json("run_meta.json", meta)
    return changed, preclean


def _default_scope_for_checkpoint(checkpoint: str) -> str:
    if checkpoint == "g1_vo_pickup":
        return "vo_pickup"
    return "full_source"


def _read_sfx_listen_results(ctx: RunContext) -> list[dict[str, Any]]:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    results = meta.get("sfx_listen_results")
    if not isinstance(results, list):
        return []
    return [r for r in results if isinstance(r, dict)]


def _read_mmaudio_qa(ctx: RunContext) -> dict[str, Any]:
    path = "sound_design/mmaudio_qa.json"
    if not ctx.artifact_exists(path):
        return {"version": 1, "assets": []}
    doc = ctx.read_json(path)
    return doc if isinstance(doc, dict) else {"version": 1, "assets": []}


def _read_sfx_generation_meta(ctx: RunContext) -> dict[str, Any]:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    gm = meta.get("sfx_generation_meta")
    return gm if isinstance(gm, dict) else {}


def _discover_generated_sfx_assets(ctx: RunContext) -> list[dict[str, str]]:
    """WAV files under sound_design/assets/ for post-listen GUI."""
    assets_dir = ctx.path("sound_design/assets")
    if not assets_dir.is_dir():
        return []
    out: list[dict[str, str]] = []
    for wav in sorted(assets_dir.glob("*.wav")):
        rel = f"sound_design/assets/{wav.name}"
        out.append({"asset_id": wav.stem, "path": rel})
    return out


def _read_prompt_review_meta(ctx: RunContext) -> dict[str, Any]:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    review = meta.get("sfx_prompt_review")
    if not isinstance(review, dict):
        return {"approved": False, "approved_by": None, "approved_at": None}
    return {
        "approved": bool(review.get("approved")),
        "approved_by": review.get("approved_by"),
        "approved_at": review.get("approved_at"),
    }


def _set_prompt_review_meta(
    ctx: RunContext,
    *,
    approved: bool,
    approved_by: str | None,
    approved_at: str | None,
) -> dict[str, Any]:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    review = {
        "approved": approved,
        "approved_by": approved_by,
        "approved_at": approved_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    meta["sfx_prompt_review"] = review
    ctx.write_json("run_meta.json", meta)
    return review


def _append_speech_under_listen_result(
    ctx: RunContext,
    *,
    asset_id: str,
    result: str,
    note: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    results = meta.get("speech_under_listen_results")
    if not isinstance(results, list):
        results = []
    entry: dict[str, Any] = {
        "asset_id": asset_id,
        "result": result,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    if note:
        entry["note"] = note
    results.append(entry)
    meta["speech_under_listen_results"] = results
    ctx.write_json("run_meta.json", meta)
    return entry, results


def _append_sfx_listen_result(
    ctx: RunContext,
    *,
    asset_id: str,
    result: str,
    note: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    results = meta.get("sfx_listen_results")
    if not isinstance(results, list):
        results = []
    entry: dict[str, Any] = {
        "asset_id": asset_id,
        "result": result,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    if note:
        entry["note"] = note
    results.append(entry)
    meta["sfx_listen_results"] = results
    ctx.write_json("run_meta.json", meta)
    return entry, results
