from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from interview_mux.openai_schema_lint import lint_openai_strict_schema
from interview_mux.openai_structured_output import composed_cache_dir
from interview_mux.prompt_validation import STAGE_ARTIFACT_SCHEMAS

REPO = Path(__file__).resolve().parents[1]
CODEGEN = REPO / "tools" / "codegen_openai_schemas.py"


def test_codegen_openai_schemas_is_fresh():
    before = {
        p.name: p.read_text(encoding="utf-8")
        for p in composed_cache_dir().glob("*.openai.json")
    }
    proc = subprocess.run(
        [sys.executable, str(CODEGEN)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    after = {
        p.name: p.read_text(encoding="utf-8")
        for p in composed_cache_dir().glob("*.openai.json")
    }
    assert before == after, "composed/*.openai.json is stale — run tools/codegen_openai_schemas.py"


@pytest.mark.parametrize("stage_key", sorted(STAGE_ARTIFACT_SCHEMAS.keys()))
def test_composed_envelope_files_lint_clean(stage_key: str):
    path = composed_cache_dir() / f"analysis_envelope_{stage_key}.openai.json"
    assert path.is_file(), f"missing composed schema for {stage_key}"
    schema = json.loads(path.read_text(encoding="utf-8"))
    errors = lint_openai_strict_schema(schema)
    assert errors == [], f"{stage_key}: {errors}"
