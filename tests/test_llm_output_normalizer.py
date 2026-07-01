"""Tests for global LLM output normalizer."""

from __future__ import annotations

import json
from pathlib import Path

from interview_mux.field_necessity_registry import FieldAction, classify_field_path
from interview_mux.llm_output_normalizer import normalize_llm_response
from interview_mux.null_field_policy import find_null_fields


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "llm_envelopes"


def test_classify_notes_nullable():
    assert classify_field_path("speaker_roles", "notes") == FieldAction.OMIT


def test_classify_role_critical():
    assert classify_field_path("speaker_roles", "speakers[0].role") == FieldAction.BLOCK


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
