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

# Shipped bundle must expose the atomic checkpoint save API (not legacy /approve-only).
_REQUIRED_JS_MARKERS = (
    "continue-after-checkpoint",
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


def primary_js_bundle(static_root: Path | None = None) -> Path | None:
    """Main entry script referenced from index.html."""
    root = static_root or _STATIC_DIR
    for name in referenced_asset_names(root / "index.html"):
        if name.endswith(".js"):
            path = root / "assets" / name
            if path.is_file():
                return path
    return None


def bundle_contract_ok(static_root: Path | None = None) -> bool:
    """True when the built JS exposes required save/checkpoint API symbols."""
    js = primary_js_bundle(static_root)
    if js is None:
        return False
    try:
        text = js.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return all(marker in text for marker in _REQUIRED_JS_MARKERS)


def needs_gui_build(static_root: Path | None = None) -> bool:
    """True when index.html is missing, assets are absent, or API contract is stale."""
    root = static_root or _STATIC_DIR
    index_path = root / "index.html"
    if not index_path.is_file():
        return True
    if missing_referenced_assets(root):
        return True
    return not bundle_contract_ok(root)
