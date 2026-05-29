"""Persisted operator API consent under ASSETS/.gui/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config, repo_root
from filelock import FileLock

from interview_mux.file_store import lock_path_for


def _consent_path() -> Path:
    cfg = merged_config()
    assets = repo_root() / cfg.get("assets_root", "ASSETS")
    gui_dir = assets / ".gui"
    gui_dir.mkdir(parents=True, exist_ok=True)
    return gui_dir / "api_consent.json"


def load_persisted_consents() -> dict[str, bool]:
    path = _consent_path()
    if not path.is_file():
        return {}
    with FileLock(lock_path_for(path)):
        data = json.loads(path.read_text(encoding="utf-8"))
    grants = data.get("grants") or {}
    return {str(k): bool(v) for k, v in grants.items()}


def save_persisted_consent(provider: str, granted: bool) -> dict[str, bool]:
    path = _consent_path()
    with FileLock(lock_path_for(path)):
        data: dict[str, Any] = {}
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
        grants = dict(data.get("grants") or {})
        grants[provider] = granted
        data["grants"] = grants
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return grants


def merge_consents(*maps: dict[str, bool] | None) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for m in maps:
        if not m:
            continue
        for k, v in m.items():
            if v:
                out[k] = True
    return out
