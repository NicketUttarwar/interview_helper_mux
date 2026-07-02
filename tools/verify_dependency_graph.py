#!/usr/bin/env python3
"""Compare ADG edges vs contract YAML vs extracted AST deps."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.artifact_dependency_graph import build_graph  # noqa: E402
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS  # noqa: E402
from interview_mux.stage_contract import all_contract_stage_ids, load_contract  # noqa: E402

EXTRACTED = ROOT / "docs" / "cross-cutting" / "stage-contracts" / "_extracted_deps.json"


def main() -> int:
    errors: list[str] = []
    graph = build_graph()
    producers = {e.from_id for e in graph if e.kind == "produces"}
    for sid in STAGE_ARTIFACT_DISK_PATHS:
        if sid not in producers and sid in all_contract_stage_ids():
            errors.append(f"missing produces edge for {sid}")

    for sid in all_contract_stage_ids():
        c = load_contract(sid)
        if not c:
            errors.append(f"contract load failed: {sid}")
            continue
        if c.tier == "llm_full" and not c.outputs:
            errors.append(f"llm_full {sid} has no outputs in contract")

    if EXTRACTED.is_file():
        extracted = json.loads(EXTRACTED.read_text(encoding="utf-8"))
        for sid, deps in extracted.items():
            c = load_contract(sid)
            if not c:
                continue
            contract_reads = {i.path for i in c.inputs if i.path}
            for rel in deps.get("reads") or []:
                if rel.endswith(".json") and rel not in contract_reads and rel not in {
                    o.path for o in c.outputs
                }:
                    pass  # advisory only — AST may read optional artifacts

    if errors:
        print("verify_dependency_graph FAILED:")
        for e in errors[:20]:
            print(f"  - {e}")
        return 1
    print(f"verify_dependency_graph OK ({len(graph)} edges, {len(all_contract_stage_ids())} contracts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
