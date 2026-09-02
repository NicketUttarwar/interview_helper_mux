"""Production execution stall guard — predicate tracking without forensic SystemExit."""

from __future__ import annotations

from typing import Any

from interview_mux.forensics_stall import (
    DEFAULT_ESCALATE_AFTER,
    predicate_key,
    product_code_fingerprint,
)
from interview_mux.run_context import RunContext

STALL_REL = "operator/execution_stall.json"


def read_stall(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists(STALL_REL):
        return {"version": 1, "predicate": "", "count": 0, "product_fingerprint": ""}
    data = ctx.read_json(STALL_REL)
    return data if isinstance(data, dict) else {"version": 1, "predicate": "", "count": 0}


def clear_stall(ctx: RunContext) -> None:
    path = ctx.run_dir / STALL_REL
    if path.is_file():
        path.unlink(missing_ok=True)


def record_execution_stall(
    ctx: RunContext,
    *,
    stage: str,
    reason: str,
    error_class: str = "",
    escalate_after: int = DEFAULT_ESCALATE_AFTER,
) -> dict[str, Any]:
    from datetime import datetime, timezone

    fingerprint = product_code_fingerprint()
    key = predicate_key(stage=stage, reason=reason, error_class=error_class)
    prev = read_stall(ctx)
    prev_fp = str(prev.get("product_fingerprint") or "")
    prev_key = str(prev.get("predicate") or "")
    remediation_progress = bool(
        prev.get("last_tier") and prev.get("last_tier") != prev.get("prev_tier")
    )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if key == prev_key and fingerprint == prev_fp and not remediation_progress:
        count = int(prev.get("count") or 0) + 1
    else:
        count = 1
    row: dict[str, Any] = {
        "version": 1,
        "updated_at": now,
        "predicate": key,
        "stage": str(stage or ""),
        "reason": str(reason or "")[:400],
        "error_class": str(error_class or ""),
        "count": count,
        "escalate_after": max(1, int(escalate_after)),
        "product_fingerprint": fingerprint,
        "fingerprint_changed": bool(prev_fp and fingerprint != prev_fp),
        "first_seen_at": str(prev.get("first_seen_at") or now),
        "should_escalate": count >= max(1, int(escalate_after)),
        "prev_tier": prev.get("last_tier") or "",
    }
    ctx.write_json(STALL_REL, row, skip_handoff=True)
    return row


def mark_tier_progress(ctx: RunContext, tier: str) -> None:
    prev = read_stall(ctx)
    if not prev.get("predicate"):
        return
    prev = dict(prev)
    prev["last_tier"] = tier
    ctx.write_json(STALL_REL, prev, skip_handoff=True)
