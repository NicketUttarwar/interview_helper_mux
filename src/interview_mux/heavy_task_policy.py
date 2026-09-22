"""App-wide policy for GPU/subprocess kills (SIGTERM/OOM) on heavy local tasks."""

from __future__ import annotations

import json
import logging
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_STATE_REL = ".heavy_abort_state.json"


def is_heavy_kill_returncode(code: int | None) -> bool:
    """True for SIGTERM, SIGKILL, SIGABRT (and common shell-encoded variants)."""
    if code is None:
        return False
    n = int(code)
    try:
        sigterm = int(signal.SIGTERM)
        sigkill = int(signal.SIGKILL)
        sigabrt = int(signal.SIGABRT)
    except Exception:
        sigterm, sigkill, sigabrt = 15, 9, 6
    return n in {
        -sigterm,
        -sigkill,
        -sigabrt,
        128 + sigterm,
        128 + sigkill,
        128 + sigabrt,
        sigabrt,
    }


def abort_backoff_sec() -> float:
    raw = os.environ.get("INTERVIEW_MUX_GPU_ABORT_BACKOFF_SEC")
    if raw is not None and str(raw).strip() != "":
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    from interview_mux.gpu_exclusive import local_gpu_cfg

    try:
        return max(0.0, float(local_gpu_cfg().get("abort_backoff_sec", 30)))
    except (TypeError, ValueError):
        return 30.0


def _state_path() -> Path:
    from interview_mux.config import repo_root

    path = repo_root() / "ASSETS" / _STATE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read_state() -> dict[str, Any]:
    path = _state_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_state(doc: dict[str, Any]) -> None:
    path = _state_path()
    try:
        path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        pass


def record_heavy_abort(
    consumer: str,
    returncode: int | None,
    *,
    ctx: Any | None = None,
    stage: str | None = None,
) -> None:
    """Persist machine-wide timestamp when a heavy subprocess was killed."""
    if not is_heavy_kill_returncode(returncode):
        return
    name = str(consumer or "unknown").strip().lower() or "unknown"
    now = datetime.now(timezone.utc).isoformat()
    doc = _read_state()
    doc["last_abort_at"] = now
    doc["last_consumer"] = name
    doc["last_returncode"] = int(returncode) if returncode is not None else None
    doc["last_stage"] = str(stage or "")
    _write_state(doc)
    if ctx is not None:
        try:
            ctx.log(
                f"Heavy task killed: {name} rc={returncode}",
                level="warning",
                stage=stage or name,
                detail={
                    "consumer": name,
                    "returncode": returncode,
                    "journey_kind": "execute",
                },
            )
        except Exception:
            pass
    else:
        logger.warning("heavy_task_abort consumer=%s returncode=%s", name, returncode)


def wait_abort_backoff(ctx: Any | None = None, consumer: str = "") -> float:
    """Sleep remainder of abort backoff if a recent kill was recorded. Returns seconds slept.

    Skip when a §0.3b reclaim settle already credited the GPU cool-down so we do
    not stack 5s settle + ~30s abort backoff (and starve the same-class retry).
    """
    backoff = abort_backoff_sec()
    if backoff <= 0:
        return 0.0
    doc = _read_state()
    if _reclaim_settle_credits_abort(doc):
        return 0.0
    last_at = str(doc.get("last_abort_at") or "").strip()
    if not last_at:
        return 0.0
    try:
        ts = datetime.fromisoformat(last_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    elapsed = (datetime.now(timezone.utc) - ts).total_seconds()
    remaining = backoff - elapsed
    if remaining <= 0:
        return 0.0
    name = str(consumer or "unknown").strip().lower() or "unknown"
    detail = {
        "consumer": name,
        "backoff_sec": backoff,
        "sleep_sec": round(remaining, 2),
        "last_consumer": doc.get("last_consumer"),
        "last_returncode": doc.get("last_returncode"),
    }
    if ctx is not None:
        try:
            ctx.log(
                f"Heavy task backoff {remaining:.0f}s before {name}",
                level="info",
                stage=str(doc.get("last_stage") or name),
                detail={**detail, "journey_kind": "execute"},
            )
        except Exception:
            pass
        try:
            from interview_mux.delivery_guardrails import record_wasted_work

            record_wasted_work(
                ctx,
                event="heavy_task_sigterm_backoff",
                stage=str(doc.get("last_stage") or name),
                detail=detail,
            )
        except Exception:
            pass
    else:
        logger.info("heavy_task_backoff consumer=%s sleep=%.1fs", name, remaining)
    time.sleep(remaining)
    return remaining


# --- Partial Zero §0.3b: reclaim → fixed settle → same-class retry -------------

_reclaim_retry_used: set[str] = set()
_reclaim_bound_run_id: str | None = None

_TRANSIENT_ERR_MARKERS = (
    "oom",
    "out of memory",
    "mps",
    "cuda",
    "metal",
    "timeout",
    "timed out",
    "resource temporarily",
    "killed",
    "sigterm",
    "sigkill",
    "sigabrt",
    "device lost",
    "allocation failed",
)


def reclaim_settle_sec() -> float:
    """Fixed settle after reclaim before same-class retry (default 5s)."""
    raw = os.environ.get("INTERVIEW_MUX_LOCAL_ML_RECLAIM_SETTLE_SEC")
    if raw is not None and str(raw).strip() != "":
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    from interview_mux.gpu_exclusive import local_gpu_cfg

    try:
        return max(0.0, float(local_gpu_cfg().get("reclaim_settle_sec", 5)))
    except (TypeError, ValueError):
        return 5.0


def clear_reclaim_retry_state() -> None:
    """Tests / run boundaries may reset same-class reclaim fingerprints."""
    global _reclaim_bound_run_id
    _reclaim_retry_used.clear()
    _reclaim_bound_run_id = None


def bind_reclaim_run(run_id: str | None) -> None:
    """Scope reclaim fingerprints to a run so long-lived serve does not permanently skip."""
    global _reclaim_bound_run_id
    rid = str(run_id or "").strip() or None
    if rid != _reclaim_bound_run_id:
        _reclaim_retry_used.clear()
        _reclaim_bound_run_id = rid


def is_reclaim_worthy_failure(
    *,
    returncode: int | None = None,
    stderr: str = "",
    exception: BaseException | None = None,
) -> bool:
    """True for hang/kill/OOM/Metal-class faults only — not deterministic app errors.

    Call only after a job has already failed. Never use this to interrupt a
    still-running / progressing subprocess; hang budgets and timeouts stay
    runner-owned and must not be shortened by reclaim.
    """
    err = str(stderr or "")
    if exception is not None:
        err = f"{err} {exception}".strip()
    from interview_mux.hang_escalation import classify_hang_vs_abort

    kind = classify_hang_vs_abort(returncode=returncode, stderr=err)
    if kind in {"hang", "abort"}:
        return True
    if is_heavy_kill_returncode(returncode):
        return True
    low = err.lower()
    return any(m in low for m in _TRANSIENT_ERR_MARKERS)


def _proc_still_running(proc: Any) -> bool:
    """True only for a live Popen; CompletedProcess is already finished."""
    poll = getattr(proc, "poll", None)
    if not callable(poll):
        return False
    try:
        return poll() is None
    except Exception:
        return False


def _reclaim_settle_credits_abort(doc: dict[str, Any] | None = None) -> bool:
    """True when a reclaim settle already covered the GPU cool-down for a prior abort."""
    state = doc if isinstance(doc, dict) else _read_state()
    settle_at = str(state.get("last_reclaim_settle_at") or "").strip()
    abort_at = str(state.get("last_abort_at") or "").strip()
    if not settle_at or not abort_at:
        return False
    try:
        settle_ts = datetime.fromisoformat(settle_at.replace("Z", "+00:00"))
        abort_ts = datetime.fromisoformat(abort_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    # Settle that happened at/after the abort (or within settle window after) credits backoff.
    if settle_ts >= abort_ts:
        return True
    return (abort_ts - settle_ts).total_seconds() <= reclaim_settle_sec() + 1.0


def _credit_abort_backoff_after_settle() -> None:
    """Mark reclaim settle so wait_abort_backoff does not stack another ~30s."""
    now = datetime.now(timezone.utc).isoformat()
    doc = _read_state()
    doc["last_reclaim_settle_at"] = now
    doc["abort_backoff_credited_by"] = "reclaim_settle"
    _write_state(doc)


def reclaim_for_same_class_retry(
    ctx: Any | None = None,
    *,
    consumer: str,
    fingerprint: str = "",
    proc: Any | None = None,
    returncode: int | None = None,
    stderr: str = "",
    exception: BaseException | None = None,
    stage: str | None = None,
    require_worthy: bool = True,
) -> bool:
    """§0.3b: kill *failed* live job → sleep reclaim_settle_sec → one same-class retry.

    Returns True once per ``consumer:fingerprint`` (caller retries same backend/params).
    Returns False if already reclaimed, or (when ``require_worthy``) if the failure
    is not hang/kill/OOM-class — callers escalate without burning settle.

    Does **not** shorten hang budgets or interrupt progressing work: callers must
    invoke only after a finished failure. Live kill is best-effort and only when
    ``proc`` is still running (never on CompletedProcess).
    """
    if ctx is not None:
        try:
            bind_reclaim_run(getattr(ctx, "run_id", None))
        except Exception:
            pass

    rc = returncode
    if rc is None and proc is not None:
        try:
            rc = getattr(proc, "returncode", None)
        except Exception:
            rc = None
    err = str(stderr or "")
    if not err and proc is not None:
        try:
            err = str(getattr(proc, "stderr", "") or "")
        except Exception:
            err = ""

    if require_worthy and not is_reclaim_worthy_failure(
        returncode=rc, stderr=err, exception=exception
    ):
        return False

    name = str(consumer or "unknown").strip().lower() or "unknown"
    fp = str(fingerprint or "default").strip() or "default"
    key = f"{name}:{fp}"
    if key in _reclaim_retry_used:
        return False

    # Only kill a still-running Popen left after a failed hang path. Never touch
    # finished CompletedProcess results — that would be a no-op at best and a
    # footgun if something still held a live child.
    if proc is not None and _proc_still_running(proc):
        try:
            from interview_mux.hang_escalation import kill_process_tree

            kill_process_tree(proc)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    # Record real kills only (local_runtime usually already did). Never synthesize
    # -15 for QC/soft fails — that poisons machine-wide abort backoff.
    if is_heavy_kill_returncode(rc):
        try:
            record_heavy_abort(name, rc, ctx=ctx, stage=stage or name)
        except Exception:
            pass

    settle = reclaim_settle_sec()
    if ctx is not None:
        try:
            ctx.log(
                f"Local ML reclaim settle {settle:.0f}s before same-class retry ({name})",
                level="info",
                stage=stage or name,
                detail={
                    "consumer": name,
                    "fingerprint": fp,
                    "settle_sec": settle,
                    "returncode": rc,
                    "journey_kind": "execute",
                },
            )
        except Exception:
            pass
    if settle > 0:
        time.sleep(settle)

    try:
        _credit_abort_backoff_after_settle()
    except Exception:
        pass

    _reclaim_retry_used.add(key)
    return True
