from __future__ import annotations

import json
import re
import threading
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
from interview_mux.gates import (
    check_g1_vo,
    check_profile_gate_pending,
    check_transcript_review_pending,
    is_operator_profile_verified,
)
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
from interview_mux.pipeline import ANALYSIS_ORDER, DELIVERY_ORDER
from interview_mux.run_context import RunContext
from interview_mux.session_log import append_log, read_log
from interview_mux.journey_state import (
    compute_milestones,
    compute_operator_phase,
    stage_operator_phase,
)
from interview_mux.operator_quality import preclean_acknowledged
from interview_mux.web.runner import RunBusyError, runner
from interview_mux.web.refinement_routes import register_refinement_routes
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
    persist_operator_investigation_queue,
    persist_operator_preclean,
)
from interview_mux.sonic_context import compact_for_volley as compact_sonic_context, load_sonic_context

STATIC_DIR = Path(__file__).resolve().parent / "static"

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".webm", ".mp4"}


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
# High-frequency poll routes — transient 500s are retried client-side; do not spam gui_log/terminal.
_API_POLL_PATH_SUFFIXES = ("/job", "/log")
_API_ERROR_DEDUPE: dict[str, float] = {}
_API_ERROR_DEDUPE_TTL_SEC = 120.0


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
    path = request.url.path
    is_poll = any(path.endswith(suffix) for suffix in _API_POLL_PATH_SUFFIXES)
    if status_code >= 500 and is_poll:
        # Job/log polling retries in the GUI and driver — not operator-actionable noise.
        return
    import time

    dedupe_key = f"{path}:{status_code}:{type(exc).__name__}:{str(exc)[:200]}"
    now = time.monotonic()
    last = _API_ERROR_DEDUPE.get(dedupe_key)
    if last is not None and now - last < _API_ERROR_DEDUPE_TTL_SEC:
        return
    _API_ERROR_DEDUPE[dedupe_key] = now

    ctx = RunContext(run_id, create=False)
    detail: dict[str, Any] = {
        "path": path,
        "method": request.method,
        "status_code": status_code,
        "error_class": type(exc).__name__,
        "journey_kind": "api",
    }
    if status_code >= 500:
        tb = traceback.format_exc()
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
    run_mode: str = "manual"  # manual | full-auto | partially-accelerated
    full_auto: bool | None = None  # optional explicit flag (overrides run_mode when true)
    homunculus_version: str | None = None  # omitted → highest registered (currently 0.1.0)
    podcast_id: str | None = None  # omitted → catalog default (zero_shot_podcast_demo)


class InvestigationPatchBody(BaseModel):
    status: str = "resolved"


class ExecuteBody(BaseModel):
    mode: str = Field(
        description=(
            "stage | analysis | analysis_until_g0 | delivery | delivery_until_preview | "
            "delivery_polish | nle_apply"
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


class GPublishReviewBody(BaseModel):
    title: str | None = None
    description: str | None = None
    cover_path: str | None = None


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
    at_ms: int | None = None
    cut_ms: list[int] | None = None


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


class TranscriptWordPatch(BaseModel):
    index: int
    text: str


class TranscriptWordsPatchBody(BaseModel):
    updates: list[TranscriptWordPatch] = Field(default_factory=list)


class TranscriptTextBody(BaseModel):
    text: str = Field(min_length=1)


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
    async def static_cache_control(request: Request, call_next):
        """Prevent stale index.html from referencing removed Vite chunk hashes after rebuild."""
        response = await call_next(request)
        path = request.url.path
        if path in ("/", "/index.html") or path.endswith(".html"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        elif path.startswith("/assets/") and (path.endswith(".js") or path.endswith(".css")):
            if re.search(r"[-.][A-Za-z0-9_-]{6,}\.(js|css)$", path):
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                response.headers["Cache-Control"] = "no-cache"
        return response

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

    @app.get("/api/homunculus/versions")
    def homunculus_versions() -> dict[str, Any]:
        from interview_mux.homunculus.version import brains_public, default_version

        return {"default": default_version(), "brains": brains_public()}

    @app.get("/api/podcasts")
    def list_podcasts() -> dict[str, Any]:
        from interview_mux.podcast_rss.settings import list_shows_public

        return list_shows_public()

    @app.get("/api/podcasts/{podcast_id}/artwork")
    def podcast_artwork(podcast_id: str) -> FileResponse:
        from interview_mux.podcast_rss.settings import normalize_podcast_id, show_artwork_file

        try:
            pid = normalize_podcast_id(podcast_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        path = show_artwork_file(pid)
        if not path.is_file():
            raise HTTPException(404, f"No artwork for podcast_id={pid!r}")
        media, _ = mimetypes.guess_type(str(path))
        return FileResponse(path, media_type=media or "image/png")

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
            "api_consent_persist": (cfg.get("web") or {}).get("api_consent_persist", True),
            "journey_ui": (cfg.get("journey_ui") or {"enabled": True}),
            "v2": {
                **(cfg.get("v2") or {"enabled": True}),
                "g1_optional": __import__(
                    "interview_mux.v2.config", fromlist=["v2_g1_optional"]
                ).v2_g1_optional(),
            },
            "v2_phases": __import__(
                "interview_mux.v2.phases", fromlist=["PHASES"]
            ).PHASES,
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
    def list_assets() -> dict[str, Any]:
        """List operator-selectable audio from the canonical ASSETS/input drop zone."""
        cfg = merged_config()
        assets = repo_root() / cfg.get("assets_root", "ASSETS")
        input_dir = assets / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        files: list[dict[str, Any]] = []
        for p in sorted(input_dir.iterdir()):
            if not p.is_file():
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
        return {"assets_root": input_dir.relative_to(repo_root()).as_posix(), "files": files}

    @app.get("/api/runs/session-scope")
    def list_runs_session_scope() -> dict[str, Any]:
        from interview_mux.web.runs_session_scope import build_session_scope_payload

        def _enrich(rid: str) -> dict[str, Any]:
            from interview_mux.web.runs_session_scope import enrich_run_summary

            return enrich_run_summary(
                rid,
                summarize_fn=RunContext.summarize_run,
                build_stage_list_fn=_build_stage_list,
                build_journey_fn=build_journey_snapshot,
                get_job_fn=runner.get_job,
                read_log_fn=read_log,
                check_g1_vo=check_g1_vo,
                check_transcript_review_pending=check_transcript_review_pending,
                is_operator_profile_verified=is_operator_profile_verified,
                check_profile_gate_pending=check_profile_gate_pending,
            )

        return build_session_scope_payload(
            summarize_fn=RunContext.summarize_run,
            enrich_fn=_enrich,
        )

    @app.get("/api/runs")
    def list_runs(
        enrich: bool = False,
        enrich_limit: int = 50,
        all_runs: bool = False,
    ) -> dict[str, Any]:
        from interview_mux.web.runs_session_scope import (
            enrich_run_summary,
            session_scoped_run_ids,
        )

        if all_runs:
            run_ids = RunContext.list_runs()
        else:
            run_ids = session_scoped_run_ids()

        runs: list[dict[str, Any]] = []
        for rid in run_ids:
            try:
                runs.append(RunContext.summarize_run(rid))
            except Exception:
                runs.append({"run_id": rid, "progress": {"done": 0, "total": 0}})
        runs.sort(key=lambda r: r.get("execution_number") or 0, reverse=True)
        if enrich:
            enriched: list[dict[str, Any]] = []
            for r in runs[: max(enrich_limit, 0)]:
                enriched.append(
                    enrich_run_summary(
                        r["run_id"],
                        summarize_fn=RunContext.summarize_run,
                        build_stage_list_fn=_build_stage_list,
                        build_journey_fn=build_journey_snapshot,
                        get_job_fn=runner.get_job,
                        read_log_fn=read_log,
                        check_g1_vo=check_g1_vo,
                        check_transcript_review_pending=check_transcript_review_pending,
                        is_operator_profile_verified=is_operator_profile_verified,
                        check_profile_gate_pending=check_profile_gate_pending,
                    )
                )
            runs = enriched
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
        from interview_mux.full_auto_launch import normalize_run_mode
        from interview_mux.homunculus.version import normalize_version, stamp_build_identity, stamp_run_meta
        from interview_mux.podcast_rss.settings import stamp_podcast_meta
        from interview_mux.source_audio_hash import pipeline_wav_path, source_audio_hash_pair

        try:
            homunculus_version = normalize_version(body.homunculus_version)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        try:
            from interview_mux.podcast_rss.settings import normalize_podcast_id

            podcast_id = normalize_podcast_id(body.podcast_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        run_mode = normalize_run_mode(body.run_mode)
        if body.full_auto is True:
            run_mode = "full-auto"
        wav_src = pipeline_wav_path(src)
        full_hash, short_hash = source_audio_hash_pair(wav_src)
        run_id = body.run_id or RunContext.allocate_run_id(source_hash=short_hash)
        ctx = RunContext(run_id, create=True)
        ctx.init_run_meta(
            body.input_audio_path,
            source_audio_hash=full_hash,
            source_audio_hash_short=short_hash,
        )
        ensure_analysis_workspace(ctx)
        stamp_run_meta(ctx, homunculus_version)
        stamp_build_identity(ctx)
        stamp_podcast_meta(ctx, podcast_id)

        def _stamp_run_mode(meta: dict[str, Any]) -> None:
            meta["run_mode"] = run_mode
            meta["full_auto"] = run_mode == "full-auto"
            meta["partial_auto"] = run_mode == "partially-accelerated"
            if run_mode != "partially-accelerated":
                meta.pop("partial_auto", None)
                meta.pop("partial_auto_driver_active", None)
                meta.pop("partial_auto_complete", None)

        ctx.mutate_run_meta(_stamp_run_mode)
        refresh_journey_meta(ctx)
        from interview_mux.session_lineage import record_immediate_previous_on_create

        record_immediate_previous_on_create(ctx)
        meta = ctx.read_json("run_meta.json")
        set_active_execution(
            ctx.run_id,
            input_audio_path=meta.get("input_audio_path"),
            source_locked=True,
        )
        payload: dict[str, Any] = {
            "run_id": ctx.run_id,
            "run_dir": str(ctx.run_dir.relative_to(ctx.root)),
            "execution_number": meta.get("execution_number"),
            "input_audio_path": meta.get("input_audio_path"),
            "source_audio_hash": meta.get("source_audio_hash"),
            "source_audio_hash_short": meta.get("source_audio_hash_short"),
            "run_mode": run_mode,
            "full_auto": run_mode == "full-auto",
            "partial_auto": run_mode == "partially-accelerated",
            "homunculus_version": homunculus_version,
            "podcast_id": podcast_id,
        }
        if run_mode == "full-auto":
            from interview_mux.full_auto_launch import (
                automation_driver_alive,
                launch_full_auto_for_run,
            )

            try:
                if automation_driver_alive():
                    launch_info = {"driver_already_running": True}
                else:
                    launch_info = launch_full_auto_for_run(
                        run_id=ctx.run_id,
                        input_audio=str(meta.get("input_audio_path") or body.input_audio_path),
                        keep_gui_server=True,
                    )
                payload["full_auto_launch"] = launch_info
                append_log(
                    ctx.run_dir,
                    "Full-auto worker launched (gates auto-accepted; package + S3 on ship).",
                    level="info",
                    stage="setup",
                    detail={"journey_kind": "full_auto", **launch_info},
                )
            except Exception as exc:
                append_log(
                    ctx.run_dir,
                    f"Full-auto launch failed: {exc}",
                    level="error",
                    stage="setup",
                )
                raise HTTPException(
                    500,
                    f"Execution created but Full-auto launch failed: {exc}",
                ) from exc
        elif run_mode == "partially-accelerated":
            from interview_mux.full_auto_launch import (
                automation_driver_alive,
                launch_partial_auto_for_run,
            )

            try:
                if automation_driver_alive():
                    launch_info = {"driver_already_running": True}
                else:
                    launch_info = launch_partial_auto_for_run(
                        run_id=ctx.run_id,
                        input_audio=str(meta.get("input_audio_path") or body.input_audio_path),
                        keep_gui_server=True,
                    )
                payload["partial_auto_launch"] = launch_info

                def _mark_driver(meta: dict[str, Any]) -> None:
                    meta["partial_auto_driver_active"] = True
                    meta.pop("partial_auto_complete", None)

                ctx.mutate_run_meta(_mark_driver)
                append_log(
                    ctx.run_dir,
                    "Partially-accelerated worker launched (G0 + S3 require operator).",
                    level="info",
                    stage="setup",
                    detail={"journey_kind": "partial_auto", **launch_info},
                )
            except Exception as exc:
                append_log(
                    ctx.run_dir,
                    f"Partially-accelerated launch failed: {exc}",
                    level="error",
                    stage="setup",
                )
                raise HTTPException(
                    500,
                    f"Execution created but partially-accelerated launch failed: {exc}",
                ) from exc
        return payload

    @app.get("/api/runs/{run_id}/summary")
    def get_run_summary(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        summary = RunContext.summarize_run(run_id)
        job = _sanitize_job(runner.get_job(run_id))
        stages = _build_stage_list(
            ctx,
            check_g1_vo(ctx),
            check_transcript_review_pending(ctx),
            is_operator_profile_verified(ctx),
            check_profile_gate_pending(ctx),
            job=job,
        )
        done = sum(1 for s in stages if s["status"] == "done")
        log_entries = read_log(ctx.run_dir, tail=1)
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        return {
            **summary,
            "progress": {"done": done, "total": len(stages)},
            "last_log": log_entries[-1] if log_entries else None,
        }

    @app.get("/api/runs/{run_id}/homunculus")
    def get_run_homunculus(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        from interview_mux.homunculus.runtime import snapshot_status

        return snapshot_status(ctx)

    @app.post("/api/runs/{run_id}/homunculus/skip-stage")
    def homunculus_skip_stage(run_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """10C GUI: skip with hollow_done structured payload — no auto-rerun."""
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            payload = body or {}
            stage = str(payload.get("stage") or "").strip()
            if not stage:
                raise HTTPException(400, "stage required")
            from interview_mux.homunculus.agenda import HollowSkipBlockedError, skip_stage

            try:
                doc = skip_stage(
                    ctx,
                    stage,
                    reason=str(payload.get("reason") or "operator"),
                    compensating_fact=(
                        str(payload["compensating_fact"])
                        if payload.get("compensating_fact")
                        else None
                    ),
                )
                return {"ok": True, "skipped": True, "agenda": doc}
            except HollowSkipBlockedError as exc:
                return exc.payload
            except RuntimeError as exc:
                raise HTTPException(400, str(exc)) from exc

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, include_log_tail: bool = False) -> dict[str, Any]:
        from interview_mux.web.gap_fields_for_run import gap_fields_for_get_run
        from interview_mux.web.run_snapshot_cache import get_or_build_run_snapshot

        ctx = _ctx(run_id)
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        g1_missing = check_g1_vo(ctx)
        from interview_mux.gates_tbiy import check_g1_5_preview_pickup_pending

        g1_5_pending = check_g1_5_preview_pickup_pending(ctx)
        from interview_mux.source_topology import check_pickup_speaker_pending

        pickup_speaker_pending = check_pickup_speaker_pending(ctx)
        tr_pending = check_transcript_review_pending(ctx)
        profile_verified = is_operator_profile_verified(ctx)
        profile_gate_pending = check_profile_gate_pending(ctx)
        from interview_mux.artifact_completeness import (
            analysis_profile_ready_for_review,
            story_board_ready_for_gui,
            timeline_ready_for_gui,
        )

        profile_ready = analysis_profile_ready_for_review(ctx)
        story_board_ready = story_board_ready_for_gui(ctx)
        timeline_ready = timeline_ready_for_gui(ctx)
        from interview_mux.gap_fill_eligibility import gap_fill_mode

        gap_mode = gap_fill_mode(ctx)
        gap_skip_reason = meta.get("gap_fill_skip_reason")
        if not gap_skip_reason and ctx.artifact_exists("understanding/gap_fill_skip.json"):
            skip_doc = ctx.read_json("understanding/gap_fill_skip.json")
            if isinstance(skip_doc, dict):
                gap_skip_reason = skip_doc.get("reason")
        job = _sanitize_job(runner.get_job(run_id))
        from interview_mux.operator_gate_view import build_operator_gates, g1_journey_clear
        from interview_mux.v2.config import v2_g1_optional

        operator_gates = build_operator_gates(
            ctx,
            job,
            meta if isinstance(meta, dict) else {},
            g1_missing=g1_missing,
        )

        def _build_stages() -> list[dict[str, Any]]:
            return _build_stage_list(
                ctx,
                g1_missing,
                tr_pending,
                profile_verified,
                profile_gate_pending,
                job=job,
            )

        def _build_journey(stages: list[dict[str, Any]]) -> dict[str, Any]:
            return build_journey_snapshot(ctx, job=job, stages=stages)

        stages, journey = get_or_build_run_snapshot(
            ctx,
            job=job,
            build_stages=_build_stages,
            build_journey=_build_journey,
        )
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
        llm_verification_alerts: list[dict[str, Any]] = []
        try:
            from interview_mux.llm_calls_gui import list_verification_alerts

            llm_verification_alerts = list_verification_alerts(ctx)
        except Exception:
            pass

        segment_lineage_warnings: list[str] = []
        try:
            from interview_mux.segment_lineage_audit import lineage_warnings_for_gui

            segment_lineage_warnings = lineage_warnings_for_gui(ctx)
        except Exception:
            pass

        gap_gates = gap_fields_for_get_run(
            ctx,
            job=job,
            operator_phase=str(journey.get("phase") or ""),
        )

        payload: dict[str, Any] = {
            "run_id": run_id,
            "meta": meta,
            "working_dir": str(ctx.run_dir),
            "snapshot_version": meta.get("snapshot_version", 0),
            "execution_number": meta.get("execution_number"),
            "immediate_previous_run_id": meta.get("immediate_previous_run_id"),
            "homunculus_plan": (
                ctx.read_json("mastering/homunculus/plan.json")
                if ctx.artifact_exists("mastering/homunculus/plan.json")
                else None
            ),
            "sfx_generated_assets": _discover_generated_sfx_assets(ctx),
            "flow_adaptation": (
                ctx.read_json("understanding/flow_adaptation.json")
                if ctx.artifact_exists("understanding/flow_adaptation.json")
                else None
            ),
            "delivery_brief": (
                ctx.read_json("understanding/delivery_brief.json")
                if ctx.artifact_exists("understanding/delivery_brief.json")
                else None
            ),
            "source_topology": (
                ctx.read_json("understanding/source_topology.json")
                if ctx.artifact_exists("understanding/source_topology.json")
                else None
            ),
            "transcript_review_pending": tr_pending,
            "transcript_review_clear": not tr_pending,
            "profile_verified": profile_verified,
            "profile_gate_pending": profile_gate_pending,
            "profile_ready_for_review": profile_ready,
            "story_board_ready": story_board_ready,
            "timeline_ready": timeline_ready,
            "g1_missing": g1_missing,
            "g1_clear": g1_journey_clear(ctx, meta, g1_missing=g1_missing),
            "g1_optional": v2_g1_optional(),
            "operator_gates": operator_gates,
            "g1_5_preview_pickup_pending": g1_5_pending,
            "g1_5_preview_pickup_clear": not g1_5_pending,
            "pickup_speaker_pending": pickup_speaker_pending,
            "gap_fill_mode": gap_mode,
            "gap_fill_skip_reason": gap_skip_reason,
            **gap_gates,
            "refinement_agenda": (
                ctx.read_json("understanding/refinement_agenda.json")
                if ctx.artifact_exists("understanding/refinement_agenda.json")
                else None
            ),
            "listener_outcome_trajectory": (
                ctx.read_json("understanding/listener_outcome_trajectory.json")
                if ctx.artifact_exists("understanding/listener_outcome_trajectory.json")
                else None
            ),
            "analysis_complete": ctx.artifact_exists("analysis_complete.json"),
            "job": job,
            "journey": journey,
            "blocking": journey.get("blocking"),
            "stages": stages,
            "llm_verification_alerts": llm_verification_alerts,
            "segment_lineage_warnings": segment_lineage_warnings,
            "resilience": _resilience_payload(ctx),
            "thrash": None,
            "wasted_work": None,
            "delivery_pin": None,
        }
        try:
            from interview_mux.thrash_hardening import (
                delivery_pin_summary,
                thrash_summary,
                wasted_work_summary,
            )

            payload["thrash"] = thrash_summary(ctx)
            payload["wasted_work"] = wasted_work_summary(ctx)
            payload["delivery_pin"] = delivery_pin_summary(ctx)
        except Exception:
            pass
        if include_log_tail:
            payload["log_tail"] = read_log(ctx.run_dir, tail=100)
        return payload

    @app.get("/api/runs/{run_id}/delivery-readiness")
    def get_delivery_readiness(
        run_id: str,
        target_stage: str = "topic_coverage_audit",
        scope: str = "delivery",
    ) -> dict[str, Any]:
        ctx = _ctx(run_id)
        from interview_mux.progression_readiness import (
            build_delivery_readiness_report,
            build_pre_audio_readiness_report,
        )

        if scope == "pre_audio":
            return build_pre_audio_readiness_report(ctx)
        return build_delivery_readiness_report(
            ctx,
            target_stage=target_stage or None,
            include_flow1_spine=target_stage not in (None, "", "topic_coverage_audit"),
        )

    @app.get("/api/runs/{run_id}/resilience")
    def get_resilience(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        payload = _resilience_payload(ctx)
        try:
            from interview_mux.delivery_recovery import suggest_delivery_resume

            payload["suggest_delivery_resume"] = suggest_delivery_resume(ctx)
        except Exception:
            pass
        return payload

    @app.get("/api/runs/{run_id}/escalations")
    def list_escalations(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        from interview_mux.stage_resilience import list_open_escalations

        return {"escalations": list_open_escalations(ctx), "quality_first": True}

    @app.post("/api/runs/{run_id}/escalations/{stage_id}/resolve")
    def resolve_escalation_endpoint(
        run_id: str,
        stage_id: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            from interview_mux.stage_resilience import resolve_escalation

            payload = body or {}
            chosen = str(payload.get("chosen_option") or "").strip()
            if not chosen:
                raise HTTPException(400, "chosen_option required")
            unattended = bool(payload.get("unattended"))
            try:
                doc = resolve_escalation(
                    ctx, stage_id, chosen_option=chosen, unattended=unattended
                )
            except FileNotFoundError as exc:
                raise HTTPException(404, str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            refresh_journey_meta(ctx)
            return {"ok": True, "escalation": doc}

    @app.post("/api/runs/{run_id}/delivery/recover")
    def delivery_recover(run_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            from interview_mux.delivery_recovery import (
                ensure_g1_pickups,
                restore_master_bundle,
                suggest_delivery_resume,
            )

            payload = body or {}
            actions = payload.get("actions") or ["restore", "g1", "resume"]
            consumer_stage = str(payload.get("consumer_stage") or payload.get("stage") or "")
            message = str(payload.get("message") or "")
            out: dict[str, Any] = {"ok": True}
            if payload.get("preflight") or consumer_stage or message:
                from interview_mux.remediation_framework import run_delivery_recover_preflight

                outcome = run_delivery_recover_preflight(
                    ctx,
                    consumer_stage=consumer_stage,
                    message=message,
                )
                out["preflight"] = {
                    "recovered": outcome.recovered,
                    "playbook_id": outcome.playbook_id,
                    "resume_stage": outcome.resume_stage,
                    "detail": outcome.detail,
                }
            if "restore" in actions:
                out["restored"] = restore_master_bundle(ctx)
            if "g1" in actions:
                out["g1"] = ensure_g1_pickups(ctx, promote=True, max_rounds=1)
            if "resume" in actions:
                out["suggest_delivery_resume"] = suggest_delivery_resume(ctx)
            refresh_journey_meta(ctx)
            return out

    @app.post("/api/runs/{run_id}/delivery/unlock")
    def delivery_epoch_unlock(run_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """G-DeliveryUnlock — allow structural invalidation after Phase A seal."""
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            from interview_mux.delivery_guardrails import unlock_delivery_epoch

            payload = body or {}
            reason = str(payload.get("reason") or "operator_unlock")
            epoch = unlock_delivery_epoch(ctx, reason)
            refresh_journey_meta(ctx)
            return {"ok": True, "delivery_epoch": epoch}

    @app.post("/api/runs/{run_id}/delivery/unstick")
    def delivery_unstick(run_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Operator unstick playbook: promote orphans, seal Phase A, clear thrash, pin resume."""
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            from interview_mux.delivery_unstick import run_delivery_unstick

            payload = body or {}
            execute_resume = bool(payload.get("execute_resume") or payload.get("execute"))
            out = run_delivery_unstick(
                ctx,
                clear_needs_operator=payload.get("clear_needs_operator", True) is not False,
                execute_resume=execute_resume,
            )
            refresh_journey_meta(ctx)
            if execute_resume and out.get("execute"):
                exe = out["execute"]
                started = runner.start(
                    run_id,
                    mode=str(exe.get("mode") or "delivery"),
                    from_stage=str(exe.get("from_stage") or ""),
                    flow=str(exe.get("mode") or "delivery"),
                )
                out["job"] = started
            return out

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
            exclude_reasons: dict[str, str] = {}
            recovery_hints: dict[str, str] = {}
            if ctx.artifact_exists("master/selection.json"):
                sel = ctx.read_json("master/selection.json")
                if isinstance(sel, dict):
                    for ex in sel.get("excluded_segment_ids") or []:
                        if isinstance(ex, dict):
                            sid = str(ex.get("segment_id") or "")
                            if sid:
                                exclude_reasons[sid] = str(
                                    ex.get("reason") or ex.get("why_dropped") or "excluded"
                                )
                        else:
                            sid = str(ex or "")
                            if sid:
                                exclude_reasons[sid] = "excluded"
            try:
                from interview_mux.omit_ledger import OMIT_LEDGER_REL, active_entries

                ledger = (
                    ctx.read_json(OMIT_LEDGER_REL)
                    if ctx.artifact_exists(OMIT_LEDGER_REL)
                    else None
                )
                for entry in active_entries(ledger, kind="layup_skip"):
                    tid = str(entry.get("target_segment_id") or "")
                    path = str(entry.get("compensating_path") or "")
                    if tid and path:
                        recovery_hints[tid] = path
                for entry in active_entries(ledger, kind="segment_exclude"):
                    sid = str(entry.get("subject_id") or "")
                    path = str(entry.get("compensating_path") or "")
                    if sid and path:
                        recovery_hints[sid] = path
            except Exception:
                pass
            for seg in segments:
                sid = str(seg.get("segment_id") or "")
                if sid in exclude_reasons:
                    seg["_exclude_reason"] = exclude_reasons[sid]
                    seg["_excluded"] = True
                if sid in recovery_hints:
                    seg["_omit_recovery"] = recovery_hints[sid]
                if sid and sid in manifest_by_id:
                    m = manifest_by_id[sid]
                    if m.get("start_ms") is not None:
                        seg["_manifest_start_ms"] = int(m["start_ms"])
                    if m.get("end_ms") is not None:
                        seg["_manifest_end_ms"] = int(m["end_ms"])
            # Attach per-edge boundary confidence when scored.
            if ctx.artifact_exists("segments/boundaries.json"):
                try:
                    bdoc = ctx.read_json("segments/boundaries.json")
                    by_id = {
                        str(r.get("segment_id")): r
                        for r in (bdoc.get("boundaries") or [])
                        if isinstance(r, dict) and r.get("segment_id")
                    }
                    for seg in segments:
                        sid = str(seg.get("segment_id") or "")
                        brow = by_id.get(sid)
                        if not brow:
                            continue
                        if brow.get("confidence") is not None:
                            seg["boundary_confidence"] = float(brow["confidence"])
                        if brow.get("edge_grade"):
                            seg["edge_grade"] = str(brow["edge_grade"])
                        if isinstance(brow.get("start_edge"), dict):
                            seg["start_edge"] = brow["start_edge"]
                        if isinstance(brow.get("end_edge"), dict):
                            seg["end_edge"] = brow["end_edge"]
                except Exception:
                    pass
            if segments:
                duration_ms = max(s.get("end_ms", 0) for s in segments)
        boundary_review: dict[str, Any] | None = None
        if ctx.artifact_exists("segments/boundary_review_queue.json"):
            try:
                q = ctx.read_json("segments/boundary_review_queue.json")
                if isinstance(q, dict):
                    boundary_review = {
                        "item_count": int(q.get("item_count") or len(q.get("items") or [])),
                        "low_confidence_threshold": q.get("low_confidence_threshold"),
                        "items": (q.get("items") or [])[:60],
                    }
            except Exception:
                boundary_review = None
        vo_lines: list[dict[str, Any]] = []
        if ctx.artifact_exists("understanding/gap_report.json"):
            from interview_mux.gates_tbiy import post_preview_vo_satisfied

            report = ctx.read_json("understanding/gap_report.json")
            pickup = ctx.path("vo_pickup")
            from interview_mux.stages.assembly import resolve_vo_pickup_path

            for line in report.get("interviewer_lines") or []:
                lid = line.get("line_id", "")
                resolved = resolve_vo_pickup_path(ctx, line)
                recorded = None
                if resolved and resolved.is_file():
                    try:
                        recorded = resolved.relative_to(pickup).as_posix()
                    except ValueError:
                        recorded = resolved.name
                else:
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
            "boundary_review_queue": boundary_review,
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
            # Mirror underscore/pace into soundscape policy when present
            try:
                from interview_mux.soundscape_policy import POLICY_PATH, save_operator_overrides as save_sp

                if ctx.artifact_exists(POLICY_PATH):
                    save_sp(ctx, body.overrides if isinstance(body.overrides, dict) else {})
                    ctx.log(
                        "Soundscape policy rebuilt from acoustic overrides.",
                        level="info",
                        stage="soundscape_policy_build",
                    )
            except Exception as exc:
                ctx.log(
                    f"soundscape policy sync skipped: {exc}",
                    level="warning",
                    stage="source_acoustic_profile",
                )
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
            from interview_mux.nle_state import split_segment_at_cuts

            cuts = list(body.cut_ms or [])
            if body.at_ms is not None:
                cuts.append(int(body.at_ms))
            if not cuts:
                raise HTTPException(400, {"errors": ["at_ms or cut_ms required"]})
            if len(cuts) == 1:
                nle = split_segment_at(ctx, body.segment_id, cuts[0])
            else:
                nle = split_segment_at_cuts(ctx, body.segment_id, cuts)
            ctx.log(
                f"Split segment {body.segment_id} at {cuts}ms.",
                level="info",
                stage="nle",
            )
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
            stage_key = body.invalidate_from or "artifact_editor"
            data = body.data
            if body.path == "understanding/speakers.json" and isinstance(data, dict):
                from interview_mux.conversation_context import (
                    enrich_speakers_artifact,
                    sync_conversation_to_analysis_state,
                )

                data = enrich_speakers_artifact(ctx, data)
                sync_conversation_to_analysis_state(ctx, data)
            ctx.write_json(body.path, data, stage_key=stage_key)
            stage = stage_key
            mirror_artifact_to_operator(ctx, body.path, data, source="artifact_json_editor")
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

    @app.get("/api/runs/{run_id}/segmentation-review")
    def get_segmentation_review(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        from interview_mux.segmentation_input_resolver import segmentation_review_report

        return segmentation_review_report(ctx)

    @app.get("/api/runs/{run_id}/timeline-optimizer")
    def get_timeline_optimizer(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        from interview_mux.timeline_optimizer.daemon import is_optimizer_running
        from interview_mux.timeline_optimizer.state import optimizer_status_payload

        payload = optimizer_status_payload(ctx)
        payload["running"] = is_optimizer_running(run_id) or payload.get("status") == "running"
        return payload

    @app.post("/api/runs/{run_id}/timeline-optimizer/start")
    def timeline_optimizer_start(run_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            from interview_mux.timeline_optimizer.daemon import start_optimizer_daemon

            return start_optimizer_daemon(ctx, force=True)

    @app.post("/api/runs/{run_id}/timeline-optimizer/stop")
    def timeline_optimizer_stop(run_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            from interview_mux.timeline_optimizer.daemon import stop_optimizer_daemon

            return stop_optimizer_daemon(ctx)

    @app.post("/api/runs/{run_id}/timeline-optimizer/take-best")
    def timeline_optimizer_take_best(
        run_id: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            body = body or {}
            remaster = bool(body.get("remaster", True))
            from interview_mux.gates import clear_timeline_optimizer_gate
            from interview_mux.timeline_optimizer.apply import take_best_candidate

            result = take_best_candidate(
                ctx,
                remaster=remaster,
                sync_remaster=remaster,
                runner=runner if not remaster else None,
            )
            clear_timeline_optimizer_gate(ctx, skipped=False)
            return result

    @app.post("/api/runs/{run_id}/timeline-optimizer/skip")
    def timeline_optimizer_skip(run_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            from interview_mux.gates import clear_timeline_optimizer_gate
            from interview_mux.timeline_optimizer.daemon import stop_optimizer_daemon

            stop_optimizer_daemon(ctx)
            clear_timeline_optimizer_gate(ctx, skipped=True)
            return {"ok": True, "skipped": True}

    @app.get("/api/runs/{run_id}/g-listen")
    def get_g_listen(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        from interview_mux.gates import check_g_listen_pending

        critic = (
            ctx.read_json("master/listen_critic.json")
            if ctx.artifact_exists("master/listen_critic.json")
            else {}
        )
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        return {
            "pending": check_g_listen_pending(ctx),
            "quality_score": (critic or {}).get("quality_score")
            if isinstance(critic, dict)
            else meta.get("g_listen_quality_score"),
            "verdict": (critic or {}).get("verdict") if isinstance(critic, dict) else None,
            "issues": ((critic or {}).get("issues") or [])[:8] if isinstance(critic, dict) else [],
            "skipped": bool(isinstance(meta, dict) and meta.get("g_listen_skipped")),
            "cleared": bool(isinstance(meta, dict) and meta.get("g_listen_cleared")),
        }

    @app.post("/api/runs/{run_id}/g-listen/continue")
    def g_listen_continue(run_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            from interview_mux.gates import clear_g_listen

            clear_g_listen(ctx, skipped=False)
            return {"ok": True, "cleared": True}

    @app.post("/api/runs/{run_id}/g-listen/skip")
    def g_listen_skip(run_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            from interview_mux.gates import clear_g_listen

            clear_g_listen(ctx, skipped=True)
            return {"ok": True, "skipped": True}

    @app.get("/api/runs/{run_id}/g-publish")
    def get_g_publish(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        from interview_mux.gates import check_g_publish_pending
        from interview_mux.podcast_rss.settings import (
            apple_podcasts_passthrough_url,
            feed_url_from_base,
            podcast_id_from_ctx,
            resolve_publish_targets,
            show_cfg,
        )
        from interview_mux.podcast_rss.sync_assets import read_last_sync_result, sync_status_summary

        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        pid = podcast_id_from_ctx(ctx)
        show = show_cfg(pid)
        targets = resolve_publish_targets(pid)
        result = (
            ctx.read_json("publish/publish_result.json")
            if ctx.artifact_exists("publish/publish_result.json")
            else {}
        )
        package_ready = (
            ctx.read_json("publish/package_ready.json")
            if ctx.artifact_exists("publish/package_ready.json")
            else {}
        )
        base = str(targets.get("feed_base_url") or "").rstrip("/")
        feed_url = feed_url_from_base(base, cfg=show) or None
        # Counts + sync are scoped to this run only — never sibling executions.
        sync_summary = sync_status_summary(execution_id=run_id)
        return {
            "pending": check_g_publish_pending(ctx),
            "enabled": bool(show.get("enabled", True)),
            "podcast_id": pid,
            "show_title": show.get("show_title") or "Zero Shot Podcast DEMO",
            "feed_base_url": base or None,
            "feed_url": feed_url,
            "apple_podcasts_passthrough_url": apple_podcasts_passthrough_url(feed_url) or None,
            "skipped": bool(isinstance(meta, dict) and meta.get("g_publish_skipped")),
            "cleared": bool(isinstance(meta, dict) and meta.get("g_publish_cleared")),
            "package_ready": bool(isinstance(package_ready, dict) and package_ready.get("ready")),
            "has_master": ctx.artifact_exists("master/master.wav"),
            "publish_result": result if isinstance(result, dict) else {},
            "ready_package_count": int(sync_summary.get("ready_package_count") or 0),
            "already_uploaded_count": int(sync_summary.get("already_uploaded_count") or 0),
            "incomplete_count": int(sync_summary.get("incomplete_count") or 0),
            "execution_id": run_id,
            "last_sync": sync_summary.get("last_sync") or read_last_sync_result(),
            "sync_job": _read_podcast_sync_job(),
        }

    @app.get("/api/runs/{run_id}/g-publish/review")
    def get_g_publish_review(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        from interview_mux.g_publish_review import load_g_publish_review

        return load_g_publish_review(ctx)

    @app.put("/api/runs/{run_id}/g-publish/review")
    def put_g_publish_review(run_id: str, body: GPublishReviewBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            from interview_mux.g_publish_review import save_g_publish_review

            try:
                return save_g_publish_review(
                    ctx,
                    title=body.title,
                    description=body.description,
                    cover_path=body.cover_path,
                )
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            except FileNotFoundError as exc:
                raise HTTPException(404, str(exc)) from exc

    @app.post("/api/runs/{run_id}/g-publish/cover")
    async def g_publish_cover_upload(run_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            from interview_mux.g_publish_review import save_uploaded_cover

            suffix = Path(file.filename or "cover.jpg").suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
                raise HTTPException(400, "Cover must be JPG, PNG, or WebP.")
            staging = ctx.path(f"publish/_operator_cover_upload{suffix or '.jpg'}")
            staging.parent.mkdir(parents=True, exist_ok=True)
            data = await file.read()
            if not data:
                raise HTTPException(400, "Empty upload.")
            staging.write_bytes(data)
            try:
                return save_uploaded_cover(ctx, staging)
            except (ValueError, FileNotFoundError) as exc:
                raise HTTPException(400, str(exc)) from exc

    @app.post("/api/runs/{run_id}/g-publish/continue")
    def g_publish_continue(run_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            from interview_mux.gates import clear_g_publish

            clear_g_publish(ctx, skipped=False)
            set_active_execution(run_id)
            ctx.log(
                "G-Publish cleared — preparing local episode package (no S3 upload)",
                level="action",
                stage="podcast_publish",
            )
        # Outside lock: background job owns the run (same pattern as /execute)
        job = runner.start(
            run_id,
            mode="stage",
            from_stage="master_transcript_build",
            until_stage="podcast_publish",
        )
        return {"ok": True, "cleared": True, "started": True, "prepare_only": True, "job": job}

    @app.post("/api/runs/{run_id}/g-publish/sync")
    def g_publish_sync(run_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Upload this run's ready package only. Never deletes S3 objects; never other executions."""
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            # Upload click is operator consent when quality advisories would block S3.
            from interview_mux.aspirational_quality import (
                consent_g_publish_advisories,
                has_quality_advisories,
            )

            if has_quality_advisories(ctx):
                consent_g_publish_advisories(ctx)
                ctx.log(
                    "G-Publish — operator consented to sync despite quality advisories",
                    level="action",
                    stage="podcast_publish",
                )
            body = body or {}
            dry_run = bool(body.get("dry_run"))
            force_files = bool(body.get("force_files"))
            existing = _read_podcast_sync_job()
            if existing.get("status") == "running":
                raise HTTPException(409, "Podcast sync already running")
            job = _start_podcast_sync_job(
                dry_run=dry_run,
                force_files=force_files,
                execution_id=run_id,
            )
            return {"ok": True, "started": True, "job": job, "execution_id": run_id}

    @app.post("/api/runs/{run_id}/g-publish/skip")
    def g_publish_skip(run_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            from interview_mux.gates import clear_g_publish
            from interview_mux.stages.podcast_publish import run_podcast_publish_skip

            clear_g_publish(ctx, skipped=True)
            run_podcast_publish_skip(ctx)
            if not ctx.is_done("podcast_publish"):
                ctx.mark_done("podcast_publish")
            return {"ok": True, "skipped": True}

    @app.post("/api/runs/{run_id}/g1/skip-optional")
    def g1_skip_optional(run_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Mark non-blocking delivery:record gaps as skipped_optional and rebuild delivery_brief."""
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            body = body or {}
            line_ids = body.get("line_ids")
            force = bool(body.get("force"))
            from interview_mux.delivery_brief import rebuild_delivery_brief

            def _line_severity(line: dict[str, Any]) -> str:
                return str(line.get("severity") or "medium").lower()

            def _line_requires_vo(line: dict[str, Any]) -> bool:
                return line.get("blocking") is True or _line_severity(line) in {"high", "critical"}

            if not ctx.artifact_exists("understanding/gap_report.json"):
                raise HTTPException(404, "gap_report.json not found")
            report = ctx.read_json("understanding/gap_report.json")
            lines = report.get("interviewer_lines") if isinstance(report, dict) else []
            if not isinstance(lines, list):
                raise HTTPException(400, "Invalid gap_report")
            wanted = {str(x) for x in line_ids} if isinstance(line_ids, list) else None
            skipped: list[str] = []
            for line in lines:
                if not isinstance(line, dict):
                    continue
                delivery = str(line.get("delivery") or "").lower()
                # Record pickups and failed/abandoned synthesize lines are both skippable at G1.
                if delivery not in {"record", "synthesize"}:
                    continue
                lid = str(line.get("line_id") or line.get("targets_segment_id") or "")
                if wanted is not None and lid not in wanted:
                    continue
                if not force and (_line_requires_vo(line) and (line.get("blocking") is True or _line_severity(line) in {"high", "critical"})):
                    if wanted is None:
                        continue
                    if _line_requires_vo(line):
                        continue
                line["skipped_optional"] = True
                line["blocking"] = False
                if not line.get("severity"):
                    line["severity"] = "medium"
                skipped.append(lid)
            ctx.write_json("understanding/gap_report.json", report)
            from interview_mux.vo_synthesis_audit import record_skipped_vo
            from interview_mux.omit_ledger import record_gap_line_skip

            waived_nuggets: list[str] = []
            if skipped and force:
                from interview_mux.nugget_layup import waive_nuggets_for_skipped_vo_lines

                try:
                    waived_nuggets = waive_nuggets_for_skipped_vo_lines(
                        ctx,
                        skipped_line_ids=skipped,
                        gap_report=report,
                    )
                except Exception:
                    waived_nuggets = []

            for lid in skipped:
                record_skipped_vo(ctx, lid, reason="g1_skip_optional")
                try:
                    target = None
                    for line in lines:
                        if not isinstance(line, dict):
                            continue
                        if str(line.get("line_id") or line.get("targets_segment_id") or "") == lid:
                            target = str(line.get("targets_segment_id") or "") or None
                            break
                    record_gap_line_skip(
                        ctx,
                        line_id=lid,
                        target_segment_id=target,
                        reason_code="g1_skipped_optional",
                        operator_override=True,
                    )
                except Exception:
                    pass

            # Never set the meta flag on a no-op skip (empty skipped) — that
            # previously cascaded into repair_gap_report marking all synthesize lines skipped.
            if skipped:

                def _mark_g1_skipped(meta: dict[str, Any]) -> None:
                    meta["g1_vo_skipped_optional"] = True
                    prev = meta.get("g1_skip_applied_line_ids")
                    existing = [str(x) for x in prev] if isinstance(prev, list) else []
                    merged = list(dict.fromkeys([*existing, *[str(x) for x in skipped if x]]))
                    meta["g1_skip_applied_line_ids"] = merged

                ctx.mutate_run_meta(_mark_g1_skipped)
            rebuild_delivery_brief(ctx, reason="g1_skip_optional")
            ctx.log(
                f"G1 skip-optional: marked {len(skipped)} line(s)",
                level="success" if skipped else "warning",
                stage="g1_vo_pickup",
                action_id="gui.g1.skip_optional",
                detail={"event": "g1_skip_optional", "line_ids": skipped, "waived_nugget_ids": waived_nuggets},
            )
            return {
                "ok": True,
                "skipped": skipped,
                "g1_missing": check_g1_vo(ctx),
                "waived_nugget_ids": waived_nuggets,
            }

    @app.get("/api/runs/{run_id}/stages/{stage_id}/reuse-offers")
    def get_stage_reuse_offers(run_id: str, stage_id: str) -> dict[str, Any]:
        from interview_mux.stage_execution_reuse import stage_reuse_offers_enabled

        if not stage_reuse_offers_enabled():
            raise HTTPException(400, "Stage reuse offers are disabled.")
        ctx = _ctx(run_id)
        if stage_id not in STAGE_BY_ID:
            raise HTTPException(404, f"Unknown stage: {stage_id}")
        from interview_mux.stage_execution_reuse import reuse_offer_payload

        return reuse_offer_payload(ctx, stage_id)

    @app.post("/api/runs/{run_id}/stages/{stage_id}/reuse")
    def post_stage_reuse(run_id: str, stage_id: str, body: StageReuseBody) -> dict[str, Any]:
        from interview_mux.stage_execution_reuse import stage_reuse_offers_enabled

        if not stage_reuse_offers_enabled():
            raise HTTPException(400, "Stage reuse offers are disabled.")
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

    @app.get("/api/runs/{run_id}/soundscape-policy")
    def get_soundscape_policy(run_id: str) -> dict[str, Any]:
        from interview_mux.soundscape_policy import POLICY_PATH, compact_for_volley, load_policy
        from interview_mux.soundscape_verify import load_soundscape_report

        ctx = _ctx(run_id)
        pol = load_policy(ctx)
        if not pol:
            raise HTTPException(404, f"Artifact not found: {POLICY_PATH}")
        report = load_soundscape_report(ctx)
        return {
            "path": POLICY_PATH,
            "policy": pol,
            "summary": compact_for_volley(pol),
            "report": report,
        }

    @app.get("/api/runs/{run_id}/audio-probes")
    def get_audio_probes(run_id: str) -> dict[str, Any]:
        """Read-only summary of vernacular audio-probe artifacts (fault-tolerant)."""
        ctx = _ctx(run_id)
        candidate_paths = (
            "analysis/run_golden_facts.json",
            "transcript/protected_zones.json",
            "transcript/speaker_flows.json",
            "vernacular/probe_report.json",
            "vernacular/audio_tags_by_flow.json",
            "vernacular/resplit_report.json",
            "analysis/vernacular_must_keep.json",
        )
        present: list[str] = []
        for path in candidate_paths:
            try:
                if ctx.artifact_exists(path):
                    present.append(path)
            except Exception:
                continue

        empty: dict[str, Any] = {
            "available": False,
            "enforcement_mode": "shadow",
            "run": {},
            "zones_count": 0,
            "must_keep_segment_ids": [],
            "answer_stats": {},
            "probe_rows_preview": [],
            "resplit_patterns": [],
            "artifacts": present,
        }
        if not present:
            return empty

        run_subset: dict[str, Any] = {}
        enforcement_mode = "shadow"
        answer_stats: dict[str, Any] = {}
        zones_count = 0
        must_keep: list[str] = []
        probe_rows: list[Any] = []
        resplit_patterns: list[Any] = []

        try:
            if ctx.artifact_exists("analysis/run_golden_facts.json"):
                gf = ctx.read_json("analysis/run_golden_facts.json")
                if isinstance(gf, dict):
                    run = gf.get("run") if isinstance(gf.get("run"), dict) else {}
                    run_keys = (
                        "has_in_flow_vernacular",
                        "has_non_english_spans",
                        "has_uncommon_english",
                        "has_high_passion",
                        "has_pull_quote",
                        "has_affect_burst",
                        "has_crosstalk",
                        "has_bleed",
                        "has_unintelligible",
                        "has_payoff",
                        "has_sensitive_disclosure",
                        "enforcement_mode",
                        "vernacular_must_keep_segment_ids",
                        "special_keywords",
                        "special_speaker_flow_ids",
                        "vernacular_flow_count",
                    )
                    run_subset = {k: run[k] for k in run_keys if k in run}
                    enforcement_mode = str(run.get("enforcement_mode") or enforcement_mode)
                    mk = run.get("vernacular_must_keep_segment_ids")
                    if isinstance(mk, list):
                        must_keep = [str(x) for x in mk if x]
                    meta = gf.get("meta") if isinstance(gf.get("meta"), dict) else {}
                    stats = meta.get("answer_stats")
                    if isinstance(stats, dict):
                        answer_stats = stats
        except Exception:
            pass

        try:
            if ctx.artifact_exists("transcript/protected_zones.json"):
                pz = ctx.read_json("transcript/protected_zones.json")
                if isinstance(pz, dict):
                    zones = pz.get("zones")
                    if isinstance(zones, list):
                        zones_count = len(zones)
        except Exception:
            pass

        try:
            if ctx.artifact_exists("vernacular/probe_report.json"):
                report = ctx.read_json("vernacular/probe_report.json")
                if isinstance(report, dict):
                    rows = report.get("rows")
                    if isinstance(rows, list):
                        probe_rows = rows[:12]
                    stats = report.get("answer_stats")
                    if isinstance(stats, dict) and not answer_stats:
                        answer_stats = stats
        except Exception:
            pass

        try:
            if ctx.artifact_exists("analysis/vernacular_must_keep.json"):
                side = ctx.read_json("analysis/vernacular_must_keep.json")
                if isinstance(side, dict):
                    mk = side.get("must_keep_segment_ids")
                    if isinstance(mk, list) and mk:
                        must_keep = [str(x) for x in mk if x]
                    mode = side.get("enforcement_mode")
                    if mode:
                        enforcement_mode = str(mode)
        except Exception:
            pass

        try:
            if ctx.artifact_exists("vernacular/resplit_report.json"):
                resplit = ctx.read_json("vernacular/resplit_report.json")
                if isinstance(resplit, dict):
                    rows = resplit.get("rows")
                    if isinstance(rows, list):
                        patterns: list[Any] = []
                        for row in rows:
                            if not isinstance(row, dict):
                                continue
                            pat = row.get("pattern")
                            if pat:
                                patterns.append(pat)
                            if len(patterns) >= 8:
                                break
                        resplit_patterns = patterns
                    mk = resplit.get("must_keep_segment_ids")
                    if isinstance(mk, list) and mk and not must_keep:
                        must_keep = [str(x) for x in mk if x]
        except Exception:
            pass

        return {
            "available": True,
            "enforcement_mode": enforcement_mode if enforcement_mode in ("shadow", "authoritative") else "shadow",
            "run": run_subset,
            "zones_count": zones_count,
            "must_keep_segment_ids": must_keep,
            "answer_stats": answer_stats,
            "probe_rows_preview": probe_rows,
            "resplit_patterns": resplit_patterns,
            "artifacts": present,
        }

    @app.get("/api/runs/{run_id}/episode-structure")
    def get_episode_structure(run_id: str) -> dict[str, Any]:
        from interview_mux.episode_structure import (
            STRUCTURE_PATH,
            compact_for_volley,
            load_episode_structure,
        )

        ctx = _ctx(run_id)
        doc = load_episode_structure(ctx)
        if not doc:
            raise HTTPException(404, f"Artifact not found: {STRUCTURE_PATH}")
        return {
            "path": STRUCTURE_PATH,
            "structure": doc,
            "summary": compact_for_volley(doc),
        }

    @app.patch("/api/runs/{run_id}/soundscape-policy/overrides")
    def patch_soundscape_policy_overrides(run_id: str, body: AcousticProfileOverridesBody) -> dict[str, Any]:
        from interview_mux.soundscape_policy import POLICY_PATH, save_operator_overrides

        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            if not ctx.artifact_exists(POLICY_PATH):
                raise HTTPException(404, "Soundscape policy not found — run soundscape_policy_build first.")
            try:
                policy = save_operator_overrides(ctx, body.overrides if isinstance(body.overrides, dict) else {})
            except ValueError as exc:
                raise HTTPException(400, {"errors": [str(exc)]}) from exc
            ctx.log(
                "Soundscape policy operator overrides saved.",
                level="success",
                stage="soundscape_policy_build",
                detail="soundscape_override_saved",
            )
            if body.invalidate_from:
                runner.invalidate_from(run_id, body.invalidate_from)
            else:
                runner.invalidate_from(run_id, "sound_design_plan")
            return {
                "ok": True,
                "operator_overrides": policy.get("operator_overrides") or {},
                "policy": policy,
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
        soundscape_summary = None
        try:
            from interview_mux.soundscape_policy import compact_for_volley, load_policy
            from interview_mux.soundscape_verify import load_soundscape_report

            pol = load_policy(ctx)
            if pol:
                soundscape_summary = compact_for_volley(pol)
                report = load_soundscape_report(ctx)
                if report:
                    soundscape_summary["verify_verdict"] = report.get("verdict")
        except Exception:
            soundscape_summary = None
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
            "soundscape_policy": soundscape_summary,
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

    @app.get("/api/runs/{run_id}/music-listen")
    def get_music_listen(run_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.music_listen_review import music_listen_status

            ctx = _ctx(run_id)
            return {"ok": True, **music_listen_status(ctx)}

    @app.post("/api/runs/{run_id}/music-listen/approve")
    def approve_music_listen(run_id: str, body: SfxPromptApproveBody) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.music_listen_review import set_music_listen_approved

            ctx = _ctx(run_id)
            review = set_music_listen_approved(
                ctx, approved=True, approved_by=body.approved_by or "operator"
            )
            ctx.log(
                "music_listen_approved",
                level="success",
                stage="mmaudio_sfx",
                detail=str(review),
            )
            return {"ok": True, "review": review}

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
                    stage="mix",
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
                stage = "mmaudio_sfx"
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
            stage = "mmaudio_sfx"
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
        delivery_modes = ("delivery", "delivery_until_preview", "delivery_polish")
        return runner.start(
            run_id,
            mode=body.mode,
            stage=body.stage,
            flow=body.mode if body.mode in delivery_modes else None,
            from_stage=body.from_stage or body.stage,
            until_stage=body.until_stage,
            nle_full_refresh=body.nle_full_refresh,
            nle_apply_mode=body.nle_apply_mode,
            api_consents=body.api_consents,
        )

    @app.post("/api/runs/{run_id}/fill-artifact-gaps")
    def fill_artifact_gaps(run_id: str, body: FillArtifactGapsBody) -> dict[str, Any]:
        from interview_mux.artifact_completeness import (
            preferred_fill_stage,
            stage_keys_for_artifact_path,
        )

        stage: str
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            _assert_artifact_path(body.path)
            stage_ids = stage_keys_for_artifact_path(body.path)
            if not stage_ids:
                raise HTTPException(400, f"No LLM stage registered for artifact path: {body.path}")
            set_active_execution(run_id)
            stage = preferred_fill_stage(body.path, ctx) or stage_ids[0]
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
            invalidate=True,
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

    @app.put("/api/runs/{run_id}/transcript/text")
    def put_transcript_text(run_id: str, body: TranscriptTextBody) -> dict[str, Any]:
        """Full-text save after transcript reuse (edit interstitial) or operator re-edit."""
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            if not ctx.artifact_exists("transcript/full.json"):
                raise HTTPException(404, "Transcript not found — run transcribe first.")
            try:
                if transcript_review.transcript_reuse_pending_edit(ctx):
                    result = transcript_review.save_reused_transcript_text(ctx, body.text)
                else:
                    result = transcript_review.apply_full_transcript_text(
                        ctx, body.text, source="operator_text_edit"
                    )
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return {
                "ok": True,
                "text": result.get("text"),
                "word_count": result.get("word_count"),
                "pending_edit": transcript_review.transcript_reuse_pending_edit(ctx),
                "transcript_review_done": ctx.is_done("transcript_review"),
            }

    @app.post("/api/runs/{run_id}/transcript/reuse-edit/complete")
    def complete_transcript_reuse_edit(run_id: str) -> dict[str, Any]:
        """Finalize reuse interstitial after dock word edits (no full-text remap)."""
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            if not ctx.artifact_exists("transcript/full.json"):
                raise HTTPException(404, "Transcript not found — run transcribe first.")
            if not transcript_review.transcript_reuse_pending_edit(ctx):
                return {
                    "ok": True,
                    "pending_edit": False,
                    "transcript_review_done": ctx.is_done("transcript_review"),
                }
            try:
                result = transcript_review.finalize_reused_transcript_from_disk(ctx)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return {
                "ok": True,
                "text": result.get("text"),
                "word_count": result.get("word_count"),
                "pending_edit": False,
                "transcript_review_done": ctx.is_done("transcript_review"),
            }

    @app.post("/api/runs/{run_id}/transcript/reuse-edit/dismiss")
    def dismiss_transcript_reuse_edit(run_id: str) -> dict[str, Any]:
        """Skip the one-time reuse edit window; do not re-open at STT review."""
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            return transcript_review.dismiss_transcript_reuse_edit(ctx)

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
            try:
                from interview_mux.delivery_brief import rebuild_delivery_brief

                rebuild_delivery_brief(ctx, reason="analysis_profile_verify")
            except Exception:
                pass
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
            ctx.read_json("master/narrative_plan.json")
            if ctx.artifact_exists("master/narrative_plan.json")
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

            def _resume_partial_auto(meta: dict[str, Any]) -> None:
                meta.pop("needs_operator", None)
                meta.pop("needs_operator_stage", None)
                meta.pop("needs_operator_reason", None)
                if meta.get("partial_auto") or meta.get("run_mode") == "partially-accelerated":
                    meta["partial_auto_driver_active"] = True

            ctx.mutate_run_meta(_resume_partial_auto)
            from interview_mux.gui_job_reconcile import reconcile_operator_gate_job
            from interview_mux.write_staging import read_gui_job

            job = read_gui_job(ctx) or {}
            reconciled = reconcile_operator_gate_job(ctx, job)
            if reconciled is not job:
                ctx.write_json("gui_job.json", reconciled, skip_handoff=True)
            refresh_journey_meta(ctx)
            return {"ok": True, "transcript_review_clear": True}

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
            from interview_mux.vo_synthesis_audit import record_recorded_vo

            record_recorded_vo(ctx, line_id, out_wav=dest, backend="upload")
            return {"ok": True, "path": f"vo_pickup/{dest.name}", "g1_missing": check_g1_vo(ctx)}

    @app.post("/api/runs/{run_id}/vo/{line_id}/synthesize")
    def vo_synthesize_line(run_id: str, line_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            if not ctx.artifact_exists("understanding/gap_report.json"):
                raise HTTPException(404, "gap_report.json not found")
            report = ctx.read_json("understanding/gap_report.json")
            line = next(
                (
                    ln
                    for ln in (report.get("interviewer_lines") or [])
                    if isinstance(ln, dict) and str(ln.get("line_id")) == line_id
                ),
                None,
            )
            if not line:
                raise HTTPException(404, f"Unknown line_id: {line_id}")
            from interview_mux import s2s_runner
            from interview_mux.synthesis_fallback import SynthesisFallbackToManual

            try:
                out = s2s_runner.synthesize_line(ctx, line, mode="synthesize")
            except SynthesisFallbackToManual as fb:
                refresh_journey_meta(ctx)
                ctx.log(
                    fb.notice,
                    level="warning",
                    stage="g1_vo_pickup",
                    action_id="gui.g1.vo.synthesize",
                    detail={"line_id": line_id, "fallback": "record"},
                )
                return {
                    "ok": False,
                    "fallback": "record",
                    "notice": fb.notice,
                    "line_id": line_id,
                    "g1_missing": check_g1_vo(ctx),
                }
            except Exception as exc:
                from interview_mux.loud_fail import LoudStageFailure

                ctx.log(
                    f"VO synthesis failed for {line_id}: {exc}",
                    level="error",
                    stage="g1_vo_pickup",
                    action_id="gui.g1.vo.synthesize",
                    detail={"line_id": line_id, "hard_stop": True},
                )
                status = 503 if isinstance(exc, LoudStageFailure) else 500
                raise HTTPException(status, str(exc)) from exc
            ctx.log(
                f"S2S synthesized vo_pickup/{out.name}",
                level="success",
                stage="g1_vo_pickup",
                action_id="gui.g1.vo.synthesize",
                detail={"line_id": line_id, "path": out.relative_to(ctx.run_dir).as_posix()},
            )
            return {
                "ok": True,
                "path": out.relative_to(ctx.run_dir).as_posix(),
                "g1_missing": check_g1_vo(ctx),
            }

    @app.post("/api/runs/{run_id}/vo/{line_id}/match")
    async def vo_match_line(run_id: str, line_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.file_store import write_bytes as fs_write_bytes
            from interview_mux.timbre_match import match_vo_take

            ctx = _ctx(run_id)
            if not ctx.artifact_exists("understanding/gap_report.json"):
                raise HTTPException(404, "gap_report.json not found")
            report = ctx.read_json("understanding/gap_report.json")
            line = next(
                (
                    ln
                    for ln in (report.get("interviewer_lines") or [])
                    if isinstance(ln, dict) and str(ln.get("line_id")) == line_id
                ),
                None,
            )
            if not line:
                raise HTTPException(404, f"Unknown line_id: {line_id}")
            pickup = ctx.path("vo_pickup")
            pickup.mkdir(parents=True, exist_ok=True)
            raw = pickup / f"{line_id}_upload.wav"
            content = await file.read()
            fs_write_bytes(raw, content)
            try:
                # DSP spectral + loudness match — never TTS/S2S convert into matched/.
                out = match_vo_take(ctx, line, raw)
            except Exception as exc:
                ctx.log(
                    f"VO timbre-match failed (upload retained): {exc}",
                    level="warning",
                    stage="g1_vo_pickup",
                    action_id="gui.g1.vo.match",
                    detail={
                        "line_id": line_id,
                        "upload": raw.relative_to(ctx.run_dir).as_posix(),
                        "error": str(exc)[:500],
                    },
                )
                raise HTTPException(
                    503,
                    {
                        "ok": False,
                        "error": str(exc)[:500],
                        "upload_path": raw.relative_to(ctx.run_dir).as_posix(),
                        "g1_missing": check_g1_vo(ctx),
                    },
                ) from exc
            ctx.log(
                f"VO timbre-match saved: {out.relative_to(ctx.run_dir).as_posix()}",
                level="success",
                stage="g1_vo_pickup",
                action_id="gui.g1.vo.match",
                detail={"line_id": line_id, "provider": "dsp_firequalizer"},
            )
            return {
                "ok": True,
                "path": out.relative_to(ctx.run_dir).as_posix(),
                "g1_missing": check_g1_vo(ctx),
            }

    @app.post("/api/runs/{run_id}/vo/{line_id}/tone")
    def vo_tone_line(run_id: str, line_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            body = body or {}
            tone = str(body.get("tone") or "neutral")
            if not ctx.artifact_exists("understanding/gap_report.json"):
                raise HTTPException(404, "gap_report.json not found")
            report = ctx.read_json("understanding/gap_report.json")
            line = next(
                (
                    ln
                    for ln in (report.get("interviewer_lines") or [])
                    if isinstance(ln, dict) and str(ln.get("line_id")) == line_id
                ),
                None,
            )
            if not line:
                raise HTTPException(404, f"Unknown line_id: {line_id}")
            from interview_mux import s2s_runner

            try:
                out = s2s_runner.synthesize_line(ctx, line, mode="tone", tone=tone)
            except Exception as exc:
                raise HTTPException(503, str(exc)) from exc
            ctx.log(
                f"S2S tone ({tone}) for {line_id}",
                level="success",
                stage="g1_vo_pickup",
                action_id="gui.g1.vo.tone",
                detail={"line_id": line_id, "tone": tone},
            )
            return {
                "ok": True,
                "path": out.relative_to(ctx.run_dir).as_posix(),
                "g1_missing": check_g1_vo(ctx),
            }

    @app.get("/api/runs/{run_id}/delivery-brief")
    def get_delivery_brief(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        if not ctx.artifact_exists("understanding/delivery_brief.json"):
            return {"brief": None}
        return {"brief": ctx.read_json("understanding/delivery_brief.json")}

    @app.patch("/api/runs/{run_id}/delivery-brief")
    def patch_delivery_brief(run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.delivery_brief import apply_delivery_brief_patch

            ctx = _ctx(run_id)
            brief = apply_delivery_brief_patch(ctx, body or {})
            ctx.log(
                "delivery_brief patched by operator",
                level="action",
                stage="delivery_brief_build",
                detail={"kind": "delivery_brief", "action_id": "gui.delivery_brief.save"},
            )
            return {"ok": True, "brief": brief}

    @app.post("/api/runs/{run_id}/delivery-brief/rebuild")
    def rebuild_delivery_brief_endpoint(run_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.delivery_brief import rebuild_delivery_brief

            ctx = _ctx(run_id)
            brief = rebuild_delivery_brief(ctx, reason="operator_rebuild")
            ctx.log(
                "delivery_brief rebuilt by operator",
                level="action",
                stage="delivery_brief_build",
                detail={"kind": "delivery_brief", "action_id": "gui.delivery_brief.reset"},
            )
            return {"ok": True, "brief": brief}

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
            try:
                from interview_mux.delivery_brief import rebuild_delivery_brief

                rebuild_delivery_brief(ctx, reason="flow_adaptation_patch")
            except Exception:
                pass
            return {"ok": True, "adaptation": adapt}

    @app.post("/api/runs/{run_id}/flow-adaptation/confirm")
    def confirm_flow_adaptation(run_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.source_topology import apply_flow_adaptation_patch

            ctx = _ctx(run_id)
            adapt = apply_flow_adaptation_patch(
                ctx, {"operator_overrides": {"topology_confirmed": True}}
            )
            try:
                from interview_mux.delivery_brief import rebuild_delivery_brief

                rebuild_delivery_brief(ctx, reason="flow_adaptation_confirm")
            except Exception:
                pass
            ctx.log(
                "Topology confirmed by operator",
                level="action",
                stage="source_topology_build",
                detail={"kind": "adaptation", "journey_kind": "adaptation", "action_id": "gui.adaptation.confirm"},
            )
            return {"ok": True, "adaptation": adapt}

    @app.post("/api/runs/{run_id}/speaker-roles/confirm-hypothesis")
    def confirm_speaker_roles_hypothesis(run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.conversation_context import confirm_conversation_hypothesis

            ctx = _ctx(run_id)
            hypothesis_id = str(body.get("hypothesis_id") or "").strip()
            if not hypothesis_id:
                raise HTTPException(400, "hypothesis_id is required")
            try:
                updated = confirm_conversation_hypothesis(ctx, hypothesis_id)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            ctx.log(
                f"Conversation hypothesis confirmed: {hypothesis_id}",
                level="action",
                stage="speaker_roles",
                detail={
                    "hypothesis_id": hypothesis_id,
                    "action_id": "gui.speaker_roles.confirm_hypothesis",
                },
            )
            return {"ok": True, "speakers": updated}

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

    @app.get("/api/runs/{run_id}/gap-framing")
    def get_gap_framing_gate(run_id: str) -> dict[str, Any]:
        from interview_mux.gap_vo_gates import gap_gate_payload

        ctx = _ctx(run_id)
        return gap_gate_payload(ctx)

    @app.get("/api/runs/{run_id}/vo-pipeline-status")
    def get_vo_pipeline_status(run_id: str) -> dict[str, Any]:
        from interview_mux.pipeline_mode import resolve_effective_mode

        ctx = _ctx(run_id)
        out: dict[str, Any] = {
            "pipeline_mode": resolve_effective_mode(ctx),
            "nugget_coverage": None,
            "nugget_coverage_target": 0.85,
            "lines": [],
        }
        if ctx.artifact_exists("understanding/nugget_allocation_plan.json"):
            try:
                plan = ctx.read_json("understanding/nugget_allocation_plan.json")
                cov = (plan or {}).get("coverage") if isinstance(plan, dict) else None
                if isinstance(cov, dict):
                    out["nugget_coverage"] = cov.get("nugget_air_ratio")
                    out["nugget_coverage_target"] = cov.get("target") or 0.85
            except Exception:
                pass
        if ctx.artifact_exists("understanding/vo_line_adjudication.json"):
            try:
                adj = ctx.read_json("understanding/vo_line_adjudication.json")
                rows = (adj or {}).get("lines") if isinstance(adj, dict) else []
                if isinstance(rows, list):
                    for row in rows[:24]:
                        if not isinstance(row, dict):
                            continue
                        out["lines"].append(
                            {
                                "line_id": row.get("line_id"),
                                "status": row.get("decision") or row.get("status"),
                                "text_preview": str(row.get("text") or "")[:120],
                            }
                        )
            except Exception:
                pass
        if not out["lines"] and ctx.artifact_exists("understanding/gap_report.json"):
            try:
                gap = ctx.read_json("understanding/gap_report.json")
                for row in (gap or {}).get("interviewer_lines") or []:
                    if not isinstance(row, dict):
                        continue
                    if str(row.get("delivery") or "") != "synthesize":
                        continue
                    out["lines"].append(
                        {
                            "line_id": row.get("line_id"),
                            "status": "pending_adjudicate",
                            "text_preview": str(row.get("text") or "")[:120],
                        }
                    )
            except Exception:
                pass
        return out

    @app.get("/api/runs/{run_id}/gap-framing/script")
    def get_gap_framing_script(run_id: str) -> dict[str, Any]:
        from interview_mux.gap_framing import load_gap_framing_plan
        from interview_mux.gap_report_api import list_lines
        from interview_mux.omit_ledger import OMIT_LEDGER_REL, build_omit_ledger

        ctx = _ctx(run_id)
        ledger = (
            ctx.read_json(OMIT_LEDGER_REL)
            if ctx.artifact_exists(OMIT_LEDGER_REL)
            else build_omit_ledger(ctx)
        )
        return {
            "lines": list_lines(ctx),
            "plan": load_gap_framing_plan(ctx),
            "omit_ledger": ledger if isinstance(ledger, dict) else {},
            "omit_summary": (ledger or {}).get("summary") if isinstance(ledger, dict) else {},
        }

    @app.get("/api/runs/{run_id}/omit-ledger")
    def get_omit_ledger(run_id: str) -> dict[str, Any]:
        from interview_mux.omit_ledger import OMIT_LEDGER_REL, build_omit_ledger

        ctx = _ctx(run_id)
        if ctx.artifact_exists(OMIT_LEDGER_REL):
            ledger = ctx.read_json(OMIT_LEDGER_REL)
        else:
            ledger = build_omit_ledger(ctx)
        if not isinstance(ledger, dict):
            ledger = {"version": 1, "entries": [], "summary": {}}
        active = [
            e
            for e in (ledger.get("entries") or [])
            if isinstance(e, dict) and e.get("active")
        ]
        return {
            "omit_ledger": ledger,
            "active_entries": active,
            "summary": ledger.get("summary") or {},
        }

    @app.post("/api/runs/{run_id}/gap-framing/enable")
    def enable_gap_framing(run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.gap_vo_gates import gap_gate_payload, set_gap_framing_enabled

            ctx = _ctx(run_id)
            enabled = bool(body.get("enabled"))
            set_gap_framing_enabled(ctx, enabled)
            if not enabled:
                runner.clear_operator_pause(
                    ctx,
                    "missing_framing",
                    message="Gap framing disabled — continuing with source segments only.",
                    level="info",
                )
                runner.clear_operator_pause(
                    ctx,
                    "gap_framing_compose",
                    message="Gap framing compose skipped.",
                    level="info",
                )
            refresh_journey_meta(ctx)
            return {"ok": True, **gap_gate_payload(ctx)}

    @app.post("/api/runs/{run_id}/gap-framing/delivery")
    def set_gap_framing_delivery(run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.gap_vo_gates import gap_gate_payload, set_gap_vo_delivery
            from interview_mux.synthesis_fallback import ensure_chatterbox_or_manual

            ctx = _ctx(run_id)
            try:
                set_gap_vo_delivery(ctx, str(body.get("delivery") or ""))
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            fallback = ensure_chatterbox_or_manual(ctx, stage="gap_delivery")
            refresh_journey_meta(ctx)
            payload = {"ok": True, **gap_gate_payload(ctx)}
            if fallback:
                payload["synthesis_fallback"] = fallback
            return payload

    @app.get("/api/runs/{run_id}/voice-reference")
    def get_voice_reference(run_id: str) -> dict[str, Any]:
        from interview_mux.voice_reference import voice_reference_payload

        ctx = _ctx(run_id)
        return voice_reference_payload(ctx)

    @app.patch("/api/runs/{run_id}/voice-reference/select")
    def patch_voice_reference_select(run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.source_topology import pickup_eligible_speaker_id
            from interview_mux.voice_reference import update_selected_segments, voice_reference_payload

            ctx = _ctx(run_id)
            speaker_id = pickup_eligible_speaker_id(ctx)
            if not speaker_id:
                raise HTTPException(400, "No pickup-eligible speaker")
            indices = body.get("selected_indices") or []
            update_selected_segments(ctx, speaker_id, [int(i) for i in indices])
            return {"ok": True, **voice_reference_payload(ctx)}

    @app.post("/api/runs/{run_id}/voice-reference/approve")
    def approve_voice_reference_endpoint(run_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.source_topology import pickup_eligible_speaker_id
            from interview_mux.voice_reference import approve_voice_reference, voice_reference_payload

            ctx = _ctx(run_id)
            speaker_id = pickup_eligible_speaker_id(ctx)
            if not speaker_id:
                raise HTTPException(400, "No pickup-eligible speaker")
            try:
                approve_voice_reference(ctx, speaker_id)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            refresh_journey_meta(ctx)
            return {"ok": True, **voice_reference_payload(ctx)}

    @app.get("/api/runs/{run_id}/voice-clone-consent")
    def get_voice_clone_consent(run_id: str) -> dict[str, Any]:
        from interview_mux.mastering_voice_clone import consent_payload

        return consent_payload(_ctx(run_id))

    @app.post("/api/runs/{run_id}/voice-clone-consent")
    def post_voice_clone_consent(run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Grant clone consent with explicit scopes. Guest cloning is always rejected."""
        with _guarded_run(run_id):
            from interview_mux.mastering_voice_clone import (
                CloneNotAuthorized,
                consent_payload,
                grant_consent,
            )
            from interview_mux.source_topology import pickup_eligible_speaker_id

            ctx = _ctx(run_id)
            speaker_id = str(body.get("speaker_id") or "") or pickup_eligible_speaker_id(ctx)
            if not speaker_id:
                raise HTTPException(400, "No pickup-eligible speaker")
            scopes = [str(s) for s in (body.get("scopes") or [])]
            if not scopes:
                raise HTTPException(400, "At least one clone scope is required")
            try:
                grant_consent(
                    ctx,
                    speaker_id=speaker_id,
                    scopes=scopes,
                    granted_by=str(body.get("granted_by") or "operator"),
                    disclosure=str(body.get("disclosure") or "none"),
                )
            except CloneNotAuthorized as exc:
                raise HTTPException(403, exc.detail) from exc
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            refresh_journey_meta(ctx)
            return {"ok": True, **consent_payload(ctx)}

    @app.delete("/api/runs/{run_id}/voice-clone-consent")
    def delete_voice_clone_consent(run_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.mastering_voice_clone import consent_payload, revoke_consent

            ctx = _ctx(run_id)
            revoke_consent(ctx)
            refresh_journey_meta(ctx)
            return {"ok": True, **consent_payload(ctx)}

    @app.post("/api/runs/{run_id}/g1/synthesize-all")
    def g1_synthesize_all(run_id: str) -> dict[str, Any]:
        with _guarded_run(run_id):
            ctx = _ctx(run_id)
            if not ctx.artifact_exists("understanding/gap_report.json"):
                raise HTTPException(404, "gap_report.json not found")
            from interview_mux.delivery_recovery import ensure_g1_pickups
            from interview_mux.loud_fail import LoudStageFailure

            try:
                result = ensure_g1_pickups(ctx, promote=True, max_rounds=2)
            except LoudStageFailure:
                raise
            except Exception as exc:
                raise HTTPException(503, f"VO synthesis failed: {exc}") from exc

            synthesized = list(result.get("synthesized") or [])
            errors = list(result.get("errors") or [])
            fallbacks = list(result.get("fallbacks") or [])
            refresh_journey_meta(ctx)
            notice = fallbacks[-1]["notice"] if fallbacks else None
            missing = list(result.get("g1_missing") or check_g1_vo(ctx))
            framing_hard = False
            try:
                from interview_mux.gap_vo_gates import (
                    gap_framing_enabled,
                    resolve_gap_vo_delivery,
                )

                framing_hard = gap_framing_enabled(ctx) and resolve_gap_vo_delivery(
                    ctx
                ) in {"chatterbox", "synthesize", "voice_clone"}
            except Exception:
                framing_hard = False
            if framing_hard and missing:
                raise HTTPException(
                    503,
                    f"VO synthesis incomplete; still missing: {missing[:8]}",
                )
            if errors and not synthesized:
                raise HTTPException(503, f"VO synthesis failed for all lines: {errors[0]}")
            return {
                "ok": not errors and not (framing_hard and missing),
                "synthesized": synthesized,
                "errors": errors,
                "fallbacks": fallbacks,
                "fallback": "record" if fallbacks else None,
                "notice": notice,
                "g1_missing": missing,
                "job": result.get("job"),
            }

    @app.post("/api/runs/{run_id}/gap-fill/skip")
    def skip_gap_fill_endpoint(run_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        with _guarded_run(run_id):
            from interview_mux.gap_fill_eligibility import (
                gap_fill_was_skipped,
                operator_skip_gap_fill,
            )

            ctx = _ctx(run_id)
            payload = body or {}
            reason = str(payload.get("reason") or "").strip() or None
            if gap_fill_was_skipped(ctx):
                refresh_journey_meta(ctx)
                return {"ok": True, "already_skipped": True, "gap_fill_mode": "skipped"}
            operator_skip_gap_fill(
                ctx,
                reason=reason
                or "Operator skipped gap speaker sections — no new VO or gap analysis",
            )
            runner.clear_operator_pause(
                ctx,
                "missing_framing",
                message="Gap-fill skipped — continuing with source segments only.",
                level="info",
            )
            runner.clear_operator_pause(
                ctx,
                "optimal_questions",
                message="Gap-fill skipped — no interviewer script required.",
                level="info",
            )
            runner.clear_operator_pause(
                ctx,
                "gap_framing_compose",
                message="Gap framing compose skipped.",
                level="info",
            )
            refresh_journey_meta(ctx)
            return {
                "ok": True,
                "gap_fill_mode": "skipped",
                "missing_framing_done": ctx.is_done("missing_framing"),
                "gap_framing_compose_done": ctx.is_done("gap_framing_compose"),
                "optimal_questions_done": ctx.is_done("optimal_questions"),
            }

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
            try:
                from interview_mux.delivery_brief import rebuild_delivery_brief

                rebuild_delivery_brief(ctx, reason="gap_report_add_line")
            except Exception:
                pass
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
            try:
                from interview_mux.delivery_brief import rebuild_delivery_brief

                rebuild_delivery_brief(ctx, reason="gap_report_remove_line")
            except Exception:
                pass
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
                for order in (ANALYSIS_ORDER, DELIVERY_ORDER):
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
            from interview_mux.write_staging import resolve_read_path

            full = resolve_read_path(ctx, path)
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
    _refinement_router = APIRouter()
    register_refinement_routes(_refinement_router, ctx_factory=_ctx)
    app.include_router(_refinement_router)

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app


def _done_markers_from(ctx: RunContext, order: list[str], from_stage: str) -> list[str]:
    if from_stage not in order:
        return []
    idx = order.index(from_stage)
    return [s for s in order[idx:] if ctx.is_done(s)]


def _invalidate_sound_design_for_pace_change(ctx: RunContext) -> list[str]:
    """Clear analysis + delivery sound-design markers after pace_class change."""
    from_stage = "sound_design_palettes"
    cleared = _done_markers_from(ctx, ANALYSIS_ORDER, from_stage)
    cleared.extend(_done_markers_from(ctx, DELIVERY_ORDER, "sound_design_plan"))
    ctx.clear_from(from_stage, ANALYSIS_ORDER)
    ctx.clear_from("sound_design_plan", DELIVERY_ORDER)
    from interview_mux.analysis_memory import invalidate_sonic_context

    invalidate_sonic_context(ctx, reason="pace_class_changed", stage="source_acoustic_profile")
    return cleared


_LEGACY_JOB_KEYS = (
    "awaiting_write_approval",
    "pending_write_stage",
    "pending_write_paths",
    "can_fix_all",
    "bridge_eligible",
    "itr_open_blocking",
    "itr_blocking_count",
    "pending_decision_count",
    "sufficiency_blocking",
)


def _sanitize_job(job: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(job, dict):
        return {}
    return {k: v for k, v in job.items() if k not in _LEGACY_JOB_KEYS}


def refresh_journey_meta(ctx: RunContext) -> None:
    milestones = compute_milestones(ctx)
    phase = compute_operator_phase(ctx, milestones)

    def patch(meta: dict[str, Any]) -> None:
        meta["journey_milestones"] = milestones
        meta["operator_phase"] = phase

    ctx.mutate_run_meta(patch)


def _resilience_payload(ctx: RunContext) -> dict[str, Any]:
    """Operator-visible resilience rollup for GUI / unattended decisioning."""
    from interview_mux.durable_jobs import list_stage_jobs
    from interview_mux.order_hash import get_order_lock
    from interview_mux.stage_resilience import (
        RESILIENCE_REPORT_REL,
        list_open_escalations,
    )

    report = None
    if ctx.artifact_exists(RESILIENCE_REPORT_REL):
        try:
            report = ctx.read_json(RESILIENCE_REPORT_REL)
        except Exception:
            report = None
    order_lock = None
    if ctx.artifact_exists("master/selection.json"):
        try:
            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict):
                order_lock = get_order_lock(sel)
        except Exception:
            order_lock = None
    jobs: list[dict[str, Any]] = []
    for stage_id in ("g1_vo", "mmaudio_sfx", "music_palette_compose", "episode_cover_generate"):
        try:
            jobs.extend(list_stage_jobs(ctx, stage_id)[:5])
        except Exception:
            pass
    return {
        "report": report,
        "open_escalations": list_open_escalations(ctx),
        "order_lock": order_lock,
        "jobs": jobs[:20],
        "quality_first": True,
        "suggest_delivery_resume": None,
        "execution_health": _execution_health_payload(ctx),
        "execution_contract": _execution_contract_payload(ctx),
        "remediation_plan": _remediation_plan_payload(ctx),
    }


def _execution_health_payload(ctx: RunContext) -> dict[str, Any] | None:
    rel = "operator/execution_health.json"
    if not ctx.artifact_exists(rel):
        return None
    try:
        doc = ctx.read_json(rel)
        return doc if isinstance(doc, dict) else None
    except Exception:
        return None


def _execution_contract_payload(ctx: RunContext) -> dict[str, Any] | None:
    rel = "operator/execution_contract.json"
    if not ctx.artifact_exists(rel):
        return None
    try:
        doc = ctx.read_json(rel)
        return doc if isinstance(doc, dict) else None
    except Exception:
        return None


def _remediation_plan_payload(ctx: RunContext) -> dict[str, Any] | None:
    try:
        from interview_mux.remediation_framework import read_active_remediation_plan
        from interview_mux.execution_contract import read_active_vo_repair_plan

        plan = read_active_remediation_plan(ctx) or read_active_vo_repair_plan(ctx)
        if not plan and ctx.artifact_exists("operator/vo_coverage_repair_plan.json"):
            vc = ctx.read_json("operator/vo_coverage_repair_plan.json")
            if isinstance(vc, dict) and vc.get("active"):
                plan = vc
        return plan
    except Exception:
        return None


def _journey_blocking(
    ctx: RunContext,
    *,
    job: dict[str, Any] | None,
    stages: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    job = job or {}
    status = str(job.get("status") or "")
    stage_id = job.get("stage") or job.get("current_stage")

    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if isinstance(meta, dict) and meta.get("needs_operator"):
        op_stage = str(meta.get("needs_operator_stage") or stage_id or "")
        if op_stage:
            return {
                "blocked": True,
                "reason": "needs_operator",
                "stage_id": op_stage,
                "message": str(meta.get("needs_operator_reason") or "Operator action required."),
            }

    if job.get("needs_stage_reuse") and stage_id:
        return {
            "blocked": True,
            "reason": "stage_reuse",
            "stage_id": stage_id,
            "message": str(job.get("message") or "Choose reuse or run fresh."),
        }
    if status == "needs_operator" and job.get("needs_api_consent"):
        return {
            "blocked": True,
            "reason": "api_consent",
            "stage_id": stage_id,
            "message": str(job.get("message") or "API consent required."),
        }

    # G0 wins over status=gate — analysis SystemExit often leaves stage unset or wrong.
    if check_transcript_review_pending(ctx):
        return {
            "blocked": True,
            "reason": "transcript_review",
            "stage_id": "transcript_review",
            "message": "G0 transcript review pending — correct STT before continuing.",
        }

    if status == "gate" and stage_id:
        return {
            "blocked": True,
            "reason": "llm_gate",
            "stage_id": stage_id,
            "message": str(job.get("message") or job.get("error") or "Operator gate."),
        }

    from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

    if not gap_fill_was_skipped(ctx):
        from interview_mux.operator_gate_view import resolve_g1_vo_gate

        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        g1_view = resolve_g1_vo_gate(ctx, job, meta if isinstance(meta, dict) else {})
        if g1_view.blocks_journey and g1_view.open:
            return {
                "blocked": True,
                "reason": "g1_vo_pickup",
                "stage_id": "g1_vo_pickup",
                "message": g1_view.message or "G1 VO pickup needs operator action.",
            }

    for stage in stages or []:
        if stage.get("status") == "action_required" and stage.get("id"):
            sid = str(stage["id"])
            if sid == "transcript_review":
                continue
            return {
                "blocked": True,
                "reason": "gate",
                "stage_id": sid,
                "message": f"{stage.get('title') or sid.replace('_', ' ')} needs operator action.",
            }

    from interview_mux.gates import check_g_publish_pending

    if check_g_publish_pending(ctx):
        package_ready = ctx.artifact_exists("publish/package_ready.json")
        return {
            "blocked": True,
            "reason": "g_publish",
            "stage_id": "podcast_publish",
            "message": (
                "G-Publish: sync local package to S3 or skip."
                if package_ready
                else "G-Publish: prepare local package, sync to S3, or skip."
            ),
        }

    return {"blocked": False}


def _journey_next_action(
    *,
    phase: str,
    blocking: dict[str, Any],
    milestones: dict[str, bool],
) -> str:
    if blocking.get("blocked"):
        reason = str(blocking.get("reason") or "")
        if reason == "transcript_review":
            return "Complete transcript review (G0)"
        if reason == "g1_vo_pickup":
            return "Record or skip G1 pickup VO"
        if reason == "g_publish":
            return "Publish package (S3 sync) or skip G-Publish"
        if reason == "stage_reuse":
            return "Choose reuse or run fresh"
        if reason == "api_consent":
            return "Grant API access"
        return str(blocking.get("message") or "Operator action required")
    if phase == "prepare":
        return "Run prepare pipeline through transcript review"
    if phase == "understand":
        return "Run shared analysis"
    if phase == "complete":
        return "Fill gaps or continue to delivery"
    if phase == "create":
        return "Run delivery through assembly preview"
    if phase == "polish":
        return "Polish sound and mix"
    if milestones.get("master_exported"):
        return "Master exported"
    return "Continue pipeline"


def build_journey_snapshot(
    ctx: RunContext,
    *,
    job: dict[str, Any] | None = None,
    stages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    milestones = compute_milestones(ctx)
    phase = compute_operator_phase(ctx, milestones)
    clean_job = _sanitize_job(job if isinstance(job, dict) else None)
    blocking = _journey_blocking(ctx, job=clean_job, stages=stages)
    return {
        "phase": phase,
        "milestones": milestones,
        "blocking": blocking,
        "next_action": _journey_next_action(
            phase=phase,
            blocking=blocking,
            milestones=milestones,
        ),
        "active_operator_action": None,
        "active_substep_id": None,
        "active_substep_label": None,
        "execute_hint": None,
        "mastering_hardening": _hardening_snapshot(ctx),
    }


def _hardening_snapshot(ctx: RunContext) -> dict[str, Any]:
    """Advisory view of the Mastering hardening gates — never blocks the journey."""
    from interview_mux.mastering_hardening_config import gate_mode
    from interview_mux.mastering_shape_gates import hardening_artifact_status

    try:
        artifacts = hardening_artifact_status(ctx)
    except (OSError, ValueError):
        return {"available": False, "artifacts": {}, "modes": {}}
    gates = (
        "context", "diversity", "feasibility", "semantic_integrity",
        "voice_clone", "rubric", "auditions", "critics", "pareto", "polish",
    )
    return {
        "available": any(artifacts.values()),
        "artifacts": artifacts,
        "modes": {g: gate_mode(g) for g in gates},
    }


def mark_preview_listened(ctx: RunContext) -> None:
    now = datetime.now(timezone.utc).isoformat()

    def patch(meta: dict[str, Any]) -> None:
        meta["preview_listened_at"] = now

    ctx.mutate_run_meta(patch)
    refresh_journey_meta(ctx)


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


def _podcast_sync_job_path() -> Path:
    return repo_root() / "ASSETS" / "podcast" / "sync_job.json"


def _read_podcast_sync_job() -> dict[str, Any]:
    path = _podcast_sync_job_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_podcast_sync_job(payload: dict[str, Any]) -> None:
    path = _podcast_sync_job_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _start_podcast_sync_job(
    *,
    dry_run: bool = False,
    force_files: bool = False,
    execution_id: str,
) -> dict[str, Any]:
    """Spawn podcast sync for one execution in a daemon thread (never deletes S3)."""
    started_at = datetime.now(timezone.utc).isoformat()
    job: dict[str, Any] = {
        "status": "running",
        "dry_run": dry_run,
        "force_files": force_files,
        "execution_id": execution_id,
        "started_at": started_at,
        "message": f"Syncing this run's package to S3 ({execution_id})",
    }
    _write_podcast_sync_job(job)

    def _worker() -> None:
        from interview_mux.podcast_rss.sync_assets import sync_ready_packages

        try:
            result = sync_ready_packages(
                dry_run=dry_run,
                force_files=force_files,
                execution_id=execution_id,
            )
            payload = {
                "status": "error" if result.errors else "done",
                "dry_run": dry_run,
                "force_files": force_files,
                "execution_id": execution_id,
                "started_at": started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "result": result.to_dict(),
                "message": (
                    f"Synced {len(result.uploaded)} package(s) for {execution_id}; "
                    f"skipped {len(result.skipped_already_uploaded)} already uploaded"
                    if not result.errors
                    else f"Sync finished with {len(result.errors)} error(s)"
                ),
            }
            _write_podcast_sync_job(payload)
            # Mark this run's G-Publish gate cleared when upload succeeded.
            if not result.errors and result.uploaded:
                try:
                    from interview_mux.gates import clear_g_publish
                    from interview_mux.run_context import RunContext

                    ctx = RunContext(execution_id, create=False)
                    clear_g_publish(ctx, skipped=False)
                    if ctx.artifact_exists("publish/publish_result.json"):
                        pr = ctx.read_json("publish/publish_result.json")
                        if isinstance(pr, dict):
                            pr["uploaded"] = True
                            pr["uploaded_at"] = datetime.now(timezone.utc).isoformat()
                            ctx.write_json("publish/publish_result.json", pr, skip_handoff=True)
                except Exception:
                    pass
        except Exception as exc:
            _write_podcast_sync_job(
                {
                    "status": "error",
                    "dry_run": dry_run,
                    "force_files": force_files,
                    "execution_id": execution_id,
                    "started_at": started_at,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "message": str(exc),
                    "error": str(exc),
                }
            )

    threading.Thread(target=_worker, daemon=True, name="podcast-sync").start()
    return job


def _assert_asset_input_path(rel: str) -> None:
    """Source audio for a new execution must live directly under ASSETS/input/."""
    cfg = merged_config()
    assets = (repo_root() / cfg.get("assets_root", "ASSETS")).resolve()
    input_dir = assets / "input"
    resolved = _resolve_repo_path(rel)
    try:
        resolved.relative_to(input_dir)
    except ValueError as exc:
        raise HTTPException(
            400,
            f"input_audio_path must be under {input_dir.relative_to(repo_root()).as_posix()}/",
        ) from exc
    rel_parts = resolved.relative_to(input_dir).parts
    if len(rel_parts) != 1:
        raise HTTPException(
            400,
            f"input_audio_path must be a file directly under "
            f"{input_dir.relative_to(repo_root()).as_posix()}/ (not in subfolders)",
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


def _build_stage_list(
    ctx: RunContext,
    g1_missing: list[str],
    transcript_review_pending: bool,
    profile_verified: bool,
    profile_gate_pending: bool,
    *,
    reconcile_done_markers: bool = False,
    job: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    stages = all_stages_for_run(None)
    from interview_mux.stage_completion import reconcile_stage_done_marker
    from interview_mux.write_staging import (
        gate_blocked_stage,
        stages_with_pending_writes,
        write_approval_enabled,
    )

    pending_write_stages = (
        set(stages_with_pending_writes(ctx)) if write_approval_enabled() else set()
    )
    gate_stage = gate_blocked_stage(ctx) if pending_write_stages else None

    from interview_mux.refinement_gate import load_plan as _load_refinement_plan

    refinement_decisions_by_pass_id: dict[str, dict[str, Any]] = {
        str(p.get("pass_id")): p
        for p in (_load_refinement_plan(ctx).get("passes") or [])
        if isinstance(p, dict) and p.get("pass_id")
    }

    run_meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if not isinstance(run_meta, dict):
        run_meta = {}
    from interview_mux.gap_fill_eligibility import gap_fill_was_skipped
    from interview_mux.operator_gate_view import resolve_framing_gate, resolve_g1_vo_gate

    # Resolve once — check_g1_vo runs speech QA on VO wavs; never per delivery stage.
    g1_view = resolve_g1_vo_gate(ctx, job, run_meta, missing=g1_missing)
    fr_view = resolve_framing_gate(ctx, run_meta)
    gap_skipped = gap_fill_was_skipped(ctx)
    g1_blocks_delivery = g1_view.blocks_delivery_sidebar and not gap_skipped
    analysis_complete = ctx.artifact_exists("analysis_complete.json")

    # Reconcile is expensive (schema/status per stage). Default off for GUI polls;
    # enable only for rare explicit refresh paths.
    if reconcile_done_markers:
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
        elif sid == "missing_framing":
            if gap_skipped or ctx.is_done(sid):
                s["status"] = "done"
            else:
                s["status"] = fr_view.stage_status if fr_view.open else (
                    "done" if ctx.is_done(sid) else "pending"
                )
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
            if gap_skipped:
                s["status"] = "done"
            elif not ctx.artifact_exists("understanding/gap_report.json"):
                s["status"] = "locked"
            elif g1_view.open:
                s["status"] = g1_view.stage_status
            else:
                s["status"] = "done"
        elif sid == "g1_5_preview_pickup":
            from interview_mux.gates_tbiy import (
                check_g1_5_preview_pickup_pending,
                g1_5_preview_pickup_enabled,
            )
            from interview_mux.production_profile import is_tbiy

            g1_5_pending = check_g1_5_preview_pickup_pending(ctx)
            if not g1_5_preview_pickup_enabled() or not is_tbiy(ctx):
                s["status"] = "done"
            elif not ctx.artifact_exists("master/assembly_preview.wav"):
                s["status"] = "locked"
            elif not run_meta.get("preview_listened_at"):
                s["status"] = "locked"
            elif g1_5_pending:
                s["status"] = "action_required"
            else:
                s["status"] = "done"
        elif sid in STAGE_BY_ID and STAGE_BY_ID[sid].phase == "delivery":
            if g1_blocks_delivery or not analysis_complete:
                s["status"] = "locked"
            elif profile_gate_pending:
                s["status"] = "locked"
            else:
                s["status"] = "done" if ctx.is_done(sid) else "pending"
        elif transcript_review_pending and sid in _g0_locked_analysis_stages():
            s["status"] = "locked"
        elif sid == "audio_preclean":
            from interview_mux.operator_quality import preclean_checkpoint_decision
            from interview_mux.stages.audio_preclean import preclean_was_skipped

            dismissed = preclean_checkpoint_decision(run_meta, "before_ingest") == "dismiss"
            if preclean_was_skipped(ctx) or ctx.is_done(sid) or dismissed:
                s["status"] = "done"
            else:
                s["status"] = "pending"
        else:
            s["status"] = "done" if ctx.is_done(sid) else "pending"
        if sid in pending_write_stages:
            if gate_stage == sid:
                s["status"] = "action_required"
            else:
                s["status"] = "awaiting_write_approval"
        info = STAGE_BY_ID.get(sid)
        if info:
            from interview_mux.artifact_completeness import artifact_status_for_stage
            from interview_mux.artifact_lifecycle import (
                build_outputs_view,
                split_artifact_lists,
                stage_output_mode,
            )

            committed, staged, lifecycle = split_artifact_lists(ctx, sid, info.artifacts)
            s["artifacts_committed"] = committed
            s["artifacts_staged"] = staged
            s["artifacts_lifecycle"] = lifecycle
            s["artifacts_present"] = committed
            s["artifacts_status"] = {
                a: artifact_status_for_stage(a, ctx, sid)
                for a in info.artifacts
                if a and not a.endswith("/")
            }
            s["outputs_view"] = build_outputs_view(ctx, sid)
            s["stage_output_mode"] = stage_output_mode(ctx, sid)
            from interview_mux.gap_fill_eligibility import gap_fill_mode, gap_fill_stage_visibility

            s["stage_visibility"] = gap_fill_stage_visibility(ctx, sid)
            from interview_mux.web.stages import reuse_policy_for

            s["reuse_policy"] = reuse_policy_for(sid)
            if info.refinement_pass:
                decision = refinement_decisions_by_pass_id.get(sid)
                if decision and decision.get("status") == "skip":
                    s["skip_reason"] = str(
                        decision.get("reason_code") or decision.get("rationale") or "skipped"
                    )
            if s["stage_output_mode"] == "optional_skipped":
                for a in info.artifacts:
                    if a and not a.endswith("/"):
                        s["artifacts_lifecycle"][a] = "n_a"
                        s["artifacts_status"][a] = "complete"
                for row in s.get("outputs_view") or []:
                    if isinstance(row, dict):
                        row["status"] = "complete"
                        row["phase"] = "n_a"
            elif sid == "g1_vo_pickup" and s.get("status") == "done":
                # Vacuous / satisfied G1: gap_report is enough; script may not exist yet.
                script = "understanding/interviewer_script.txt"
                if (s.get("artifacts_status") or {}).get(script) in ("pending", "partial"):
                    s.setdefault("artifacts_lifecycle", {})[script] = "n_a"
                    s["artifacts_status"][script] = "complete"
                    for row in s.get("outputs_view") or []:
                        if isinstance(row, dict) and row.get("path") == script:
                            row["status"] = "complete"
                            row["phase"] = "n_a"
            elif sid == "ideal_cuts_materialize" and s.get("status") == "done":
                # Ranking seed is optional — materialize may only write windows/boundaries.
                seed = "understanding/ideal_cuts_selection_seed.json"
                if (s.get("artifacts_status") or {}).get(seed) in ("pending", "partial"):
                    s.setdefault("artifacts_lifecycle", {})[seed] = "n_a"
                    s["artifacts_status"][seed] = "complete"
                    for row in s.get("outputs_view") or []:
                        if isinstance(row, dict) and row.get("path") == seed:
                            row["status"] = "complete"
                            row["phase"] = "n_a"
            from interview_mux.write_staging import expand_audio_output_paths

            s["audio_outputs_present"] = expand_audio_output_paths(ctx, info.audio_outputs)
            from interview_mux.ui_truth import reconcile_stage_status

            reconcile_stage_status(s)
        s["operator_phase"] = stage_operator_phase(sid)
    from interview_mux.web.job_progress import overlay_stage_list_status

    overlay_stage_list_status(ctx, stages, job)
    from interview_mux.stage_guidance import attach_guidance_to_stages

    attach_guidance_to_stages(
        ctx,
        stages,
        flow=None,
        g1_missing=g1_missing,
        transcript_review_pending=transcript_review_pending,
        profile_gate_pending=profile_gate_pending,
        profile_verified=profile_verified,
    )
    return stages


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
