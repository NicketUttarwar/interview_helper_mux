"""Shared types for baseline artifact sanitizers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SanitizeResult:
    """Outcome of a deterministic, non-amplifying sanitize pass."""

    doc: dict[str, Any]
    actions: list[dict[str, Any]] = field(default_factory=list)
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    artifact_rel: str = ""

    @property
    def changed(self) -> bool:
        return bool(self.actions)
