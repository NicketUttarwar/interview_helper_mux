#!/usr/bin/env python3
"""CI: quality_status Python frozenset must match PMQ/scorecard schema enums.

Also forbids hardcoded ``advisory_fail`` string literals under ``src/interview_mux/``
except ``quality_status.py`` (writers/readers must use the vocabulary module).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO / "src" / "interview_mux"
ALLOWED_LITERAL_FILES = frozenset(
    {
        "quality_status.py",
    }
)
# Wire token — only quality_status.py may embed this literal in src/.
_ADVISORY_LITERAL = re.compile(r"""['"]advisory_fail['"]""")

GENERATED_ZOD_REQUIRED = (
    "frontend/src/schemas/generated/master_post_master_quality_jsonSchema.ts",
    "frontend/src/schemas/generated/master_listener_scorecard_jsonSchema.ts",
)


def _enum_from_schema(path: Path, prop: str) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    props = (data.get("properties") or {}).get(prop) or {}
    enum = props.get("enum")
    if not isinstance(enum, list):
        raise SystemExit(f"{path}: missing enum for properties.{prop}")
    return {str(x) for x in enum}


def _scan_hardcoded_advisory_literals() -> list[str]:
    hits: list[str] = []
    if not SRC_ROOT.is_dir():
        return [f"missing {SRC_ROOT}"]
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if path.name in ALLOWED_LITERAL_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            hits.append(f"{path.relative_to(REPO)}: unreadable ({exc})")
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if _ADVISORY_LITERAL.search(line):
                rel = path.relative_to(REPO)
                hits.append(f"{rel}:{i}: hardcoded advisory_fail literal")
    return hits


def main() -> int:
    sys.path.insert(0, str(REPO / "src"))
    from interview_mux.quality_status import (
        QUALITY_STATUS_SCHEMA_ENUM_PATHS,
        QUALITY_STATUS_VALUES,
        STATUS_ADVISORY_FAIL,
    )

    errors: list[str] = []
    py_set = set(QUALITY_STATUS_VALUES)
    if STATUS_ADVISORY_FAIL not in py_set:
        errors.append("quality_status missing STATUS_ADVISORY_FAIL")

    for rel, prop in QUALITY_STATUS_SCHEMA_ENUM_PATHS:
        path = REPO / rel
        if not path.is_file():
            errors.append(f"missing schema {rel}")
            continue
        sch = _enum_from_schema(path, prop)
        if sch != py_set:
            errors.append(
                f"{rel} properties.{prop} enum {sorted(sch)} != "
                f"quality_status {sorted(py_set)}"
            )

    zod_map = REPO / "tools" / "codegen_zod_schemas.py"
    text = zod_map.read_text(encoding="utf-8") if zod_map.is_file() else ""
    if "post_master_quality" not in text or "listener_scorecard" not in text:
        errors.append(
            "tools/codegen_zod_schemas.py must map master/post_master_quality.json "
            "and master/listener_scorecard.json"
        )

    for rel in GENERATED_ZOD_REQUIRED:
        if not (REPO / rel).is_file():
            errors.append(
                f"missing generated Zod schema {rel} — run: "
                "python tools/codegen_zod_schemas.py"
            )

    errors.extend(_scan_hardcoded_advisory_literals())

    if errors:
        print("audit_quality_status_enum FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("audit_quality_status_enum OK:", sorted(py_set))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
