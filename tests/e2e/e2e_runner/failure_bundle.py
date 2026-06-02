"""Write structured failure bundles for heal + final report."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_failure_bundle(
    log_dir: Path,
    *,
    repo_root: Path | None = None,
    incident_id: int,
    failure_type: str,
    summary: str,
    run: dict[str, Any] | None,
    log_tail: list[dict[str, Any]] | None,
    screenshot_path: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    failures_dir = log_dir / "failures"
    failures_dir.mkdir(parents=True, exist_ok=True)
    path = failures_dir / f"{incident_id:03d}_{failure_type}.json"

    root = repo_root or (log_dir.parents[3] if len(log_dir.parents) >= 4 else log_dir)
    git_diff = _git_diff(root)

    payload = {
        "incident_id": incident_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "failure_type": failure_type,
        "summary": summary,
        "run_id": (run or {}).get("run_id"),
        "journey": (run or {}).get("journey"),
        "job": (run or {}).get("job"),
        "log_tail": log_tail or [],
        "screenshot_path": screenshot_path,
        "git_diff_names": git_diff.get("names") or [],
        "git_diff_stat": git_diff.get("stat") or "",
        "extra": extra or {},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _git_diff(repo_root: Path) -> dict[str, Any]:
    try:
        names = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        stat = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "names": [n for n in names.stdout.splitlines() if n.strip()],
            "stat": stat.stdout.strip(),
        }
    except Exception:
        return {"names": [], "stat": ""}
