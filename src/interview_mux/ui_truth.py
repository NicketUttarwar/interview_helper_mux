"""Validate run snapshot invariants (T1–T10)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Violation:
    code: str
    message: str
    stage_id: str | None = None


def validate_run_snapshot(
    *,
    stages: list[dict[str, Any]],
    journey: dict[str, Any] | None = None,
    job: dict[str, Any] | None = None,
) -> list[Violation]:
    violations: list[Violation] = []
    for stage in stages:
        sid = stage.get("id")
        status = stage.get("status")
        if status == "done":
            for path, st in (stage.get("artifacts_status") or {}).items():
                if st == "pending":
                    phase = (stage.get("artifacts_lifecycle") or {}).get(path)
                    if phase not in ("n_a", "skipped", None):
                        violations.append(
                            Violation(
                                "T1",
                                f"Stage {sid} done but artifact {path} pending",
                                sid,
                            )
                        )
            outputs = stage.get("outputs_view") or []
            for row in outputs:
                if row.get("status") == "pending" and row.get("phase") not in (
                    "n_a",
                    "skipped",
                    "staged",
                ):
                    violations.append(
                        Violation(
                            "T8",
                            f"Stage {sid} outputs_view pending for {row.get('path')}",
                            sid,
                        )
                    )
        if status == "awaiting_write_approval":
            staged = stage.get("artifacts_staged") or []
            if not staged and not (stage.get("artifacts_lifecycle") or {}):
                violations.append(
                    Violation("T9", f"Stage {sid} awaiting_write_approval without staged artifacts", sid)
                )
    if job and job.get("status") in ("complete",):
        if job.get("awaiting_write_approval") or job.get("pending_write_stage"):
            violations.append(
                Violation(
                    "T10",
                    "Job complete but write approval fields still set",
                    str(job.get("pending_write_stage") or job.get("stage") or ""),
                )
            )
    return violations
