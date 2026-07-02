"""Critical LLM stages list stays aligned with stage contracts."""

from __future__ import annotations

from interview_mux.llm_flow_hardening import ALL_CRITICAL_LLM_STAGES
from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS


def test_critical_stages_subset_of_schema_registry():
    unknown = sorted(ALL_CRITICAL_LLM_STAGES - set(STAGE_ARTIFACT_SCHEMAS.keys()))
    assert unknown == [], f"ALL_CRITICAL_LLM_STAGES has unknown keys: {unknown}"
