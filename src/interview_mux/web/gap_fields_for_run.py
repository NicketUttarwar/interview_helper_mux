"""Helpers for conditional gap runtime fields on GET /api/runs/{id}."""

from __future__ import annotations

from typing import Any

from interview_mux.gap_vo_gates import gap_gate_payload_for_run, global_gap_runtime_fields
from interview_mux.run_context import RunContext

_GAP_VO_PHASES = frozenset(
    {
        "gap_framing",
        "g1_vo_pickup",
        "g1_5_preview_pickup",
        "delivery",
        "mastering",
    }
)
_GAP_VO_STAGES = frozenset(
    {
        "missing_framing",
        "g1_vo_pickup",
        "g1_5_preview_pickup",
        "vo_ingest",
        "vo_synthesize",
        "vo_line_adjudicate",
    }
)


def gap_fields_for_get_run(
    ctx: RunContext,
    *,
    job: dict[str, Any] | None,
    operator_phase: str | None,
) -> dict[str, Any]:
    """Include Chatterbox probe only when operator is at or past gap/VO gates."""
    payload = gap_gate_payload_for_run(ctx)
    phase = str(operator_phase or "")
    stage = str((job or {}).get("stage") or (job or {}).get("current_stage") or "")
    if phase in _GAP_VO_PHASES or stage in _GAP_VO_STAGES:
        payload.update(global_gap_runtime_fields())
    return payload
