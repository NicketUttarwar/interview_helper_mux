"""Smoke test for Zod schema codegen."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CODEGEN = REPO / "tools" / "codegen_zod_schemas.py"
OUT_INDEX = REPO / "frontend" / "src" / "schemas" / "generated" / "index.ts"


def test_codegen_zod_schemas_writes_registry():
    proc = subprocess.run(
        [sys.executable, str(CODEGEN)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert OUT_INDEX.is_file()
    text = OUT_INDEX.read_text(encoding="utf-8")
    assert "sound_design/placement_adjustments.json" in text
    assert "run_meta.json" in text
