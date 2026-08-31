"""Forensics stall guard — exit the driver when the same predicate repeats without a product patch."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from interview_mux.identical_failures import (
    normalize_reason,
    product_code_fingerprint,
)
from interview_mux.run_context import RunContext

STALL_REL = "operator/forensics_stall.json"
ESCALATION_REL = "operator/forensics_escalation.json"
DEFAULT_ESCALATE_AFTER = 3


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def predicate_key(*, stage: str, reason: str, error_class: str = "") -> str:
    body = "|".join(
        [
            str(stage or "").strip().lower(),
            str(error_class or "").strip().lower(),
            normalize_reason(reason),
        ]
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def read_stall(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists(STALL_REL):
        return {"version": 1, "predicate": "", "count": 0, "product_fingerprint": ""}
    data = ctx.read_json(STALL_REL)
    return data if isinstance(data, dict) else {"version": 1, "predicate": "", "count": 0}


def read_escalation(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(ESCALATION_REL):
        return None
    data = ctx.read_json(ESCALATION_REL)
    return data if isinstance(data, dict) else None


def clear_escalation(ctx: RunContext) -> None:
    path = ctx.run_dir / ESCALATION_REL
    if path.is_file():
        path.unlink(missing_ok=True)


def record_stall(
    ctx: RunContext,
    *,
    stage: str,
    reason: str,
    error_class: str = "",
    escalate_after: int = DEFAULT_ESCALATE_AFTER,
) -> dict[str, Any]:
    """Track repeated predicates; return row with ``should_escalate`` when parent must patch."""
    fingerprint = product_code_fingerprint()
    key = predicate_key(stage=stage, reason=reason, error_class=error_class)
    prev = read_stall(ctx)
    prev_fp = str(prev.get("product_fingerprint") or "")
    prev_key = str(prev.get("predicate") or "")
    if key == prev_key and fingerprint == prev_fp:
        count = int(prev.get("count") or 0) + 1
    else:
        count = 1
    row: dict[str, Any] = {
        "version": 1,
        "updated_at": _utc_now(),
        "predicate": key,
        "stage": str(stage or ""),
        "reason": str(reason or "")[:400],
        "error_class": str(error_class or ""),
        "count": count,
        "escalate_after": max(1, int(escalate_after)),
        "product_fingerprint": fingerprint,
        "fingerprint_changed": bool(prev_fp and fingerprint != prev_fp),
        "first_seen_at": str(prev.get("first_seen_at") or _utc_now()),
        "should_escalate": count >= max(1, int(escalate_after)),
    }
    ctx.write_json(STALL_REL, row)
    return row


def write_escalation(
    ctx: RunContext,
    *,
    stage: str,
    reason: str,
    error_class: str = "",
    stall_row: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "version": 1,
        "kind": "forensics_escalation",
        "updated_at": _utc_now(),
        "stage": str(stage or ""),
        "reason": str(reason or "")[:800],
        "error_class": str(error_class or ""),
        "product_fingerprint": product_code_fingerprint(),
        "stall": dict(stall_row or read_stall(ctx)),
        "parent_action": (
            "Run: python tools/forensics_probe.py --run-id "
            f"{ctx.run_id} → patch product → pytest → restart driver same run_id"
        ),
    }
    if extra:
        doc["evidence"] = extra
    ctx.write_json(ESCALATION_REL, doc)
    return doc


def escalation_blocks_driver(ctx: RunContext) -> tuple[bool, str]:
    """True when an escalation exists and product code has not changed since it was written."""
    esc = read_escalation(ctx)
    if not esc:
        return False, ""
    esc_fp = str(esc.get("product_fingerprint") or "")
    cur_fp = product_code_fingerprint()
    if esc_fp and esc_fp == cur_fp:
        return True, str(esc.get("reason") or "forensics escalation pending parent patch")
    clear_escalation(ctx)
    return False, ""


def sync_escalation_with_product(ctx: RunContext) -> bool:
    """Clear stale escalation after a product patch; return True when cleared."""
    blocked, _ = escalation_blocks_driver(ctx)
    if blocked:
        return False
    if ctx.artifact_exists(ESCALATION_REL):
        clear_escalation(ctx)
        return True
    return False
