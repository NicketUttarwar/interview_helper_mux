from __future__ import annotations

from interview_mux.stage_input_helpers import attach_disfluency_context
from interview_mux.llm_specialists import maybe_run_post_stage_specialists
from interview_mux.run_context import RunContext
from interview_mux.stage_enrichment import (
    compact_value_features_summary,
    emphasis_regions_for_segments,
)
from interview_mux.operator_trace import logged_step
from interview_mux.artifact_completeness import make_stage_persist
from interview_mux.artifact_repairs import enrich_narrative_plan_for_persist
from interview_mux.production_profile import prompt_variant
from interview_mux.source_topology import attach_adaptation_to_payload
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
        from interview_mux.coherence import attach_coherence_summary

        attach_coherence_summary(payload, c, "topic_coverage_audit")
        return attach_disfluency_context(
            __import__("interview_mux.delivery_brief", fromlist=["attach_delivery_brief_to_payload"]).attach_delivery_brief_to_payload(
                c, attach_adaptation_to_payload(c, payload)
            ),
            c,
        )

    persist = make_stage_persist("master/coverage_audit.json", "topic_coverage_audit")

    with logged_step("topic_coverage_audit/llm_stage", ctx=ctx, stage="topic_coverage_audit"):
        run_flow_llm_stage(
            ctx,
            "topic_coverage_audit",
            prompt_variant("selection/topic-coverage-audit.system.txt", ctx),
            build_input,
            persist,
        )
    if ctx.is_done("topic_coverage_audit"):
        regions = emphasis_regions_for_segments(ctx)
        ctx.log(
            f"topic_coverage_audit: emphasis_regions count={len(regions)}",
            level="info",
            stage="topic_coverage_audit",
        )
    with logged_step("topic_coverage_audit/post_specialists", ctx=ctx, stage="topic_coverage_audit"):
        maybe_run_post_stage_specialists(ctx, "topic_coverage_audit", build_input(ctx))
    if ctx.is_done("topic_coverage_audit"):
        with logged_step("topic_coverage_audit/coherence", ctx=ctx, stage="topic_coverage_audit"):
            from interview_mux.coherence import maybe_run_coherence_analysis

            maybe_run_coherence_analysis(ctx, phase="post_coverage")


def run_narrative_arc(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        payload = {
            "content_brief": c.read_json("understanding/content_brief.json"),
            "coverage_audit": c.read_json("master/coverage_audit.json"),
            "segments": c.read_json("segments/manifest.json"),
            "emphasis_regions": emphasis_regions_for_segments(c),
        }
        vf = compact_value_features_summary(c)
        if vf:
            payload["value_features_summary"] = vf
        from interview_mux.coherence import attach_coherence_summary

        attach_coherence_summary(payload, c, "narrative_arc_plan")
        from interview_mux.episode_structure import attach_episode_structure_to_payload

        return attach_disfluency_context(
            attach_episode_structure_to_payload(
                c,
                __import__("interview_mux.delivery_brief", fromlist=["attach_delivery_brief_to_payload"]).attach_delivery_brief_to_payload(
                    c, attach_adaptation_to_payload(c, payload)
                ),
            ),
            c,
        )

    def _persist_narrative(c: RunContext, artifacts: dict) -> None:
        enriched = enrich_narrative_plan_for_persist(c, artifacts)
        write = make_stage_persist("master/narrative_plan.json", "narrative_arc_plan")
        write(c, enriched)

    persist = _persist_narrative

    with logged_step("narrative_arc_plan/llm_stage", ctx=ctx, stage="narrative_arc_plan"):
        run_flow_llm_stage(
            ctx,
            "narrative_arc_plan",
            prompt_variant("selection/narrative-arc-plan.system.txt", ctx),
            build_input,
            persist,
        )
