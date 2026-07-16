#!/usr/bin/env python3
"""Fail CI when new hard timeline slices or undocumented max_* ints appear in src."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "interview_mux"

# Protected modules migrated to ratio/spread policy — must not regress to head slices.
PROTECTED_FILES = frozenset(
    {
        "interview_spine/boundaries.py",
        "coherence/compact.py",
        "value_analysis/extract.py",
        "llm_shard_plans.py",
        "llm_subtasks.py",
    }
)

SLICE_RE = re.compile(r"\[[\s]*:[\s]*(\d+)[\s]*\]")
TIMELINE_HINTS = (
    "segment",
    "boundary",
    "spine",
    "window",
    "risk",
    "investigation",
    "gap",
    "theme",
    "claim",
    "hypoth",
    "entity",
    "flag",
    "event",
)


def _is_timeline_slice(line: str) -> bool:
    low = line.lower()
    if "[:\"" in line or "')[:]" in line or "str(" in low and "[:" in line:
        return False
    if any(h in low for h in TIMELINE_HINTS):
        return True
    if "start_ms" in low or "time_ms" in low:
        return True
    return False


def main() -> int:
    violations: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        if rel not in PROTECTED_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if "spread_sample" in line or "ratio_cap" in line:
                continue
            for m in SLICE_RE.finditer(line):
                n = int(m.group(1))
                if n <= 3:
                    continue
                if _is_timeline_slice(line):
                    violations.append(f"{rel}:{i}: hard slice [:{n}] — {line.strip()[:100]}")
    if violations:
        print("audit_hard_caps: timeline head slices found (use coverage_limits.spread_sample):")
        for v in violations[:40]:
            print(f"  {v}")
        if len(violations) > 40:
            print(f"  ... and {len(violations) - 40} more")
        return 1
    print("audit_hard_caps: OK (no new timeline head slices in scoped files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
