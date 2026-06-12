from __future__ import annotations

import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import Lock, Thread
from typing import Any, Iterator

from interview_mux.api_providers import (
    PROVIDERS,
    all_provider_grants,
    missing_consents,
    providers_for_stages,
    stage_api_providers,
)
from interview_mux.gui_api_consent import load_persisted_consents, merge_consents
from interview_mux.g15_prompt_review import can_run_elevenlabs_generation
from interview_mux.gates import get_selected_flow, set_selected_flow
from interview_mux.master_qc import FlowName, verify_master
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
from interview_mux.run_lock import RunDirectoryLock
from interview_mux.stage_execution_reuse import (
    StageReuseOfferPending,
    check_stage_reuse_before_execute,
    clear_stage_reuse_from,
)
from interview_mux.write_staging import (
    WriteApprovalPending,
    check_write_approval_before_execute,
)
from interview_mux.web.job_progress import clear_job_progress, register_job_progress
from interview_mux.web.stages import EXECUTABLE_ORDER, STAGE_BY_ID


class RunBusyError(RuntimeError):
    def __init__(self, run_id: str) -> None:
        super().__init__(f"A job is already running for run {run_id}")
        self.run_id = run_id


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

    def _stage_title(self, stage_id: str | None) -> str:
        if not stage_id:
            return "pipeline"
        info = STAGE_BY_ID.get(stage_id)
        return info.title if info else stage_id.replace("_", " ")

    def _update_running_stage(
        self,
        ctx: RunContext,
        job_base: dict[str, Any],
        stage_id: str,
        *,
        index: int,
        total: int,
        stages_planned: list[str],
    ) -> None:
        title = self._stage_title(stage_id)
        self._write_job(
            ctx,
            {
                **job_base,
                "status": "running",
                "stage": stage_id,
                "current_stage": stage_id,
                "stage_index": index,
                "stage_total": total,
                "stages_planned": stages_planned,
                "message": f"Running {title}… ({index}/{total})",
            },
        )

    def _write_job(self, ctx: RunContext, payload: dict[str, Any]) -> None:
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        ctx.write_json("gui_job.json", payload)

    def lock_held(self, run_id: str) -> bool:
        """True when an in-process background job holds the run lock."""
        lock = self._lock_for(run_id)
        if lock.acquire(blocking=False):
            lock.release()
            return False
        return True

    def get_job(self, run_id: str) -> dict[str, Any]:
        from interview_mux.gui_job_reconcile import reconcile_job_if_stale

        return reconcile_job_if_stale(run_id, lock_held=self.lock_held(run_id))

    def is_running(self, run_id: str) -> bool:
        """True only when this process is executing a background job for the run."""
        return self.lock_held(run_id)

    @contextmanager
    def run_guard(self, run_id: str) -> Iterator[None]:
        """Serialize mutating API calls with background execute for one run."""
        lock = self._lock_for(run_id)
        dir_lock = RunDirectoryLock(run_id)
        if not lock.acquire(blocking=False):
            raise RunBusyError(run_id)
        if not dir_lock.acquire(blocking=False):
            lock.release()
            raise RunBusyError(run_id)
        try:
            yield
        finally:
            dir_lock.release()
            lock.release()

    def _resolve_consents(self, api_consents: dict[str, bool] | None) -> dict[str, bool]:
        return merge_consents(
            all_provider_grants(),
            load_persisted_consents(),
            api_consents,
        )

    def _nle_apply_stages(
        self,
        ctx: RunContext,
        *,
        full_refresh: bool,
        apply_mode: str = "structural",
    ) -> list[str]:
        nle = load_nle(ctx)
        cats = nle_edit_categories(nle)
        if not cats["has_any"]:
            return []
        if apply_mode == "trim_only":
            return ["edl_flow1", "assembly_preview"]
        stages: list[str] = []
        if cats["structural"] or full_refresh:
            stages.append("full_master_ranking")
        if full_refresh or apply_mode == "full_refresh":
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
        nle_apply_mode: str = "structural",
    ) -> list[str]:
        if mode == "nle_apply":
            mode_arg = "full_refresh" if nle_full_refresh else nle_apply_mode
            return self._nle_apply_stages(
                ctx,
                full_refresh=nle_full_refresh or nle_apply_mode == "full_refresh",
                apply_mode=mode_arg,
            )
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
        nle_apply_mode: str = "structural",
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
            nle_apply_mode=nle_apply_mode,
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
        nle_apply_mode: str = "structural",
        api_consents: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        lock = self._lock_for(run_id)
        dir_lock = RunDirectoryLock(run_id)
        if not lock.acquire(blocking=False):
            return {"ok": False, "error": "A job is already running for this run."}
        if not dir_lock.acquire(blocking=False):
            lock.release()
            return {"ok": False, "error": "A job is already running for this run."}

        ctx_pre = RunContext(run_id, create=False)
        consent_err = self._check_api_consent(
            ctx_pre,
            mode=mode,
            stage=stage,
            from_stage=from_stage,
            until_stage=until_stage,
            nle_full_refresh=nle_full_refresh,
            nle_apply_mode=nle_apply_mode,
            api_consents=api_consents,
        )
        stage_ids = self._stages_for_execute(
            ctx_pre,
            mode=mode,
            stage=stage,
            from_stage=from_stage,
            until_stage=until_stage,
            nle_full_refresh=nle_full_refresh,
            nle_apply_mode=nle_apply_mode,
        )
        write_pending = check_write_approval_before_execute(ctx_pre)
        if write_pending:
            msg = str(write_pending)
            ctx_pre.log(msg, level="action", stage=write_pending.stage_id)
            self._write_job(
                ctx_pre,
                {
                    "status": "awaiting_write_approval",
                    "mode": mode,
                    "stage": write_pending.stage_id,
                    "message": msg,
                    "pending_write_stage": write_pending.stage_id,
                    "pending_write_paths": write_pending.paths,
                },
            )
            dir_lock.release()
            lock.release()
            return {
                "ok": False,
                "error": msg,
                "needs_operator": True,
                "awaiting_write_approval": True,
                "pending_write_stage": write_pending.stage_id,
                "pending_write_paths": write_pending.paths,
            }

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
            dir_lock.release()
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
            dir_lock.release()
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
                            nle_apply_mode=nle_apply_mode,
                        )
                        for p in missing_consents(sid, self._resolve_consents(api_consents))
                    ],
                },
            )
            dir_lock.release()
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
            stage_ids = self._stages_for_execute(
                ctx,
                mode=mode,
                stage=stage,
                from_stage=from_stage,
                until_stage=until_stage,
                nle_full_refresh=nle_full_refresh,
                nle_apply_mode=nle_apply_mode,
            )
            job_base: dict[str, Any] = {
                "mode": mode,
                "stage": stage,
                "flow": flow,
                "from_stage": from_stage or stage,
                "until_stage": until_stage,
                "nle_full_refresh": nle_full_refresh,
                "nle_apply_mode": nle_apply_mode,
            }
            total = len(stage_ids) or 1
            if stage_ids:
                job_base["stages_planned"] = stage_ids
                job_base["stage_total"] = total
                job_base["stage_index"] = 0

            def _progress_hook(
                sid: str,
                index: int,
                t: int,
                planned: list[str],
            ) -> None:
                self._update_running_stage(
                    ctx,
                    job_base,
                    sid,
                    index=index,
                    total=t,
                    stages_planned=planned,
                )

            register_job_progress(run_id, _progress_hook)
            try:
                msg = info.description if info else f"Running pipeline mode: {mode}"
                ctx.log(f"Starting: {info.title if info else label}", level="info", stage=label, detail=msg)
                first_stage = stage_ids[0] if stage_ids else (stage or label)
                self._update_running_stage(
                    ctx,
                    job_base,
                    str(first_stage),
                    index=1 if stage_ids else 0,
                    total=total,
                    stages_planned=stage_ids,
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
                    )
                    refresh_journey_meta(ctx)
                elif mode == "nle_apply":
                    set_selected_flow(ctx, "flow1")
                    mode_arg = "full_refresh" if nle_full_refresh else nle_apply_mode
                    stages = self._nle_apply_stages(
                        ctx,
                        full_refresh=nle_full_refresh or nle_apply_mode == "full_refresh",
                        apply_mode=mode_arg,
                    )
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
                    for i, sid in enumerate(stages, start=1):
                        self._update_running_stage(
                            ctx,
                            job_base,
                            sid,
                            index=i,
                            total=len(stages),
                            stages_planned=stages,
                        )
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
            except WriteApprovalPending as exc:
                gate_msg = str(exc)
                ctx.log(gate_msg, level="action", stage=exc.stage_id)
                refresh_journey_meta(ctx)
                self._write_job(
                    ctx,
                    {
                        "status": "awaiting_write_approval",
                        "mode": mode,
                        "stage": exc.stage_id,
                        "message": gate_msg,
                        "pending_write_stage": exc.stage_id,
                        "pending_write_paths": exc.paths,
                    },
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
                clear_job_progress(run_id)
                dir_lock.release()
                lock.release()

        Thread(target=_run, daemon=True).start()
        return {"ok": True, "run_id": run_id, "mode": mode}

    def _execute_single_stage(self, ctx: RunContext, stage: str, from_stage: str | None) -> None:
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
