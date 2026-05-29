from __future__ import annotations

import traceback
from datetime import datetime, timezone
from threading import Lock, Thread
from typing import Any

from interview_mux.config import merged_config
from interview_mux.g15_prompt_review import can_run_elevenlabs_generation
from interview_mux.gates import get_selected_flow, set_selected_flow
from interview_mux.master_qc import FlowName, verify_master
from interview_mux.operator_quality import preclean_acknowledged, stage_requires_preclean_ack
from interview_mux.pipeline import (
    ANALYSIS_ORDER,
    FLOW1_ORDER,
    FLOW2_ORDER,
    FLOW3_ORDER,
    run_analysis,
    run_flow1,
    run_flow2,
    run_flow3,
    run_single_stage,
)
from interview_mux.stages import transcript_review
from interview_mux.run_context import RunContext
from interview_mux.web.stages import EXECUTABLE_ORDER, STAGE_BY_ID


class JobRunner:
    """Background pipeline executor — one active job per run_id."""

    def __init__(self) -> None:
        self._locks: dict[str, Lock] = {}
        self._global = Lock()

    def _lock_for(self, run_id: str) -> Lock:
        with self._global:
            if run_id not in self._locks:
                self._locks[run_id] = Lock()
            return self._locks[run_id]

    def _write_job(self, ctx: RunContext, payload: dict[str, Any]) -> None:
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        ctx.write_json("gui_job.json", payload)

    def get_job(self, run_id: str) -> dict[str, Any]:
        ctx = RunContext(run_id, create=False)
        p = ctx.path("gui_job.json")
        if not p.is_file():
            return {"status": "idle", "run_id": run_id}
        data = ctx.read_json("gui_job.json")
        data["run_id"] = run_id
        return data

    def is_running(self, run_id: str) -> bool:
        return self.get_job(run_id).get("status") == "running"

    def start(
        self,
        run_id: str,
        *,
        mode: str,
        stage: str | None = None,
        flow: str | None = None,
        from_stage: str | None = None,
    ) -> dict[str, Any]:
        lock = self._lock_for(run_id)
        if not lock.acquire(blocking=False):
            return {"ok": False, "error": "A job is already running for this run."}

        def _run() -> None:
            ctx = RunContext(run_id, create=False)
            label = stage or from_stage or mode
            info = STAGE_BY_ID.get(label or "")
            try:
                msg = info.description if info else f"Running pipeline mode: {mode}"
                ctx.log(f"Starting: {info.title if info else label}", level="info", stage=label, detail=msg)
                self._write_job(
                    ctx,
                    {"status": "running", "mode": mode, "stage": stage, "flow": flow, "message": msg},
                )
                if mode == "stage" and stage == "transcript_review":
                    transcript_review.mark_transcript_review_complete(ctx)
                elif mode == "stage" and stage:
                    self._execute_single_stage(ctx, stage, from_stage)
                elif mode == "analysis":
                    ctx.log("Running full shared analysis pipeline…", level="info", stage="analysis")
                    run_analysis(ctx, from_stage=from_stage or stage)
                elif mode == "flow1":
                    set_selected_flow(ctx, "flow1")
                    ctx.log("Running Flow 1 — full master podcast pipeline…", level="info", stage="flow1")
                    run_flow1(ctx, from_stage=from_stage or stage)
                    self._run_master_qa(ctx, flow="flow1", rel_path="flow_1_master/master.wav")
                elif mode == "flow2":
                    set_selected_flow(ctx, "flow2")
                    ctx.log("Running Flow 2 — highlight reel pipeline…", level="info", stage="flow2")
                    run_flow2(ctx, from_stage=from_stage or stage)
                    self._run_master_qa(ctx, flow="flow2", rel_path="flow_2_highlights/master.wav")
                elif mode == "flow3":
                    set_selected_flow(ctx, "flow3")
                    ctx.log(
                        "Running Flow 3 — podcast show description (text only)…",
                        level="info",
                        stage="flow3",
                    )
                    run_flow3(ctx, from_stage=from_stage or stage)
                else:
                    raise ValueError(f"Unknown mode: {mode}")
                done_msg = f"Finished: {info.title if info else label}"
                ctx.log(done_msg, level="success", stage=label)
                self._write_job(
                    ctx,
                    {"status": "complete", "mode": mode, "stage": stage, "flow": flow, "message": done_msg},
                )
            except SystemExit as exc:
                gate_msg = str(exc) or "Operator gate — action required."
                ctx.log(gate_msg, level="action", stage=label, detail="Complete the gate in the GUI to continue.")
                self._write_job(
                    ctx,
                    {
                        "status": "gate",
                        "mode": mode,
                        "stage": stage,
                        "message": gate_msg,
                        "error": str(exc),
                    },
                )
            except Exception as exc:
                err_msg = str(exc)
                ctx.log(err_msg, level="error", stage=label, detail=traceback.format_exc())
                self._write_job(
                    ctx,
                    {
                        "status": "error",
                        "mode": mode,
                        "stage": stage,
                        "message": err_msg,
                        "error": err_msg,
                        "traceback": traceback.format_exc(),
                    },
                )
            finally:
                lock.release()

        Thread(target=_run, daemon=True).start()
        return {"ok": True, "run_id": run_id, "mode": mode}

    def _check_preclean_gate(self, ctx: RunContext, stage: str, *, mode: str) -> None:
        checkpoint = stage_requires_preclean_ack(stage)
        if not checkpoint:
            return
        mix_cfg = merged_config().get("mix") or {}
        if not mix_cfg.get("require_preclean_acknowledgment", True):
            return
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        if preclean_acknowledged(meta, checkpoint):
            return
        if mode.startswith("flow"):
            ctx.log(
                f"Pre-clean offer ({checkpoint}) not acknowledged — continuing full-flow run.",
                level="warning",
                stage=stage,
            )
            return
        msg = (
            f"Complete the pre-clean quality offer for checkpoint '{checkpoint}' "
            f"on the {stage} stage panel before auto-running this stage."
        )
        ctx.log(msg, level="action", stage=stage)
        self._write_job(
            ctx,
            {"status": "needs_operator", "mode": mode, "stage": stage, "message": msg},
        )
        raise RuntimeError(msg)

    def _execute_single_stage(self, ctx: RunContext, stage: str, from_stage: str | None) -> None:
        self._check_preclean_gate(ctx, stage, mode="stage")
        if from_stage and from_stage != stage:
            self.invalidate_from(ctx.run_id, from_stage)
            ctx = RunContext(ctx.run_id, create=False)
        if stage in ("elevenlabs_sfx_flow1", "elevenlabs_sfx_flow2"):
            ok, message = can_run_elevenlabs_generation(ctx)
            if not ok:
                ctx.log(message, level="warning", stage=stage)
                raise RuntimeError(message)
        run_single_stage(ctx, stage)

    def _run_master_qa(self, ctx: RunContext, *, flow: FlowName, rel_path: str) -> None:
        master = ctx.path(rel_path)
        if not master.is_file():
            raise FileNotFoundError(f"Expected master file missing after {flow}: {master}")
        result = verify_master(master, flow=flow)
        if result.ok:
            ctx.log(
                f"Master QA pass ({flow}): LUFS {result.metrics.integrated_lufs:.2f}, TP {result.metrics.true_peak_dbtp:.2f} dBTP.",
                level="success",
                stage="verify_master",
                detail="; ".join(result.checks),
            )
            return
        detail = "; ".join(result.failures)
        ctx.log(
            f"Master QA failed ({flow}): {detail}",
            level="error",
            stage="verify_master",
            detail="; ".join(result.checks),
        )
        raise RuntimeError(f"verify_master failed for {master}: {detail}")

    def invalidate_from(self, run_id: str, stage_id: str) -> None:
        ctx = RunContext(run_id, create=False)
        for order in EXECUTABLE_ORDER.values():
            if stage_id in order:
                ctx.clear_from(stage_id, order)
                break
        if stage_id in ANALYSIS_ORDER:
            ctx.clear_from(stage_id, ANALYSIS_ORDER)
        flow = get_selected_flow(ctx)
        if flow == "flow1" and stage_id in FLOW1_ORDER:
            ctx.clear_from(stage_id, FLOW1_ORDER)
        if flow == "flow2" and stage_id in FLOW2_ORDER:
            ctx.clear_from(stage_id, FLOW2_ORDER)
        if flow == "flow3" and stage_id in FLOW3_ORDER:
            ctx.clear_from(stage_id, FLOW3_ORDER)


runner = JobRunner()
