from __future__ import annotations

from interview_mux.disfluency.context import attach_disfluency_context
from interview_mux.context_volley import transcript_quality_for_ctx
from interview_mux.analysis_memory import load_analysis_state
from interview_mux.llm_specialists import maybe_run_post_stage_specialists
from interview_mux.run_context import RunContext
from interview_mux.stage_enrichment import compact_value_features_summary, pause_ladder_hints
from interview_mux.tone_taxonomy import compact_profile_style_hints
from interview_mux.artifact_completeness import make_stage_persist
from interview_mux.stages.analysis_stage import run_analysis_llm_stage


def run_boundaries(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        payload = {
            "transcript": c.read_json("transcript/full.json"),
            "speakers": c.read_json("understanding/speakers.json"),
            "content_brief": c.read_json("understanding/content_brief.json"),
        }
        quality = transcript_quality_for_ctx(c)
        if quality:
            payload["transcript_quality"] = quality
        payload["pause_ladder_hints"] = pause_ladder_hints(c)
        return attach_disfluency_context(payload, c)

    persist = make_stage_persist("segments/boundaries.json", "boundary_detection")

    run_analysis_llm_stage(
        ctx,
        "boundary_detection",
        "segmentation/boundary-detection.system.txt",
        build_input,
        persist,
    )
    ctx.mark_done("boundary_detection")


def run_classification(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        payload: dict = {
            "boundaries": c.read_json("segments/boundaries.json"),
            "transcript": c.read_json("transcript/full.json"),
            "speakers": c.read_json("understanding/speakers.json"),
            "content_brief": c.read_json("understanding/content_brief.json"),
        }
        hints = compact_profile_style_hints(load_analysis_state(c))
        if hints:
            payload["profile_style"] = hints
        vf = compact_value_features_summary(c)
        if vf:
            payload["value_features_summary"] = vf
        return attach_disfluency_context(payload, c)

    def _manifest_transform(artifacts: dict) -> dict:
        segments = artifacts.get("segments") or artifacts
        if isinstance(segments, dict):
            segments = segments.get("segments", [])
        return {"segments": segments}

    persist = make_stage_persist(
        "segments/manifest.json",
        "segment_classification",
        transform=_manifest_transform,
    )

    run_analysis_llm_stage(
        ctx,
        "segment_classification",
        "segmentation/segment-classification.system.txt",
        build_input,
        persist,
    )
    maybe_run_post_stage_specialists(ctx, "segment_classification", build_input(ctx))
    ctx.mark_done("segment_classification")
