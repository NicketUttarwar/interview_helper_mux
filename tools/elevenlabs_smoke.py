#!/usr/bin/env python3
"""Verify ElevenLabs API key (reads user info)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo / "ai" / "python"))

    p = argparse.ArgumentParser(description="Call ElevenLabs user API to verify API key.")
    p.add_argument("--repo", default=str(repo), help="Repository root")
    args = p.parse_args()
    repo_root = Path(args.repo).resolve()

    from elevenlabs_mux import get_elevenlabs_client

    client = get_elevenlabs_client(repo_root=repo_root)
    user = client.user.get()
    # SDK returns a model object; dump common fields if present
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
