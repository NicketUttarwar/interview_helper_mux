#!/usr/bin/env python3
"""Diff STAGE_PLANS in code against context-padding.md per-stage table."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from interview_mux.context_volley import STAGE_PLANS  # noqa: E402

DOC = REPO / "docs" / "cross-cutting" / "context-padding.md"


def _parse_doc_table() -> dict[str, dict[str, str]]:
    text = DOC.read_text(encoding="utf-8")
    rows: dict[str, dict[str, str]] = {}
    in_table = False
    for line in text.splitlines():
        if line.startswith("| `") and "Prior conclusions" in text:
            in_table = True
        if not in_table:
            if line.startswith("| `") and "Stage |" in line:
                in_table = True
            continue
        if not line.startswith("| `"):
            if in_table and line.strip() == "":
                break
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 5:
            continue
        stage = parts[1].strip("` ")
        if not stage or stage == "Stage":
            continue
        rows[stage] = {
            "prior": parts[2],
            "profile": parts[3],
            "investigations": parts[4],
        }
    return rows


def main() -> int:
    doc_rows = _parse_doc_table()
    errors: list[str] = []
    for stage, plan in STAGE_PLANS.items():
        if stage not in doc_rows:
            errors.append(f"missing in doc table: {stage}")
            continue
        doc_prior = doc_rows[stage]["prior"]
        if doc_prior.lower() == "none":
            expected: tuple[str, ...] = ()
        else:
            expected = tuple(
                s.strip().replace(" ", "_")
                for s in doc_prior.split(",")
                if s.strip()
            )
        if tuple(plan.prior_stages) != expected:
            errors.append(
                f"{stage} prior_stages: code={plan.prior_stages} doc={expected}"
            )
    for stage in doc_rows:
        if stage not in STAGE_PLANS:
            errors.append(f"doc table has unknown stage: {stage}")
    if errors:
        print("STAGE_PLANS / context-padding.md drift detected:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("STAGE_PLANS matches context-padding.md table.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
