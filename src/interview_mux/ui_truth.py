"""Validate run snapshot invariants (T1–T11)."""

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
    analysis_state: dict[str, Any] | None = None,
    context_index: dict[str, Any] | None = None,
) -> list[Violation]:
    violations: list[Violation] = []
    for stage in stages:
        sid = stage.get("id")
        status = stage.get("status")
        if status == "done":
            for path, st in (stage.get("artifacts_status") or {}).items():
                phase = (stage.get("artifacts_lifecycle") or {}).get(path)
                if phase in ("n_a", "skipped", None) and st == "pending":
                    continue
                if st in ("pending", "partial"):
                    violations.append(
                        Violation(
                            "T1",
                            f"Stage {sid} done but artifact {path} {st}",
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
    violations.extend(
        _t11_volley_without_artifact(stages, analysis_state=analysis_state, context_index=context_index)
    )
    return violations


def _p0_stages_with_volley_conclusion(
    *,
    analysis_state: dict[str, Any] | None,
    context_index: dict[str, Any] | None,
) -> set[str]:
    from interview_mux.progression_spine import P0_ANALYSIS_SPINE

    found: set[str] = set()
    if analysis_state:
        summaries = (analysis_state.get("meta") or {}).get("stage_summaries") or {}
        for sid in summaries:
            if sid in P0_ANALYSIS_SPINE:
                found.add(sid)
    if context_index:
        for entry in context_index.get("volley_entries") or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("kind") != "stage_conclusion":
                continue
            if entry.get("status") == "invalidated":
                continue
            src = entry.get("source") or {}
            sid = src.get("stage_key")
            if sid in P0_ANALYSIS_SPINE:
                found.add(str(sid))
    return found


def _t11_volley_without_artifact(
    stages: list[dict[str, Any]],
    *,
    analysis_state: dict[str, Any] | None,
    context_index: dict[str, Any] | None,
) -> list[Violation]:
    from interview_mux.llm_flow_hardening import producer_artifact_path

    if not analysis_state and not context_index:
        return []
    stage_by_id = {s.get("id"): s for s in stages if s.get("id")}
    violations: list[Violation] = []
    for sid in sorted(_p0_stages_with_volley_conclusion(
        analysis_state=analysis_state,
        context_index=context_index,
    )):
        stage = stage_by_id.get(sid) or {"id": sid}
        rel = producer_artifact_path(sid)
        if not rel:
            continue
        arts = stage.get("artifacts_status") or {}
        lifecycle = stage.get("artifacts_lifecycle") or {}
        staged = stage.get("artifacts_staged") or []
        st = arts.get(rel)
        phase = lifecycle.get(rel)
        if st == "complete" or phase == "committed":
            continue
        if rel in staged or phase == "staged":
            continue
        violations.append(
            Violation(
                "T11",
                f"Stage {sid} has volley stage_conclusion but producer artifact {rel} is not complete or staged",
                sid,
            )
        )
    return violations


def reconcile_stage_status(stage: dict[str, Any]) -> dict[str, Any]:
    """Downgrade done → incomplete when the stage's producer artifact is pending/partial (T1).

    Collateral / optional listed artifacts (e.g. nugget_allocation_plan on an otherwise
    complete vo_line_adjudicate) must not paint a ship-ready run as Failed.
    """
    if stage.get("status") != "done":
        return stage
    # N/A / optional skips: artifacts are marked n_a before reconcile; never T1-downgrade.
    if stage.get("stage_output_mode") == "optional_skipped":
        return stage

    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

    arts = stage.get("artifacts_status") or {}
    lifecycle = stage.get("artifacts_lifecycle") or {}
    sid = str(stage.get("id") or "")
    producer = STAGE_ARTIFACT_DISK_PATHS.get(sid)

    if producer:
        check_paths = [producer]
    else:
        # No canonical producer: keep done when any listed output is complete.
        if any(st == "complete" for st in arts.values()):
            return stage
        check_paths = [p for p in arts.keys() if p]

    for path in check_paths:
        st = arts.get(path)
        if st not in ("pending", "partial"):
            continue
        phase = lifecycle.get(path)
        if phase in ("n_a", "skipped"):
            continue
        stage["status"] = "incomplete"
        stage["incomplete_reason"] = f"{path} is {st}"
        return stage

    if producer:
        # Producer complete — do not T1 on collateral outputs_view rows.
        return stage

    outputs = stage.get("outputs_view") or []
    for row in outputs:
        if row.get("status") == "pending" and row.get("phase") not in (
            "n_a",
            "skipped",
            "staged",
        ):
            stage["status"] = "incomplete"
            stage["incomplete_reason"] = f"{row.get('path')} missing on disk"
            return stage
    return stage
