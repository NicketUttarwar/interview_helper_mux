from __future__ import annotations

from typing import Any

from interview_mux.analysis_memory import record_stage_attempt
from interview_mux.context_volley import build_message_volley, truncation_flags_for_volley
from interview_mux.llm_shard_plans import DECOMPOSE_ELIGIBLE
from interview_mux.prompt_validation import validate_stage_artifacts
from interview_mux.run_context import RunContext
from interview_mux.stages.llm_runner import run_prompt_envelope

__all__ = ["DECOMPOSE_ELIGIBLE", "run_shards_then_collate"]


def run_shards_then_collate(
    ctx: RunContext,
    *,
    stage_key: str,
    prompt_rel: str,
    stage_input: dict[str, Any],
    shard_plan: list[dict[str, Any]],
    parent_attempt: int = 1,
) -> tuple[dict[str, Any], int]:
    shard_outputs: list[dict[str, Any]] = []
    for shard_idx, shard in enumerate(shard_plan[:8], start=1):
        shard_input = _slice_stage_input(stage_key, stage_input, shard)
        volley = build_message_volley(ctx, stage_key, shard_input, profile="shard")
        env = run_prompt_envelope(
            stage_key,
            prompt_rel,
            messages=volley,
            ctx=ctx,
            task_kind="shard",
            call_attempt=parent_attempt,
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
        record_stage_attempt(
            ctx,
            stage_key,
            parent_attempt,
            env,
            context_volley=volley,
            task_kind=f"shard_{shard_idx:03d}",
            truncation_flags=truncation_flags_for_volley(volley),
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
        call_attempt=parent_attempt,
    )
    record_stage_attempt(
        ctx,
        stage_key,
        parent_attempt,
        collate_env,
        context_volley=collate_volley,
        task_kind="collate",
        shard_count=len(shard_outputs),
        truncation_flags=truncation_flags_for_volley(collate_volley),
    )
    artifacts = collate_env.get("artifacts") or {}
    errors = validate_stage_artifacts(stage_key, artifacts)
    if errors:
        collate_env.setdefault("needs", [])
        collate_env["needs"].append(
            {
                "type": "rerun_stage",
                "stage": stage_key,
                "reason": f"collate_schema_errors:{errors[:2]}",
                "blocking": True,
            }
        )
    return collate_env, len(shard_outputs)


def _slice_stage_input(stage_key: str, stage_input: dict[str, Any], shard: dict[str, Any]) -> dict[str, Any]:
    copied = dict(stage_input)
    segment_ids = set(shard.get("segment_ids") or [])

    if stage_key == "content_context" and shard.get("text_start") is not None:
        tr = copied.get("transcript")
        text = tr.get("text", "") if isinstance(tr, dict) else str(tr or "")
        start = int(shard["text_start"])
        end = int(shard["text_end"])
        chunk = text[start:end]
        if isinstance(tr, dict):
            copied["transcript"] = {**tr, "text": chunk}
        else:
            copied["transcript"] = chunk
        return copied

    if stage_key == "boundary_detection" and shard.get("start_ms") is not None:
        tr = copied.get("transcript")
        if isinstance(tr, dict) and tr.get("items"):
            start_ms = shard.get("start_ms", 0)
            end_ms = shard.get("end_ms", 0)
            copied["transcript"] = {
                **tr,
                "items": [
                    it
                    for it in tr["items"]
                    if isinstance(it, dict)
                    and it.get("end_ms", 0) >= start_ms
                    and it.get("start_ms", 0) <= end_ms
                ],
            }
        return copied

    if not segment_ids:
        return copied

    if stage_key == "segment_classification" and isinstance(copied.get("boundaries"), dict):
        boundaries = copied["boundaries"].get("boundaries") or []
        copied["boundaries"] = {
            **copied["boundaries"],
            "boundaries": [b for b in boundaries if isinstance(b, dict) and b.get("segment_id") in segment_ids],
        }
    if stage_key in ("missing_framing", "topic_coverage_audit", "highlight_selection", "full_master_ranking"):
        segs = copied.get("segments")
        if isinstance(segs, dict):
            all_segments = segs.get("segments") or []
            copied["segments"] = {
                **segs,
                "segments": [s for s in all_segments if isinstance(s, dict) and s.get("segment_id") in segment_ids],
            }
        elif isinstance(segs, list):
            copied["segments"] = [s for s in segs if isinstance(s, dict) and s.get("segment_id") in segment_ids]
    return copied
