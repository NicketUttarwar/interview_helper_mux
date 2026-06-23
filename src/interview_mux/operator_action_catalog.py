"""Load operator action catalog for dump descriptions."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_JSON = _REPO_ROOT / "docs" / "cross-cutting" / "operator_action_catalog.json"


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, dict[str, object]]:
    if not _CATALOG_JSON.is_file():
        return {}
    data = json.loads(_CATALOG_JSON.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {str(e["action_id"]): e for e in data if isinstance(e, dict) and e.get("action_id")}
    if isinstance(data, dict) and "actions" in data:
        actions = data["actions"]
        if isinstance(actions, list):
            return {
                str(e["action_id"]): e for e in actions if isinstance(e, dict) and e.get("action_id")
            }
    return {}


def describe(action_id: str) -> str | None:
    entry = load_catalog().get(action_id)
    if not entry:
        return None
    desc = entry.get("description")
    return str(desc) if desc else None


def reload_catalog() -> None:
    load_catalog.cache_clear()
