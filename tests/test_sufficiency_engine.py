from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS
from interview_mux.sufficiency_engine import evaluate

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sufficiency"


@pytest.mark.parametrize("stage_key", sorted(STAGE_ARTIFACT_SCHEMAS.keys()))
def test_llm_stage_has_default_or_contract_rules(stage_key: str):
    art = {"thesis": "x" * 12, "topics": [{}], "speakers": [{}], "segments": [{}], "boundaries": [{}]}
    findings = evaluate(stage_key, art, None)
    assert isinstance(findings, list)


def test_content_context_pass_fixture():
    data = json.loads((FIXTURES / "content_context" / "pass.json").read_text())
    blocking = [f for f in evaluate("content_context", data, None) if f.blocking]
    assert not blocking


def test_content_context_fail_empty_thesis():
    data = json.loads((FIXTURES / "content_context" / "fail_empty_thesis.json").read_text())
    blocking = [f for f in evaluate("content_context", data, None) if f.blocking]
    assert blocking


def test_speaker_roles_pass():
    data = json.loads((FIXTURES / "speaker_roles" / "pass.json").read_text())
    assert not [f for f in evaluate("speaker_roles", data, None) if f.blocking]


def test_speaker_roles_fail_all_unknown():
    data = json.loads((FIXTURES / "speaker_roles" / "fail_all_unknown.json").read_text())
    assert [f for f in evaluate("speaker_roles", data, None) if f.blocking]
