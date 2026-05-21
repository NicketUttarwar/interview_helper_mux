from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Ensure repo packages resolve when pytest runs before/without editable install.
for sub in ("", "ai/python", "db/python"):
    root = REPO_ROOT / sub if sub else REPO_ROOT
    entry = str(root)
    if entry not in sys.path:
        sys.path.insert(0, entry)

from pipeline.common import set_assets_root_override  # noqa: E402


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session", autouse=True)
def _isolated_pytest_assets(repo_root: Path) -> None:
    """Keep pytest media under ASSETS/_pytest without shell env or PYTHONPATH."""
    assets = repo_root / "ASSETS" / "_pytest"
    assets.mkdir(parents=True, exist_ok=True)
    set_assets_root_override(assets)


@pytest.fixture
def tmp_assets(tmp_path: Path, repo_root: Path) -> Path:
    """Per-test ASSETS root (overrides session default for the test body)."""
    assets = tmp_path / "ASSETS"
    assets.mkdir(parents=True, exist_ok=True)
    session_assets = repo_root / "ASSETS" / "_pytest"
    set_assets_root_override(assets)
    yield assets
    set_assets_root_override(session_assets)


@pytest.fixture
def speech_wav(tmp_path: Path, repo_root: Path) -> Path:
    """Short speech WAV: bundled fixture, macOS say, or skip."""
    bundled = repo_root / "tests" / "fixtures" / "speech_short.wav"
    if bundled.is_file():
        return bundled

    import platform
    import shutil
    import subprocess

    if platform.system() == "Darwin" and shutil.which("say") and shutil.which("ffmpeg"):
        aiff = tmp_path / "speech.aiff"
        wav = tmp_path / "speech_short.wav"
        subprocess.run(
            [
                "say",
                "-o",
                str(aiff),
                "This is a short test clip for the interview helper mux pipeline.",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(aiff), "-ar", "48000", "-ac", "1", str(wav)],
            check=True,
            capture_output=True,
        )
        return wav

    pytest.skip(
        "No speech fixture: add tests/fixtures/speech_short.wav or run on macOS with say+ffmpeg"
    )
