"""Single-driver claim for a run_id — prevent dual healers after restart."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.run_context import RunContext

DRIVER_CLAIM_REL = "operator/driver_claim.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        from interview_mux.process_cleanup import worker_pid_alive

        return bool(worker_pid_alive(pid))
    except Exception:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def read_driver_claim(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(DRIVER_CLAIM_REL):
        return None
    try:
        doc = ctx.read_json(DRIVER_CLAIM_REL)
    except Exception:
        return None
    return doc if isinstance(doc, dict) else None


def claim_driver_run(ctx: RunContext, *, force: bool = False) -> dict[str, Any]:
    """Claim this process as the sole full-auto/partial-auto driver for the run.

    Raises RuntimeError if another live driver already holds the claim (unless force).
    """
    pid = os.getpid()
    existing = read_driver_claim(ctx)
    if isinstance(existing, dict):
        other = int(existing.get("pid") or 0)
        if other and other != pid and _pid_alive(other) and not force:
            raise RuntimeError(
                f"driver already active for {ctx.run_id} pid={other} "
                f"(started={existing.get('claimed_at')}) — refuse second driver; "
                f"stop the other process or pass force=True"
            )
    claim = {
        "version": 1,
        "run_id": ctx.run_id,
        "pid": pid,
        "claimed_at": _utc_now(),
        "host_pid_file": str(_assets_driver_pid_path()),
    }
    ctx.write_json(DRIVER_CLAIM_REL, claim, skip_handoff=True)

    def _mark(meta: dict[str, Any]) -> None:
        meta["partial_auto_driver_active"] = True
        meta["driver_claim_pid"] = pid
        meta["driver_claimed_at"] = claim["claimed_at"]

    try:
        if ctx.artifact_exists("run_meta.json"):
            ctx.mutate_run_meta(_mark)
    except Exception:
        pass
    try:
        _assets_driver_pid_path().write_text(str(pid), encoding="utf-8")
    except Exception:
        pass
    return claim


def release_driver_run(ctx: RunContext) -> bool:
    """Release claim if held by this PID (or stale dead PID)."""
    pid = os.getpid()
    existing = read_driver_claim(ctx)
    if not isinstance(existing, dict):
        return False
    other = int(existing.get("pid") or 0)
    if other and other != pid and _pid_alive(other):
        return False
    try:
        ctx.write_json(
            DRIVER_CLAIM_REL,
            {
                "version": 1,
                "run_id": ctx.run_id,
                "pid": None,
                "released_at": _utc_now(),
                "released_by": pid,
            },
            skip_handoff=True,
        )
    except Exception:
        return False

    def _mark(meta: dict[str, Any]) -> None:
        meta["partial_auto_driver_active"] = False
        meta.pop("driver_claim_pid", None)

    try:
        if ctx.artifact_exists("run_meta.json"):
            ctx.mutate_run_meta(_mark)
    except Exception:
        pass
    return True


def live_foreign_driver_claim(
    ctx: RunContext, *, force: bool = False
) -> dict[str, Any] | None:
    """Return live claim owned by another PID, or None if free / force / self."""
    existing = read_driver_claim(ctx)
    if not isinstance(existing, dict):
        return None
    other = int(existing.get("pid") or 0)
    if other and other != os.getpid() and _pid_alive(other) and not force:
        return existing
    return None


def assert_can_bind_driver(run_id: str, *, force: bool = False) -> dict[str, Any] | None:
    """Pre-bind check on a product execution dir: return existing live claim or None."""
    if not RunContext.exists(run_id):
        return None
    return live_foreign_driver_claim(RunContext(run_id, create=False), force=force)

def _assets_driver_pid_path() -> Path:
    try:
        from interview_mux.assets_ephemeral_cleanup import assets_root

        return Path(assets_root()) / "full_auto.pid"
    except Exception:
        return Path("ASSETS") / "full_auto.pid"


def on_serve_restart_harden() -> dict[str, Any]:
    """Serve-start hardening: reconcile jobs, hydrate fail counts, sync driver claims."""
    out: dict[str, Any] = {
        "reconciled_jobs": 0,
        "hydrated_runs": [],
        "stale_claims_cleared": [],
        "active_driver": None,
    }
    try:
        from interview_mux.gui_job_reconcile import reconcile_stale_jobs

        out["reconciled_jobs"] = int(reconcile_stale_jobs() or 0)
    except Exception as exc:
        out["reconcile_error"] = str(exc)[:200]

    run_ids: list[str] = []
    try:
        from interview_mux.application_session import get_active

        active = get_active() or {}
        rid = str(active.get("run_id") or "").strip()
        if rid:
            run_ids.append(rid)
    except Exception:
        pass
    try:
        pointer = _assets_driver_pid_path().parent / "full_auto_current_run.txt"
        if pointer.is_file():
            rid = pointer.read_text(encoding="utf-8").strip().splitlines()[0].strip()
            if rid and rid not in run_ids:
                run_ids.append(rid)
    except Exception:
        pass

    for rid in run_ids:
        if not RunContext.exists(rid):
            continue
        ctx = RunContext(rid, create=False)
        claim = read_driver_claim(ctx)
        if isinstance(claim, dict):
            other = int(claim.get("pid") or 0)
            if other and not _pid_alive(other):
                try:
                    release_driver_run(ctx)
                    out["stale_claims_cleared"].append(rid)
                except Exception:
                    pass
            elif other and _pid_alive(other):
                out["active_driver"] = {"run_id": rid, "pid": other}
        try:
            from interview_mux.identical_failures import hydrate_driver_fail_counts

            hydrated = hydrate_driver_fail_counts(ctx)
            if hydrated:
                out["hydrated_runs"].append(
                    {"run_id": rid, "keys": len(hydrated)}
                )
        except Exception:
            pass
        # Reconcile expensive lease visibility: if gui_job claims running but
        # worker PID is dead, gui_job_reconcile already handled; stamp lease idle.
        try:
            from interview_mux.write_staging import read_gui_job

            job = read_gui_job(ctx) or {}
            if isinstance(job, dict) and str(job.get("status") or "") == "running":
                from interview_mux.process_cleanup import worker_pid_alive

                if not worker_pid_alive(job.get("worker_pid")):
                    # Leave to reconcile_stale_jobs; record for operator.
                    out.setdefault("stale_running_jobs", []).append(rid)
        except Exception:
            pass
    return out
