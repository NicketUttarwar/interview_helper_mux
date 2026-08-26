#!/usr/bin/env python3
"""Scan ASSETS/executions for air-order integrity violations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXEC = ROOT / "ASSETS" / "executions"


def _read_json(path: Path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def scan_run(run_dir: Path) -> dict | None:
    sel_path = run_dir / "master" / "selection.json"
    if not sel_path.is_file():
        return None
    sel = _read_json(sel_path)
    if not isinstance(sel, dict):
        return None
    ordered = [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]
    if not ordered:
        return None

    starts: dict[str, int] = {}
    for rel in ("segments/boundaries.json", "segments/manifest.json"):
        doc = _read_json(run_dir / rel.replace("/", "/"))
        if not isinstance(doc, dict):
            continue
        rows = list(doc.get("boundaries") or doc.get("segments") or [])
        for row in rows:
            if isinstance(row, dict) and row.get("segment_id"):
                try:
                    starts[str(row["segment_id"])] = int(
                        row.get("start_ms") or row.get("source_start_ms") or 0
                    )
                except (TypeError, ValueError):
                    continue

    sys.path.insert(0, str(ROOT / "src"))
    from interview_mux.air_order_integrity import (
        critical_violations,
        late_opening_cluster_violations,
        reverse_tape_jump_violations,
    )

    violations = reverse_tape_jump_violations(None, ordered, starts=starts or None)
    violations.extend(late_opening_cluster_violations(None, ordered, starts=starts or None))
    critical = critical_violations(violations)
    if not critical:
        return None
    return {
        "run_id": run_dir.name,
        "critical_count": len(critical),
        "violations": critical[:8],
        "has_master": (run_dir / "master" / "master.wav").is_file(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executions", type=Path, default=DEFAULT_EXEC)
    parser.add_argument("--fail-on-critical", action="store_true")
    args = parser.parse_args()
    exec_root: Path = args.executions
    if not exec_root.is_dir():
        print(f"No executions dir: {exec_root}")
        return 0
    hits: list[dict] = []
    for run_dir in sorted(exec_root.glob("exec_*")):
        if not run_dir.is_dir():
            continue
        row = scan_run(run_dir)
        if row:
            hits.append(row)
    if not hits:
        print("No critical air-order integrity violations found.")
        return 0
    for row in hits:
        print(
            f"{row['run_id']}: {row['critical_count']} critical "
            f"(master={'yes' if row.get('has_master') else 'no'})"
        )
        for v in row.get("violations") or []:
            print(f"  - {v.get('message') or v.get('code')}")
    if args.fail_on_critical:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
