"""Artifacts are conformed to their own schema before a refused write is final (ISSUES 169).

Client run: full_master_ranking stopped because master/selection.json refused
``media_ip_cta[1].mixed_with_story: null`` (the LLM envelope allows null, the
selection schema does not), and the CTA lock re-applied the null on every retry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.media_ip_cta import extract_judgments, normalize_media_ip_cta_rows
from interview_mux.schema_conform import artifact_schema_for, conform_to_schema

SCHEMA = {
    "type": "object",
    "required": ["flag", "rows", "name"],
    "additionalProperties": False,
    "properties": {
        "flag": {"type": "boolean"},
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id"],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "mixed": {"type": "boolean"},
                    "region": {"type": "string", "enum": ["start", "end"]},
                    "n": {"type": "integer"},
                },
            },
        },
        "name": {"type": "string"},
        "note": {"type": ["string", "null"]},
    },
}


def test_conform_repairs_what_the_schema_states() -> None:
    doc = {
        "flag": None,
        "rows": [None, {"id": "a", "mixed": None, "region": "End", "n": "3", "junk": 1}],
        "name": "x",
        "note": None,
        "extra": True,
    }
    out, notes = conform_to_schema(doc, SCHEMA)
    assert out == {"flag": False, "rows": [{"id": "a", "region": "end", "n": 3}], "name": "x", "note": None}
    assert notes and doc["flag"] is None  # input untouched


def test_required_string_null_is_left_to_fail() -> None:
    out, _ = conform_to_schema({"flag": True, "rows": [], "name": None}, SCHEMA)
    assert out["name"] is None


def test_valid_document_is_unchanged() -> None:
    doc = {"flag": True, "rows": [{"id": "a", "mixed": False}], "name": "x"}
    out, notes = conform_to_schema(doc, SCHEMA)
    assert out == doc and notes == []


def test_cta_null_and_case_handled_by_normalizer_and_lock() -> None:
    rows = [{"segment_id": "seg_035", "clearly_media_ip_pitch": True, "mixed_with_story": None, "cta_region": "End", "must_keep_in_clip": "false"}]
    row = normalize_media_ip_cta_rows({"media_ip_cta": rows})["media_ip_cta"][0]
    assert "mixed_with_story" not in row and row["cta_region"] == "end" and row["must_keep_in_clip"] is False
    # _reapply_locked reads judgments through extract_judgments
    locked = extract_judgments({"media_ip_cta": rows})
    assert locked and "mixed_with_story" not in locked[0]


def test_every_schema_backed_writer_is_covered() -> None:
    from interview_mux import prompt_validation as pv

    missing = [r for r in pv.ARTIFACT_WRITE_VALIDATORS if artifact_schema_for(r) is None]
    assert missing == ["mastering/research/waves.json"]


def test_write_json_admits_a_conformable_document(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from run_fixtures import isolated_run_ctx

    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "exec_conform")
    doc = {
        "verdict": "pass",
        "blocking_issues": [None],
        "warnings": [],
        "recommended_actions": [],
        "reasoning_summary": "ok",
        "repair_attempted": "true",
    }
    ctx.write_json("master/edl_narrative_audit.json", doc, skip_handoff=True)
    stored = ctx.read_json("master/edl_narrative_audit.json")
    assert stored["blocking_issues"] == []
