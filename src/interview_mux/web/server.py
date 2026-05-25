from __future__ import annotations

import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
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
from interview_mux.file_store import read_json, write_json
from interview_mux.gates import check_g1_vo, check_transcript_review_pending, get_selected_flow, set_selected_flow
from interview_mux.stages import transcript_review
from interview_mux.gui_session import get_active_execution, get_server_session, set_active_execution
from interview_mux.nle_state import apply_segments_with_nle, load_nle, save_nle, split_segment_at
from interview_mux.pipeline import ANALYSIS_ORDER, FLOW1_ORDER, FLOW2_ORDER
from interview_mux.run_context import RunContext
from interview_mux.session_log import append_log, read_log
from interview_mux.web.runner import runner
from interview_mux.web.stages import STAGE_BY_ID, all_stages_for_run

STATIC_DIR = Path(__file__).resolve().parent / "static"

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".webm"}
SKIP_ASSET_PARTS = {"executions", ".gui"}


class CreateRunBody(BaseModel):
    input_audio_path: str
    run_id: str | None = None


class FlowBody(BaseModel):
    flow: str = Field(pattern="^(flow1|flow2)$")


class ExecuteBody(BaseModel):
    mode: str = Field(description="stage | analysis | flow1 | flow2")
    stage: str | None = None
    from_stage: str | None = None


class ArtifactBody(BaseModel):
    path: str
    data: Any
    invalidate_from: str | None = None


class ResetBody(BaseModel):
    from_stage: str | None = None
    new_input_audio_path: str | None = None


class ActiveBody(BaseModel):
    run_id: str
    selected_stage_id: str | None = None


class NleBody(BaseModel):
    data: dict[str, Any]


class NleSegmentBody(BaseModel):
    segment_id: str
    patch: dict[str, Any]


class SplitBody(BaseModel):
    segment_id: str
    at_ms: int


class LogBody(BaseModel):
    message: str
    level: str = "info"
    stage: str | None = None


class TranscriptChunkBody(BaseModel):
    text: str
    reviewed: bool = True


class TranscriptReviewCompleteBody(BaseModel):
    accept_unreviewed: bool = False


class AnalysisProfileBody(BaseModel):
    data: dict[str, Any]
    operator_verified: bool | None = None
    invalidate_from: str | None = None


def create_app() -> FastAPI:
    app = FastAPI(title="Interview Helper Mux", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
        }

    @app.get("/api/session")
    def get_session() -> dict[str, Any]:
        active = get_active_execution()
        session = get_server_session()
        out: dict[str, Any] = {"server": session, "active": active}
        if active and active.get("run_id"):
            rid = active["run_id"]
            try:
                ctx = _ctx(rid)
                out["log"] = read_log(ctx.run_dir, tail=200)
                out["run_summary"] = RunContext.summarize_run(rid)
            except HTTPException:
                out["active"] = None
        return out

    @app.put("/api/session/active")
    def put_active(body: ActiveBody) -> dict[str, Any]:
        _ctx(body.run_id)
        return set_active_execution(body.run_id, selected_stage_id=body.selected_stage_id)

    @app.get("/api/assets")
    def list_assets(recursive: bool = True) -> dict[str, Any]:
        cfg = merged_config()
        assets = repo_root() / cfg.get("assets_root", "ASSETS")
        assets.mkdir(parents=True, exist_ok=True)
        files: list[dict[str, Any]] = []
        iterator = assets.rglob("*") if recursive else assets.iterdir()
        for p in sorted(iterator):
            if not p.is_file():
                continue
            rel_parts = p.relative_to(assets).parts
            if rel_parts and rel_parts[0] in SKIP_ASSET_PARTS:
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
    def list_runs() -> dict[str, Any]:
        runs = [RunContext.summarize_run(rid) for rid in RunContext.list_runs()]
        runs.sort(key=lambda r: r.get("execution_number") or 0, reverse=True)
        for r in runs:
            try:
                ctx = RunContext(r["run_id"])
                flow = get_selected_flow(ctx)
                stages = _build_stage_list(ctx, flow, check_g1_vo(ctx), check_transcript_review_pending(ctx))
                done = sum(1 for s in stages if s["status"] == "done")
                r["progress"] = {"done": done, "total": len(stages)}
                r["last_stage"] = next((s["title"] for s in reversed(stages) if s["status"] == "done"), None)
            except Exception:
                r["progress"] = {"done": 0, "total": 0}
        return {"runs": runs}

    @app.post("/api/runs")
    def create_run(body: CreateRunBody) -> dict[str, Any]:
        src = _resolve_repo_path(body.input_audio_path)
        if not src.is_file():
            raise HTTPException(404, f"Audio file not found: {body.input_audio_path}")
        ctx = RunContext(body.run_id)
        ctx.init_run_meta(body.input_audio_path)
        ensure_analysis_workspace(ctx)
        set_active_execution(ctx.run_id)
        return {
            "run_id": ctx.run_id,
            "run_dir": str(ctx.run_dir.relative_to(ctx.root)),
            "execution_number": ctx.read_json("run_meta.json").get("execution_number"),
        }

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        g1_missing = check_g1_vo(ctx)
        flow = get_selected_flow(ctx)
        tr_pending = check_transcript_review_pending(ctx)
        stages = _build_stage_list(ctx, flow, g1_missing, tr_pending)
        return {
            "run_id": run_id,
            "meta": meta,
            "selected_flow": flow,
            "transcript_review_pending": tr_pending,
            "transcript_review_clear": not tr_pending,
            "g1_missing": g1_missing,
            "g1_clear": not g1_missing,
            "analysis_complete": ctx.artifact_exists("analysis_complete.json"),
            "job": runner.get_job(run_id),
            "stages": stages,
            "log_tail": read_log(ctx.run_dir, tail=100),
        }

    @app.get("/api/runs/{run_id}/log")
    def get_log(run_id: str, tail: int = 200) -> dict[str, Any]:
        ctx = _ctx(run_id)
        return {"entries": read_log(ctx.run_dir, tail=tail)}

    @app.post("/api/runs/{run_id}/log")
    def post_log(run_id: str, body: LogBody) -> dict[str, Any]:
        ctx = _ctx(run_id)
        entry = append_log(ctx.run_dir, body.message, level=body.level, stage=body.stage)
        return {"ok": True, "entry": entry}

    @app.get("/api/runs/{run_id}/timeline")
    def get_timeline(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        nle = load_nle(ctx)
        segments: list[dict[str, Any]] = []
        duration_ms = 0
        if ctx.artifact_exists("segments/manifest.json"):
            manifest = ctx.read_json("segments/manifest.json")
            raw = manifest.get("segments") or []
            segments = apply_segments_with_nle(raw, nle)
            if segments:
                duration_ms = max(s.get("end_ms", 0) for s in segments)
        vo_lines: list[dict[str, Any]] = []
        if ctx.artifact_exists("understanding/gap_report.json"):
            report = ctx.read_json("understanding/gap_report.json")
            pickup = ctx.path("vo_pickup")
            for line in report.get("interviewer_lines") or []:
                lid = line.get("line_id", "")
                seg = line.get("targets_segment_id", "")
                candidates = [pickup / f"{lid}.wav", pickup / f"{seg}.wav"]
                recorded = next((p.name for p in candidates if p.is_file()), None)
                vo_lines.append({**line, "recorded_file": recorded})
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
        ctx = _ctx(run_id)
        save_nle(ctx, body.data)
        ctx.log("NLE timeline state saved to disk.", level="info", stage="nle")
        return {"ok": True}

    @app.patch("/api/runs/{run_id}/nle/segment")
    def patch_nle_segment(run_id: str, body: NleSegmentBody) -> dict[str, Any]:
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
        ctx = _ctx(run_id)
        nle = split_segment_at(ctx, body.segment_id, body.at_ms)
        ctx.log(f"Split segment {body.segment_id} at {body.at_ms}ms.", level="info", stage="nle")
        return {"ok": True, "nle": nle}

    @app.get("/api/runs/{run_id}/artifact")
    def get_artifact(run_id: str, path: str) -> Any:
        ctx = _ctx(run_id)
        _assert_artifact_path(path)
        full = ctx.path(path)
        if not full.is_file():
            raise HTTPException(404, f"Artifact not found: {path}")
        if path.endswith(".json"):
            return read_json(full)
        return {"path": path, "text": full.read_text(encoding="utf-8")}

    @app.put("/api/runs/{run_id}/artifact")
    def put_artifact(run_id: str, body: ArtifactBody) -> dict[str, Any]:
        ctx = _ctx(run_id)
        _assert_artifact_path(body.path)
        if not body.path.endswith(".json"):
            raise HTTPException(400, "Only JSON artifacts can be edited via this endpoint.")
        write_json(ctx.path(body.path), body.data)
        ctx.log(f"Saved artifact {body.path} from GUI editor.", level="info", stage=body.invalidate_from)
        if body.invalidate_from:
            runner.invalidate_from(run_id, body.invalidate_from)
        return {"ok": True, "path": body.path}

    @app.post("/api/runs/{run_id}/flow")
    def set_flow(run_id: str, body: FlowBody) -> dict[str, Any]:
        ctx = _ctx(run_id)
        set_selected_flow(ctx, body.flow)
        ctx.log(f"Output flow selected: {body.flow}", level="success", stage="g2_flow_select")
        return {"ok": True, "selected_flow": body.flow}

    @app.post("/api/runs/{run_id}/execute")
    def execute(run_id: str, body: ExecuteBody) -> dict[str, Any]:
        _ctx(run_id)
        if runner.is_running(run_id):
            raise HTTPException(409, "A job is already running for this run.")
        set_active_execution(run_id)
        return runner.start(
            run_id,
            mode=body.mode,
            stage=body.stage,
            flow=body.mode if body.mode in ("flow1", "flow2") else None,
            from_stage=body.from_stage or body.stage,
        )

    @app.get("/api/runs/{run_id}/job")
    def get_job(run_id: str) -> dict[str, Any]:
        return runner.get_job(run_id)

    @app.get("/api/runs/{run_id}/transcript-review")
    def get_transcript_review(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        return transcript_review.get_review_state(ctx)

    @app.put("/api/runs/{run_id}/transcript-review/{chunk_id}")
    def put_transcript_chunk(run_id: str, chunk_id: str, body: TranscriptChunkBody) -> dict[str, Any]:
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
        ctx = _ctx(run_id)
        ensure_analysis_workspace(ctx)
        save_analysis_state(ctx, body.data, stage="operator_gui")
        if body.operator_verified is not None:
            mark_operator_verified(ctx, body.operator_verified)
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
        ctx = _ctx(run_id)
        ensure_analysis_workspace(ctx)
        mark_operator_verified(ctx, True)
        ctx.log("Interview profile marked verified.", level="success", stage="analysis_profile")
        return {"ok": True, "operator_verified": True}

    @app.post("/api/runs/{run_id}/transcript-review/complete")
    def complete_transcript_review(run_id: str, body: TranscriptReviewCompleteBody) -> dict[str, Any]:
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
        return {"ok": True, "transcript_review_clear": True}

    @app.post("/api/runs/{run_id}/vo/{line_id}")
    async def upload_vo(run_id: str, line_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
        ctx = _ctx(run_id)
        pickup = ctx.path("vo_pickup")
        pickup.mkdir(parents=True, exist_ok=True)
        dest = pickup / f"{line_id}.wav"
        content = await file.read()
        dest.write_bytes(content)
        ctx.log(f"VO pickup saved: vo_pickup/{line_id}.wav", level="success", stage="g1_vo_pickup")
        return {"ok": True, "path": f"vo_pickup/{dest.name}", "g1_missing": check_g1_vo(ctx)}

    @app.post("/api/runs/{run_id}/reset")
    def reset_run(run_id: str, body: ResetBody) -> dict[str, Any]:
        ctx = _ctx(run_id)
        if body.new_input_audio_path:
            src = _resolve_repo_path(body.new_input_audio_path)
            if not src.is_file():
                raise HTTPException(404, f"Audio file not found: {body.new_input_audio_path}")
            ctx.init_run_meta(body.new_input_audio_path)
            for order in (ANALYSIS_ORDER, FLOW1_ORDER, FLOW2_ORDER):
                if order:
                    ctx.clear_from(order[0], order)
        elif body.from_stage:
            runner.invalidate_from(run_id, body.from_stage)
        else:
            raise HTTPException(400, "Provide from_stage or new_input_audio_path.")
        return {"ok": True}

    @app.get("/api/runs/{run_id}/audio")
    def serve_audio(run_id: str, path: str) -> FileResponse:
        ctx = _ctx(run_id)
        _assert_artifact_path(path)
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

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app


def _ctx(run_id: str) -> RunContext:
    ctx = RunContext(run_id)
    if not ctx.run_dir.is_dir():
        raise HTTPException(404, f"Run not found: {run_id}")
    return ctx


def _resolve_repo_path(rel: str) -> Path:
    p = Path(rel)
    if not p.is_absolute():
        p = repo_root() / p
    return p.resolve()


def _assert_artifact_path(path: str) -> None:
    if ".." in path or path.startswith("/"):
        raise HTTPException(400, "Invalid artifact path.")


def _build_stage_list(
    ctx: RunContext,
    flow: str | None,
    g1_missing: list[str],
    transcript_review_pending: bool,
) -> list[dict[str, Any]]:
    stages = all_stages_for_run(flow)
    for s in stages:
        sid = s["id"]
        if sid == "transcript_review":
            if not ctx.artifact_exists("transcript/review_queue.json"):
                s["status"] = "locked"
            elif transcript_review_pending:
                s["status"] = "action_required"
            else:
                s["status"] = "done"
        elif sid == "analysis_profile":
            ensure_analysis_workspace(ctx)
            verified = (ctx.read_json(ANALYSIS_STATE_PATH).get("meta") or {}).get(
                "operator_verified"
            )
            s["status"] = "done" if verified else "action_required"
        elif sid == "g1_vo_pickup":
            if not ctx.artifact_exists("understanding/gap_report.json"):
                s["status"] = "locked"
            elif g1_missing:
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
            else:
                s["status"] = "locked"
        elif sid in STAGE_BY_ID and STAGE_BY_ID[sid].phase in ("flow1", "flow2"):
            if not flow:
                s["status"] = "locked"
            else:
                s["status"] = "done" if ctx.is_done(sid) else "pending"
        elif transcript_review_pending and sid in (
            "speaker_roles",
            "content_context",
            "boundary_detection",
            "segment_classification",
            "missing_framing",
            "optimal_questions",
        ):
            s["status"] = "locked"
        else:
            s["status"] = "done" if ctx.is_done(sid) else "pending"
        info = STAGE_BY_ID.get(sid)
        if info:
            s["artifacts_present"] = [a for a in info.artifacts if ctx.artifact_exists(a)]
    return stages
