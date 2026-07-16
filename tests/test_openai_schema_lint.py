from __future__ import annotations

import pytest

from interview_mux.openai_schema_lint import assert_openai_strict_schema, lint_openai_strict_schema
from interview_mux.openai_structured_output import strictify_schema


def test_lint_rejects_array_without_items():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"tags": {"type": "array"}},
        "required": ["tags"],
    }
    errors = lint_openai_strict_schema(schema)
    assert any("missing items" in e for e in errors)


def test_strictify_raises_on_array_without_items():
    with pytest.raises(ValueError, match="missing items"):
        strictify_schema({"type": "array"})


def test_lint_accepts_strictified_content_context_envelope():
    from interview_mux.openai_structured_output import compose_envelope_schema

    schema = compose_envelope_schema("content_context", strict=True)
    assert lint_openai_strict_schema(schema) == []


def test_content_context_openai_schema_exposes_claim_approx_time_range():
    from interview_mux.openai_structured_output import (
        compose_envelope_schema,
        load_schema_file,
        min_example_for_stage,
    )

    load_schema_file.cache_clear()
    schema = compose_envelope_schema("content_context", strict=True)
    claim_props = schema["properties"]["artifacts"]["properties"]["key_claims"]["items"][
        "properties"
    ]
    assert "approx_time_range" in claim_props
    assert claim_props["approx_time_range"]["type"] == ["string", "null"]

    example = min_example_for_stage("content_context")
    claim0 = (example.get("artifacts") or {}).get("key_claims") or [{}]
    assert claim0[0].get("approx_time_range") == "05:10-06:05"


def test_assert_openai_strict_schema_raises_with_details():
    with pytest.raises(ValueError, match="missing items"):
        assert_openai_strict_schema({"type": "array"})
