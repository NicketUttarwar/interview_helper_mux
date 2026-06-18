"""Rate-limited full-page screenshots under ASSETS/ (local git archive)."""

from __future__ import annotations

import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from logging_banner import EventLogger

_DEFAULT_DIR = "ASSETS/flow1-gui-e2e-screenshots"
_DEFAULT_INTERVAL_S = 120


class ExecutionScreenshotArchive:
    """Save full-page GUI captures on button clicks, at most once per interval."""

    def __init__(
        self,
        repo_root: Path,
        session_id: str,
        *,
        archive_dir: str = _DEFAULT_DIR,
        min_interval_s: float = _DEFAULT_INTERVAL_S,
        log: EventLogger | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.archive_root = repo_root / archive_dir
        self.session_id = session_id
        self.session_dir = self.archive_root / "sessions" / session_id
        self.min_interval_s = min_interval_s
        self.log = log
        self._last_capture_at = 0.0
        self._counter = 0
        self._paths: list[Path] = []
        self.ensure_repo()

    def ensure_repo(self) -> None:
        self.archive_root.mkdir(parents=True, exist_ok=True)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        readme = self.archive_root / "README.md"
        if not readme.is_file():
            readme.write_text(
                "# Flow 1 GUI E2E — execution screenshots\n\n"
                "Auto-captured full-page screenshots during `./CURSOR_EXECUTE/flow1-gui-e2e/run.sh`.\n"
                "Gitignored under repo-root `ASSETS/`; this folder is its own local git repo.\n",
                encoding="utf-8",
            )
        if not (self.archive_root / ".git").is_dir():
            subprocess.run(
                ["git", "init"],
                cwd=str(self.archive_root),
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "add", "README.md"],
                cwd=str(self.archive_root),
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "init flow1-gui-e2e-screenshots archive"],
                cwd=str(self.archive_root),
                check=True,
                capture_output=True,
                text=True,
            )
            if self.log:
                self.log.info(f"Initialized screenshot git repo at {self.archive_root}")

    def maybe_capture_after_click(self, page: Page, reason: str) -> Path | None:
        """Capture full-page screenshot if at least min_interval_s since last capture."""
        now = time.time()
        if self._last_capture_at and (now - self._last_capture_at) < self.min_interval_s:
            return None
        self._counter += 1
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        slug = re.sub(r"[^\w\-]+", "_", reason.strip())[:80].strip("_") or "click"
        path = self.session_dir / f"{self._counter:03d}_{ts}_{slug}.png"
        page.screenshot(path=str(path), full_page=True)
        self._last_capture_at = now
        self._paths.append(path)
        if self.log:
            self.log.info(f"Execution screenshot [{self._counter}] → {path.relative_to(self.repo_root)}")
        return path

    @property
    def capture_count(self) -> int:
        return len(self._paths)

    def commit_session(self, run_id: str | None = None, note: str = "e2e session") -> bool:
        """Commit this session's screenshots in the ASSETS archive repo."""
        if not self._paths and not any(self.session_dir.glob("*.png")):
            return False
        rel_session = self.session_dir.relative_to(self.archive_root)
        subprocess.run(["git", "add", str(rel_session)], cwd=str(self.archive_root), check=False)
        msg = f"{note}: {self.session_id}"
        if run_id:
            msg += f" run_id={run_id}"
        msg += f" ({self.capture_count} captures)"
        result = subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=str(self.archive_root),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and self.log:
            self.log.info(f"Screenshot archive commit OK ({self.archive_root})")
        return result.returncode == 0
