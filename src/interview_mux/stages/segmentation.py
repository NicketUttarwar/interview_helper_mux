"""Boundary detection and segment classification stages."""

from __future__ import annotations

from interview_mux.disfluency.context import attach_disfluency_context
from interview_mux.context_volley import transcript_quality_for_ctx
from interview_mux.analysis_memory import load_analysis_state
from interview_mux.llm_specialists import maybe_run_post_stage_specialists
from interview_mux.run_context import RunContext
from interview_mux.boundary_observability import observe_boundary_detection_input, pace_class_from_sap
from interview_mux.operator_trace import logged_step
from interview_mux.stage_enrichment import compact_value_features_summary, pause_ladder_hints
from interview_mux.tone_taxonomy import compact_profile_style_hints
from interview_mux.artifact_completeness import make_stage_persist
from interview_mux.production_profile import prompt_variant
from interview_mux.source_topology import attach_adaptation_to_payload
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
        pace = pace_class_from_sap(c)
        raw_hints = payload["pause_ladder_hints"]
        from interview_mux.stage_enrichment import thin_pause_ladder_hints

        payload["pause_ladder_hints"] = thin_pause_ladder_hints(raw_hints, pace)
        pre_thin = {"candidates": list(raw_hints.get("candidates") or [])}
        if c.artifact_exists("understanding/source_acoustic_profile.json"):
            payload["source_acoustic_profile"] = {
                "pacing": {"pace_class": pace},
            }
        from interview_mux.interview_spine.compact import attach_spine_to_payload

        from interview_mux.conversation_context import attach_conversation_context

        attach_spine_to_payload(c, payload, "boundary_detection")
        observe_boundary_detection_input(c, payload, pre_thin_counts=pre_thin)
        payload = attach_conversation_context(c, payload, "boundary_detection")
        return attach_disfluency_context(payload, c)

    persist = make_stage_persist("segments/boundaries.json", "boundary_detection")

    with logged_step("boundary_detection/llm_stage", ctx=ctx, stage="boundary_detection"):
        run_analysis_llm_stage(
            ctx,
            "boundary_detection",
            "segmentation/boundary-detection.system.txt",
            build_input,
            persist,
        )


def run_classification(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        from interview_mux.segmentation_input_resolver import build_classification_payload

        return build_classification_payload(c)

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

    with logged_step("segment_classification/llm_stage", ctx=ctx, stage="segment_classification"):
        run_analysis_llm_stage(
            ctx,
            "segment_classification",
            prompt_variant("segmentation/segment-classification.system.txt", ctx),
            build_input,
            persist,
        )
    with logged_step("segment_classification/post_specialists", ctx=ctx, stage="segment_classification"):
        maybe_run_post_stage_specialists(ctx, "segment_classification", build_input(ctx))
