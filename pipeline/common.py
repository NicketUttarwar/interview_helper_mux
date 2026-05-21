from __future__ import annotations

import hashlib
from pathlib import Path

_assets_override: Path | None = None


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def set_assets_root_override(path: Path | None) -> None:
    """Tests only: redirect ASSETS without editing config or shell env."""
    global _assets_override
    _assets_override = path.resolve() if path is not None else None


def assets_root(root: Path | None = None) -> Path:
    if _assets_override is not None:
        return _assets_override
    base = root or repo_root()
    from mux_store.repo_config import default_assets_path

    return default_assets_path(base)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
