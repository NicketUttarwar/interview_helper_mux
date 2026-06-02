"""Journey state machine — maps API snapshot to next step."""

from __future__ import annotations

from typing import Any

from e2e_runner.types import StepAction, StepKind


def decide_next_step(
    run: dict[str, Any],
    *,
    flow: str,
    until_stage: str | None = None,
    job_running: bool = False,
) -> StepAction:
    run_id = str(run.get("run_id") or "")
    job = run.get("job") or {}
    job_status = str(job.get("status") or "idle")
    journey = run.get("journey") or {}
    phase = str(journey.get("phase") or "")
    blocking = journey.get("blocking") or {}
    execute_hint = journey.get("execute_hint")
    milestones = journey.get("milestones") or {}

    if until_stage and _until_stage_reached(run, until_stage):
        return StepAction(StepKind.DONE, detail=f"until_stage:{until_stage}")

    if _flow_ship_complete(flow, run, milestones, phase):
        return StepAction(StepKind.VERIFY_FLOW, detail=f"verify:{flow}")

    if job_status == "error":
        msg = str(job.get("message") or job.get("error") or "job error")
        return StepAction(StepKind.WAIT, detail=f"error:{msg}")

    if job_status in ("running", "running_with_warnings") or job_running:
        return StepAction(StepKind.WAIT, detail="job_running")

    if blocking.get("blocked"):
        return StepAction(
            StepKind.RESOLVE_GATE,
            detail=str(blocking.get("message") or "blocked"),
        )

    if job_status in ("gate", "needs_operator"):
        return StepAction(StepKind.RESOLVE_GATE, detail=f"job:{job_status}")

    if _has_pending_gates(run):
        return StepAction(StepKind.RESOLVE_GATE, detail="pending_gates")

    if execute_hint:
        body = {
            "mode": execute_hint.get("mode"),
        }
        if execute_hint.get("from_stage"):
            body["from_stage"] = execute_hint["from_stage"]
        if execute_hint.get("until_stage"):
            body["until_stage"] = execute_hint["until_stage"]
        if until_stage and not body.get("until_stage"):
            body["until_stage"] = until_stage
        return StepAction(
            StepKind.EXECUTE,
            detail=str(execute_hint.get("label") or "execute"),
            execute_body=body,
        )

    if phase == "ship" and milestones.get("master_exported"):
        return StepAction(StepKind.VERIFY_FLOW, detail=f"verify:{flow}")

    next_action = str(journey.get("next_action") or "")
    return StepAction(StepKind.WAIT, detail=f"idle:{next_action}")


def _flow_ship_complete(
    flow: str,
    run: dict[str, Any],
    milestones: dict[str, bool],
    phase: str,
) -> bool:
    if flow == "flow3":
        return bool(
            run.get("artifacts", {}).get("show_description_md")
            or _artifact_exists(run, "flow_3_description/show_description.md")
        )
    if flow in ("flow1", "flow2"):
        key = "flow_1_master/master.wav" if flow == "flow1" else "flow_2_highlights/master.wav"
        return _artifact_exists(run, key) or bool(milestones.get("master_exported"))
    return phase == "ship" and bool(milestones.get("master_exported"))


def _artifact_exists(run: dict[str, Any], rel: str) -> bool:
    deliverable = (run.get("journey") or {}).get("deliverable") or {}
    path = deliverable.get("path") or ""
    if rel.split("/")[-1] in path:
        return True
    for stage in run.get("stages") or []:
        for art in stage.get("artifacts") or []:
            if art.get("path") == rel:
                return True
    return False


def _until_stage_reached(run: dict[str, Any], until_stage: str) -> bool:
    for stage in run.get("stages") or []:
        if stage.get("id") == until_stage and stage.get("status") == "done":
            return True
    return False


def _has_pending_gates(run: dict[str, Any]) -> bool:
    if run.get("transcript_review_pending"):
        return True
    if run.get("g1_missing"):
        return True
    if run.get("profile_gate_pending"):
        return True
    for stage in run.get("stages") or []:
        if stage.get("status") == "action_required":
            return True
    return False


def fingerprint(run: dict[str, Any]) -> tuple[str, ...]:
    journey = run.get("journey") or {}
    job = run.get("job") or {}
    action_stage = ""
    for stage in run.get("stages") or []:
        if stage.get("status") == "action_required":
            action_stage = str(stage.get("id") or "")
            break
    return (
        str(run.get("run_id") or ""),
        str(journey.get("phase") or ""),
        str(journey.get("next_action") or ""),
        str(job.get("status") or "idle"),
        action_stage,
    )
