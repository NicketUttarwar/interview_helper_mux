from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.openai_structured_output import compose_envelope_schema, resolve_response_format
from interview_mux.openai_schema_lint import lint_openai_strict_schema
from interview_mux.openai_schema_semantic_lint import lint_openai_semantic_schema
from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "llm_envelopes"


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.json")))
def test_golden_envelope_fixture_has_stage_key(path: Path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert (
        raw.get("stage_key") in STAGE_ARTIFACT_SCHEMAS
        or "expected_substring" in raw
        or "artifacts" in raw
    )


def test_content_context_claim_type_is_string_nullable():
    fmt = resolve_response_format("content_context", "primary")
    claim = (
        fmt["json_schema"]["schema"]["properties"]["artifacts"]["properties"]["key_claims"]["items"][
            "properties"
        ]["claim_type"]
    )
    t = claim.get("type")
    if isinstance(t, list):
        assert "string" in t
        assert "null" in t
    else:
        assert t == "string"


@pytest.mark.parametrize("stage_key", sorted(STAGE_ARTIFACT_SCHEMAS.keys()))
def test_composed_schema_matches_codegen(stage_key: str):
    composed_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "cross-cutting"
        / "json-schemas"
        / "composed"
        / f"analysis_envelope_{stage_key}.openai.json"
    )
    live = compose_envelope_schema(stage_key, strict=True)
    assert lint_openai_strict_schema(live) == []
    assert lint_openai_semantic_schema(live) == []
    if composed_path.is_file():
        on_disk = json.loads(composed_path.read_text(encoding="utf-8"))
        assert on_disk == live
