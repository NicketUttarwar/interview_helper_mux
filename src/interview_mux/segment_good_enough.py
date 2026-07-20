"""Good-enough advance for segment_classification before hard LLM gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GoodEnoughResult:
    cleared: bool
    message: str = ""


def try_good_enough_advance(
    ctx: Any,
    stage_key: str,
    lint_errors: list[str] | None,
) -> GoodEnoughResult:
    return GoodEnoughResult(cleared=False)


__all__ = ["GoodEnoughResult", "try_good_enough_advance"]
