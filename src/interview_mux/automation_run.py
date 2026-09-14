"""Full-auto and partially-accelerated runs share one detached driver stack."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

_FULL_AUTO_MODES = frozenset({"full-auto", "fullauto", "auto", "e2e"})
_PARTIAL_AUTO_MODES = frozenset(
    {"partially-accelerated", "partial-auto", "partiallyaccelerated"}
)

# Partial-auto: reach G0 after ingest+STT only — defer DeepFilterNet until after operator review.
PARTIAL_AUTO_PREPARE_UNTIL_G0: tuple[str, ...] = (
    "ingest",
    "transcribe",
    "transcript_review_build",
)
_AUTOMATION_ENV_KEYS = (
    "MUX_FULL_AUTO",
    "MUX_BABA_E2E",
    "MUX_PARTIAL_AUTO",
    "INTERVIEW_MUX_AUTO_ACCEPT_GATES",
)


def _normalize_run_mode_token(raw: str | None) -> str:
    return str(raw or "").strip().lower().replace("_", "-").replace(" ", "")


def is_partially_accelerated_run(meta: dict[str, Any] | None) -> bool:
    if not isinstance(meta, dict):
        return False
    if meta.get("partial_auto"):
        return True
    return _normalize_run_mode_token(str(meta.get("run_mode") or "")) in _PARTIAL_AUTO_MODES


def is_full_auto_run(meta: dict[str, Any] | None) -> bool:
    if not isinstance(meta, dict):
        return False
    if meta.get("full_auto"):
        return True
    return _normalize_run_mode_token(str(meta.get("run_mode") or "")) in _FULL_AUTO_MODES


def automation_driver_run(meta: dict[str, Any] | None) -> bool:
    """True when the shared automation driver stack applies (full or partial)."""
    return is_full_auto_run(meta) or is_partially_accelerated_run(meta)


# Partial-auto operator gate SSOT (Cluster D / SYN-MODE) — mirror of
# frontend/src/utils/partialOperatorGates.ts
PARTIAL_MUST_ACT_GATES: tuple[str, ...] = ("transcript_review", "g_publish")
PARTIAL_MAY_PAUSE_GATES: tuple[str, ...] = (
    "gap_framing",
    "missing_framing",
    "g1_vo_pickup",
    "stage_reuse",
    "write_approval",
)


def should_advance_after_gate_post(meta: dict[str, Any] | None) -> bool:
    """After a gate POST the operator clicked Continue — Manual, Partial, and Full-auto.

    Dual *walk* is prevented by ``gate_advance_lease`` (GUI vs driver single-flight),
    not by refusing GUI Continue.
    """
    return True


GATE_ADVANCE_LEASE_REL = "operator/gate_advance_lease.json"
GATE_ADVANCE_LEASE_TTL_SEC = 20.0


def take_gate_advance_lease(ctx: Any, *, source: str, gate_id: str = "") -> dict[str, Any]:
    doc = {
        "source": str(source or "").strip() or "driver",
        "gate_id": str(gate_id or "").strip(),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        ctx.write_json(GATE_ADVANCE_LEASE_REL, doc, skip_handoff=True)
    except Exception:
        dest = ctx.path(*GATE_ADVANCE_LEASE_REL.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        import json

        dest.write_text(json.dumps(doc), encoding="utf-8")
    return doc


def read_gate_advance_lease(ctx: Any) -> dict[str, Any] | None:
    try:
        if not ctx.artifact_exists(GATE_ADVANCE_LEASE_REL):
            return None
        doc = ctx.read_json(GATE_ADVANCE_LEASE_REL)
        return doc if isinstance(doc, dict) else None
    except Exception:
        return None


def _lease_age_sec(doc: dict[str, Any]) -> float:
    raw = str(doc.get("at") or "").strip()
    if not raw:
        return 1e9
    try:
        stamped = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return max(0.0, time.time() - stamped.timestamp())
    except Exception:
        return 1e9


def gui_holds_fresh_lease(ctx: Any) -> bool:
    doc = read_gate_advance_lease(ctx)
    if not doc or str(doc.get("source") or "") != "gui":
        return False
    return _lease_age_sec(doc) <= GATE_ADVANCE_LEASE_TTL_SEC


def _job_is_running(ctx: Any) -> bool:
    try:
        from interview_mux.write_staging import read_gui_job

        job = read_gui_job(ctx) or {}
        status = str((job or {}).get("status") or "").lower()
        return status in {"running", "queued", "starting", "gate"}
    except Exception:
        return False


def driver_may_walk(ctx: Any) -> bool:
    """False when GUI holds a fresh lease and is (or is about to be) walking."""
    if gui_holds_fresh_lease(ctx):
        if _job_is_running(ctx):
            return False
        if _lease_age_sec(read_gate_advance_lease(ctx) or {}) <= GATE_ADVANCE_LEASE_TTL_SEC:
            return False
    take_gate_advance_lease(ctx, source="driver", gate_id="handle_gate")
    return True


def automation_driver_env_enabled() -> bool:
    """True when the current process was launched by the automation driver."""
    for key in _AUTOMATION_ENV_KEYS:
        raw = str(os.environ.get(key) or "").strip().lower()
        if raw in {"1", "true", "yes"}:
            return True
    mode = _normalize_run_mode_token(os.environ.get("MUX_RUN_MODE"))
    return mode in _FULL_AUTO_MODES or mode in _PARTIAL_AUTO_MODES
