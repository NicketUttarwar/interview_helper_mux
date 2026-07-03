"""P0 analysis spine progression — earliest incomplete producer for journey blocking."""

from __future__ import annotations

from typing import Any

from interview_mux.llm_flow_hardening import CRITICAL_LLM_STAGES, producer_artifact_path

# Foundation LLM stages whose artifacts poison downstream work (see llm-guidance-program P0).
P0_ANALYSIS_SPINE: tuple[str, ...] = (
    "speaker_roles",
    "content_context",
    "boundary_detection",
    "segment_classification",
    "content_brief_reanchor",
)

_P0_SPINE_SET = frozenset(P0_ANALYSIS_SPINE)


def is_p0_spine_stage(stage_id: str) -> bool:
    return stage_id in _P0_SPINE_SET


def first_incomplete_p0_stage(ctx: Any) -> str | None:
    """Return the earliest P0 spine stage whose producer artifact is not complete."""
    from interview_mux.artifact_completeness import artifact_status

    for stage_id in P0_ANALYSIS_SPINE:
        if stage_id not in CRITICAL_LLM_STAGES:
            continue
        rel = producer_artifact_path(stage_id)
        if not rel:
            if not ctx.is_done(stage_id):
                return stage_id
            continue
        if artifact_status(rel, ctx) != "complete":
            return stage_id
    return None


def p0_stage_remediation(ctx: Any, stage_id: str) -> str:
    from interview_mux.web.stages import STAGE_BY_ID

    info = STAGE_BY_ID.get(stage_id)
    title = info.title if info else stage_id.replace("_", " ")
    rel = producer_artifact_path(stage_id) or ""
    from interview_mux.artifact_completeness import artifact_status

    st = artifact_status(rel, ctx) if rel else "missing"
    return f"Complete {title} ({rel or stage_id} is {st}) before running later stages."
