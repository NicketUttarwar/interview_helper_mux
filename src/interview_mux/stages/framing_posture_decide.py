"""Advisory framing posture LLM — homunculus 0.1.0+ only."""

from __future__ import annotations

from typing import Any

from interview_mux.framing_posture import (
    apply_host_gate,
    build_framing_posture_input,
    build_monologue_decision,
    framing_posture_enabled,
    persist_framing_decision,
    should_run_framing_posture_llm,
)
from interview_mux.homunculus.runtime import is_homunculus_run
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.stages.analysis_stage import run_analysis_llm_stage
from interview_mux.stage_completion import heal_or_refuse_mark

STAGE_KEY = "framing_posture_decide"
PROMPT_REL = "framing/framing-posture-decide.system.txt"


def run_framing_posture_decide(ctx: RunContext) -> None:
    # TH1b allow-stub paths: no producer artifact required → heal marks when incomplete None.
    if not is_homunculus_run(ctx):
        heal_or_refuse_mark(ctx, STAGE_KEY, force=True)
        return

    if not framing_posture_enabled():
        heal_or_refuse_mark(ctx, STAGE_KEY, force=True)
        return

    if not should_run_framing_posture_llm(ctx):
        with logged_step(
            "framing_posture_decide/monologue_skip",
            ctx=ctx,
            stage=STAGE_KEY,
        ):
            persist_framing_decision(ctx, build_monologue_decision(ctx))
            apply_host_gate(ctx)
            heal_or_refuse_mark(ctx, STAGE_KEY, force=True)
        return

    def build_input(c: RunContext) -> dict[str, Any]:
        return build_framing_posture_input(c)

    def persist(c: RunContext, artifacts: dict[str, Any]) -> None:
        doc = dict(artifacts or {})
        doc["decided_by"] = "llm_advisory"
        doc["advisory_only"] = True
        persist_framing_decision(c, doc)

    with logged_step("framing_posture_decide/llm_stage", ctx=ctx, stage=STAGE_KEY):
        run_analysis_llm_stage(
            ctx,
            STAGE_KEY,
            PROMPT_REL,
            build_input,
            persist,
        )

    apply_host_gate(ctx)
