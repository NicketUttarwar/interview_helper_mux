#!/usr/bin/env python3
"""Diff app.defaults.json keys against config-keys.md documentation rows."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = ROOT / "config" / "app.defaults.json"
DOC = ROOT / "docs" / "cross-cutting" / "config-keys.md"
SCHEMA = ROOT / "docs" / "cross-cutting" / "json-schemas" / "app_config.schema.json"
SECRETS_EXAMPLE = ROOT / "config" / "secrets" / "secrets.env.example"

NESTED_DOC_KEYS = (
    "analysis.sufficiency.enabled",
    "analysis.sufficiency.default_blocking_tier",
    "analysis.sufficiency.per_stage_overrides",
    "analysis.artifact_lifecycle.fingerprint_enabled",
    "analysis.artifact_lifecycle.post_commit_validate",
    "analysis.artifact_lifecycle.read_stale_guard",
    "analysis.artifact_lifecycle.reuse_validate",
    "analysis.artifact_contract.enabled",
    "analysis.artifact_contract.contracts_dir",
    "analysis.artifact_contract.verify_on_ci",
)


def _doc_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for line in text.splitlines():
        if line.strip().startswith("|"):
            for m in re.finditer(r"`([^`]+)`", line):
                keys.add(m.group(1).strip())
        m2 = re.match(r"^## `([^`]+)`", line)
        if m2:
            keys.add(m2.group(1).strip())
    return keys


def _validate_subset_schema(defaults: dict) -> list[str]:
    errors: list[str] = []
    if not SCHEMA.is_file():
        return errors
    try:
        import jsonschema
    except ImportError:
        return errors
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(defaults, schema)
    except jsonschema.ValidationError as exc:
        errors.append(str(exc.message))
    return errors


def main() -> int:
    if not DEFAULTS.is_file():
        print(f"Missing {DEFAULTS}", file=sys.stderr)
        return 1
    defaults = json.loads(DEFAULTS.read_text(encoding="utf-8"))
    top_level = {k for k in defaults if not str(k).startswith("_comment")}
    doc_keys = _doc_keys(DOC.read_text(encoding="utf-8")) if DOC.is_file() else set()
    if SECRETS_EXAMPLE.is_file():
        for line in SECRETS_EXAMPLE.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                keys = line.split("=", 1)[0].strip()
                if keys:
                    doc_keys.add(keys)

    missing_doc: list[str] = []
    for key in sorted(top_level):
        if key in doc_keys:
            continue
        if any(d.startswith(f"{key}.") or d == key for d in doc_keys):
            continue
        missing_doc.append(key)

    missing_nested = [k for k in NESTED_DOC_KEYS if k not in doc_keys]
    schema_errors = _validate_subset_schema(defaults)

    if missing_doc:
        print("Top-level app.defaults.json namespaces missing from config-keys.md:", file=sys.stderr)
        for k in missing_doc:
            print(f"  - {k}", file=sys.stderr)
    if missing_nested:
        print("Nested analysis keys missing from config-keys.md:", file=sys.stderr)
        for k in missing_nested:
            print(f"  - {k}", file=sys.stderr)
    if schema_errors:
        print("app_config.schema.json validation errors:", file=sys.stderr)
        for e in schema_errors:
            print(f"  - {e}", file=sys.stderr)

    if missing_doc or missing_nested or schema_errors:
        return 1

    print(
        f"OK — {len(top_level)} top-level namespaces + {len(NESTED_DOC_KEYS)} nested analysis keys documented"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
