from __future__ import annotations

import pytest

from interview_mux.openai_structured_output import (
    _OPENAI_SCHEMA_NAME_MAX,
    _schema_name,
    compose_arbiter_schema,
    compose_envelope_schema,
    min_example_for_stage,
    resolve_response_format,
    schema_to_min_example,
    strictify_schema,
)
from interview_mux.openai_schema_lint import lint_openai_strict_schema
from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS
from interview_mux.llm_specialists import POST_STAGE_SPECIALISTS, PRE_STAGE_SPECIALISTS


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


def test_content_context_enum_fields_are_string_nullable():
    fmt = resolve_response_format("content_context", "primary")
    items = fmt["json_schema"]["schema"]["properties"]["artifacts"]["properties"]["key_claims"]["items"]
    claim_type = items["properties"]["claim_type"]
    assert "string" in (claim_type["type"] if isinstance(claim_type["type"], list) else [claim_type["type"]])


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


def _specialist_stage_keys() -> list[str]:
    keys: list[str] = []
    for mapping in (PRE_STAGE_SPECIALISTS, POST_STAGE_SPECIALISTS):
        for parent, specs in mapping.items():
            for spec in specs:
                keys.append(f"{parent}__{spec}")
    return keys


@pytest.mark.parametrize("stage_key", _specialist_stage_keys())
def test_specialist_schema_names_fit_openai_limit(stage_key: str):
    name = _schema_name(stage_key, "specialist")
    assert len(name) <= _OPENAI_SCHEMA_NAME_MAX
    fmt = resolve_response_format(stage_key, "specialist")
    if fmt and fmt.get("type") == "json_schema":
        assert len(fmt["json_schema"]["name"]) <= _OPENAI_SCHEMA_NAME_MAX


@pytest.mark.parametrize("stage_key", sorted(STAGE_ARTIFACT_SCHEMAS.keys()))
def test_primary_schema_names_fit_openai_limit(stage_key: str):
    name = _schema_name(stage_key, "primary")
    assert len(name) <= _OPENAI_SCHEMA_NAME_MAX


def test_long_specialist_name_hashes_instead_of_overflow():
    stage_key = "full_master_ranking__stt_lexicon_island_verify"
    name = _schema_name(stage_key, "specialist")
    assert len(name) <= 64
    assert name.endswith("_specialist_response")
    naive = stage_key.replace("__", "_").replace("-", "_") + "_specialist_response"
    assert len(naive) > 64

