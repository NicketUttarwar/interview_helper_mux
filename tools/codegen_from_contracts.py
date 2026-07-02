#!/usr/bin/env python3
"""Generate contract index artifacts: mermaid ADG + drift report."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_mux.artifact_dependency_graph import build_graph  # noqa: E402
from interview_mux.stage_contract import all_contract_stage_ids, load_contract  # noqa: E402

OUT_DIR = ROOT / "docs" / "cross-cutting" / "stage-contracts"


def main() -> int:
    edges = build_graph()
    lines = ["```mermaid", "flowchart LR"]
    seen: set[tuple[str, str, str]] = set()
    for e in edges:
        if e.kind not in ("invalidates", "requires", "consumes"):
            continue
        key = (e.kind, e.from_id, e.to_id)
        if key in seen:
            continue
        seen.add(key)
        label = e.kind[0].upper()
        lines.append(f'  {e.from_id} -->|{label}| {e.to_id}')
    lines.append("```")
    (OUT_DIR / "ADG.mmd").write_text("\n".join(lines) + "\n", encoding="utf-8")

    drift: list[str] = []
    for sid in all_contract_stage_ids():
        c = load_contract(sid)
        if not c:
            drift.append(f"missing contract body: {sid}")
        elif c.tier == "llm_full" and not c.sufficiency:
            drift.append(f"llm_full without sufficiency rules: {sid}")

    report = OUT_DIR / "drift-report.md"
    body = ["# Contract drift report\n", f"Contracts: {len(all_contract_stage_ids())}\n"]
    if drift:
        body.append("## Warnings\n")
        for d in drift[:40]:
            body.append(f"- {d}\n")
    else:
        body.append("No drift warnings.\n")
    report.write_text("".join(body), encoding="utf-8")
    print(f"wrote {OUT_DIR / 'ADG.mmd'} and {report.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
