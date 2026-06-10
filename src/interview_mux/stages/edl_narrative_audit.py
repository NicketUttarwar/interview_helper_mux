from __future__ import annotations

from interview_mux.disfluency.context import attach_disfluency_context
from interview_mux.run_context import RunContext
from interview_mux.artifact_completeness import make_stage_persist
from interview_mux.stages.analysis_stage import run_flow_llm_stage


def _optional_json(ctx: RunContext, rel_path: str) -> dict:
    return ctx.read_json(rel_path) if ctx.artifact_exists(rel_path) else {}


def run_edl_narrative_audit(ctx: RunContext) -> None:
    """Flagship semantic audit before final Flow 1 EDL construction."""

    def build_input(c: RunContext) -> dict:
        payload = {
            "content_brief": c.read_json("understanding/content_brief.json"),
            "coverage_audit": c.read_json("flow_1_master/coverage_audit.json"),
            "narrative_plan": c.read_json("flow_1_master/narrative_plan.json"),
            "selection": c.read_json("flow_1_master/selection.json"),
            "transitions": _optional_json(c, "flow_1_master/transitions.json"),
            "gap_report": _optional_json(c, "understanding/gap_report.json"),
            "nle_edits": _optional_json(c, "segments/nle_edits.json"),
            "sound_design_plan": _optional_json(c, "understanding/sound_design_plan.json"),
        }
        return attach_disfluency_context(payload, c)

    persist = make_stage_persist("flow_1_master/edl_narrative_audit.json", "edl_narrative_audit")

    ctx.log(
        "Running EDL narrative audit with local volley framing before flagship review.",
        level="info",
        stage="edl_narrative_audit",
    )
    run_flow_llm_stage(
        ctx,
        "edl_narrative_audit",
        "selection/edl-narrative-audit.system.txt",
        build_input,
        persist,
    )
    ctx.mark_done("edl_narrative_audit")
