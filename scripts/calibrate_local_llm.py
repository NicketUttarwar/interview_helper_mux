#!/usr/bin/env python3
"""Stage-1: calibrate local LLM capabilities after model selection.

Writes ASSETS/local_llm/capability_manifest.json.
Non-fatal by design — degraded manifest on failure (bootstrap WARN).

Usage:
  python scripts/calibrate_local_llm.py
  python scripts/calibrate_local_llm.py --dry-run
  python scripts/calibrate_local_llm.py --refresh
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.local_capability_manifest import (  # noqa: E402
    degraded_manifest,
    validate_fixture_against_schema,
    write_capability_manifest,
)
from interview_mux.local_llm_config import (  # noqa: E402
    capability_manifest_path,
    lx03_min_verify_rate,
    lx04_min_agreement,
    lx05_min_verify_rate,
    max_enabled_caps,
    resolve_model_id,
)
from interview_mux.local_llm_selection import load_selection_manifest  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "local_llm"

_FIXTURE_SCHEMAS = (
    ("framer_ok.json", "local_framer_response.schema.json", "framer_verify_rate"),
    ("compressor_ok.json", "local_digest_compressor.schema.json", "compressor_verify_rate"),
    ("escalate_advisory_ok.json", "local_escalate_advisory.schema.json", "advisory_verify_rate"),
    ("shard_prep_ok.json", "local_shard_packet_prep.schema.json", "shard_prep_verify_rate"),
    ("planner_ok.json", "local_capability_planner.schema.json", "planner_verify_rate"),
)


def _load_fixture(name: str) -> dict:
    path = FIXTURES / name
    return json.loads(path.read_text(encoding="utf-8"))


def run_offline_scorecard() -> dict[str, float]:
    scores: dict[str, float] = {}
    for fname, schema, key in _FIXTURE_SCHEMAS:
        path = FIXTURES / fname
        if not path.is_file():
            scores[key] = 0.0
            continue
        errs = validate_fixture_against_schema(_load_fixture(fname), schema)
        scores[key] = 1.0 if not errs else 0.0
    # Advisory agreement with "must escalate on high severity" golden = 1.0 when fixture ok
    scores["escalate_agreement"] = scores.get("advisory_verify_rate", 0.0)
    return scores


def select_enabled_caps(scores: dict[str, float], *, context_length: int) -> list[str]:
    enabled: list[str] = ["LX-01", "LX-02"]
    ceiling = max_enabled_caps()
    if scores.get("compressor_verify_rate", 0.0) >= lx03_min_verify_rate() and context_length >= 4096:
        enabled.append("LX-03")
    if scores.get("escalate_agreement", 0.0) >= lx04_min_agreement():
        enabled.append("LX-04")
    if (
        scores.get("shard_prep_verify_rate", 0.0) >= lx05_min_verify_rate()
        and context_length >= 8192
        and len(enabled) < ceiling
    ):
        enabled.append("LX-05")
    return enabled[:ceiling]


def build_manifest(*, dry_run: bool = False) -> dict:
    selection = load_selection_manifest() or {}
    model_id = str(selection.get("model_id") or resolve_model_id())
    context_length = int(selection.get("context_length") or 8192)
    scores = run_offline_scorecard()
    enabled = select_enabled_caps(scores, context_length=context_length)
    status = "ok" if scores.get("framer_verify_rate", 0) >= 1.0 else "warn"
    manifest = {
        "schema_version": 1,
        "model_id": model_id,
        "calibrate_status": status,
        "context_length": context_length,
        "enabled_caps": enabled,
        "budgets": {
            "lx03_max_tokens": 512,
            "lx04_max_tokens": 256,
            "lx05_max_tokens": 768,
            "planner_max_tokens": 400,
        },
        "bench": {**scores, "dry_run": dry_run},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate local LLM capability manifest")
    parser.add_argument("--dry-run", action="store_true", help="Print scorecard; do not write manifest")
    parser.add_argument("--refresh", action="store_true", help="Overwrite existing manifest")
    args = parser.parse_args()

    out = capability_manifest_path()
    if out.is_file() and not args.refresh and not args.dry_run:
        print(f"Manifest exists: {out} (pass --refresh to overwrite)")
        print(out.read_text(encoding="utf-8"))
        return 0

    try:
        manifest = build_manifest(dry_run=args.dry_run)
    except Exception as exc:
        print(f"WARN: calibrate failed: {exc}", file=sys.stderr)
        manifest = degraded_manifest(reason=str(exc))
        if args.dry_run:
            print(json.dumps(manifest, indent=2))
            return 0
        write_capability_manifest(manifest)
        print(f"Wrote degraded manifest → {out}")
        return 0

    print("=== Local LLM capability scorecard ===")
    print(json.dumps({k: manifest[k] for k in ("model_id", "calibrate_status", "enabled_caps", "bench")}, indent=2))
    if args.dry_run:
        print("(dry-run — not written)")
        return 0

    write_capability_manifest(manifest)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
