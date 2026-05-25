from __future__ import annotations

from interview_mux.run_context import RunContext
from interview_mux.stages.analysis_stage import run_flow_llm_stage


def run_topic_coverage(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        return {
            "content_brief": c.read_json("understanding/content_brief.json"),
            "segments": c.read_json("segments/manifest.json"),
        }

    def persist(c: RunContext, artifacts: dict) -> None:
        c.write_json("flow_1_master/coverage_audit.json", artifacts)

    run_flow_llm_stage(
        ctx,
        "topic_coverage_audit",
        "selection/topic-coverage-audit.system.txt",
        build_input,
        persist,
    )
    ctx.mark_done("topic_coverage_audit")


def run_narrative_arc(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        return {
            "content_brief": c.read_json("understanding/content_brief.json"),
            "coverage_audit": c.read_json("flow_1_master/coverage_audit.json"),
            "segments": c.read_json("segments/manifest.json"),
        }

    def persist(c: RunContext, artifacts: dict) -> None:
        c.write_json("flow_1_master/narrative_plan.json", artifacts)

    run_flow_llm_stage(
        ctx,
        "narrative_arc_plan",
        "selection/narrative-arc-plan.system.txt",
        build_input,
        persist,
    )
    ctx.mark_done("narrative_arc_plan")
