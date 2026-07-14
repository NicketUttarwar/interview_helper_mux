"""Load / validate ASSETS/local_llm/capability_manifest.json from Stage-1 calibrate."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.local_llm_config import (
    capability_manifest_path,
    resolve_model_id,
)


KNOWN_CAPS = frozenset({"LX-01", "LX-02", "LX-03", "LX-04", "LX-05", "LX-06"})


def load_capability_manifest(path: Path | None = None) -> dict[str, Any] | None:
    p = path or capability_manifest_path()
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def enabled_caps_from_manifest(
    manifest: dict[str, Any] | None,
    *,
    default: tuple[str, ...] = ("LX-01", "LX-02"),
) -> frozenset[str]:
    if not manifest:
        return frozenset(default)
    raw = manifest.get("enabled_caps") or []
    if not isinstance(raw, list):
        return frozenset(default)
    caps = {str(x).strip() for x in raw if str(x).strip() in KNOWN_CAPS}
    if not caps:
        return frozenset(default)
    return frozenset(caps)


def write_capability_manifest(data: dict[str, Any], path: Path | None = None) -> Path:
    p = path or capability_manifest_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def degraded_manifest(*, model_id: str | None = None, reason: str = "calibrate_failed") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "model_id": model_id or resolve_model_id(),
        "calibrate_status": "warn",
        "context_length": 0,
        "enabled_caps": ["LX-01"],
        "budgets": {"lx03_max_tokens": 512, "lx05_max_tokens": 768},
        "bench": {"degraded_reason": reason},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def validate_fixture_against_schema(fixture: dict[str, Any], schema_name: str) -> list[str]:
    from interview_mux.llm_response_verify import _validate_against_schema
    from interview_mux.openai_structured_output import load_schema_file

    schema = load_schema_file(schema_name)
    if not schema:
        return [f"missing_schema:{schema_name}"]
    return _validate_against_schema(fixture, schema, prefix=schema_name.replace(".schema.json", ""))
