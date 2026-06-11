from __future__ import annotations

from interview_mux.disfluency.context import attach_disfluency_context
from interview_mux.llm_specialists import maybe_run_post_stage_specialists
from interview_mux.run_context import RunContext
from interview_mux.stage_enrichment import (
    compact_value_features_summary,
    emphasis_regions_for_segments,
)
from interview_mux.artifact_completeness import make_stage_persist
from interview_mux.stages.analysis_stage import run_flow_llm_stage


def run_topic_coverage(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        payload = {
            "content_brief": c.read_json("understanding/content_brief.json"),
            "segments": c.read_json("segments/manifest.json"),
            "emphasis_regions": emphasis_regions_for_segments(c),
        }
        vf = compact_value_features_summary(c)
        if vf:
            payload["value_features_summary"] = vf
        return attach_disfluency_context(payload, c)

    persist = make_stage_persist("flow_1_master/coverage_audit.json", "topic_coverage_audit")

    run_flow_llm_stage(
        ctx,
        "topic_coverage_audit",
        "selection/topic-coverage-audit.system.txt",
        build_input,
        persist,
    )
    maybe_run_post_stage_specialists(ctx, "topic_coverage_audit", build_input(ctx))


def run_narrative_arc(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        payload = {
            "content_brief": c.read_json("understanding/content_brief.json"),
            "coverage_audit": c.read_json("flow_1_master/coverage_audit.json"),
            "segments": c.read_json("segments/manifest.json"),
            "emphasis_regions": emphasis_regions_for_segments(c),
        }
        vf = compact_value_features_summary(c)
        if vf:
            payload["value_features_summary"] = vf
        return attach_disfluency_context(payload, c)

    persist = make_stage_persist("flow_1_master/narrative_plan.json", "narrative_arc_plan")

    run_flow_llm_stage(
        ctx,
        "narrative_arc_plan",
        "selection/narrative-arc-plan.system.txt",
        build_input,
        persist,
    )
