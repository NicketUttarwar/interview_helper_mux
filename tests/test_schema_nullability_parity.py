"""CI: artifact schema nullability matches OpenAI composed schemas."""

from __future__ import annotations

import json

import pytest

from interview_mux.openai_structured_output import composed_cache_dir
from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS, _load_schema
from interview_mux.schema_nullability import with_nullable_optional_leaves


@pytest.mark.parametrize("stage_key,artifact_file", list(STAGE_ARTIFACT_SCHEMAS.items()))
def test_optional_artifact_fields_allow_null_after_normalization(stage_key: str, artifact_file: str):
    raw = _load_schema(artifact_file)
    assert raw is not None, artifact_file
    normalized = with_nullable_optional_leaves(raw)
    req = set(normalized.get("required") or [])
    for key, prop in (normalized.get("properties") or {}).items():
        if key in req:
            continue
        types = prop.get("type")
        if isinstance(types, list):
            assert "null" in types, f"{stage_key}.{key} optional but null not allowed"


def test_composed_speaker_roles_notes_allows_null():
    path = composed_cache_dir() / "analysis_envelope_speaker_roles.openai.json"
    if not path.is_file():
        pytest.skip("composed schema not generated")
    composed = json.loads(path.read_text())
    art = composed.get("properties", {}).get("artifacts", {})
    notes = (art.get("properties") or {}).get("notes", {})
    types = notes.get("type")
    if isinstance(types, list):
        assert "null" in types
