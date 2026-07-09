#!/usr/bin/env python3
"""Export committed run artifacts as regression fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS  # noqa: E402
from interview_mux.run_context import RunContext  # noqa: E402


def export_run_fixtures(run_dir: Path, *, out: Path) -> dict[str, object]:
    ctx = RunContext(run_dir)
    exported: dict[str, object] = {"run_id": ctx.run_id, "artifacts": {}}
    seen: set[str] = set()
    for stage_id, rel in STAGE_ARTIFACT_DISK_PATHS.items():
        if rel in seen or not ctx.artifact_exists(rel):
            continue
        seen.add(rel)
        doc = ctx.read_json(rel)
        exported["artifacts"][rel] = {"stage_id": stage_id, "data": doc}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(exported, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return exported


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="Path to exec_* run directory")
    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        default=ROOT / "tests" / "fixtures" / "exported_run_artifacts.json",
    )
    args = parser.parse_args()
    result = export_run_fixtures(args.run_dir.resolve(), out=args.out)
    print(f"Exported {len(result['artifacts'])} artifacts → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
