"""Journey-scoped operator log events (single taxonomy for GUI filters and docs)."""

from __future__ import annotations

from typing import Any, Literal

from interview_mux.run_context import RunContext

JourneyLogKind = Literal[
    "gate",
    "quality",
    "preview",
    "sfx",
    "qc",
    "milestone",
    "execute",
]

JOURNEY_LOG_KINDS: tuple[JourneyLogKind, ...] = (
    "gate",
    "quality",
    "preview",
    "sfx",
    "qc",
    "milestone",
    "execute",
)


def log_journey(
    ctx: RunContext,
    kind: JourneyLogKind,
    message: str,
    *,
    level: str = "info",
    stage: str | None = None,
    **detail_extra: Any,
) -> None:
    detail: dict[str, Any] = {"journey_kind": kind}
    detail.update(detail_extra)
    ctx.log(message, level=level, stage=stage, detail=detail)
