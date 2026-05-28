from __future__ import annotations

from typing import Any

from interview_mux.context_volley import build_message_volley
from interview_mux.prompt_validation import validate_stage_artifacts
from interview_mux.run_context import RunContext
from interview_mux.stages.llm_runner import run_prompt_envelope

DECOMPOSE_ELIGIBLE = {"segment_classification", "missing_framing"}


def run_shards_then_collate(
    ctx: RunContext,
    *,
    stage_key: str,
    prompt_rel: str,
    stage_input: dict[str, Any],
    shard_plan: list[dict[str, Any]],
) -> tuple[dict[str, Any], int]:
    shard_outputs: list[dict[str, Any]] = []
    for shard in shard_plan[:8]:
        shard_input = _slice_stage_input(stage_key, stage_input, shard)
        volley = build_message_volley(ctx, stage_key, shard_input, profile="shard")
        env = run_prompt_envelope(
            stage_key,
            prompt_rel,
            messages=volley,
            ctx=ctx,
            task_kind="shard",
        )
        shard_outputs.append(
            {
                "label": shard.get("label"),
                "segment_ids": shard.get("segment_ids") or [],
                "start_ms": shard.get("start_ms"),
                "end_ms": shard.get("end_ms"),
                "envelope": env,
            }
        )

    collate_input = {
        "mode": "collate",
        "stage_key": stage_key,
        "shard_outputs": shard_outputs,
        "instruction": "Merge shard outputs into one final stage envelope.",
    }
    collate_volley = build_message_volley(ctx, stage_key, collate_input, profile="collate")
    collate_env = run_prompt_envelope(
        stage_key,
        prompt_rel,
        messages=collate_volley,
        ctx=ctx,
        task_kind="collate",
    )
    artifacts = collate_env.get("artifacts") or {}
    errors = validate_stage_artifacts(stage_key, artifacts)
    if errors:
        collate_env.setdefault("needs", [])
        collate_env["needs"].append(
            {"type": "rerun_stage", "stage": stage_key, "reason": f"collate_schema_errors:{errors[:2]}", "blocking": True}
        )
    return collate_env, len(shard_outputs)


def _slice_stage_input(stage_key: str, stage_input: dict[str, Any], shard: dict[str, Any]) -> dict[str, Any]:
    copied = dict(stage_input)
    segment_ids = set(shard.get("segment_ids") or [])
    if not segment_ids:
        return copied
    if stage_key == "segment_classification" and isinstance(copied.get("boundaries"), dict):
        boundaries = copied["boundaries"].get("boundaries") or []
        copied["boundaries"] = {
            **copied["boundaries"],
            "boundaries": [b for b in boundaries if isinstance(b, dict) and b.get("segment_id") in segment_ids],
        }
        return copied
    if stage_key == "missing_framing":
        segs = copied.get("segments")
        if isinstance(segs, dict):
            all_segments = segs.get("segments") or []
            copied["segments"] = {
                **segs,
                "segments": [s for s in all_segments if isinstance(s, dict) and s.get("segment_id") in segment_ids],
            }
    return copied
