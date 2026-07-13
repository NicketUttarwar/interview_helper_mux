"""Operator-visible halt logging with recovery CLI commands."""

from __future__ import annotations

from typing import Any, Literal

from interview_mux.run_context import RunContext

ToolName = Literal["run_analysis", "run_flow"]


def format_recovery_command(
    ctx: RunContext,
    *,
    from_stage: str,
    tool: ToolName = "run_analysis",
    flow: str | None = None,
) -> str:
    run_id = ctx.run_id
    if tool == "run_flow" and flow:
        return (
            f"python tools/run_delivery.py --run-id {run_id} --flow {flow} "
            f"--from-stage {from_stage}"
        )
    return f"python tools/run_analysis.py --run-id {run_id} --from-stage {from_stage}"


def log_operator_halt(
    ctx: RunContext,
    *,
    stage_key: str,
    halt_kind: str,
    message: str,
    recovery_from_stage: str,
    action_id: str,
    cap_name: str | None = None,
    cap_value: int | None = None,
    current_value: int | None = None,
    extra_detail: dict[str, Any] | None = None,
    level: str = "action",
    tool: ToolName = "run_analysis",
    flow: str | None = None,
) -> None:
    """Log structured halt with recovery_command for Show detail in Activity dock."""
    recovery_command = format_recovery_command(
        ctx, from_stage=recovery_from_stage, tool=tool, flow=flow
    )
    detail: dict[str, Any] = {
        "journey_kind": "execute",
        "halt_kind": halt_kind,
        "recovery_from_stage": recovery_from_stage,
        "recovery_command": recovery_command,
    }
    if cap_name is not None:
        detail["cap_name"] = cap_name
    if cap_value is not None:
        detail["cap_value"] = cap_value
    if current_value is not None:
        detail["current_value"] = current_value
    if extra_detail:
        detail.update(extra_detail)
    ctx.log(
        message,
        level=level,
        stage=stage_key,
        action_id=action_id,
        origin="pipeline",
        detail=detail,
    )


def log_adaptation_step(
    ctx: RunContext,
    *,
    stage_key: str,
    message: str,
    action_id: str = "llm.adaptation.step",
    extra_detail: dict[str, Any] | None = None,
) -> None:
    detail: dict[str, Any] = {"journey_kind": "execute"}
    if extra_detail:
        detail.update(extra_detail)
    ctx.log(
        message,
        level="info",
        stage=stage_key,
        action_id=action_id,
        origin="pipeline",
        detail=detail,
    )
