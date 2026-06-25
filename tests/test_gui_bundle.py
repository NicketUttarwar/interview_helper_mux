"""GUI static bundle integrity and gitignore guards."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from interview_mux.config import repo_root
from interview_mux.gui_bundle import (
    bundle_contract_ok,
    missing_referenced_assets,
    needs_gui_build,
    referenced_asset_names,
    static_dir,
)


def test_shipped_static_bundle_is_complete() -> None:
    """Production static dir should reference only files that exist."""
    root = static_dir()
    if not (root / "index.html").is_file():
        pytest.skip("GUI not built yet — run ./scripts/build_gui.sh")
    assert referenced_asset_names()
    assert missing_referenced_assets(root) == []
    assert bundle_contract_ok(root) is True
    assert needs_gui_build(root) is False


def test_needs_gui_build_when_checkpoint_api_missing(tmp_path: Path) -> None:
    root = tmp_path / "static"
    assets = root / "assets"
    assets.mkdir(parents=True)
    (assets / "index-old.js").write_text('pending-writes/${s}/approve', encoding="utf-8")
    (root / "index.html").write_text(
        '<script type="module" crossorigin src="/assets/index-old.js"></script>\n',
        encoding="utf-8",
    )
    assert bundle_contract_ok(root) is False
    assert needs_gui_build(root) is True


def test_needs_gui_build_when_asset_missing(tmp_path: Path) -> None:
    root = tmp_path / "static"
    root.mkdir()
    (root / "index.html").write_text(
        '<script type="module" crossorigin src="/assets/missing-abc123.js"></script>\n',
        encoding="utf-8",
    )
    assert needs_gui_build(root) is True
    assert missing_referenced_assets(root) == ["assets/missing-abc123.js"]


def test_web_static_assets_not_gitignored() -> None:
    """Regression: unanchored ASSETS/ in .gitignore must not ignore web/static/assets/."""
    sample = repo_root() / "src" / "interview_mux" / "web" / "static" / "assets"
    if not sample.is_dir():
        pytest.skip("no static assets dir")
    js_files = list(sample.glob("*.js"))
    if not js_files:
        pytest.skip("no js bundle committed yet")
    target = js_files[0].relative_to(repo_root()).as_posix()
    proc = subprocess.run(
        ["git", "check-ignore", "-q", target],
        cwd=repo_root(),
        capture_output=True,
    )
    assert proc.returncode == 1, f"{target} should not be gitignored"
