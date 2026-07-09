"""Canonical JSON serialization for content fingerprints."""

from __future__ import annotations

import json
from typing import Any


def dumps_canonical(data: Any) -> str:
    """Stable compact JSON for hashing (sort_keys, no whitespace)."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def loads_canonical(text: str) -> Any:
    return json.loads(text)
