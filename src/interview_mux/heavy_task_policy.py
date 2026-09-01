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
    """Sleep remainder of abort backoff if a recent kill was recorded. Returns seconds slept."""
    backoff = abort_backoff_sec()
    if backoff <= 0:
        return 0.0
    doc = _read_state()
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
