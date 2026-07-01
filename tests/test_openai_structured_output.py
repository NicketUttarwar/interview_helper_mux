from __future__ import annotations

from interview_mux.openai_structured_output import (
    compose_arbiter_schema,
    compose_envelope_schema,
    min_example_for_stage,
    resolve_response_format,
    schema_to_min_example,
    strictify_schema,
)


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
