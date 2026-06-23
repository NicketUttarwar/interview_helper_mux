#!/usr/bin/env python3
"""Fail when code references action_id values missing from operator_action_catalog.json."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "docs" / "cross-cutting" / "operator_action_catalog.json"
SCAN_DIRS = [ROOT / "src" / "interview_mux", ROOT / "frontend" / "src"]

PATTERNS = [
    re.compile(r'action_id\s*=\s*["\']([^"\']+)["\']'),
    re.compile(r'"action_id"\s*:\s*["\']([^"\']+)["\']'),
    re.compile(r"data-action-id=[\"']([^\"']+)[\"']"),
    re.compile(r'data-action-id=\{["\']([^"\']+)["\']\}'),
]


def load_catalog_ids() -> set[str]:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    return {str(e["action_id"]) for e in data if isinstance(e, dict) and e.get("action_id")}


def scan_refs() -> set[str]:
    refs: set[str] = set()
    for base in SCAN_DIRS:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"}:
                continue
            if "node_modules" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for pat in PATTERNS:
                refs.update(pat.findall(text))
    return refs


def main() -> int:
    if not CATALOG.is_file():
        print(f"Missing catalog: {CATALOG}", file=sys.stderr)
        return 1
    catalog = load_catalog_ids()
    refs = scan_refs()
    missing = sorted(refs - catalog)
    if missing:
        print("Unknown action_id references (add to operator_action_catalog.json):", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 1
    print(f"OK — {len(refs)} action_id references match catalog ({len(catalog)} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
