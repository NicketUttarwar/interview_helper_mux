from __future__ import annotations

from interview_mux.context_volley import transcript_quality_for_ctx
from interview_mux.run_context import RunContext
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
        return payload

    def persist(c: RunContext, artifacts: dict) -> None:
        c.write_json("segments/boundaries.json", artifacts)

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
        return {
            "boundaries": c.read_json("segments/boundaries.json"),
            "transcript": c.read_json("transcript/full.json"),
            "speakers": c.read_json("understanding/speakers.json"),
            "content_brief": c.read_json("understanding/content_brief.json"),
        }

    def persist(c: RunContext, artifacts: dict) -> None:
        segments = artifacts.get("segments") or artifacts
        if isinstance(segments, dict):
            segments = segments.get("segments", [])
        c.write_json("segments/manifest.json", {"segments": segments})

    run_analysis_llm_stage(
        ctx,
        "segment_classification",
        "segmentation/segment-classification.system.txt",
        build_input,
        persist,
    )
    ctx.mark_done("segment_classification")
