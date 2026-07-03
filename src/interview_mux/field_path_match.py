"""Dotted JSON path pattern matching for field policy (shared by null + necessity registries)."""

from __future__ import annotations

import re


def normalize_field_path(path: str) -> str:
    """Collapse concrete list indices to ``[]`` for pattern matching."""
    return re.sub(r"\[\d+\]", "[]", path)


def path_matches_pattern(path: str, pattern: str) -> bool:
    norm = normalize_field_path(path)
    if pattern == norm or pattern == path:
        return True
    if "[]" in pattern:
        regex = "^" + re.escape(pattern).replace(r"\[\]", r"\[\d+\]") + "$"
        return bool(re.match(regex, norm)) or bool(re.match(regex, path))
    return norm == pattern or norm.startswith(pattern + ".")
