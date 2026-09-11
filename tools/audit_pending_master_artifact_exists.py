#!/usr/bin/env python3
"""Fail if agenda/ship paths use pending-aware master.wav checks outside allowlist.

Wave 10 static guard for major thrash hardening.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "interview_mux"

# Call sites that may still use artifact_exists for UI/status (not walk/ship).
ALLOWLIST = {
    "web/server.py",
    "web/runner.py",
    "journey_state.py",
    "gates.py",
    "homunculus/gates.py",
    "homunculus/ears.py",
    "homunculus/judge.py",
    "asset_transcripts.py",
    "llm_flow_hardening.py",
    "post_master_quality.py",
    # Completeness of finalize itself may probe via artifact_exists for QA.
    "stages/mastering.py",
    "stages/podcast_publish.py",
}

PATTERN = re.compile(
    r"""artifact_exists\(\s*["']master/master\.wav["']\s*\)"""
)


def _code_lines(text: str) -> list[tuple[int, str]]:
    """Yield (lineno, line) skipping module/docstring-ish and comment-only lines."""
    out: list[tuple[int, str]] = []
    in_doc = False
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not in_doc and (stripped.startswith('"""') or stripped.startswith("'''")):
            if stripped.count('"""') >= 2 or stripped.count("'''") >= 2:
                continue
            in_doc = True
            continue
        if in_doc:
            if '"""' in stripped or "'''" in stripped:
                in_doc = False
            continue
        if stripped.startswith("#"):
            continue
        out.append((i, line))
    return out


def main() -> int:
    bad: list[str] = []
    for path in SRC.rglob("*.py"):
        rel = str(path.relative_to(SRC))
        if rel in ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in _code_lines(text):
            if PATTERN.search(line):
                bad.append(f"{rel}:{i}: {line.strip()}")
    if bad:
        print("pending-master artifact_exists outside allowlist:")
        for row in bad:
            print(f"  {row}")
        print(
            "Use delivery_invariants.committed_master_wav for walk/ship decisions."
        )
        return 1
    print("ok: no disallowed artifact_exists('master/master.wav')")
    return 0


if __name__ == "__main__":
    sys.exit(main())
