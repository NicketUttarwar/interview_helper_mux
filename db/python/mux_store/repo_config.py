from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json_config(repo_root: Path, rel_under_config: str) -> Any:
    """Load JSON from ``repo_root / config / rel_under_config``."""
    path = (repo_root / "config" / rel_under_config).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Missing config file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def default_sqlite_path(repo_root: Path) -> Path:
    """SQLite path from ``config/app.defaults.json`` (``database_path``), relative to repo root."""
    data = read_json_config(repo_root, "app.defaults.json")
    if not isinstance(data, dict):
        raise ValueError("app.defaults.json must be a JSON object")
    raw = data.get("database_path")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("app.defaults.json must set non-empty string database_path")
    p = Path(raw.strip())
    return p if p.is_absolute() else (repo_root / p).resolve()
