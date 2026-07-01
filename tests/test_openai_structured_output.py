from __future__ import annotations

import pytest

from interview_mux.openai_structured_output import (
    compose_arbiter_schema,
    compose_envelope_schema,
    min_example_for_stage,
    resolve_response_format,
    schema_to_min_example,
    strictify_schema,
)
from interview_mux.openai_schema_lint import lint_openai_strict_schema
from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS


def test_resolve_response_format_primary_uses_json_schema():
    fmt = resolve_response_format("speaker_roles", "primary")
    assert fmt is not None
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True
    assert "speakers" in str(fmt["json_schema"]["schema"])


def test_resolve_response_format_arbiter():
    fmt = resolve_response_format("_arbiter", "arbiter")
    assert fmt["json_schema"]["name"] == "arbiter_verdict"


def test_compose_envelope_schema_has_required_envelope_keys():
    schema = compose_envelope_schema("boundary_detection", strict=True)
    assert "status" in schema["properties"]
    assert "artifacts" in schema["properties"]


def test_strictify_adds_additional_properties_false():
    raw = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
    out = strictify_schema(raw)
    assert out["additionalProperties"] is False
    assert "a" in out["required"]


def test_schema_to_min_example_boundary():
    schema = compose_envelope_schema("boundary_detection", strict=False)
    art_schema = schema["properties"]["artifacts"]
    example = schema_to_min_example(art_schema)
    assert "boundaries" in example


def test_min_example_for_stage_is_envelope():
    env = min_example_for_stage("speaker_roles")
    assert env["status"] == "complete"
    assert "speakers" in env["artifacts"]


@pytest.mark.parametrize("stage_key", sorted(STAGE_ARTIFACT_SCHEMAS.keys()))
def test_all_stage_envelopes_compose_and_lint_clean(stage_key: str):
    schema = compose_envelope_schema(stage_key, strict=True)
    assert lint_openai_strict_schema(schema) == []


def test_speaker_roles_required_speakers_not_nullable_in_composed_schema():
    schema = compose_envelope_schema("speaker_roles", strict=True)
    speakers = schema["properties"]["artifacts"]["properties"]["speakers"]
    assert speakers["type"] == "array"
    assert "items" in speakers
    assert "null" not in (speakers["type"] if isinstance(speakers["type"], list) else [])


def test_content_context_jargon_glossary_has_items():
    fmt = resolve_response_format("content_context", "primary")
    art = fmt["json_schema"]["schema"]["properties"]["artifacts"]["properties"]
    assert "items" in art["jargon_glossary"]
    assert "items" in art["emotional_beats"]


def test_min_example_for_stage_includes_optional_structured_fields():
    env = min_example_for_stage("content_context")
    art = env["artifacts"]
    assert "jargon_glossary" in art
    assert "key_claims" in art
    assert "topic_relationships" in art


def test_compose_arbiter_schema_lints_clean():
    schema = compose_arbiter_schema(strict=True)
    assert lint_openai_strict_schema(schema) == []
