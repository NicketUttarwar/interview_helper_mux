#!/usr/bin/env python3
"""Audit direct JSON writes that bypass RunContext.write_json."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "interview_mux"

# Allowed patterns (operational / bootstrap).
ALLOWLIST = {
    "run_context.py": {"mutate_run_meta", "init_run_meta"},
    "file_store.py": set(),
    "session_log.py": set(),
    "operator_action_trace.py": set(),
    "llm_call_record.py": set(),
    "stage_execution_reuse.py": set(),
    "application_session.py": set(),
    "operator_snapshots.py": {"record_action_trace_manifest"},
    "write_staging.py": {"write_pending_content", "flush_stage_writes"},
    "audio_preclean.py": set(),
    "vo_pickup_trim.py": set(),
    "placement_qa.py": set(),
    "mmaudio_asset_qa.py": set(),
}

PATTERNS = [
    re.compile(r"fs_write_json\s*\("),
    re.compile(r"file_store\.write_json\s*\("),
    re.compile(r"write_text\s*\(\s*json\.dumps"),
    re.compile(r"\.write_text\s*\(\s*json\.dumps"),
]

def main() -> int:
    violations: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC)
        text = path.read_text(encoding="utf-8")
        if "write_json(" not in text and "json.dumps" not in text:
            continue
        for pat in PATTERNS:
            if pat.search(text):
                allowed = ALLOWLIST.get(path.name)
                if allowed is not None:
                    continue
                if "ctx.write_json" in text and pat.pattern.startswith("write_json"):
                    continue
                violations.append(f"{rel}: {pat.pattern}")
                break
    if violations:
        print("Direct JSON I/O audit — review required:")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("Direct JSON I/O audit — no unlisted bypasses found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
