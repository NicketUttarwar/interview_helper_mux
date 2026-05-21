#!/usr/bin/env python3
"""Minimal OpenAI connectivity check using repo config (see config/README.md)."""

from __future__ import annotations

import importlib.util
import argparse
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "mux_tools_runtime", Path(__file__).resolve().parent / "_runtime.py"
)
_rt = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_rt)
_rt.bootstrap(tools_file=__file__)

from openai_mux import get_openai_client, load_openai_settings
from openai_mux.prompts import smoke_connectivity_system_prompt
from pipeline.common import repo_root


def main() -> int:
    p = argparse.ArgumentParser(description="Call OpenAI once to verify credentials and model.")
    p.add_argument("--repo", default=None, help="Repository root (default: auto-detect)")
    args = p.parse_args()
    repo_root_path = Path(args.repo).resolve() if args.repo else repo_root()

    settings = load_openai_settings(repo_root=repo_root_path)
    client = get_openai_client(repo_root=repo_root_path)
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
