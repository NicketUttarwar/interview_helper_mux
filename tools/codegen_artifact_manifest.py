#!/usr/bin/env python3
"""Generate unified artifact manifest from prompt_validation registries + stage contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # type: ignore

from interview_mux.prompt_validation import (  # noqa: E402
    ARTIFACT_WRITE_VALIDATORS,
    STAGE_ARTIFACT_DISK_PATHS,
    STAGE_ARTIFACT_SCHEMAS,
)


def _load_contract(stage_id: str) -> dict | None:
    path = ROOT / "docs" / "cross-cutting" / "stage-contracts" / f"{stage_id}.yaml"
    if not path.is_file():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def build_manifest() -> dict:
    by_path: dict[str, dict] = {}
    for stage_id, rel in STAGE_ARTIFACT_DISK_PATHS.items():
        entry = by_path.setdefault(
            rel,
            {
                "schemas_by_producer": {},
                "producers": [],
                "consumers": [],
                "has_write_validator": rel in ARTIFACT_WRITE_VALIDATORS,
            },
        )
        schema = STAGE_ARTIFACT_SCHEMAS.get(stage_id)
        if schema:
            entry["schemas_by_producer"][stage_id] = schema
        if stage_id not in entry["producers"]:
            entry["producers"].append(stage_id)
    contracts_dir = ROOT / "docs" / "cross-cutting" / "stage-contracts"
    if contracts_dir.is_dir():
        for path in sorted(contracts_dir.glob("*.yaml")):
            if path.name.startswith("_"):
                continue
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            stage_id = doc.get("stage_id")
            for out in doc.get("outputs") or []:
                if not isinstance(out, dict):
                    continue
                rel = out.get("path")
                if rel and rel in by_path:
                    by_path[rel].setdefault("schemas_by_producer", {})[stage_id] = out.get("schema")
            for consumer in doc.get("consumers") or []:
                if isinstance(consumer, str):
                    contract = _load_contract(consumer)
                    if not contract:
                        continue
                    for out in contract.get("outputs") or []:
                        if isinstance(out, dict) and out.get("path") in by_path:
                            rel = out["path"]
                            if stage_id not in by_path[rel]["consumers"]:
                                by_path[rel]["consumers"].append(stage_id)
    return {"version": 1, "artifacts": by_path}


def main() -> int:
    manifest = build_manifest()
    out = ROOT / "docs" / "cross-cutting" / "artifact-manifest.json"
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(manifest['artifacts'])} artifacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
