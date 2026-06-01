from __future__ import annotations

import json
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
from interview_mux.value_analysis.config import value_analysis_enabled
from interview_mux.g15_prompt_review import (
    sdp_asset_id_warnings,
    validate_prompts_payload,
)
from interview_mux.prompt_validation import validate_artifact_write
from interview_mux.file_store import read_json, write_json
from interview_mux.gates import (
    check_g1_vo,
    check_profile_gate_pending,
    check_transcript_review_pending,
    get_selected_flow,
    is_operator_profile_verified,
    set_selected_flow,
)
from interview_mux.stages import transcript_review
from interview_mux.api_providers import list_providers
from interview_mux.gui_api_consent import load_persisted_consents, save_persisted_consent
from interview_mux.gui_session import (
    clear_active_execution,
    get_active_execution,
    get_server_session,
    set_active_execution,
)
from interview_mux.nle_state import apply_segments_with_nle, load_nle, save_nle, split_segment_at
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
from interview_mux.web.runner import runner
from interview_mux.web.stages import STAGE_BY_ID, all_stages_for_run

STATIC_DIR = Path(__file__).resolve().parent / "static"

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".webm"}
SKIP_ASSET_PARTS = {"executions", ".gui"}


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
            "flow1_polish | flow2 | flow3"
        )
    )
    stage: str | None = None
    from_stage: str | None = None
    until_stage: str | None = None
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


class TranscriptChunkBody(BaseModel):
    text: str
    reviewed: bool = True


class TranscriptReviewCompleteBody(BaseModel):
    accept_unreviewed: bool = False


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


class ElevenLabsPromptApproveBody(BaseModel):
    approved_by: str | None = None


class ElevenLabsListenResultBody(BaseModel):
    asset_id: str = Field(min_length=1)
    result: str = Field(pattern="^(pass|fail)$")
    note: str | None = None


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
            "value_analysis_enabled": value_analysis_enabled(cfg),
            "api_consent_persist": (cfg.get("web") or {}).get("api_consent_persist", True),
            "journey_ui": (cfg.get("journey_ui") or {"enabled": True}),
        }

    @app.get("/api/session/api-consent")
    def get_api_consent() -> dict[str, Any]:
        persisted = load_persisted_consents()
        return {
            "providers": list_providers(),
            "grants": persisted,
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

    @app.get("/api/session")
    def get_session() -> dict[str, Any]:
        active = get_active_execution()
        session = get_server_session()
        out: dict[str, Any] = {"server": session, "active": active}
        if active and active.get("run_id"):
            rid = active["run_id"]
            if not RunContext.exists(rid):
                clear_active_execution()
                out["active"] = None
            else:
                ctx = _ctx(rid)
                out["log"] = read_log(ctx.run_dir, tail=200)
                out["run_summary"] = RunContext.summarize_run(rid)
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
    def list_runs() -> dict[str, Any]:
        runs = [RunContext.summarize_run(rid) for rid in RunContext.list_runs()]
        runs.sort(key=lambda r: r.get("execution_number") or 0, reverse=True)
        for r in runs:
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
                r["last_stage"] = next((s["title"] for s in reversed(stages) if s["status"] == "done"), None)
                log_entries = read_log(ctx.run_dir, tail=1)
                if log_entries:
                    r["last_log"] = log_entries[-1]
            except Exception:
                r["progress"] = {"done": 0, "total": 0}
        return {"runs": runs}

    @app.post("/api/runs")
    def create_run(body: CreateRunBody) -> dict[str, Any]:
        src = _resolve_repo_path(body.input_audio_path)
        if not src.is_file():
            raise HTTPException(404, f"Audio file not found: {body.input_audio_path}")
        _assert_asset_input_path(body.input_audio_path)
        if body.run_id and RunContext.exists(body.run_id):
            raise HTTPException(409, f"Execution already exists: {body.run_id}")
        ctx = RunContext(body.run_id, create=True)
        ctx.init_run_meta(body.input_audio_path)
        if body.flow_intent:
            set_flow_intent(ctx, body.flow_intent)
        ensure_analysis_workspace(ctx)
        refresh_journey_meta(ctx)
        set_active_execution(ctx.run_id)
        return {
            "run_id": ctx.run_id,
            "run_dir": str(ctx.run_dir.relative_to(ctx.root)),
            "execution_number": ctx.read_json("run_meta.json").get("execution_number"),
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
        flow = get_selected_flow(ctx)
        tr_pending = check_transcript_review_pending(ctx)
        profile_verified = is_operator_profile_verified(ctx)
        profile_gate_pending = check_profile_gate_pending(ctx)
        stages = _build_stage_list(
            ctx, flow, g1_missing, tr_pending, profile_verified, profile_gate_pending
        )
        handoff_ack = meta.get("handoff_ack") or {}
        job = runner.get_job(run_id)
        journey = build_journey_snapshot(ctx, job=job, stages=stages)
        intent = get_flow_intent(ctx)
        display_flow = flow or intent
        return {
            "run_id": run_id,
            "meta": meta,
            "handoff_ack": handoff_ack,
            "elevenlabs_generated_assets": _discover_generated_sfx_assets(ctx),
            "selected_flow": flow,
            "flow_intent": intent,
            "transcript_review_pending": tr_pending,
            "transcript_review_clear": not tr_pending,
            "profile_verified": profile_verified,
            "profile_gate_pending": profile_gate_pending,
            "g1_missing": g1_missing,
            "g1_clear": not g1_missing,
            "analysis_complete": ctx.artifact_exists("analysis_complete.json"),
            "job": job,
            "journey": journey,
            "blocking": journey.get("blocking"),
            "stages": stages,
            "log_tail": read_log(ctx.run_dir, tail=100),
            "display_flow": display_flow,
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
        try:
            save_nle(ctx, body.data)
        except ValueError as exc:
            raise HTTPException(400, {"errors": [str(exc)]}) from exc
        ctx.log("NLE timeline state saved to disk.", level="info", stage="nle")
        return {"ok": True}

    @app.post("/api/runs/{run_id}/recompute-acoustic-profile")
    def recompute_acoustic_profile(run_id: str) -> dict[str, Any]:
        from interview_mux.stages.understanding import run_source_acoustic_profile

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

    @app.patch("/api/runs/{run_id}/acoustic-profile/overrides")
    def patch_acoustic_profile_overrides(run_id: str, body: AcousticProfileOverridesBody) -> dict[str, Any]:
        from interview_mux.acoustic_profile import SAP_PATH, load_profile, save_operator_overrides

        ctx = _ctx(run_id)
        if not ctx.artifact_exists(SAP_PATH):
            raise HTTPException(404, "Source acoustic profile not found — run source_acoustic_profile first.")
        try:
            merged = save_operator_overrides(ctx, body.overrides)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, {"errors": [str(exc)]}) from exc
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

    @app.put("/api/runs/{run_id}/artifact/text")
    def put_artifact_text(run_id: str, body: ArtifactTextBody) -> dict[str, Any]:
        ctx = _ctx(run_id)
        _assert_artifact_path(body.path)
        if body.path.endswith(".json"):
            raise HTTPException(400, "Use PUT /artifact with JSON body for .json files.")
        if not _is_editable_text_path(body.path):
            raise HTTPException(400, f"Path not editable via GUI: {body.path}")
        full = ctx.path(body.path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(body.text, encoding="utf-8")
        ctx.log(f"Saved artifact {body.path} from GUI editor.", level="info", stage="artifact_editor")
        if body.invalidate_from:
            runner.invalidate_from(run_id, body.invalidate_from)
        return {"ok": True, "path": body.path}

    @app.put("/api/runs/{run_id}/artifact")
    def put_artifact(run_id: str, body: ArtifactBody) -> dict[str, Any]:
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
        write_json(ctx.path(body.path), body.data)
        stage = body.invalidate_from or "artifact_editor"
        ctx.log(f"Saved artifact {body.path} from GUI editor.", level="info", stage=stage)
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
        ctx = _ctx(run_id)
        set_selected_flow(ctx, body.flow)
        ctx.log(f"Output flow selected: {body.flow}", level="success", stage="g2_flow_select")
        refresh_journey_meta(ctx)
        return {"ok": True, "selected_flow": body.flow}

    @app.post("/api/runs/{run_id}/preclean-offer")
    def preclean_offer(run_id: str, body: PrecleanOfferBody) -> dict[str, Any]:
        ctx = _ctx(run_id)
        allowed_checkpoints = {
            "before_ingest",
            "after_g0",
            "after_profile_or_segmentation",
            "g1_vo_pickup",
            "before_sfx_spend",
            "before_flow_mix",
            "before_master_export",
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
        return {"ok": True, "changed": changed, "audio_preclean": payload}

    @app.get("/api/runs/{run_id}/elevenlabs-prompts")
    def get_elevenlabs_prompts(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        path = "sound_design/elevenlabs_prompts.json"
        if not ctx.artifact_exists(path):
            raise HTTPException(404, f"Artifact not found: {path}")
        data = ctx.read_json(path)
        rows = data.get("prompts") if isinstance(data, dict) and isinstance(data.get("prompts"), list) else []
        review = _read_prompt_review_meta(ctx)
        review_required = bool(merged_config().get("g1_5_require_prompt_approval", False))
        approved = bool(review.get("approved"))
        warnings = sdp_asset_id_warnings(ctx, rows)
        listen_results = _read_elevenlabs_listen_results(ctx)
        return {
            "path": path,
            "prompts": rows,
            "review": review,
            "review_required": review_required,
            "can_generate": (not review_required) or approved,
            "warnings": warnings,
            "listen_results": listen_results,
            "generated_assets": _discover_generated_sfx_assets(ctx),
        }

    @app.put("/api/runs/{run_id}/elevenlabs-prompts")
    def put_elevenlabs_prompts(run_id: str, body: ArtifactBody) -> dict[str, Any]:
        ctx = _ctx(run_id)
        if body.path != "sound_design/elevenlabs_prompts.json":
            raise HTTPException(400, "This endpoint only supports sound_design/elevenlabs_prompts.json")
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
            "ElevenLabs prompts edited in review panel; approval reset.",
            level="info",
            stage="elevenlabs_prompt_craft",
            detail=f"rows={len(rows)}",
        )
        if body.invalidate_from:
            runner.invalidate_from(run_id, body.invalidate_from)
        warnings = sdp_asset_id_warnings(ctx, rows)
        return {"ok": True, "path": body.path, "review": review, "warnings": warnings}

    @app.post("/api/runs/{run_id}/elevenlabs-prompts/approve")
    def approve_elevenlabs_prompts(run_id: str, body: ElevenLabsPromptApproveBody) -> dict[str, Any]:
        ctx = _ctx(run_id)
        path = "sound_design/elevenlabs_prompts.json"
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
            "elevenlabs_prompts_approved",
            level="success",
            stage="elevenlabs_prompt_craft",
            detail=str(detail),
        )
        warnings = sdp_asset_id_warnings(ctx, rows)
        for w in warnings:
            ctx.log(w, level="warning", stage="elevenlabs_prompt_craft")
        return {"ok": True, "review": review, "asset_ids": asset_ids, "warnings": warnings}

    @app.post("/api/runs/{run_id}/elevenlabs-prompts/listen-result")
    def post_elevenlabs_listen_result(run_id: str, body: ElevenLabsListenResultBody) -> dict[str, Any]:
        ctx = _ctx(run_id)
        asset_id = body.asset_id.strip()
        if not asset_id:
            raise HTTPException(400, "asset_id is required")
        entry, results = _append_elevenlabs_listen_result(
            ctx,
            asset_id=asset_id,
            result=body.result,
            note=body.note,
        )
        event = (
            "elevenlabs_post_listen_pass"
            if body.result == "pass"
            else "elevenlabs_post_listen_fail"
        )
        detail: dict[str, str] = {"asset_id": asset_id}
        if body.note:
            detail["note"] = body.note
        ctx.log(
            event,
            level="success" if body.result == "pass" else "warning",
            detail=str(detail),
        )
        return {"ok": True, "entry": entry, "elevenlabs_listen_results": results}

    @app.post("/api/runs/{run_id}/handoff-ack")
    def handoff_ack(run_id: str, body: HandoffAckBody) -> dict[str, Any]:
        ctx = _ctx(run_id)
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        ack = dict(meta.get("handoff_ack") or {})
        ack[body.stage_id] = datetime.now(timezone.utc).isoformat()
        meta["handoff_ack"] = ack
        meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        ctx.write_json("run_meta.json", meta)
        ctx.log(
            f"Handoff acknowledged for {body.stage_id} — ready for next step.",
            level="success",
            stage=body.stage_id,
        )
        return {"ok": True, "handoff_ack": ack}

    @app.post("/api/runs/{run_id}/execute")
    def execute(run_id: str, body: ExecuteBody) -> dict[str, Any]:
        _ctx(run_id)
        if runner.is_running(run_id):
            raise HTTPException(409, "A job is already running for this run.")
        set_active_execution(run_id)
        flow_modes = ("flow1", "flow2", "flow3", "flow1_until_preview", "flow1_polish")
        return runner.start(
            run_id,
            mode=body.mode,
            stage=body.stage,
            flow=body.mode if body.mode in flow_modes else None,
            from_stage=body.from_stage or body.stage,
            until_stage=body.until_stage,
            api_consents=body.api_consents,
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
        return {
            "analysis_state": state,
            "investigation_queue": queue,
            "content_brief": brief,
            "narrative_plan": narrative,
            "source_acoustic_profile": sap,
            "value_features": value_features,
            "operator_verified": (state.get("meta") or {}).get("operator_verified", False),
        }

    @app.patch("/api/runs/{run_id}/investigation-queue/{item_id}")
    def patch_investigation_item(
        run_id: str, item_id: str, body: InvestigationPatchBody
    ) -> dict[str, Any]:
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
        ctx.log(
            f"Investigation {item_id} marked {body.status}.",
            level="success",
            stage="analysis_profile",
        )
        refresh_journey_meta(ctx)
        return {"ok": True, "investigation_queue": queue}

    @app.get("/api/runs/{run_id}/audio-quality")
    def get_audio_quality(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        preclean = meta.get("audio_preclean") if isinstance(meta.get("audio_preclean"), dict) else {}
        journey = build_journey_snapshot(ctx)
        checkpoints = []
        for cp in sorted(journey.get("preclean_checkpoints") or []):
            checkpoints.append(
                {
                    "id": cp,
                    "acknowledged": preclean_acknowledged(meta, cp),
                }
            )
        return {
            "audio_preclean": preclean,
            "checkpoints": checkpoints,
            "recommended": journey.get("recommended_preclean"),
        }

    @app.post("/api/runs/{run_id}/milestones/preview-listened")
    def post_preview_listened(run_id: str) -> dict[str, Any]:
        ctx = _ctx(run_id)
        mark_preview_listened(ctx)
        return {"ok": True, "journey": build_journey_snapshot(ctx)}

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
        refresh_journey_meta(ctx)
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
    return cleared


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
    if any(part in SKIP_ASSET_PARTS for part in rel_parts):
        raise HTTPException(400, "input_audio_path cannot be under executions/ or .gui/")


def _resolve_repo_path(rel: str) -> Path:
    p = Path(rel)
    if not p.is_absolute():
        p = repo_root() / p
    return p.resolve()


def _assert_artifact_path(path: str) -> None:
    if ".." in path or path.startswith("/"):
        raise HTTPException(400, "Invalid artifact path.")


def _is_editable_text_path(path: str) -> bool:
    if path.endswith(".json"):
        return True
    if not (path.endswith(".md") or path.endswith(".txt")):
        return False
    for info in STAGE_BY_ID.values():
        if path in info.editable or path in info.artifacts:
            return True
    return False


def _build_stage_list(
    ctx: RunContext,
    flow: str | None,
    g1_missing: list[str],
    transcript_review_pending: bool,
    profile_verified: bool,
    profile_gate_pending: bool,
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
            s["audio_outputs_present"] = [a for a in info.audio_outputs if ctx.artifact_exists(a)]
        s["operator_phase"] = stage_operator_phase(sid)
    return _filter_stages_for_intent(ctx, stages, flow or get_flow_intent(ctx))


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
        preclean["provider"] = "elevenlabs"
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
    if checkpoint in {"before_flow_mix", "before_master_export"}:
        return "normalized_rebuild"
    return "full_source"


def _read_elevenlabs_listen_results(ctx: RunContext) -> list[dict[str, Any]]:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    results = meta.get("elevenlabs_listen_results")
    if not isinstance(results, list):
        return []
    return [r for r in results if isinstance(r, dict)]


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
    review = meta.get("elevenlabs_prompt_review")
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
    meta["elevenlabs_prompt_review"] = review
    ctx.write_json("run_meta.json", meta)
    return review


def _append_elevenlabs_listen_result(
    ctx: RunContext,
    *,
    asset_id: str,
    result: str,
    note: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    results = meta.get("elevenlabs_listen_results")
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
    meta["elevenlabs_listen_results"] = results
    ctx.write_json("run_meta.json", meta)
    return entry, results
