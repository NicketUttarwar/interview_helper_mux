"""Tests for normalization decision tree and permissive field classification."""

from __future__ import annotations

import json
from pathlib import Path

from interview_mux.field_necessity_registry import FieldAction, classify_field_path
from interview_mux.llm_output_normalizer import normalize_llm_response
from interview_mux.normalization_decision import (
    DownstreamAction,
    resolve_normalization_decision,
)
from interview_mux.null_field_policy import find_null_fields

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "llm_envelopes"


def test_classify_notes_nullable():
    assert classify_field_path("speaker_roles", "notes") == FieldAction.OMIT


def test_classify_role_critical():
    assert classify_field_path("speaker_roles", "speakers[0].role") == FieldAction.BLOCK


def test_classify_unknown_optional_permissive_fabricates():
    assert (
        classify_field_path("content_context", "unknown_optional_field", permissive=True)
        == FieldAction.FABRICATE
    )


def test_decision_tree_omit_for_notes():
    d = resolve_normalization_decision("speaker_roles", "notes")
    assert d.action == FieldAction.OMIT
    assert d.downstream == DownstreamAction.OMIT_AND_ACKNOWLEDGE


def test_decision_tree_block_critical_null_suggests_gap_fill():
    d = resolve_normalization_decision(
        "content_context",
        "thesis",
        error_kind="critical_null",
    )
    assert d.action == FieldAction.BLOCK
    assert d.downstream == DownstreamAction.MICRO_GAP_FILL


def test_normalize_speaker_roles_notes_null():
    raw = json.loads((FIXTURES / "speaker_roles_notes_null.json").read_text())
    result = normalize_llm_response(
        None,
        interaction_id="OA-01",
        parsed=raw,
        stage_key="speaker_roles",
        task_kind="primary",
    )
    assert result.ok, result.verification_errors
    artifacts = result.normalized.get("artifacts") or {}
    assert "notes" not in artifacts
    assert any(a.kind == "omit" and a.path == "notes" for a in result.actions)


def test_normalize_records_decision_summary():
    raw = json.loads((FIXTURES / "speaker_roles_notes_null.json").read_text())
    result = normalize_llm_response(
        None,
        interaction_id="OA-01",
        parsed=raw,
        stage_key="speaker_roles",
        task_kind="primary",
    )
    meta = (result.normalized.get("artifacts") or {}).get("_meta") or {}
    summary = meta.get("normalization_summary") or {}
    assert summary.get("action_counts") or summary.get("omit_count")


def test_normalize_arbiter_skips_null_policy():
    raw = {
        "status": "complete",
        "artifacts": {
            "verdict": "accept",
            "confidence": 0.9,
            "gaps": [],
            "suggested_investigation": {"kind": "test", "question": "q"},
        },
    }
    result = normalize_llm_response(
        None,
        interaction_id="OA-arbiter",
        parsed=raw,
        stage_key="speaker_roles",
        task_kind="arbiter",
    )
    assert result.ok or result.normalized.get("artifacts")


def test_find_null_fields_includes_notes():
    artifacts = {"speakers": [{"speaker_id": "a", "role": "unknown", "confidence": 0.5}], "notes": None}
    paths = find_null_fields("speaker_roles", artifacts)
    assert "notes" in paths
