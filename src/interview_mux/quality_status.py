"""Shared quality status vocabulary (PMQ / scorecard / QC summaries).

Wire tokens on disk: ``pass`` | ``fail`` | ``advisory_fail``.
Ship artifacts (PMQ ``status``, scorecard ``quality_status``) write only
``pass`` (publish allowed) or ``fail`` (blocked) — never ``advisory_fail``.
Do not invent status strings elsewhere — import from here.
"""

from __future__ import annotations

from typing import Final, Literal

QualityStatus = Literal["pass", "fail", "advisory_fail"]

STATUS_PASS: Final = "pass"
STATUS_FAIL: Final = "fail"
STATUS_ADVISORY_FAIL: Final = "advisory_fail"

QUALITY_STATUS_VALUES: frozenset[str] = frozenset(
    {STATUS_PASS, STATUS_FAIL, STATUS_ADVISORY_FAIL}
)

# Schema paths that must keep the same enum (CI audit).
QUALITY_STATUS_SCHEMA_ENUM_PATHS: tuple[tuple[str, str], ...] = (
    (
        "docs/cross-cutting/json-schemas/artifacts/post_master_quality.schema.json",
        "status",
    ),
    (
        "docs/cross-cutting/json-schemas/artifacts/listener_scorecard.schema.json",
        "quality_status",
    ),
)


def is_quality_status(value: object) -> bool:
    return str(value or "").strip() in QUALITY_STATUS_VALUES


def normalize_quality_status(value: object, *, default: str = STATUS_FAIL) -> str:
    s = str(value or "").strip()
    if s in QUALITY_STATUS_VALUES:
        return s
    return default if default in QUALITY_STATUS_VALUES else STATUS_FAIL


def is_blocking_status(status: object) -> bool:
    """True when status is structural fail (not advisory)."""
    return normalize_quality_status(status) == STATUS_FAIL


def is_advisory_status(status: object) -> bool:
    return normalize_quality_status(status) == STATUS_ADVISORY_FAIL


def ship_wire_status(*, publish_allowed: bool) -> str:
    """F6 1B: allowed ship is ``pass``; blocked ship is ``fail``. Never ``advisory_fail``."""
    return STATUS_PASS if publish_allowed else STATUS_FAIL


def coerce_ship_envelope_status(quality: dict) -> dict:
    """Stamp PMQ-like docs so disk ``status`` matches publish_allowed."""
    out = dict(quality)
    allowed = bool(out.get("publish_allowed"))
    out["status"] = ship_wire_status(publish_allowed=allowed)
    return out


def qc_summary_flags(status: object, *, publish_allowed: bool | None = None) -> dict:
    """Build run_meta.qc_summaries fields for a PMQ-like status."""
    st = normalize_quality_status(status, default=STATUS_PASS)
    advisory = st == STATUS_ADVISORY_FAIL
    blocking = st == STATUS_FAIL
    out: dict = {
        "passed": st == STATUS_PASS,
        "status": st,
        "blocking": blocking,
        "advisory": advisory,
    }
    if publish_allowed is not None:
        out["publish_allowed"] = bool(publish_allowed)
    return out
