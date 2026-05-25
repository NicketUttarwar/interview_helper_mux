from __future__ import annotations

from interview_mux.context_volley import transcript_quality_for_ctx
from interview_mux.run_context import RunContext
from interview_mux.stages.analysis_stage import (
    run_analysis_llm_stage,
    sync_content_brief_to_state,
    sync_speakers_to_state,
)


def run_speaker_roles(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        transcript = c.read_json("transcript/full.json")
        speakers = c.read_json("transcript/speakers.json")
        return {
            "transcript_excerpt": transcript.get("text", "")[:12000],
            "speakers": speakers,
        }

    def persist(c: RunContext, artifacts: dict) -> None:
        c.write_json("understanding/speakers.json", artifacts)

    run_analysis_llm_stage(
        ctx,
        "speaker_roles",
        "understanding/speaker-roles.system.txt",
        build_input,
        persist,
        sync_fn=lambda c, a: sync_speakers_to_state(c, a if "speakers" in a else {"speakers": a.get("speakers", [])}),
    )
    ctx.mark_done("speaker_roles")


def run_content_context(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        transcript = c.read_json("transcript/full.json")
        payload: dict = {"transcript": transcript.get("text", "")}
        quality = transcript_quality_for_ctx(c)
        if quality:
            payload["transcript_quality"] = quality
        return payload

    def persist(c: RunContext, artifacts: dict) -> None:
        brief = artifacts
        c.write_json("understanding/content_brief.json", brief)

    run_analysis_llm_stage(
        ctx,
        "content_context",
        "understanding/content-context.system.txt",
        build_input,
        persist,
        sync_fn=lambda c, a: sync_content_brief_to_state(c, a),
    )
    ctx.mark_done("content_context")
