"""Read repo secrets.env for E2E (mirrors interview_mux.config.load_secrets)."""

from __future__ import annotations

import os
from pathlib import Path


def load_secrets(repo_root: Path) -> dict[str, str]:
    path = repo_root / "config" / "secrets" / "secrets.env"
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def cursor_api_key(repo_root: Path) -> str | None:
    """CURSOR_API_KEY from env (override) or config/secrets/secrets.env."""
    env = os.environ.get("CURSOR_API_KEY", "").strip()
    if env:
        return env
    key = load_secrets(repo_root).get("CURSOR_API_KEY", "").strip()
    return key or None
