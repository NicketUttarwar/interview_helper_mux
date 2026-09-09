"""Baseline artifact sanitizers — deterministic, non-amplifying handoff cleanup."""

from __future__ import annotations

from interview_mux.artifact_sanitize.registry import (
    air_contract_sanitary_errors,
    assert_air_contract_sanitary,
    assert_edl_sanitary,
    assert_gap_sanitary,
    assert_layup_sanitary,
    assert_sanitized_or_raise,
    assert_sdp_sanitary,
    assert_selection_sanitary,
    assert_transitions_sanitary,
    assert_vo_sanitary,
    edl_sanitary_errors,
    gap_sanitary_errors,
    layup_sanitary_errors,
    sanitize_artifact,
    sdp_sanitary_errors,
    selection_sanitary_errors,
    transitions_sanitary_errors,
    vo_sanitary_errors,
)
from interview_mux.artifact_sanitize.admit import admit_sanitized
from interview_mux.artifact_sanitize.invalidate import maybe_invalidate_after_sanitize
from interview_mux.artifact_sanitize.one_writer import (
    HOT_ARTIFACT_RELS,
    commit_nugget_layup_plan_doc,
    commit_sound_design_plan_doc,
    commit_transitions_doc,
    maybe_admit_hot_write,
)
from interview_mux.artifact_sanitize.preflight import sanitary_preflight_errors
from interview_mux.artifact_sanitize.selection import run_selection_order_sanitize
from interview_mux.artifact_sanitize.types import SanitizeResult

__all__ = [
    "SanitizeResult",
    "sanitize_artifact",
    "assert_sanitized_or_raise",
    "assert_selection_sanitary",
    "assert_gap_sanitary",
    "assert_layup_sanitary",
    "assert_air_contract_sanitary",
    "assert_transitions_sanitary",
    "assert_vo_sanitary",
    "assert_edl_sanitary",
    "assert_sdp_sanitary",
    "selection_sanitary_errors",
    "gap_sanitary_errors",
    "layup_sanitary_errors",
    "air_contract_sanitary_errors",
    "transitions_sanitary_errors",
    "vo_sanitary_errors",
    "edl_sanitary_errors",
    "sdp_sanitary_errors",
    "run_selection_order_sanitize",
    "sanitary_preflight_errors",
    "maybe_invalidate_after_sanitize",
    "HOT_ARTIFACT_RELS",
    "maybe_admit_hot_write",
    "commit_transitions_doc",
    "commit_sound_design_plan_doc",
    "commit_nugget_layup_plan_doc",
    "admit_sanitized",
]
