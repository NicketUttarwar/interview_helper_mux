from __future__ import annotations

import traceback
from datetime import datetime, timezone
from threading import Lock, Thread
from typing import Any

from interview_mux.api_providers import (
    PROVIDERS,
    missing_consents,
    providers_for_stages,
    stage_api_providers,
)
from interview_mux.config import merged_config
from interview_mux.gui_api_consent import load_persisted_consents, merge_consents
from interview_mux.g15_prompt_review import can_run_elevenlabs_generation
from interview_mux.gates import get_selected_flow, set_selected_flow
from interview_mux.master_qc import FlowName, verify_master
from interview_mux.operator_quality import preclean_acknowledged, stage_requires_preclean_ack
from interview_mux.nle_state import load_nle, nle_edit_categories
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
from interview_mux.journey_orchestrator import refresh_journey_meta
from interview_mux.custom_run_handoff import check_handoff_before_execute, pending_handoff_stage
from interview_mux.run_context import RunContext
from interview_mux.stage_execution_reuse import (
    StageReuseOfferPending,
    check_stage_reuse_before_execute,
    clear_stage_reuse_from,
)
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
        status = self.get_job(run_id).get("status")
        return status in ("running", "running_with_warnings")

    def _resolve_consents(self, api_consents: dict[str, bool] | None) -> dict[str, bool]:
        return merge_consents(load_persisted_consents(), api_consents)

    def _nle_apply_stages(self, ctx: RunContext, *, full_refresh: bool) -> list[str]:
        nle = load_nle(ctx)
        cats = nle_edit_categories(nle)
        if not cats["has_any"]:
            return []
        stages: list[str] = []
        if cats["structural"] or full_refresh:
            stages.append("full_master_ranking")
        if full_refresh:
            stages.extend(["transitions", "edl_narrative_audit"])
        stages.extend(["edl_flow1", "assembly_preview"])
        return stages

    def _stages_for_execute(
        self,
        ctx: RunContext,
        *,
        mode: str,
        stage: str | None,
        from_stage: str | None,
        until_stage: str | None = None,
        nle_full_refresh: bool = False,
    ) -> list[str]:
        if mode == "nle_apply":
            return self._nle_apply_stages(ctx, full_refresh=nle_full_refresh)
        if mode == "stage" and stage:
            return [stage]
        if mode in ("analysis", "analysis_until_g0"):
            order = list(ANALYSIS_ORDER)
            start = from_stage or stage
            if start and start in order:
                order = order[order.index(start) :]
            if until_stage and until_stage in order:
                order = order[: order.index(until_stage) + 1]
            elif mode == "analysis_until_g0":
                if "transcript_review_build" in order:
                    order = order[: order.index("transcript_review_build") + 1]
            pending = [s for s in order if not ctx.is_done(s)]
            return pending
        flow_orders = {
            "flow1": FLOW1_ORDER,
            "flow2": FLOW2_ORDER,
            "flow3": FLOW3_ORDER,
            "flow1_until_preview": FLOW1_ORDER,
            "flow1_polish": FLOW1_ORDER,
        }
        if mode in flow_orders:
            order = list(flow_orders[mode])
            start = from_stage or stage
            if start and start in order:
                order = order[order.index(start) :]
            if until_stage and until_stage in order:
                order = order[: order.index(until_stage) + 1]
            elif mode == "flow1_until_preview" and "assembly_preview" in order:
                order = order[: order.index("assembly_preview") + 1]
            elif mode == "flow1_polish" and "elevenlabs_prompt_craft" in order:
                order = order[order.index("elevenlabs_prompt_craft") :]
            return [s for s in order if not ctx.is_done(s)]
        return []

    def _check_api_consent(
        self,
        ctx: RunContext,
        *,
        mode: str,
        stage: str | None,
        from_stage: str | None,
        until_stage: str | None = None,
        nle_full_refresh: bool = False,
        api_consents: dict[str, bool] | None,
    ) -> str | None:
        """Return error message when required providers are not consented."""
        consents = self._resolve_consents(api_consents)
        stage_ids = self._stages_for_execute(
            ctx,
            mode=mode,
            stage=stage,
            from_stage=from_stage,
            until_stage=until_stage,
            nle_full_refresh=nle_full_refresh,
        )
        missing: list[str] = []
        for sid in stage_ids:
            for pid in missing_consents(sid, consents):
                if pid not in missing:
                    missing.append(pid)
        if not missing:
            return None
        labels = [PROVIDERS[p].label for p in missing if p in PROVIDERS]
        return (
            f"API consent required before running: {', '.join(labels or missing)}. "
            "Grant access in the GUI, then try again."
        )

    def start(
        self,
        run_id: str,
        *,
        mode: str,
        stage: str | None = None,
        flow: str | None = None,
        from_stage: str | None = None,
        until_stage: str | None = None,
        nle_full_refresh: bool = False,
        api_consents: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        lock = self._lock_for(run_id)
        if not lock.acquire(blocking=False):
            return {"ok": False, "error": "A job is already running for this run."}

        ctx_pre = RunContext(run_id, create=False)
        consent_err = self._check_api_consent(
            ctx_pre,
            mode=mode,
            stage=stage,
            from_stage=from_stage,
            until_stage=until_stage,
            nle_full_refresh=nle_full_refresh,
            api_consents=api_consents,
        )
        stage_ids = self._stages_for_execute(
            ctx_pre,
            mode=mode,
            stage=stage,
            from_stage=from_stage,
            until_stage=until_stage,
            nle_full_refresh=nle_full_refresh,
        )
        reuse_pending = check_stage_reuse_before_execute(ctx_pre, stage_ids)
        if reuse_pending:
            msg = str(reuse_pending)
            ctx_pre.log(msg, level="action", stage=reuse_pending.stage_id)
            self._write_job(
                ctx_pre,
                {
                    "status": "needs_operator",
                    "mode": mode,
                    "stage": reuse_pending.stage_id,
                    "message": msg,
                    "needs_stage_reuse": True,
                    "reuse_candidates": [c.to_dict() for c in reuse_pending.candidates],
                },
            )
            lock.release()
            return {
                "ok": False,
                "error": msg,
                "needs_operator": True,
                "needs_stage_reuse": True,
                "stage": reuse_pending.stage_id,
                "reuse_candidates": [c.to_dict() for c in reuse_pending.candidates],
            }

        handoff_err = check_handoff_before_execute(ctx_pre)
        if handoff_err:
            ctx_pre.log(handoff_err, level="action", stage=pending_handoff_stage(ctx_pre))
            self._write_job(
                ctx_pre,
                {
                    "status": "needs_operator",
                    "mode": mode,
                    "stage": stage,
                    "message": handoff_err,
                },
            )
            lock.release()
            return {
                "ok": False,
                "error": handoff_err,
                "needs_operator": True,
                "needs_handoff_review": True,
            }

        if consent_err:
            ctx_pre.log(consent_err, level="action", stage=stage or mode)
            self._write_job(
                ctx_pre,
                {
                    "status": "needs_operator",
                    "mode": mode,
                    "stage": stage,
                    "message": consent_err,
                    "missing_api_providers": [
                        p
                        for sid in self._stages_for_execute(
                            ctx_pre,
                            mode=mode,
                            stage=stage,
                            from_stage=from_stage,
                            until_stage=until_stage,
                            nle_full_refresh=nle_full_refresh,
                        )
                        for p in missing_consents(sid, self._resolve_consents(api_consents))
                    ],
                },
            )
            lock.release()
            return {
                "ok": False,
                "error": consent_err,
                "needs_api_consent": True,
                "needs_operator": True,
            }

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
                elif mode in ("analysis", "analysis_until_g0"):
                    ctx.log("Running shared analysis pipeline…", level="info", stage="analysis")
                    us = until_stage
                    if mode == "analysis_until_g0" and not us:
                        us = "transcript_review_build"
                    run_analysis(ctx, from_stage=from_stage or stage, until_stage=us)
                    refresh_journey_meta(ctx)
                elif mode in ("flow1", "flow1_until_preview", "flow1_polish"):
                    set_selected_flow(ctx, "flow1")
                    ctx.log("Running Flow 1 — full master podcast pipeline…", level="info", stage="flow1")
                    us = until_stage
                    fs = from_stage or stage
                    if mode == "flow1_until_preview" and not us:
                        us = "assembly_preview"
                    if mode == "flow1_polish" and not fs:
                        fs = "elevenlabs_prompt_craft"
                    run_flow1(
                        ctx,
                        from_stage=fs,
                        until_stage=us,
                        preclean_hook=lambda s: self._check_preclean_gate(ctx, s, mode="flow1"),
                    )
                    refresh_journey_meta(ctx)
                    if mode == "flow1" and not us:
                        self._run_master_qa(ctx, flow="flow1", rel_path="flow_1_master/master.wav")
                elif mode == "flow2":
                    set_selected_flow(ctx, "flow2")
                    ctx.log("Running Flow 2 — highlight reel pipeline…", level="info", stage="flow2")
                    run_flow2(
                        ctx,
                        from_stage=from_stage or stage,
                        until_stage=until_stage,
                        preclean_hook=lambda s: self._check_preclean_gate(ctx, s, mode="flow2"),
                    )
                    refresh_journey_meta(ctx)
                    if not until_stage:
                        self._run_master_qa(ctx, flow="flow2", rel_path="flow_2_highlights/master.wav")
                elif mode == "flow3":
                    set_selected_flow(ctx, "flow3")
                    ctx.log(
                        "Running Flow 3 — podcast show description (text only)…",
                        level="info",
                        stage="flow3",
                    )
                    run_flow3(
                        ctx,
                        from_stage=from_stage or stage,
                        until_stage=until_stage,
                        preclean_hook=lambda s: self._check_preclean_gate(ctx, s, mode="flow3"),
                    )
                    refresh_journey_meta(ctx)
                elif mode == "nle_apply":
                    set_selected_flow(ctx, "flow1")
                    stages = self._nle_apply_stages(ctx, full_refresh=nle_full_refresh)
                    if not stages:
                        raise ValueError("No NLE edits to apply.")
                    if "full_master_ranking" in stages:
                        self.invalidate_from(run_id, "full_master_ranking")
                    self.invalidate_from(run_id, "edl_flow1")
                    ctx.log(
                        f"Applying NLE edits: {', '.join(stages)}",
                        level="info",
                        stage="nle",
                    )
                    for sid in stages:
                        ctx.log(f"NLE apply — running {sid}", level="info", stage=sid)
                        run_single_stage(ctx, sid)
                    refresh_journey_meta(ctx)
                else:
                    raise ValueError(f"Unknown mode: {mode}")
                done_msg = f"Finished: {info.title if info else label}"
                ctx.log(done_msg, level="success", stage=label)
                refresh_journey_meta(ctx)
                self._write_job(
                    ctx,
                    {"status": "complete", "mode": mode, "stage": stage, "flow": flow, "message": done_msg},
                )
            except StageReuseOfferPending as exc:
                gate_msg = str(exc)
                ctx.log(gate_msg, level="action", stage=exc.stage_id)
                refresh_journey_meta(ctx)
                self._write_job(
                    ctx,
                    {
                        "status": "needs_operator",
                        "mode": mode,
                        "stage": exc.stage_id,
                        "message": gate_msg,
                        "needs_stage_reuse": True,
                        "reuse_candidates": [c.to_dict() for c in exc.candidates],
                    },
                )
            except SystemExit as exc:
                gate_msg = str(exc) or "Operator gate — action required."
                ctx.log(gate_msg, level="action", stage=label, detail="Complete the gate in the GUI to continue.")
                refresh_journey_meta(ctx)
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

    def _append_preclean_warning(
        self,
        ctx: RunContext,
        *,
        checkpoint: str,
        stage: str,
        mode: str,
    ) -> None:
        job = self.get_job(ctx.run_id)
        warnings: list[dict[str, str]] = list(job.get("preclean_warnings") or [])
        entry = {"checkpoint": checkpoint, "stage": stage}
        if entry not in warnings:
            warnings.append(entry)
        payload = {
            k: v
            for k, v in job.items()
            if k not in ("run_id", "updated_at", "preclean_warnings", "status")
        }
        payload.update(
            {
                "status": "running_with_warnings",
                "preclean_warnings": warnings,
                "mode": mode,
            }
        )
        self._write_job(ctx, payload)

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
            self._append_preclean_warning(ctx, checkpoint=checkpoint, stage=stage, mode=mode)
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
        orders: list[list[str]] = []
        for order in EXECUTABLE_ORDER.values():
            if stage_id in order:
                ctx.clear_from(stage_id, order)
                orders.append(order)
                break
        if stage_id in ANALYSIS_ORDER:
            ctx.clear_from(stage_id, ANALYSIS_ORDER)
            orders.append(ANALYSIS_ORDER)
        flow = get_selected_flow(ctx)
        if flow == "flow1" and stage_id in FLOW1_ORDER:
            ctx.clear_from(stage_id, FLOW1_ORDER)
            orders.append(FLOW1_ORDER)
        if flow == "flow2" and stage_id in FLOW2_ORDER:
            ctx.clear_from(stage_id, FLOW2_ORDER)
            orders.append(FLOW2_ORDER)
        if flow == "flow3" and stage_id in FLOW3_ORDER:
            ctx.clear_from(stage_id, FLOW3_ORDER)
            orders.append(FLOW3_ORDER)
        seen: set[tuple[str, ...]] = set()
        for order in orders:
            key = tuple(order)
            if key in seen:
                continue
            seen.add(key)
            clear_stage_reuse_from(ctx, stage_id, order)


runner = JobRunner()
