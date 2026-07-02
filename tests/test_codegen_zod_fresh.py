"""Fail when generated Zod schemas are stale vs JSON source schemas."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CODEGEN = REPO / "tools" / "codegen_zod_schemas.py"
OUT_DIR = REPO / "frontend" / "src" / "schemas" / "generated"


def test_codegen_zod_schemas_is_fresh():
    before = {p.name: p.read_text(encoding="utf-8") for p in OUT_DIR.glob("*.ts")}
    proc = subprocess.run(
        [sys.executable, str(CODEGEN)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    after = {p.name: p.read_text(encoding="utf-8") for p in OUT_DIR.glob("*.ts")}
    assert before == after, "frontend/src/schemas/generated is stale — run tools/codegen_zod_schemas.py"
