from __future__ import annotations

from interview_mux.run_context import RunContext
from interview_mux.stage_enrichment import compact_value_features_summary, quotability_signals
from interview_mux.stages.analysis_stage import run_flow_llm_stage


def run_highlight_selection(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        payload = {
            "segments": c.read_json("segments/manifest.json"),
            "content_brief": c.read_json("understanding/content_brief.json"),
            "gap_report": c.read_json("understanding/gap_report.json"),
            "quotability_signals": quotability_signals(c),
        }
        vf = compact_value_features_summary(c)
        if vf:
            payload["value_features_summary"] = vf
        return payload

    def persist(c: RunContext, artifacts: dict) -> None:
        c.write_json("flow_2_highlights/selection.json", artifacts)

    run_flow_llm_stage(
        ctx,
        "highlight_selection",
        "selection/highlight-selection.system.txt",
        build_input,
        persist,
    )
    ctx.mark_done("highlight_selection")


def run_sfx_brief(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        return {
            "selection": c.read_json("flow_2_highlights/selection.json"),
            "content_brief": c.read_json("understanding/content_brief.json"),
        }

    def persist(c: RunContext, artifacts: dict) -> None:
        c.write_json("flow_2_highlights/sfx_brief.json", artifacts)

    run_flow_llm_stage(
        ctx,
        "sfx_brief",
        "assembly/sfx-brief.system.txt",
        build_input,
        persist,
    )
    ctx.mark_done("sfx_brief")
