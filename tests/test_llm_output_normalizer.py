"""Tests for LLM output normalization and permissive field classification."""

from __future__ import annotations

import json
from pathlib import Path

from interview_mux.field_necessity_registry import (
    FieldAction,
    classify_field_path,
    parse_verification_error_path,
)
from interview_mux.llm_output_normalizer import normalize_llm_response
from interview_mux.null_field_policy import find_null_fields

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "llm_envelopes"


def test_parse_verification_error_path_strips_envelope_prefix():
    err = (
        "envelope.artifacts.emotional_beats.0.segment_ids: "
        "None is not of type 'array'"
    )
    assert parse_verification_error_path(err) == "emotional_beats.0.segment_ids"


def test_classify_notes_nullable():
    assert classify_field_path("speaker_roles", "notes") == FieldAction.OMIT


def test_classify_role_critical():
    assert classify_field_path("speaker_roles", "speakers[0].role") == FieldAction.BLOCK


def test_classify_unknown_optional_permissive_fabricates():
    assert (
        classify_field_path("content_context", "unknown_optional_field", permissive=True)
        == FieldAction.FABRICATE
    )


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


def test_normalize_content_context_empty_string_arrays():
    """LLM empty strings on array|null fields coerce to null and pass verification."""
    from interview_mux.openai_structured_output import min_example_for_stage

    raw = min_example_for_stage("content_context")
    raw["status"] = "complete"
    raw["needs"] = []
    raw["follow_up_investigations"] = []
    art = raw["artifacts"]
    art["era_tags"] = ""
    art["narrative_beats"] = ""
    art["topic_relationships"] = ""
    result = normalize_llm_response(
        None,
        interaction_id="OA-02",
        parsed=raw,
        stage_key="content_context",
        task_kind="primary",
    )
    assert result.ok, result.verification_errors
    normalized_art = result.normalized.get("artifacts") or {}
    for field in ("era_tags", "narrative_beats", "topic_relationships"):
        val = normalized_art.get(field)
        assert val is None or val == [], f"{field} should be null or empty array, got {val!r}"


def test_normalize_content_context_null_emotional_beat_segment_ids():
    """Null segment_ids on emotional_beats coerce to [] and pass OA-02 verification."""
    from interview_mux.openai_structured_output import min_example_for_stage

    raw = min_example_for_stage("content_context")
    raw["status"] = "complete"
    raw["needs"] = []
    raw["follow_up_investigations"] = []
    raw["artifacts"]["emotional_beats"] = [
        {"label": "tension", "description": "stakes rise", "segment_ids": None},
        {"label": "humor", "description": "light moment", "segment_ids": None},
        {"label": "vulnerability", "description": "personal share", "segment_ids": None},
    ]
    result = normalize_llm_response(
        None,
        interaction_id="OA-02",
        parsed=raw,
        stage_key="content_context",
        task_kind="primary",
    )
    assert result.ok, result.verification_errors
    beats = (result.normalized.get("artifacts") or {}).get("emotional_beats") or []
    assert len(beats) == 3
    for beat in beats:
        assert beat.get("segment_ids") == []
