#!/usr/bin/env python3
"""Verify ElevenLabs API key (reads user info)."""

from __future__ import annotations

import importlib.util
import argparse
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "mux_tools_runtime", Path(__file__).resolve().parent / "_runtime.py"
)
_rt = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_rt)
_rt.bootstrap(tools_file=__file__)

from elevenlabs_mux import get_elevenlabs_client
from pipeline.common import repo_root


def main() -> int:
    p = argparse.ArgumentParser(description="Call ElevenLabs user API to verify API key.")
    p.add_argument("--repo", default=None, help="Repository root (default: auto-detect)")
    args = p.parse_args()
    repo_root_path = Path(args.repo).resolve() if args.repo else repo_root()

    client = get_elevenlabs_client(repo_root=repo_root_path)
    user = client.user.get()
    out: dict[str, object] = {}
    for attr in ("user_id", "subscription", "first_name", "is_new_user"):
        if hasattr(user, attr):
            out[attr] = getattr(user, attr)
    if not out:
        out["repr"] = repr(user)
    print(json.dumps(out, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
