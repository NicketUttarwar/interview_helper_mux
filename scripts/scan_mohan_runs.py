#!/usr/bin/env python3
"""Scan mohan (d19c15b58ab4) executions — era tags and stall verdicts."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXEC = ROOT / "ASSETS" / "executions"
HASH = "d19c15b58ab4"


def _era(ts: datetime) -> str:
    if ts < datetime(2026, 8, 27):
        return "A"
    if ts < datetime(2026, 8, 29):
        return "B-C"
    if ts < datetime(2026, 9, 1):
        return "D"
    if ts < datetime(2026, 9, 1, 18):
        return "E"
    if ts < datetime(2026, 9, 2):
        return "F"
    return "G"


def main() -> int:
    rows: list[str] = []
    for d in sorted(EXEC.glob(f"exec_*{HASH}*")):
        master = (d / "master/master.wav").is_file()
        done = len(list((d / ".stage_done").glob("*"))) if (d / ".stage_done").is_dir() else 0
        m = re.search(r"(\d{8}T\d{6}Z)$", d.name)
        ts = datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ") if m else datetime.min
        meta = {}
        rm = d / "run_meta.json"
        if rm.is_file():
            meta = json.loads(rm.read_text(encoding="utf-8"))
        git_sha = str(meta.get("git_sha") or "")[:12]
        rows.append(
            f"{d.name} | ship={'Y' if master else 'N'} | done={done} | era={_era(ts)} | git={git_sha}"
        )
    print(f"Mohan runs ({HASH}): {len(rows)}")
    for r in rows:
        print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
