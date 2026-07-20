"""Load per-stage arbiter rubrics and build stage_expectations payloads."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from interview_mux.config import repo_root
from interview_mux.model_registry import resolve_model, stage_severity

DECOMPOSE_ELIGIBLE: frozenset[str] = frozenset()

RUBRICS_DIR = repo_root() / "docs" / "prompts" / "_shared" / "arbiter-rubrics"


@lru_cache(maxsize=64)
def _load_rubric(stage_key: str) -> dict[str, Any] | None:
    path = RUBRICS_DIR / f"{stage_key}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def rubric_for_stage(stage_key: str) -> dict[str, Any] | None:
    return _load_rubric(stage_key)


def build_stage_expectations(
    stage_key: str,
    *,
    bump_tier: bool = False,
) -> dict[str, Any]:
    """Compact rubric slice for arbiter user payload."""
    rubric = _load_rubric(stage_key) or {}
    default_tier = resolve_model(stage_key, "primary", bump_tier=bump_tier).tier
    severity = rubric.get("severity") or stage_severity(stage_key) or (
        "high" if default_tier == "flagship" else "medium"
    )
    return {
        "severity": severity,
        "default_tier": default_tier,
        "decompose_eligible": stage_key in DECOMPOSE_ELIGIBLE,
        "accept_criteria": rubric.get("accept_criteria") or [],
        "reject_patterns": rubric.get("reject_patterns") or [],
        "min_confidence_on_accept": float(rubric.get("min_confidence_on_accept", 0.75) or 0.75),
        "deterministic_lint_keys": rubric.get("deterministic_lint_keys") or [],
    }


def clear_rubric_cache() -> None:
    _load_rubric.cache_clear()
