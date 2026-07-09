"""Verify generated artifact manifest matches live registries."""

from __future__ import annotations

import json
from pathlib import Path

from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS, STAGE_ARTIFACT_SCHEMAS

MANIFEST = Path(__file__).resolve().parents[1] / "docs" / "cross-cutting" / "artifact-manifest.json"


def test_artifact_manifest_matches_stage_disk_paths():
    if not MANIFEST.is_file():
        import pytest

        pytest.skip("Run tools/codegen_artifact_manifest.py first")
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    artifacts = doc.get("artifacts") or {}
    for stage_id, rel in STAGE_ARTIFACT_DISK_PATHS.items():
        assert rel in artifacts, f"missing manifest entry for {rel}"
        entry = artifacts[rel]
        assert stage_id in (entry.get("producers") or []), f"{stage_id} not producer of {rel}"
        schema = STAGE_ARTIFACT_SCHEMAS.get(stage_id)
        if schema:
            by_schema = (entry.get("schemas_by_producer") or {})
            assert by_schema.get(stage_id) == schema
