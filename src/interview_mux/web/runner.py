from __future__ import annotations

import subprocess
import sys
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
import threading
from threading import Lock, Thread
from typing import Any, Iterator

from interview_mux.api_providers import (
    PROVIDERS,
    all_provider_grants,
    missing_consents,
    missing_secrets,
    providers_for_stages,
    stage_api_providers,
)
from interview_mux.gui_api_consent import load_persisted_consents, merge_consents
from interview_mux.sfx_prompt_review import can_run_sfx_generation
from interview_mux.master_qc import FlowName, verify_master
from interview_mux.nle_state import load_nle, nle_edit_categories
from interview_mux.pipeline import (
    ANALYSIS_ORDER,
    DELIVERY_ORDER,
    run_analysis,
    run_delivery,
    run_single_stage,
)
from interview_mux.stages import transcript_review
from interview_mux.run_context import RunContext
from interview_mux.run_lock import RunDirectoryLock
from interview_mux.stage_execution_reuse import (
    StageReuseOfferPending,
    check_stage_reuse_before_execute,
    clear_stage_reuse_from,
)
from interview_mux.stage_input_checks import StageInputError
from interview_mux.web.job_progress import clear_job_progress, register_job_progress
from interview_mux.web.stages import EXECUTABLE_ORDER, STAGE_BY_ID

SUBPROCESS_STAGES = frozenset({"audio_preclean"})


def refresh_journey_meta(ctx: RunContext) -> None:
    from interview_mux.journey_state import compute_milestones, compute_operator_phase

    milestones = compute_milestones(ctx)
    phase = compute_operator_phase(ctx, milestones)

    def patch(meta: dict[str, Any]) -> None:
        meta["journey_milestones"] = milestones
        meta["operator_phase"] = phase

    ctx.mutate_run_meta(patch)


class RunBusyError(RuntimeError):
    def __init__(self, run_id: str, *, detail: str | None = None) -> None:
        msg = detail or (
            f"Run {run_id} is busy — a pipeline step or save is already in progress. "
            "Watch Activity for progress, then retry."
        )
        super().__init__(msg)
        self.run_id = run_id


class JobRunner:
    """Background pipeline executor — one active job per run_id."""

    def __init__(self) -> None:
        self._locks: dict[str, Lock] = {}
        self._global = Lock()
        self._lock_holder_tid: dict[str, int] = {}
        self._starting_runs: set[str] = set()

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
        from interview_mux.web.job_progress import persist_running_stage_progress

        written = persist_running_stage_progress(
            ctx.run_id,
            stage_id,
            index=index,
            total=total,
            stages_planned=stages_planned,
            job_base=job_base,
            ctx=ctx,
        )
        if written is None:
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

    def clear_operator_pause(
        self,
        ctx: RunContext,
        stage_id: str,
        *,
        message: str,
        level: str = "success",
    ) -> None:
        """Clear gui_job pause states (write approval, reuse offer) after operator action."""
        ctx.log(message, level=level, stage=stage_id)
        self._write_job(
            ctx,
            {
                "status": "complete",
                "stage": stage_id,
                "current_stage": None,
                "message": message,
                "needs_stage_reuse": False,
            },
        )

    def _record_lock_holder(self, run_id: str) -> None:
        self._lock_holder_tid[run_id] = threading.get_ident()

    def _clear_lock_holder(self, run_id: str) -> None:
        self._lock_holder_tid.pop(run_id, None)

    def _holder_thread_alive(self, run_id: str) -> bool:
        tid = self._lock_holder_tid.get(run_id)
        if tid is None:
            return False
        return any(t.ident == tid and t.is_alive() for t in threading.enumerate())

    def _recover_orphaned_thread_lock(self, run_id: str) -> bool:
        """Replace in-process run lock when holder thread died but lock was never released."""
        lock = self._lock_for(run_id)
        if lock.acquire(blocking=False):
            lock.release()
            self._clear_lock_holder(run_id)
            return False
        if self._holder_thread_alive(run_id):
            return False
        from interview_mux.gui_job_reconcile import RUNNING_STATUSES, reconcile_stale_job

        if RunContext.exists(run_id):
            try:
                ctx = RunContext(run_id, create=False)
                job = ctx.read_json("gui_job.json")
                status = job.get("status")
                if status in RUNNING_STATUSES:
                    if run_id in self._lock_holder_tid and self._holder_thread_alive(run_id):
                        return False
            except OSError:
                pass
        with self._global:
            self._locks[run_id] = Lock()
            self._lock_holder_tid.pop(run_id, None)
        return True

    def _acquire_thread_lock(self, run_id: str) -> bool:
        self._recover_orphaned_thread_lock(run_id)
        lock = self._lock_for(run_id)
        if lock.acquire(blocking=False):
            self._record_lock_holder(run_id)
            return True
        if self._recover_orphaned_thread_lock(run_id):
            lock = self._lock_for(run_id)
            if lock.acquire(blocking=False):
                self._record_lock_holder(run_id)
                return True
        return False

    def _release_thread_lock(self, run_id: str, lock: Lock) -> None:
        try:
            holder = self._lock_holder_tid.get(run_id)
            if holder is not None and holder == threading.get_ident() and lock.locked():
                lock.release()
        finally:
            self._clear_lock_holder(run_id)

    def _caller_holds_run_lock(self, run_id: str) -> bool:
        return self._lock_holder_tid.get(run_id) == threading.get_ident()

    def _reserve_pipeline_start(self, run_id: str) -> bool:
        """Mark a run as starting so execute cannot double-spawn before the worker acquires."""
        if not self._caller_holds_run_lock(run_id) and self.lock_held(run_id):
            return False
        with self._global:
            if run_id in self._starting_runs:
                return False
            self._starting_runs.add(run_id)
            return True

    def _clear_pipeline_start_reservation(self, run_id: str) -> None:
        with self._global:
            self._starting_runs.discard(run_id)

    def _release_run_locks(self, run_id: str, dir_lock: RunDirectoryLock, lock: Lock) -> None:
        try:
            dir_lock.release()
        except Exception:
            pass
        self._release_thread_lock(run_id, lock)

    def lock_held(self, run_id: str) -> bool:
        """True when an in-process background job holds the run lock."""
        lock = self._lock_for(run_id)
        if lock.acquire(blocking=False):
            lock.release()
            return False
        return True

    def get_job(self, run_id: str) -> dict[str, Any]:
        from interview_mux.gui_job_reconcile import reconcile_job_if_stale
        from interview_mux.web.job_progress import attach_live_stage_progress

        job = reconcile_job_if_stale(run_id, lock_held=self.lock_held(run_id))
        return attach_live_stage_progress(run_id, job)

    def is_running(self, run_id: str) -> bool:
        """True only when this process is executing a background job for the run."""
        from interview_mux.process_cleanup import worker_pid_alive

        with self._global:
            if run_id in self._starting_runs:
                return True
        if self._caller_holds_run_lock(run_id):
            return False
        if self.lock_held(run_id):
            return True
        try:
            job = self._read_gui_job(run_id)
            if worker_pid_alive(job.get("worker_pid")):
                return True
        except OSError:
            pass
        return False

    def _read_gui_job(self, run_id: str) -> dict[str, Any]:
        if not RunContext.exists(run_id):
            return {}
        try:
            ctx = RunContext(run_id, create=False)
            if ctx.artifact_exists("gui_job.json"):
                job = ctx.read_json("gui_job.json")
                return job if isinstance(job, dict) else {}
        except OSError:
            pass
        return {}

    def _is_operator_pause_job(self, job: dict[str, Any]) -> bool:
        status = job.get("status")
        return bool(
            job.get("needs_stage_reuse")
            or status
            in (
                "needs_operator",
                "gate",
                "interrupted",
            )
        )

    def _is_legitimate_pipeline_busy(self, run_id: str) -> bool:
        """True when a live worker is executing a stage (not an operator pause)."""
        from interview_mux.gui_job_reconcile import RUNNING_STATUSES
        from interview_mux.process_cleanup import worker_pid_alive

        job = self._read_gui_job(run_id)
        if worker_pid_alive(job.get("worker_pid")):
            return True
        if not self._holder_thread_alive(run_id):
            return False
        status = job.get("status")
        if status not in RUNNING_STATUSES and status != "stalled":
            return False
        return True

    def _prepare_for_operator_action(self, run_id: str) -> None:
        from interview_mux.gui_job_reconcile import reconcile_stale_job

        if not self.lock_held(run_id):
            reconcile_stale_job(run_id)
        else:
            self._recover_orphaned_thread_lock(run_id)

    def _acquire_run_locks(
        self,
        run_id: str,
        *,
        operator_priority: bool = False,
    ) -> tuple[Lock, RunDirectoryLock] | None:
        """Acquire thread + directory locks; GUI operator actions may wait or recover stale locks."""
        import time

        deadline = time.monotonic() + (3.0 if operator_priority else 0.0)
        while True:
            self._prepare_for_operator_action(run_id)
            lock = self._lock_for(run_id)
            dir_lock = RunDirectoryLock(run_id)
            if self._acquire_thread_lock(run_id):
                if self._try_acquire_dir_lock(run_id, dir_lock, thread_lock=lock):
                    return lock, dir_lock
                self._release_thread_lock(run_id, lock)

            if not operator_priority:
                return None

            if self._is_legitimate_pipeline_busy(run_id):
                return None

            job = self._read_gui_job(run_id)
            if self._is_operator_pause_job(job) and not self._holder_thread_alive(run_id):
                self._recover_orphaned_thread_lock(run_id)

            if time.monotonic() >= deadline:
                return None
            time.sleep(0.1)

    @contextmanager
    def run_guard(self, run_id: str, *, operator_priority: bool = False) -> Iterator[None]:
        """Serialize mutating API calls with background execute for one run."""
        acquired = self._acquire_run_locks(run_id, operator_priority=operator_priority)
        if acquired is None:
            raise RunBusyError(run_id)
        lock, dir_lock = acquired
        try:
            yield
        finally:
            self._release_run_locks(run_id, dir_lock, lock)

    @contextmanager
    def operator_guard(self, run_id: str) -> Iterator[None]:
        """GUI operator mutations — recover stale locks and wait briefly for pause handoff."""
        with self.run_guard(run_id, operator_priority=True):
            yield

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
            return ["edl", "assembly_preview"]
        stages: list[str] = []
        if cats["structural"] or full_refresh:
            stages.append("full_master_ranking")
            # Reorder/split: rebase gap VO, remint bridges, then transition + audit.
            for sid in (
                "selection_framing_apply",
                "transitions",
                "edl_narrative_audit",
            ):
                if sid not in stages:
                    stages.append(sid)
        if full_refresh or apply_mode == "full_refresh":
            for sid in (
                "selection_framing_apply",
                "transitions",
                "edl_narrative_audit",
            ):
                if sid not in stages:
                    stages.append(sid)
        stages.extend(["vo_synthesize", "edl", "assembly_preview"])
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
                from interview_mux.automation_run import (
                    PARTIAL_AUTO_PREPARE_UNTIL_G0,
                    is_partially_accelerated_run,
                )

                meta: dict[str, Any] = {}
                if ctx.artifact_exists("run_meta.json"):
                    raw_meta = ctx.read_json("run_meta.json")
                    if isinstance(raw_meta, dict):
                        meta = raw_meta
                if is_partially_accelerated_run(meta):
                    order = list(PARTIAL_AUTO_PREPARE_UNTIL_G0)
                    start = from_stage or stage
                    if start and start in order:
                        order = order[order.index(start) :]
                elif "transcript_review_build" in order:
                    order = order[: order.index("transcript_review_build") + 1]
            pending = [s for s in order if not ctx.is_done(s)]
            from interview_mux.gap_fill_eligibility import filter_visible_job_stages

            return filter_visible_job_stages(ctx, pending)
        delivery_orders = {
            "delivery": DELIVERY_ORDER,
            "delivery_until_preview": DELIVERY_ORDER,
            "delivery_polish": DELIVERY_ORDER,
        }
        if mode in delivery_orders:
            order = list(delivery_orders[mode])
            start = from_stage or stage
            if not start and mode == "delivery":
                try:
                    from interview_mux.delivery_recovery import suggest_delivery_resume

                    suggested = suggest_delivery_resume(ctx)
                    if suggested and suggested in order:
                        start = suggested
                except Exception:
                    start = None
            if start and start in order:
                order = order[order.index(start) :]
            if until_stage and until_stage in order:
                order = order[: order.index(until_stage) + 1]
            elif mode == "delivery_until_preview" and "assembly_preview" in order:
                order = order[: order.index("assembly_preview") + 1]
            elif mode == "delivery_polish" and "sfx_prompt_craft" in order:
                order = order[order.index("sfx_prompt_craft") :]
            pending = [s for s in order if not ctx.is_done(s)]
            from interview_mux.gap_fill_eligibility import filter_visible_job_stages

            return filter_visible_job_stages(ctx, pending)
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
            secret_missing = missing_secrets(stage_ids)
            if secret_missing:
                labels = [PROVIDERS[p].label for p in secret_missing if p in PROVIDERS]
                return (
                    f"Missing credentials for: {', '.join(labels or secret_missing)}. "
                    "Set keys in config/secrets/secrets.env, then try again."
                )
            return None
        labels = [PROVIDERS[p].label for p in missing if p in PROVIDERS]
        return (
            f"API consent required before running: {', '.join(labels or missing)}. "
            "Grant access in the GUI, then try again."
        )

    def _busy_job_error(self, run_id: str, *, reason: str) -> dict[str, Any]:
        job = self.get_job(run_id)
        stage_id = job.get("current_stage") or job.get("stage")
        title = self._stage_title(stage_id)
        msg = job.get("message") or ""
        if stage_id:
            detail = f"{title} is already running"
            if msg and msg not in detail:
                detail = f"{detail} — {msg}"
            error = (
                f"A job is already running for this run ({detail}). "
                "Watch Activity for live command output."
            )
        else:
            error = (
                "A job is already running for this run. "
                "Watch Activity for live command output."
            )
        if reason == "directory":
            error = (
                f"{error} If nothing is progressing, another server process may hold "
                "the run lock — stop duplicate instances or refresh after restart."
            )
        try:
            ctx = RunContext(run_id, create=False)
            ctx.log(error, level="warning", stage=stage_id or "gui")
        except OSError:
            pass
        return {"ok": False, "error": error, "job": job}

    def _try_acquire_dir_lock(
        self,
        run_id: str,
        dir_lock: RunDirectoryLock,
        *,
        thread_lock: Lock,
    ) -> bool:
        if dir_lock.acquire(blocking=False):
            return True
        from interview_mux.gui_job_reconcile import reconcile_stale_job

        # When the caller already holds thread_lock (run_guard), lock_held(run_id) is
        # always True — still attempt stale dir-lock recovery before giving up.
        if not thread_lock.locked() and self.lock_held(run_id):
            if self._recover_orphaned_thread_lock(run_id):
                return dir_lock.acquire(blocking=False)
            return False
        reconcile_stale_job(run_id)
        if dir_lock.try_recover_stale():
            return True
        return dir_lock.acquire(blocking=False)

    def _spawn_pipeline_thread(
        self,
        run_id: str,
        *,
        mode: str,
        stage: str | None = None,
        flow: str | None = None,
        from_stage: str | None = None,
        until_stage: str | None = None,
        invalidate: bool = False,
        nle_full_refresh: bool = False,
        nle_apply_mode: str = "structural",
    ) -> None:
        def _run(lock: Lock, dir_lock: RunDirectoryLock) -> None:
            from interview_mux.operator_trace import active_run_context

            ctx = RunContext(run_id, create=False)
            ctx_token = active_run_context.set(ctx)
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
                "invalidate": invalidate,
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

            register_job_progress(run_id, _progress_hook, job_base=job_base)
            dir_lock_released = {"value": False}
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
                    if stage in SUBPROCESS_STAGES:
                        dir_lock_released["value"] = True
                        self._run_subprocess_stage(
                            ctx, stage, from_stage, dir_lock, invalidate=invalidate
                        )
                    else:
                        self._execute_single_stage(
                            ctx, stage, from_stage, invalidate=invalidate
                        )
                elif mode in ("analysis", "analysis_until_g0"):
                    ctx.log("Running shared analysis pipeline…", level="info", stage="analysis")
                    us = until_stage
                    if mode == "analysis_until_g0" and not us:
                        us = "transcript_review_build"
                    run_analysis(
                        ctx,
                        from_stage=from_stage or stage,
                        until_stage=us,
                        invalidate=invalidate,
                    )
                    refresh_journey_meta(ctx)
                elif mode in ("delivery", "delivery_until_preview", "delivery_polish"):
                    if mode == "delivery_polish":
                        self._preflight_delivery_polish(ctx, job_base)
                    ctx.log("Running delivery pipeline…", level="info", stage="delivery")
                    us = until_stage
                    fs = from_stage or stage
                    if mode == "delivery_until_preview" and not us:
                        us = "assembly_preview"
                    if mode == "delivery_polish" and not fs:
                        fs = "sfx_prompt_craft"
                    run_delivery(
                        ctx,
                        from_stage=fs,
                        until_stage=us,
                        invalidate=invalidate,
                    )
                    refresh_journey_meta(ctx)
                    if mode == "delivery" and not us and self._should_verify_master_after_delivery(ctx):
                        self._run_master_qa(ctx, flow="podcast", rel_path="master/master.wav")
                elif mode == "nle_apply":
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
                    self.invalidate_from(run_id, "edl")
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
                vo_incomplete = False
                try:
                    from interview_mux.gates import check_g1_vo
                    from interview_mux.stage_completion import vo_synthesize_should_defer_done

                    missing_g1 = check_g1_vo(ctx)
                    vo_open = bool(
                        vo_synthesize_should_defer_done(ctx, "vo_synthesize") or missing_g1
                    )
                    vo_job = stage == "vo_synthesize"
                    if vo_job and vo_open:
                        vo_incomplete = True
                        done_msg = (
                            "VO synthesize incomplete — G1 missing "
                            + ", ".join((missing_g1 or ["pickups"])[:6])
                        )
                except Exception:
                    vo_incomplete = False
                if vo_incomplete:
                    ctx.log(done_msg, level="warning", stage="vo_synthesize")
                    refresh_journey_meta(ctx)
                    self._write_job(
                        ctx,
                        {
                            "status": "running",
                            "mode": mode,
                            "stage": "vo_synthesize",
                            "flow": flow,
                            "message": done_msg,
                        },
                    )
                else:
                    ctx.log(done_msg, level="success", stage=label)
                    refresh_journey_meta(ctx)
                    self._write_job(
                        ctx,
                        {"status": "complete", "mode": mode, "stage": stage, "flow": flow, "message": done_msg},
                    )
            except StageInputError as exc:
                # Soft operator/gate pause — warning note only, never ERROR+traceback.
                gate_msg = str(exc)
                ctx.log(
                    gate_msg,
                    level="warning",
                    stage=exc.stage_id,
                    detail={
                        "event": "stage_input_blocked",
                        "issues": [issue.message for issue in exc.issues],
                        "remediation": [
                            issue.remediation for issue in exc.issues if issue.remediation
                        ],
                    },
                )
                refresh_journey_meta(ctx)
                self._release_run_locks(run_id, dir_lock, lock)
                self._write_job(
                    ctx,
                    {
                        "status": "gate",
                        "mode": mode,
                        "stage": exc.stage_id,
                        "message": gate_msg,
                        "error": gate_msg,
                    },
                )
            except StageReuseOfferPending as exc:
                gate_msg = str(exc)
                ctx.log(gate_msg, level="action", stage=exc.stage_id)
                refresh_journey_meta(ctx)
                self._release_run_locks(run_id, dir_lock, lock)
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
                from interview_mux.gate_focus import gate_focus_stage

                gate_stage = gate_focus_stage(gate_msg, job_stage=stage) or stage
                ctx.log(
                    gate_msg,
                    level="action",
                    stage=gate_stage,
                    detail="Complete the gate in the GUI to continue.",
                )
                refresh_journey_meta(ctx)
                self._release_run_locks(run_id, dir_lock, lock)
                self._write_job(
                    ctx,
                    {
                        "status": "gate",
                        "mode": mode,
                        "stage": gate_stage,
                        "message": gate_msg,
                        "error": str(exc),
                    },
                )
            except Exception as exc:
                err_msg = str(exc)
                tb = traceback.format_exc()
                # Prefer the stage that was actually running — not the batch from_stage.
                # Mis-attributing failures to from_stage makes e2e clear_from() archive
                # good upstream artifacts (talking_points, speakers, …).
                stage_id = ""
                try:
                    prev = ctx.read_json("gui_job.json")
                    if isinstance(prev, dict):
                        stage_id = str(
                            prev.get("current_stage") or prev.get("stage") or ""
                        ).strip()
                except Exception:
                    stage_id = ""
                if not stage_id or stage_id in {"analysis", "delivery", "gui", "None"}:
                    stage_id = str(stage or label or "").strip()
                if stage_id:
                    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

                    rel = STAGE_ARTIFACT_DISK_PATHS.get(stage_id)
                    if rel and not ctx.artifact_exists(rel):
                        marker = ctx.final_path(".stage_done", stage_id)
                        if marker.is_file():
                            marker.unlink(missing_ok=True)
                            ctx.log(
                                f"Cleared stale .stage_done/{stage_id} after failure "
                                f"(missing {rel})",
                                level="warning",
                                stage=stage_id,
                            )
                last_error = {
                    "message": err_msg,
                    "stage": stage_id,
                    "error_class": type(exc).__name__,
                    "traceback_excerpt": tb[:2000] if tb else None,
                }
                ctx.log(err_msg, level="error", stage=stage_id or label, detail=tb)
                self._write_job(
                    ctx,
                    {
                        "status": "error",
                        "mode": mode,
                        "stage": stage_id or stage,
                        "current_stage": stage_id or stage,
                        "message": err_msg,
                        "error": err_msg,
                        "traceback": tb,
                        "last_error": last_error,
                    },
                )
            finally:
                try:
                    clear_job_progress(run_id)
                finally:
                    if not dir_lock_released["value"]:
                        try:
                            dir_lock.release()
                        except Exception:
                            pass
                    self._release_thread_lock(run_id, lock)
                    active_run_context.reset(ctx_token)

        def _run_with_holder() -> None:
            lock = self._lock_for(run_id)
            dir_lock = RunDirectoryLock(run_id)
            if not self._acquire_thread_lock(run_id):
                self._clear_pipeline_start_reservation(run_id)
                try:
                    ctx = RunContext(run_id, create=False)
                    ctx.log(
                        "Could not start pipeline — run lock busy.",
                        level="error",
                        stage=stage or mode or "gui",
                    )
                    self._write_job(
                        ctx,
                        {
                            "status": "error",
                            "mode": mode,
                            "stage": stage,
                            "message": "Could not start pipeline — run lock busy.",
                        },
                    )
                except OSError:
                    pass
                return
            if not self._try_acquire_dir_lock(run_id, dir_lock, thread_lock=lock):
                self._release_thread_lock(run_id, lock)
                self._clear_pipeline_start_reservation(run_id)
                try:
                    ctx = RunContext(run_id, create=False)
                    ctx.log(
                        "Could not start pipeline — directory lock busy.",
                        level="error",
                        stage=stage or mode or "gui",
                    )
                    self._write_job(
                        ctx,
                        {
                            "status": "error",
                            "mode": mode,
                            "stage": stage,
                            "message": "Could not start pipeline — directory lock busy.",
                        },
                    )
                except OSError:
                    pass
                return
            self._clear_pipeline_start_reservation(run_id)
            _run(lock, dir_lock)

        Thread(target=_run_with_holder, daemon=True).start()

    def decline_reuse_and_run(
        self,
        run_id: str,
        stage_id: str,
        *,
        api_consents: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        """Record reuse decline and start the stage in one lock scope — avoids double-click races."""
        from interview_mux.stage_execution_reuse import (
            get_reuse_decision,
            record_reuse_decision,
        )

        acquired = self._acquire_run_locks(run_id, operator_priority=True)
        if acquired is None:
            return self._busy_job_error(run_id, reason="thread")
        lock, dir_lock = acquired

        ctx = RunContext(run_id, create=False)
        title = STAGE_BY_ID.get(stage_id)
        stage_label = title.title if title else stage_id.replace("_", " ")
        existing = get_reuse_decision(ctx, stage_id)
        if not existing or existing.get("action") != "decline":
            record_reuse_decision(ctx, stage_id, action="decline")
            from interview_mux.operator_snapshots import append_operator_stage_reuse

            append_operator_stage_reuse(ctx, stage_id, get_reuse_decision(ctx, stage_id) or {}, source="gui_decline")

        consent_err = self._check_api_consent(
            ctx,
            mode="stage",
            stage=stage_id,
            from_stage=None,
            until_stage=None,
            nle_full_refresh=False,
            nle_apply_mode="structural",
            api_consents=api_consents,
        )
        if consent_err:
            ctx.log(consent_err, level="action", stage=stage_id)
            self._write_job(
                ctx,
                {
                    "status": "needs_operator",
                    "mode": "stage",
                    "stage": stage_id,
                    "message": consent_err,
                    "needs_api_consent": True,
                },
            )
            self._release_run_locks(run_id, dir_lock, lock)
            return {
                "ok": False,
                "error": consent_err,
                "needs_api_consent": True,
                "needs_operator": True,
            }

        ctx.log(
            f"Running {stage_label} fresh (declined reuse) — job starting…",
            level="action",
            stage=stage_id,
        )
        refresh_journey_meta(ctx)
        self._release_run_locks(run_id, dir_lock, lock)
        if not self._reserve_pipeline_start(run_id):
            return self._busy_job_error(run_id, reason="thread")
        self._spawn_pipeline_thread(
            run_id,
            mode="stage",
            stage=stage_id,
            from_stage=stage_id,
        )
        return {"ok": True, "run_id": run_id, "mode": "stage", "stage": stage_id}

    def _next_analysis_stage(self, ctx: RunContext, after_stage_id: str) -> str | None:
        if after_stage_id not in ANALYSIS_ORDER:
            return None
        idx = ANALYSIS_ORDER.index(after_stage_id)
        for sid in ANALYSIS_ORDER[idx + 1 :]:
            if not ctx.is_done(sid):
                return sid
        return None

    def _preflight_and_spawn(
        self,
        run_id: str,
        *,
        mode: str,
        stage: str | None = None,
        flow: str | None = None,
        from_stage: str | None = None,
        until_stage: str | None = None,
        invalidate: bool = False,
        nle_full_refresh: bool = False,
        nle_apply_mode: str = "structural",
        api_consents: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        """Run start() preflight checks and spawn pipeline thread (worker acquires locks)."""
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
            self._clear_pipeline_start_reservation(run_id)
            return {
                "ok": False,
                "error": msg,
                "needs_operator": True,
                "needs_stage_reuse": True,
                "stage": reuse_pending.stage_id,
                "reuse_candidates": [c.to_dict() for c in reuse_pending.candidates],
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
                    "needs_api_consent": True,
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
            self._clear_pipeline_start_reservation(run_id)
            return {
                "ok": False,
                "error": consent_err,
                "needs_api_consent": True,
                "needs_operator": True,
            }

        self._preflight_delivery_dispatch(
            ctx_pre,
            stage=stage,
            from_stage=from_stage,
            stage_ids=stage_ids,
        )
        self._spawn_pipeline_thread(
            run_id,
            mode=mode,
            stage=stage,
            flow=flow,
            from_stage=from_stage,
            until_stage=until_stage,
            invalidate=invalidate,
            nle_full_refresh=nle_full_refresh,
            nle_apply_mode=nle_apply_mode,
        )
        return {"ok": True, "run_id": run_id, "mode": mode, "stage": stage}

    def start(
        self,
        run_id: str,
        *,
        mode: str,
        stage: str | None = None,
        flow: str | None = None,
        from_stage: str | None = None,
        until_stage: str | None = None,
        invalidate: bool = False,
        nle_full_refresh: bool = False,
        nle_apply_mode: str = "structural",
        api_consents: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        if not self._reserve_pipeline_start(run_id):
            return self._busy_job_error(run_id, reason="thread")
        try:
            return self._preflight_and_spawn(
                run_id,
                mode=mode,
                stage=stage,
                flow=flow,
                from_stage=from_stage,
                until_stage=until_stage,
                invalidate=invalidate,
                nle_full_refresh=nle_full_refresh,
                nle_apply_mode=nle_apply_mode,
                api_consents=api_consents,
            )
        except Exception:
            self._clear_pipeline_start_reservation(run_id)
            raise

    def _preflight_delivery_dispatch(
        self,
        ctx: RunContext,
        *,
        stage: str | None,
        from_stage: str | None,
        stage_ids: list[str],
    ) -> None:
        """R9b: block expensive delivery stages when prerequisites are red."""
        from interview_mux.delivery_guardrails import EXPENSIVE_STAGES, G1_CONSUMERS, record_wasted_work
        from interview_mux.stage_input_checks import collect_stage_input_issues

        targets: list[str] = []
        if stage:
            targets = [stage]
        elif from_stage:
            targets = [
                sid
                for sid in stage_ids
                if sid in EXPENSIVE_STAGES or sid in G1_CONSUMERS
            ][:1]
        for sid in targets:
            issues = [
                issue
                for issue in collect_stage_input_issues(ctx, sid)
                if issue.kind != "write_approval"
            ]
            if not issues:
                continue
            record_wasted_work(
                ctx,
                event="avoided_expensive_start",
                stage=sid,
                detail={"reason": issues[0].message, "source": "gui_runner"},
            )
            raise RuntimeError(issues[0].message)

    def _preflight_delivery_polish(self, ctx: RunContext, job_base: dict[str, Any]) -> None:
        """Block delivery_polish when post-listen or mmaudio QA gates are not clear."""
        from interview_mux.gates import check_post_listen_gate_pending, require_post_listen_clear
        from interview_mux.llm_flow_hardening import require_spend_artifacts_complete
        from interview_mux.config import merged_config

        failed_listen = check_post_listen_gate_pending(ctx)
        sound_cfg = merged_config().get("sound_design") or {}
        post_mode = str(sound_cfg.get("post_listen_gate_mode", "warn")).lower()
        soft_listen = post_mode in {"warn", "soft"}
        if failed_listen:
            msg = (
                f"Delivery polish blocked: post_listen failures for {', '.join(failed_listen[:6])}. "
                "Mark Pass in the post-listen panel before continuing."
            )
            if soft_listen:
                ctx.log(msg, level="warning", stage="delivery_polish")
            else:
                ctx.log(msg, level="error", stage="delivery_polish")
                self._write_job(ctx, {**job_base, "status": "gate", "message": msg, "stage": "delivery_polish"})
                raise SystemExit(msg)
        if not soft_listen:
            require_post_listen_clear(ctx, stage="delivery_polish")
        require_spend_artifacts_complete(ctx, "mix")

    def _stage_worker_cmd(self, run_id: str, stage_id: str) -> list[str]:
        return [sys.executable, "-m", "interview_mux.stage_worker", run_id, stage_id]

    def _run_subprocess_stage(
        self,
        ctx: RunContext,
        stage: str,
        from_stage: str | None,
        dir_lock: RunDirectoryLock,
        *,
        invalidate: bool = False,
    ) -> None:
        from interview_mux.gui_job_reconcile import WRITE_APPROVAL_EXIT
        from interview_mux.process_cleanup import track_worker_pid, untrack_worker_pid

        if invalidate and from_stage and from_stage != stage:
            self.invalidate_from(ctx.run_id, from_stage)
            ctx = RunContext(ctx.run_id, create=False)
        if stage == "mmaudio_sfx":
            ok, message = can_run_sfx_generation(ctx)
            if not ok:
                ctx.log(message, level="warning", stage=stage)
                raise RuntimeError(message)
        try:
            dir_lock.release()
        except Exception:
            pass
        proc = subprocess.Popen(
            self._stage_worker_cmd(ctx.run_id, stage),
            cwd=str(ctx.root),
        )
        track_worker_pid(proc.pid)
        if ctx.artifact_exists("gui_job.json"):
            job = ctx.read_json("gui_job.json")
            job["worker_pid"] = proc.pid
            job["worker_kind"] = "stage_subprocess"
            ctx.write_json("gui_job.json", job)
        try:
            returncode = proc.wait()
        finally:
            untrack_worker_pid(proc.pid)
            if ctx.artifact_exists("gui_job.json"):
                job = ctx.read_json("gui_job.json")
                if job.get("worker_pid") == proc.pid:
                    job.pop("worker_pid", None)
                    job.pop("worker_kind", None)
                    ctx.write_json("gui_job.json", job)
        if returncode == WRITE_APPROVAL_EXIT:
            raise RuntimeError(
                f"Stage {stage} paused for staged writes — v2 auto-commit should prevent this."
            )
        if returncode != 0:
            job = ctx.read_json("gui_job.json") if ctx.artifact_exists("gui_job.json") else {}
            msg = str(job.get("message") or job.get("error") or "").strip()
            if msg:
                raise RuntimeError(msg)
            raise RuntimeError(f"Stage {stage} failed (exit {returncode})")

    def _execute_single_stage(
        self,
        ctx: RunContext,
        stage: str,
        from_stage: str | None,
        *,
        invalidate: bool = False,
    ) -> None:
        if invalidate and from_stage and from_stage != stage:
            self.invalidate_from(ctx.run_id, from_stage)
            ctx = RunContext(ctx.run_id, create=False)
        if stage == "mmaudio_sfx":
            ok, message = can_run_sfx_generation(ctx)
            if not ok:
                ctx.log(message, level="warning", stage=stage)
                raise RuntimeError(message)
        run_single_stage(ctx, stage)

    def _should_verify_master_after_delivery(self, ctx: RunContext) -> bool:
        """Homunculus 0.1.0 may return from a delivery phase before master_finalize.

        Master QA belongs after a real master exists (or master_finalize is done
        and the file is missing — that is a product failure). Partial delivery
        must not raise FileNotFoundError and poison Full-auto retries.
        """
        if ctx.artifact_exists("master/master.wav"):
            return True
        return bool(ctx.is_done("master_finalize") or ctx.is_done("podcast_publish"))

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
        from interview_mux.aspirational_quality import is_aspirational_enabled

        aspirational = is_aspirational_enabled(ctx)
        lufs_failures = [
            f for f in result.failures if "Integrated LUFS" in f or "LUFS" in f
        ]
        if aspirational and lufs_failures and len(lufs_failures) == len(result.failures):
            ctx.log(
                f"Master QA LUFS advisory ({flow}): {detail}",
                level="warning",
                stage="verify_master",
                detail="; ".join(result.checks),
            )
            try:
                from interview_mux.aspirational_quality import record_quality_advisories

                record_quality_advisories(
                    ctx,
                    gate_id="verify_master_lufs",
                    failed_checks=lufs_failures,
                    detail={"flow": flow, "checks": result.checks},
                )
            except Exception:
                pass
            return
        # True-peak-only misses after loudnorm are usually measurement noise — warn, don't poison Activity.
        # Borderline integrated LUFS (SOFT: prefix) same treatment for long sparse podcasts.
        soft_only = bool(result.failures) and all(
            f.startswith("SOFT:") or "True peak" in f for f in result.failures
        )
        tp_only = bool(result.failures) and all("True peak" in f for f in result.failures)
        if soft_only or tp_only:
            ctx.log(
                f"Master QA soft warning ({flow}): {detail}",
                level="warning",
                stage="verify_master",
                detail="; ".join(result.checks),
            )
            return
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
        if stage_id in DELIVERY_ORDER:
            ctx.clear_from(stage_id, DELIVERY_ORDER)
            orders.append(DELIVERY_ORDER)
        seen: set[tuple[str, ...]] = set()
        for order in orders:
            key = tuple(order)
            if key in seen:
                continue
            seen.add(key)
            clear_stage_reuse_from(ctx, stage_id, order)
        if stage_id in {
            "source_acoustic_profile",
            "content_context",
            "content_brief_reanchor",
            "boundary_topic_resplit",
            "segment_classification",
            "sound_design_palettes",
            "sonic_context_build",
        }:
            from interview_mux.analysis_memory import invalidate_sonic_context

            invalidate_sonic_context(ctx, reason=f"invalidate_from:{stage_id}", stage=stage_id)

runner = JobRunner()
