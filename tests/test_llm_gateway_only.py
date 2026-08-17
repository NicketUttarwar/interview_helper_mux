"""Ensure OpenAI client usage stays in approved gateway modules."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src" / "interview_mux"

ALLOWED = {
    SRC / "stages" / "llm_runner.py",
    SRC / "homunculus" / "loop.py",
    SRC / "safe_pruning.py",
    # Podcast cover cascade (DALL·E + vision pick) — see docs/cross-cutting/podcast-cover-theme.md
    SRC / "podcast_rss" / "openai_cover.py",
    SRC / "podcast_rss" / "cover_vision.py",
}

PATTERNS = [
    re.compile(r"from openai import OpenAI"),
    re.compile(r"OpenAI\(api_key"),
    re.compile(r"client\.chat\.completions\.create"),
]


def test_no_openai_outside_llm_runner():
    violations: list[str] = []
    for path in SRC.rglob("*.py"):
        if path in ALLOWED:
            continue
        text = path.read_text(encoding="utf-8")
        for pat in PATTERNS:
            if pat.search(text):
                violations.append(f"{path.relative_to(REPO)}: {pat.pattern}")
    assert violations == [], (
        "OpenAI calls must go through llm_runner.py / homunculus/loop.py:\n" + "\n".join(violations)
    )
