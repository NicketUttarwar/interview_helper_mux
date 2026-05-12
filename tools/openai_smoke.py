#!/usr/bin/env python3
"""Minimal OpenAI connectivity check using repo config (see config/README.md)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo / "ai" / "python"))

    p = argparse.ArgumentParser(description="Call OpenAI once to verify credentials and model.")
    p.add_argument("--repo", default=str(repo), help="Repository root")
    args = p.parse_args()
    repo_root = Path(args.repo).resolve()

    from openai_mux import get_openai_client, load_openai_settings
    from openai_mux.prompts import smoke_connectivity_system_prompt

    settings = load_openai_settings(repo_root=repo_root)
    client = get_openai_client(repo_root=repo_root)
    r = client.chat.completions.create(
        model=settings.model,
        messages=[
            {"role": "system", "content": smoke_connectivity_system_prompt()},
            {"role": "user", "content": "Reply with exactly: ok"},
        ],
        max_tokens=16,
    )
    text = (r.choices[0].message.content or "").strip()
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
