from __future__ import annotations

from typing import Any

from interview_mux.analysis_memory import record_stage_attempt
from interview_mux.context_volley import truncation_flags_for_volley
from interview_mux.llm_flow_hardening import flow_hardening_cfg, flow_hardening_enabled
from interview_mux.local_volley_framer import prepare_volley_for_llm
from interview_mux.llm_shard_plans import DECOMPOSE_ELIGIBLE, normalize_shard_plan
from interview_mux.prompt_validation import validate_envelope, validate_stage_artifacts
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
    ok_shards: list[dict[str, Any]] = []
    failed_count = 0
    shard_plan = normalize_shard_plan(stage_key, stage_input, shard_plan[:8])
    plan_len = max(len(shard_plan), 1)

    for shard_idx, shard in enumerate(shard_plan, start=1):
        shard_input = _slice_stage_input(stage_key, stage_input, shard)
        volley, _ = prepare_volley_for_llm(
            ctx, stage_key, shard_input, profile="shard", task_kind="shard"
        )
        env = run_prompt_envelope(
            stage_key,
            prompt_rel,
            messages=volley,
            ctx=ctx,
            task_kind="shard",
            call_attempt=parent_attempt,
        )
        shard_entry = {
            "label": shard.get("label"),
            "segment_ids": shard.get("segment_ids") or [],
            "start_ms": shard.get("start_ms"),
            "end_ms": shard.get("end_ms"),
            "envelope": env,
        }
        shard_outputs.append(shard_entry)
        schema_errors = validate_stage_artifacts(stage_key, env.get("artifacts") or {})
        if env.get("status") == "complete" and not schema_errors:
            ok_shards.append(shard_entry)
        else:
            failed_count += 1
            ctx.log(
                f"Shard {shard_idx}/{plan_len} for {stage_key} failed "
                f"(status={env.get('status')}, schema_errors={schema_errors[:2]})",
                level="warning",
                stage=stage_key,
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
        try:
            from interview_mux.context_resolver import append_shard_summary, context_index_enabled, write_on_accept

            if context_index_enabled() and write_on_accept():
                append_shard_summary(
                    ctx,
                    stage_key=stage_key,
                    attempt=parent_attempt,
                    shard_label=str(shard.get("label") or f"shard_{shard_idx}"),
                    reasoning_summary=str(env.get("reasoning_summary") or ""),
                    segment_ids=list(shard.get("segment_ids") or []),
                )
        except Exception:
            pass

    min_ratio = float(flow_hardening_cfg().get("shard_min_success_ratio", 0.75))
    if flow_hardening_enabled() and len(ok_shards) / plan_len < min_ratio:
        ctx.log(
            f"Stage {stage_key}: shard success ratio {len(ok_shards)}/{plan_len} "
            f"below minimum {min_ratio}",
            level="warning",
            stage=stage_key,
        )
        return (
            {
                "status": "blocked",
                "artifacts": {},
                "memory_updates": {},
                "needs": [
                    {
                        "type": "rerun_stage",
                        "stage": stage_key,
                        "reason": (
                            f"shard_min_success_ratio: {len(ok_shards)}/{plan_len} "
                            f"shards complete (need {min_ratio})"
                        ),
                        "blocking": True,
                    }
                ],
                "follow_up_investigations": [],
                "reasoning_summary": f"Collate skipped — {failed_count} shard(s) failed.",
            },
            len(shard_outputs),
        )

    collate_shards = ok_shards if ok_shards else shard_outputs
    collate_input = {
        "mode": "collate",
        "stage_key": stage_key,
        "shard_outputs": collate_shards,
        "instruction": "Merge shard outputs into one final stage envelope.",
    }
    collate_volley, _ = prepare_volley_for_llm(
        ctx, stage_key, collate_input, profile="collate", task_kind="collate"
    )
    collate_env = run_prompt_envelope(
        stage_key,
        prompt_rel,
        messages=collate_volley,
        ctx=ctx,
        task_kind="collate",
        call_attempt=parent_attempt,
    )
    artifacts = collate_env.get("artifacts") or {}
    errors = validate_stage_artifacts(stage_key, artifacts)
    env_errors = validate_envelope(collate_env)
    all_errors = errors + env_errors
    if all_errors:
        from interview_mux.prompt_validation import format_validation_feedback

        collate_volley = [
            *collate_volley,
            {"role": "assistant", "content": f"Prior collate status: {collate_env.get('status')}"},
            {
                "role": "user",
                "content": format_validation_feedback(all_errors, stage_key=stage_key),
            },
        ]
        collate_env = run_prompt_envelope(
            stage_key,
            prompt_rel,
            messages=collate_volley,
            ctx=ctx,
            task_kind="collate",
            call_attempt=parent_attempt,
            volley_retry_index=1,
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
    if stage_key == "segment_classification":
        collate_env = _apply_deterministic_segment_collate(collate_env, collate_shards)
    record_stage_attempt(
        ctx,
        stage_key,
        parent_attempt,
        collate_env,
        context_volley=collate_volley,
        task_kind="collate",
        shard_count=len(collate_shards),
        truncation_flags=truncation_flags_for_volley(collate_volley),
    )
    return collate_env, len(shard_outputs)

def _apply_deterministic_segment_collate(
    collate_env: dict[str, Any],
    shard_outputs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Union shard segment rows by segment_id (deterministic fallback)."""
    by_id: dict[str, dict[str, Any]] = {}
    for shard in shard_outputs:
        env = shard.get("envelope") or {}
        artifacts = env.get("artifacts") or {}
        segments = artifacts.get("segments") or []
        if not isinstance(segments, list):
            continue
        for seg in segments:
            if isinstance(seg, dict) and seg.get("segment_id"):
                by_id[str(seg["segment_id"])] = seg
    if not by_id:
        return collate_env
    merged = dict(collate_env)
    artifacts = dict(merged.get("artifacts") or {})
    artifacts["segments"] = [by_id[k] for k in sorted(by_id.keys())]
    merged["artifacts"] = artifacts
    if merged.get("status") != "complete" and len(by_id) >= 1:
        merged["status"] = "complete"
    return merged

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
        start_ms = int(shard.get("start_ms", 0))
        end_ms = int(shard.get("end_ms", 0))
        if isinstance(tr, dict):
            sliced = dict(tr)
            if tr.get("items"):
                sliced["items"] = [
                    it
                    for it in tr["items"]
                    if isinstance(it, dict)
                    and int(it.get("end_ms", 0)) >= start_ms
                    and int(it.get("start_ms", 0)) <= end_ms
                ]
            if tr.get("words"):
                sliced["words"] = [
                    w
                    for w in tr["words"]
                    if isinstance(w, dict)
                    and int(w.get("end_ms", 0)) >= start_ms
                    and int(w.get("start_ms", 0)) <= end_ms
                ]
            if isinstance(tr.get("text"), str) and sliced.get("words"):
                sliced["text"] = " ".join(
                    str(w.get("text") or "") for w in sliced["words"] if isinstance(w, dict)
                )
            spine = copied.get("interview_spine")
            if isinstance(spine, dict) and spine.get("boundary_events"):
                sliced_spine = dict(spine)
                sliced_spine["boundary_events"] = [
                    ev
                    for ev in spine["boundary_events"]
                    if isinstance(ev, dict)
                    and int(ev.get("start_ms") or ev.get("time_ms") or 0) <= end_ms
                    and int(ev.get("end_ms") or ev.get("start_ms") or ev.get("time_ms") or 0) >= start_ms
                ]
                copied["interview_spine"] = sliced_spine
            copied["transcript"] = sliced
        return copied

    if not segment_ids:
        return copied

    if stage_key == "segment_classification" and isinstance(copied.get("boundaries"), dict):
        boundaries = copied["boundaries"].get("boundaries") or []
        copied["boundaries"] = {
            **copied["boundaries"],
            "boundaries": [b for b in boundaries if isinstance(b, dict) and b.get("segment_id") in segment_ids],
        }
        obligation = copied.get("classification_obligation")
        if isinstance(obligation, dict) and obligation.get("segments"):
            copied["classification_obligation"] = {
                **obligation,
                "segments": [
                    s
                    for s in obligation["segments"]
                    if isinstance(s, dict) and str(s.get("segment_id")) in segment_ids
                ],
                "required_segment_ids": sorted(segment_ids),
                "required_count": len(segment_ids),
            }
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
