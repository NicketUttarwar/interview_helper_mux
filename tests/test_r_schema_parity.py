"""Residual schema parity — sound_design_vo_finalize + junction_snip_qa.

Asserts on-disk JSON Schema files exist and validate minimal documents via
prompt_validation write validators (MUX_FORENSICS=0).
"""

from __future__ import annotations

from pathlib import Path

from interview_mux.prompt_validation import (
    ARTIFACT_WRITE_VALIDATORS,
    STAGE_ARTIFACT_DISK_PATHS,
    STAGE_ARTIFACT_SCHEMAS,
    validate_junction_snip_qa,
    validate_sound_design_vo_finalize,
)

_REPO = Path(__file__).resolve().parents[1]
_SCHEMAS = _REPO / "docs" / "cross-cutting" / "json-schemas" / "artifacts"

_TARGETS = (
    (
        "sound_design_vo_finalize",
        "mastering/sound_design_vo_finalize.json",
        "sound_design_vo_finalize.schema.json",
        validate_sound_design_vo_finalize,
        {"skipped": True, "refused": False, "reason": "no_vo_bridge_cues"},
    ),
    (
        "junction_snip_qa",
        "master/junction_snip_qa.json",
        "junction_snip_qa.schema.json",
        validate_junction_snip_qa,
        {"version": 1, "generated_at": "2026-09-15T00:00:00Z", "findings": []},
    ),
)


def test_r_schema_files_exist_and_are_registered() -> None:
    for stage, disk, schema_name, validator, _doc in _TARGETS:
        path = _SCHEMAS / schema_name
        assert path.is_file(), f"missing schema {path}"
        assert STAGE_ARTIFACT_DISK_PATHS.get(stage) == disk
        assert STAGE_ARTIFACT_SCHEMAS.get(stage) == schema_name
        assert ARTIFACT_WRITE_VALIDATORS.get(disk) is validator


def test_r_schema_minimal_docs_validate() -> None:
    for _stage, _disk, _schema_name, validator, doc in _TARGETS:
        errs = validator(doc)
        assert errs == [], f"{_schema_name}: {errs}"


def test_r_schema_minimal_docs_reject_hollow() -> None:
    assert validate_sound_design_vo_finalize({}) != []
    assert validate_junction_snip_qa({}) != []
