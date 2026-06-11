"""GUI static bundle integrity checks (Vite build output under web/static/)."""

from __future__ import annotations

import re
from pathlib import Path

from interview_mux.config import repo_root

_STATIC_DIR = repo_root() / "src" / "interview_mux" / "web" / "static"
_INDEX_HTML = _STATIC_DIR / "index.html"

# Vite index.html: src="/assets/index-….js" and href="/assets/index-….css"
_ASSET_REF_RE = re.compile(
    r'(?:src|href)="/assets/([^"]+\.(?:js|css))"',
    re.IGNORECASE,
)


def static_dir() -> Path:
    return _STATIC_DIR


def index_html_path() -> Path:
    return _INDEX_HTML


def referenced_asset_names(index_html: Path | None = None) -> list[str]:
    """Return asset filenames referenced from index.html (e.g. index-abc123.js)."""
    path = index_html or _INDEX_HTML
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    return list(dict.fromkeys(_ASSET_REF_RE.findall(text)))


def missing_referenced_assets(static_root: Path | None = None) -> list[str]:
    """Asset paths referenced in index.html that are absent on disk."""
    root = static_root or _STATIC_DIR
    index_path = root / "index.html"
    missing: list[str] = []
    for name in referenced_asset_names(index_path):
        rel = f"assets/{name}"
        if not (root / rel).is_file():
            missing.append(rel)
    return missing


def needs_gui_build(static_root: Path | None = None) -> bool:
    """True when index.html is missing or any hashed bundle file it references is absent."""
    root = static_root or _STATIC_DIR
    index_path = root / "index.html"
    if not index_path.is_file():
        return True
    return bool(missing_referenced_assets(root))
