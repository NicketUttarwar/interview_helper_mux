from __future__ import annotations

from interview_mux.disfluency.context import attach_disfluency_context
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.artifact_completeness import make_stage_persist
from interview_mux.production_profile import prompt_variant
from interview_mux.source_topology import attach_adaptation_to_payload
from interview_mux.sonic_context import compact_for_volley as sonic_compact_for_volley, load_sonic_context
from interview_mux.stages.analysis_stage import run_flow_llm_stage


def _optional_json(ctx: RunContext, rel_path: str) -> dict:
    return ctx.read_json(rel_path) if ctx.artifact_exists(rel_path) else {}


def run_edl_narrative_audit(ctx: RunContext) -> None:
    """Flagship semantic audit before final Flow 1 EDL construction."""

    def build_input(c: RunContext) -> dict:
        payload = {
            "content_brief": c.read_json("understanding/content_brief.json"),
            "coverage_audit": c.read_json("master/coverage_audit.json"),
            "narrative_plan": c.read_json("master/narrative_plan.json"),
            "selection": c.read_json("master/selection.json"),
            "transitions": _optional_json(c, "master/transitions.json"),
            "gap_report": _optional_json(c, "understanding/gap_report.json"),
            "nle_edits": _optional_json(c, "segments/nle_edits.json"),
            "sound_design_plan": _optional_json(c, "understanding/sound_design_plan.json"),
        }
        sdp = payload.get("sound_design_plan")
        if isinstance(sdp, dict):
            assets = sdp.get("assets") if isinstance(sdp.get("assets"), list) else []
            payload["sound_design_asset_summary"] = {
                "asset_count": len(assets),
                "roles": sorted(
                    {
                        str(row.get("role"))
                        for row in assets
                        if isinstance(row, dict) and row.get("role")
                    }
                ),
            }
        sonic_context = load_sonic_context(c)
        if sonic_context:
            payload["sonic_context"] = sonic_compact_for_volley(sonic_context)
        return attach_disfluency_context(
            __import__("interview_mux.delivery_brief", fromlist=["attach_delivery_brief_to_payload"]).attach_delivery_brief_to_payload(
                c, attach_adaptation_to_payload(c, payload)
            ),
            c,
        )

    persist = make_stage_persist("master/edl_narrative_audit.json", "edl_narrative_audit")

    ctx.log(
        "Running EDL narrative audit with local volley framing before flagship review.",
        level="info",
        stage="edl_narrative_audit",
    )
    with logged_step("edl_narrative_audit/llm_stage", ctx=ctx, stage="edl_narrative_audit"):
        run_flow_llm_stage(
            ctx,
            "edl_narrative_audit",
            prompt_variant("selection/edl-narrative-audit.system.txt", ctx),
            build_input,
            persist,
        )
