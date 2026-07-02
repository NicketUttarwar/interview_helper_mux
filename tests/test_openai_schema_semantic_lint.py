from __future__ import annotations

import pytest

from interview_mux.openai_schema_semantic_lint import (
    assert_openai_semantic_schema,
    lint_openai_semantic_schema,
    resolve_effective_type,
)
from interview_mux.openai_structured_output import compose_envelope_schema
from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS


def test_enum_on_object_without_properties_rejected():
    bad = {"type": "object", "enum": ["fact", "opinion"]}
    errors = lint_openai_semantic_schema(bad, path="claim_type")
    assert any("enum on type object" in e for e in errors)


def test_enum_string_inferred():
    node = {"enum": ["fact", "opinion"]}
    assert resolve_effective_type(node) == "string"
    assert lint_openai_semantic_schema(node) == []


def test_assert_raises_on_bad_schema():
    with pytest.raises(ValueError, match="semantic schema lint failed"):
        assert_openai_semantic_schema({"type": "object", "enum": ["a"]})


@pytest.mark.parametrize("stage_key", sorted(STAGE_ARTIFACT_SCHEMAS.keys()))
def test_all_llm_envelopes_pass_semantic_lint(stage_key: str):
    schema = compose_envelope_schema(stage_key, strict=True)
    assert lint_openai_semantic_schema(schema) == []
