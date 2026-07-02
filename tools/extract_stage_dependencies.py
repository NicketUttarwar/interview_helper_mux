#!/usr/bin/env python3
"""AST scan for artifact read/write dependencies per stage module."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "cross-cutting" / "stage-contracts" / "_extracted_deps.json"


def _scan_file(path: Path) -> dict[str, list[str]]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    reads: set[str] = set()
    writes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = ""
            if isinstance(fn, ast.Attribute):
                name = fn.attr
            elif isinstance(fn, ast.Name):
                name = fn.id
            if name in ("read_json", "artifact_exists", "read_json_required") and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    reads.add(arg.value)
            if name in ("write_json", "write_text") and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    writes.add(arg.value)
    return {"reads": sorted(reads), "writes": sorted(writes)}


def main() -> int:
    stages_dir = ROOT / "src" / "interview_mux" / "stages"
    out: dict[str, dict[str, list[str]]] = {}
    for path in sorted(stages_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        out[path.stem] = _scan_file(path)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(out)} modules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
