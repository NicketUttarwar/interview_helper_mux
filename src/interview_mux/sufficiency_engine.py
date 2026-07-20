"""Legacy sufficiency stubs — disabled in v2."""

from __future__ import annotations

from typing import Any


def sufficiency_enabled(*_args: Any, **_kwargs: Any) -> bool:
    return False


def evaluate(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {"findings": []}


def findings_to_gap_paths(findings: list[Any]) -> list[str]:
    _ = findings
    return []
