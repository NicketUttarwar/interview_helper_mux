"""Resolve which pipeline stage the operator should focus on for gate messages."""

from __future__ import annotations

import re

_UPSTREAM_STAGE_RE = re.compile(
    r"(?:from stage|Prerequisite stage)\s+([a-z][a-z0-9_]*)",
    re.IGNORECASE,
)


def upstream_stage_from_gate_message(
    message: str | None,
    *,
    current_stage: str | None = None,
) -> str | None:
    """Extract upstream stage id when a gate message references a prerequisite failure."""
    if not message:
        return None
    match = _UPSTREAM_STAGE_RE.search(message)
    if not match:
        return None
    upstream = match.group(1)
    if current_stage and upstream == current_stage:
        return None
    return upstream


def operator_gate_focus_stage(
    message: str | None,
    *,
    job_stage: str | None = None,
) -> str | None:
    """Map automated stage gates to the operator checkpoint stage the GUI should open."""
    if not message or not job_stage:
        return None
    low = message.lower()
    if job_stage == "transcript_review_build" and "transcript review required" in low:
        return "transcript_review"
    return None


def gate_focus_stage(
    message: str | None,
    *,
    job_stage: str | None = None,
) -> str | None:
    """Stage id the GUI should focus on for a gate job."""
    upstream = upstream_stage_from_gate_message(message, current_stage=job_stage)
    if upstream:
        return upstream
    operator = operator_gate_focus_stage(message, job_stage=job_stage)
    if operator:
        return operator
    return job_stage
