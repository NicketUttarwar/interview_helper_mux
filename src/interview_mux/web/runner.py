from __future__ import annotations

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
    providers_for_stages,
    stage_api_providers,
)
from interview_mux.gui_api_consent import load_persisted_consents, merge_consents
from interview_mux.sfx_prompt_review import can_run_sfx_generation
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


def _invalidate_disfluency_review_gate(ctx: RunContext) -> None:
    marker = ctx.final_path(".stage_done", "disfluency_review")
    if marker.is_file():
        marker.unlink()
    review_summary = ctx.final_path("transcript", "disfluency_review.json")
    if review_summary.is_file():
        review_summary.unlink()


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
                "pending_write_stage": None,
                "pending_write_paths": None,
                "awaiting_write_approval": False,
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
                    if job.get("mode") == "write_approval":
                        reconcile_stale_job(run_id)
                    elif run_id in self._lock_holder_tid:
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

    def _reserve_pipeline_start(self, run_id: str) -> bool:
        """Mark a run as starting so execute cannot double-spawn before the worker acquires."""
        if self.lock_held(run_id):
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

        return reconcile_job_if_stale(run_id, lock_held=self.lock_held(run_id))

    def is_running(self, run_id: str) -> bool:
        """True only when this process is executing a background job for the run."""
        with self._global:
            if run_id in self._starting_runs:
                return True
        return self.lock_held(run_id)

    def mark_write_approval_saving(
        self,
        ctx: RunContext,
        stage_id: str,
        paths: list[str],
    ) -> None:
        """Show live save progress in gui_job while staged files are promoted to disk."""
        title = self._stage_title(stage_id)
        self._write_job(
            ctx,
            {
                "status": "running",
                "mode": "write_approval",
                "stage": stage_id,
                "current_stage": stage_id,
                "message": f"Saving {len(paths)} file(s) for {title}…",
                "pending_write_stage": stage_id,
                "pending_write_paths": paths,
            },
        )
        ctx.log(
            f"Saving {len(paths)} staged file(s) for {title}…",
            level="action",
            stage=stage_id,
            action_id="write_approval.save",
            origin="api",
            detail={
                "journey_kind": "execute",
                "event": "write_approval_save_start",
                "paths": paths,
            },
        )

    def _read_gui_job(self, run_id: str) -> dict[str, Any]:
        if not RunContext.exists(run_id):
            return {}
        try:
            return RunContext(run_id, create=False).read_json("gui_job.json")
        except OSError:
            return {}

    def _is_operator_pause_job(self, job: dict[str, Any]) -> bool:
        status = job.get("status")
        return bool(
            job.get("awaiting_write_approval")
            or job.get("needs_stage_reuse")
            or status
            in (
                "awaiting_write_approval",
                "needs_operator",
                "gate",
                "interrupted",
            )
        )

    def _is_legitimate_pipeline_busy(self, run_id: str) -> bool:
        """True when a live worker is executing a stage (not an operator pause)."""
        if not self._holder_thread_alive(run_id):
            return False
        from interview_mux.gui_job_reconcile import RUNNING_STATUSES

        job = self._read_gui_job(run_id)
        status = job.get("status")
        if status not in RUNNING_STATUSES:
            return False
        if job.get("mode") == "write_approval":
            return self._holder_thread_alive(run_id)
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
            elif mode == "flow1_polish" and "sfx_prompt_craft" in order:
                order = order[order.index("sfx_prompt_craft") :]
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

    def restore_write_approval_pause(
        self,
        ctx: RunContext,
        stage_id: str,
        paths: list[str],
    ) -> None:
        """Revert gui_job to awaiting_write_approval after a failed staged save."""
        title = self._stage_title(stage_id)
        self._write_job(
            ctx,
            {
                "status": "awaiting_write_approval",
                "mode": "stage",
                "stage": stage_id,
                "current_stage": stage_id,
                "message": f"{title} outputs await review before saving ({len(paths)} file(s)).",
                "pending_write_stage": stage_id,
                "pending_write_paths": paths,
                "awaiting_write_approval": True,
            },
        )

    def _spawn_pipeline_thread(
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
                    if mode == "flow1_polish":
                        self._preflight_flow1_polish(ctx, job_base)
                    ctx.log("Running Flow 1 — full master podcast pipeline…", level="info", stage="flow1")
                    us = until_stage
                    fs = from_stage or stage
                    if mode == "flow1_until_preview" and not us:
                        us = "assembly_preview"
                    if mode == "flow1_polish" and not fs:
                        fs = "sfx_prompt_craft"
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
                ctx.log(str(exc), level="action", stage=exc.stage_id)
                refresh_journey_meta(ctx)
                self._release_run_locks(run_id, dir_lock, lock)
                from interview_mux.artifact_issue_triage import (
                    apply_clarification_gate_after_pause,
                    blocking_issues_remaining,
                    triage_enabled,
                )
                from interview_mux.full_autopilot import full_autopilot_enabled
                from interview_mux.operator_decisions import pending_decision_count

                if full_autopilot_enabled() and pending_decision_count(ctx, exc.stage_id) > 0:
                    self._write_job(
                        ctx,
                        {
                            "status": "awaiting_write_approval",
                            "mode": mode,
                            "stage": exc.stage_id,
                            "message": "Your input needed before review",
                            "pending_write_stage": exc.stage_id,
                            "pending_write_paths": exc.paths,
                            "awaiting_write_approval": True,
                            "pending_decision_count": pending_decision_count(ctx, exc.stage_id),
                        },
                    )
                elif triage_enabled() and blocking_issues_remaining(ctx, exc.stage_id) > 0:
                    apply_clarification_gate_after_pause(ctx, exc.stage_id)
                else:
                    self._write_job(
                        ctx,
                        {
                            "status": "awaiting_write_approval",
                            "mode": mode,
                            "stage": exc.stage_id,
                            "message": "Awaiting your review",
                            "pending_write_stage": exc.stage_id,
                            "pending_write_paths": exc.paths,
                            "awaiting_write_approval": True,
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
                from interview_mux.write_staging import read_gui_job

                existing = read_gui_job(ctx) or {}
                if str(existing.get("status")) == "needs_clarification":
                    ctx.log(
                        gate_msg,
                        level="action",
                        stage=label,
                        detail="ITR clarification gate — resolve issues in the GUI.",
                    )
                    refresh_journey_meta(ctx)
                    self._release_run_locks(run_id, dir_lock, lock)
                    return
                ctx.log(gate_msg, level="action", stage=label, detail="Complete the gate in the GUI to continue.")
                refresh_journey_meta(ctx)
                self._release_run_locks(run_id, dir_lock, lock)
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
                tb = traceback.format_exc()
                stage_id = stage or label
                last_error = {
                    "message": err_msg,
                    "stage": stage_id,
                    "error_class": type(exc).__name__,
                    "traceback_excerpt": tb[:2000] if tb else None,
                }
                ctx.log(err_msg, level="error", stage=label, detail=tb)
                self._write_job(
                    ctx,
                    {
                        "status": "error",
                        "mode": mode,
                        "stage": stage,
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
        write_pending = check_write_approval_before_execute(ctx)
        if write_pending:
            msg = str(write_pending)
            ctx.log(msg, level="action", stage=write_pending.stage_id)
            self._write_job(
                ctx,
                {
                    "status": "awaiting_write_approval",
                    "mode": "stage",
                    "stage": write_pending.stage_id,
                    "message": msg,
                    "pending_write_stage": write_pending.stage_id,
                    "pending_write_paths": write_pending.paths,
                },
            )
            self._release_run_locks(run_id, dir_lock, lock)
            return {
                "ok": False,
                "error": msg,
                "needs_operator": True,
                "awaiting_write_approval": True,
                "pending_write_stage": write_pending.stage_id,
                "pending_write_paths": write_pending.paths,
            }

        handoff_err = check_handoff_before_execute(ctx)
        if handoff_err:
            ctx.log(handoff_err, level="action", stage=pending_handoff_stage(ctx))
            self._write_job(
                ctx,
                {
                    "status": "needs_operator",
                    "mode": "stage",
                    "stage": stage_id,
                    "message": handoff_err,
                },
            )
            self._release_run_locks(run_id, dir_lock, lock)
            return {
                "ok": False,
                "error": handoff_err,
                "needs_operator": True,
                "needs_handoff_review": True,
            }

        if consent_err:
            ctx.log(consent_err, level="action", stage=stage_id)
            self._write_job(
                ctx,
                {
                    "status": "needs_operator",
                    "mode": "stage",
                    "stage": stage_id,
                    "message": consent_err,
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
        if after_stage_id == "disfluency_extract":
            from interview_mux.gates import check_disfluency_review_pending

            if check_disfluency_review_pending(ctx):
                return "disfluency_review"
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
                    "awaiting_write_approval": True,
                },
            )
            self._clear_pipeline_start_reservation(run_id)
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
            self._clear_pipeline_start_reservation(run_id)
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
            self._clear_pipeline_start_reservation(run_id)
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
            self._clear_pipeline_start_reservation(run_id)
            return {
                "ok": False,
                "error": consent_err,
                "needs_api_consent": True,
                "needs_operator": True,
            }

        self._spawn_pipeline_thread(
            run_id,
            mode=mode,
            stage=stage,
            flow=flow,
            from_stage=from_stage,
            until_stage=until_stage,
            nle_full_refresh=nle_full_refresh,
            nle_apply_mode=nle_apply_mode,
        )
        return {"ok": True, "run_id": run_id, "mode": mode, "stage": stage}

    def approve_write_and_continue(
        self,
        run_id: str,
        stage_id: str,
        *,
        api_consents: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        """Flush staged writes and start the next runnable stage under one lock scope."""
        from interview_mux.write_staging import approve_stage_writes, assert_write_approval_allowed, list_pending_paths

        acquired = self._acquire_run_locks(run_id, operator_priority=True)
        if acquired is None:
            raise RunBusyError(run_id)
        lock, dir_lock = acquired

        ctx = RunContext(run_id, create=False)
        title = STAGE_BY_ID.get(stage_id)
        stage_label = title.title if title else stage_id.replace("_", " ")
        try:
            assert_write_approval_allowed(ctx, stage_id)
            paths = list_pending_paths(ctx, stage_id)

            self.mark_write_approval_saving(ctx, stage_id, paths)
            try:
                flushed = approve_stage_writes(ctx, stage_id)
            except Exception:
                if list_pending_paths(ctx, stage_id):
                    self.restore_write_approval_pause(ctx, stage_id, paths)
                self._release_run_locks(run_id, dir_lock, lock)
                raise

            self.clear_operator_pause(
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

            next_stage = self._next_analysis_stage(ctx, stage_id)
            self._release_run_locks(run_id, dir_lock, lock)
            return {
                "ok": True,
                "flushed": flushed,
                "stage_id": stage_id,
                "started_stage": next_stage,
                "job": {
                    "status": "complete",
                    "stage": stage_id,
                    "message": (
                        f"{stage_label}: saved {len(flushed)} file(s) — ready for next step."
                    ),
                },
            }
        except RunBusyError:
            raise
        except Exception:
            if lock.locked():
                self._release_run_locks(run_id, dir_lock, lock)
            raise

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
                nle_full_refresh=nle_full_refresh,
                nle_apply_mode=nle_apply_mode,
                api_consents=api_consents,
            )
        except Exception:
            self._clear_pipeline_start_reservation(run_id)
            raise

    def _preflight_flow1_polish(self, ctx: RunContext, job_base: dict[str, Any]) -> None:
        """Block flow1_polish when post-listen or mmaudio QA gates are not clear."""
        from interview_mux.gates import check_post_listen_gate_pending, require_post_listen_clear
        from interview_mux.llm_flow_hardening import require_spend_artifacts_complete

        failed_listen = check_post_listen_gate_pending(ctx)
        if failed_listen:
            msg = (
                f"Flow 1 polish blocked: post_listen failures for {', '.join(failed_listen[:6])}. "
                "Mark Pass in the post-listen panel before continuing."
            )
            ctx.log(msg, level="error", stage="flow1_polish")
            self._write_job(ctx, {**job_base, "status": "gate", "message": msg, "stage": "flow1_polish"})
            raise SystemExit(msg)
        require_post_listen_clear(ctx, stage="flow1_polish")
        require_spend_artifacts_complete(ctx, "mix_flow1")

    def _execute_single_stage(self, ctx: RunContext, stage: str, from_stage: str | None) -> None:
        if from_stage and from_stage != stage:
            self.invalidate_from(ctx.run_id, from_stage)
            ctx = RunContext(ctx.run_id, create=False)
        if stage in ("mmaudio_sfx_flow1", "mmaudio_sfx_flow2"):
            ok, message = can_run_sfx_generation(ctx)
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
        if stage_id in {"disfluency_extract", "disfluency_review"}:
            _invalidate_disfluency_review_gate(ctx)
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
        if stage_id in {
            "source_acoustic_profile",
            "content_context",
            "content_brief_reanchor",
            "segment_classification",
            "sound_design_palettes",
            "sonic_context_build",
        }:
            from interview_mux.analysis_memory import invalidate_sonic_context

            invalidate_sonic_context(ctx, reason=f"invalidate_from:{stage_id}", stage=stage_id)
        from interview_mux.attempt_budget import reset_stage_attempt_budget

        reset_stage_attempt_budget(ctx, stage_id)

runner = JobRunner()
