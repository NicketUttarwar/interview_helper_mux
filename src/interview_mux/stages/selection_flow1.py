from __future__ import annotations

from interview_mux.context_volley import interviewer_sample_lines
from interview_mux.run_context import RunContext
from interview_mux.stages.analysis_stage import run_flow_llm_stage


def run_full_master_ranking(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        return {
            "segments": c.read_json("segments/manifest.json"),
            "gap_report": c.read_json("understanding/gap_report.json"),
            "content_brief": c.read_json("understanding/content_brief.json"),
            "coverage_audit": c.read_json("flow_1_master/coverage_audit.json"),
            "narrative_plan": c.read_json("flow_1_master/narrative_plan.json"),
        }

    def persist(c: RunContext, artifacts: dict) -> None:
        c.write_json("flow_1_master/selection.json", artifacts)

    run_flow_llm_stage(
        ctx,
        "full_master_ranking",
        "selection/full-master-ranking.system.txt",
        build_input,
        persist,
    )
    ctx.mark_done("full_master_ranking")


def run_transitions(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        return {
            "selection": c.read_json("flow_1_master/selection.json"),
            "segments": c.read_json("segments/manifest.json"),
            "content_brief": c.read_json("understanding/content_brief.json"),
            "gap_report": c.read_json("understanding/gap_report.json"),
            "interviewer_sample_lines": interviewer_sample_lines(c),
        }

    def persist(c: RunContext, artifacts: dict) -> None:
        c.write_json("flow_1_master/transitions.json", artifacts)

    run_flow_llm_stage(
        ctx,
        "transitions",
        "assembly/transitions.system.txt",
        build_input,
        persist,
    )
    ctx.mark_done("transitions")


def run_podcast_sfx_brief(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        return {
            "selection": c.read_json("flow_1_master/selection.json"),
            "transitions": c.read_json("flow_1_master/transitions.json"),
            "narrative_plan": c.read_json("flow_1_master/narrative_plan.json"),
        }

    def persist(c: RunContext, artifacts: dict) -> None:
        c.write_json("flow_1_master/podcast_sfx_brief.json", artifacts)

    run_flow_llm_stage(
        ctx,
        "podcast_sfx_brief",
        "assembly/podcast-sfx-brief.system.txt",
        build_input,
        persist,
    )
    ctx.mark_done("podcast_sfx_brief")
