"""Sanitize understanding/omit_ledger.json — thin wrapper to air_contract."""

from __future__ import annotations

from typing import Any

from interview_mux.artifact_sanitize.air_script import sanitize_omit_ledger as _sanitize
from interview_mux.artifact_sanitize.types import SanitizeResult

REL = "understanding/omit_ledger.json"


def sanitize_omit_ledger(ctx: Any, doc: dict[str, Any]) -> SanitizeResult:
    return _sanitize(ctx, doc)
