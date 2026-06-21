from __future__ import annotations

from interview_mux.acoustic_profile import compact_for_volley, load_profile, pacing_one_liner
from interview_mux.analysis_memory import load_analysis_state
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.stage_enrichment import compact_value_features_summary, quotability_signals
from interview_mux.tone_taxonomy import compact_profile_style_hints
from interview_mux.artifact_completeness import make_stage_persist
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
        hints = compact_profile_style_hints(load_analysis_state(c))
        if hints:
            payload["profile_style"] = hints
        from interview_mux.interview_spine.compact import attach_spine_to_payload

        attach_spine_to_payload(c, payload, "highlight_selection")
        return payload

    persist = make_stage_persist("flow_2_highlights/selection.json", "highlight_selection")

    with logged_step("highlight_selection/llm_stage", ctx=ctx, stage="highlight_selection"):
        run_flow_llm_stage(
            ctx,
            "highlight_selection",
            "selection/highlight-selection.system.txt",
            build_input,
            persist,
        )
    if ctx.is_done("highlight_selection"):
        signals = quotability_signals(ctx)
        top_ids = [str(s.get("segment_id") or "") for s in signals[:3] if s.get("segment_id")]
        ctx.log(
            f"highlight_selection: quotability top-3 segment_ids={top_ids}",
            level="info",
            stage="highlight_selection",
        )


def run_sfx_brief(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        payload = {
            "selection": c.read_json("flow_2_highlights/selection.json"),
            "content_brief": c.read_json("understanding/content_brief.json"),
        }
        profile = load_profile(c)
        if profile:
            compact = compact_for_volley(profile)
            payload["source_acoustic_profile"] = compact
            payload["pace_class"] = compact.get("pace_class") or pacing_one_liner(profile)
            mix = compact.get("mix_contract") if isinstance(compact.get("mix_contract"), dict) else {}
            if mix.get("underscore_policy"):
                payload["underscore_policy"] = mix["underscore_policy"]
        return payload

    persist = make_stage_persist("flow_2_highlights/sfx_brief.json", "sfx_brief")

    with logged_step("sfx_brief/llm_stage", ctx=ctx, stage="sfx_brief"):
        run_flow_llm_stage(
            ctx,
            "sfx_brief",
            "assembly/sfx-brief.system.txt",
            build_input,
            persist,
        )
