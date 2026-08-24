#!/usr/bin/env python3
"""Catalog unattended breakpoints from contracts, completeness rules, and driver fail keys."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "cross-cutting" / "unattended-breakpoints.json"
DRIVER = ROOT / "tools" / "full_auto_driver.py"
CONTRACTS = ROOT / "docs" / "cross-cutting" / "stage-contracts"

FAIL_KEY_RE = re.compile(
    r"""fail_key\s*=\s*f?(?:'''|\"\"\"|'|")([^'\"]+)"""
)
FAIL_KEY_F_RE = re.compile(r'fail_key\s*=\s*f["\']([^"\']+)["\']')


def _load_contracts() -> list[dict]:
    rows: list[dict] = []
    if not CONTRACTS.is_dir():
        return rows
    try:
        import yaml  # type: ignore
    except ImportError:
        return rows
    for path in sorted(CONTRACTS.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(doc, dict):
            continue
        stage_id = str(doc.get("stage_id") or path.stem)
        outputs = []
        for out in doc.get("outputs") or []:
            if isinstance(out, dict) and out.get("path"):
                outputs.append(str(out["path"]))
        rows.append(
            {
                "id": f"contract:{stage_id}",
                "kind": "stage_contract",
                "stage": stage_id,
                "tier": doc.get("tier"),
                "outputs": outputs,
            }
        )
    return rows


def _completeness_rules() -> list[dict]:
    sys.path.insert(0, str(ROOT / "src"))
    from interview_mux.artifact_completeness import ARTIFACT_COMPLETENESS_RULES
    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
    from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

    rows: list[dict] = []
    for rel, rule in ARTIFACT_COMPLETENESS_RULES.items():
        rows.append(
            {
                "id": f"completeness:{rel}",
                "kind": "completeness_gap_rule",
                "path": rel,
                "rule": getattr(rule, "__name__", str(rule)),
            }
        )
    covered_paths = set(ARTIFACT_COMPLETENESS_RULES)
    for stage, rel in STAGE_ARTIFACT_DISK_PATHS.items():
        if rel in covered_paths:
            continue
        rows.append(
            {
                "id": f"disk_path:{stage}",
                "kind": "stage_artifact_path",
                "stage": stage,
                "path": rel,
                "note": "no dedicated completeness gap rule",
            }
        )
    all_stages = list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
    mapped = set(STAGE_ARTIFACT_DISK_PATHS)
    for sid in all_stages:
        if sid in mapped:
            continue
        rows.append(
            {
                "id": f"no_unattended_check:{sid}",
                "kind": "no_unattended_check",
                "stage": sid,
                "reason": "process/gate stage without primary JSON completeness rule",
            }
        )
    return rows


def _progression_layers() -> list[dict]:
    sys.path.insert(0, str(ROOT / "src"))
    from interview_mux.progression_readiness import Layer  # noqa: F401

    return [
        {
            "id": f"progression_layer:{name}",
            "kind": "progression_layer",
            "layer": name,
        }
        for name in (
            "gate",
            "cross",
            "completeness",
            "preflight",
            "itr",
            "io",
            "schema",
            "sufficiency",
            "audio",
        )
    ]


def _driver_fail_keys() -> list[dict]:
    text = DRIVER.read_text(encoding="utf-8") if DRIVER.is_file() else ""
    keys: list[str] = []
    for rx in (FAIL_KEY_RE, FAIL_KEY_F_RE):
        keys.extend(rx.findall(text))
    # Literal fail_key = "foo:bar"
    keys.extend(re.findall(r'fail_key\s*=\s*"([a-z0-9_.:{}-]+)"', text))
    uniq: list[str] = []
    seen: set[str] = set()
    for k in keys:
        token = k.strip()
        if not token or token in seen:
            continue
        seen.add(token)
        uniq.append(token)
    return [
        {
            "id": f"driver_fail_key:{k}",
            "kind": "driver_fail_key",
            "fail_key": k,
        }
        for k in uniq
    ]


def build_catalog() -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

    breakpoints = []
    breakpoints.extend(_load_contracts())
    breakpoints.extend(_completeness_rules())
    breakpoints.extend(_progression_layers())
    breakpoints.extend(_driver_fail_keys())
    return {
        "version": 1,
        "pipeline_stages": len(ANALYSIS_ORDER) + len(DELIVERY_ORDER),
        "breakpoint_count": len(breakpoints),
        "breakpoints": breakpoints,
    }


def main() -> int:
    check = "--check" in sys.argv
    catalog = build_catalog()
    payload = json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"
    if check:
        if not OUT.is_file():
            print(f"missing {OUT}", file=sys.stderr)
            return 1
        current = OUT.read_text(encoding="utf-8")
        if current != payload:
            print(f"{OUT} is stale — run tools/catalog_unattended_breakpoints.py", file=sys.stderr)
            return 1
        print(f"ok {catalog['breakpoint_count']} breakpoints")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(payload, encoding="utf-8")
    print(f"wrote {OUT} ({catalog['breakpoint_count']} breakpoints)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
