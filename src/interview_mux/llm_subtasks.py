from __future__ import annotations

from typing import Any

from interview_mux.analysis_memory import record_stage_attempt
from interview_mux.content_brief_collate import merge_shard_content_brief
from interview_mux.context_volley import truncation_flags_for_volley
from interview_mux.coverage_limits import effective_shard_min_success_ratio
from interview_mux.llm_flow_hardening import flow_hardening_cfg, flow_hardening_enabled
from interview_mux.local_volley_framer import prepare_volley_for_llm
from interview_mux.llm_shard_plans import DECOMPOSE_ELIGIBLE, normalize_shard_plan, shard_batch_cap
from interview_mux.prompt_validation import validate_envelope, validate_stage_artifacts
from interview_mux.run_context import RunContext
from interview_mux.stages.llm_runner import run_prompt_envelope
from interview_mux.truncation_policy import (
    TruncationScan,
    context_cap_boost,
    escalation_boost_rounds,
    log_truncation_event,
)

__all__ = ["DECOMPOSE_ELIGIBLE", "run_shards_then_collate"]


def run_shards_then_collate(
    ctx: RunContext,
    *,
    stage_key: str,
    prompt_rel: str,
    stage_input: dict[str, Any],
    shard_plan: list[dict[str, Any]],
    parent_attempt: int = 1,
    context_cap_boost_round: int = 0,
    clear_field_truncation: bool = False,
) -> tuple[dict[str, Any], int]:
    shard_plan = normalize_shard_plan(stage_key, stage_input, shard_plan)
    cap = shard_batch_cap(len(shard_plan))
    if cap < len(shard_plan):
        shard_plan = shard_plan[:cap]
    plan_len = max(len(shard_plan), 1)

    # Progressive rebuild: if shards are truncation-blocked, boost caps and re-run all shards.
    boost_rounds = [max(0, int(context_cap_boost_round))]
    for extra in escalation_boost_rounds():
        if extra not in boost_rounds:
            boost_rounds.append(extra)

    last_outputs: list[dict[str, Any]] = []
    last_ok: list[dict[str, Any]] = []
    last_failed = 0

    for round_idx in boost_rounds:
        clear_field = bool(clear_field_truncation) or round_idx >= 1
        with context_cap_boost(round_idx, clear_field_truncation=clear_field):
            shard_outputs, ok_shards, failed_count, trunc_fail_count = _run_shard_pass(
                ctx,
                stage_key=stage_key,
                prompt_rel=prompt_rel,
                stage_input=stage_input,
                shard_plan=shard_plan,
                parent_attempt=parent_attempt,
            )
        last_outputs, last_ok, last_failed = shard_outputs, ok_shards, failed_count
        min_ratio = effective_shard_min_success_ratio(plan_len)
        success_ratio = len(ok_shards) / plan_len
        if success_ratio >= min_ratio or not flow_hardening_enabled():
            break
        # Only escalate caps when truncation caused the failures — other errors won't clear with boost.
        if trunc_fail_count <= 0 or round_idx >= boost_rounds[-1]:
            break
        log_truncation_event(
            ctx,
            stage_key=stage_key,
            event="shard_cap_boost_retry",
            scan=TruncationScan(
                truncated=True,
                flags=["field_truncated"],
                locations=[f"shards_failed={trunc_fail_count}"],
            ),
            step=f"cap_boost_r{round_idx + 1}",
        )
        ctx.log(
            f"Stage {stage_key}: {trunc_fail_count}/{plan_len} shards truncation-blocked — "
            f"rebuilding all shards with higher context caps (round {round_idx + 1})",
            level="warning",
            stage=stage_key,
            action_id="truncation.shard_cap_boost_retry",
            detail={
                "from_round": round_idx,
                "ok": len(ok_shards),
                "trunc_fail_count": trunc_fail_count,
            },
        )

    min_ratio = effective_shard_min_success_ratio(plan_len)
    success_ratio = len(last_ok) / plan_len
    if flow_hardening_enabled() and success_ratio < min_ratio:
        if last_ok:
            ctx.log(
                f"Stage {stage_key}: shard success {len(last_ok)}/{plan_len} below {min_ratio} "
                f"— collating partial shard set (soft progression)",
                level="warning",
                stage=stage_key,
            )
        else:
            ctx.log(
                f"Stage {stage_key}: shard success ratio {len(last_ok)}/{plan_len} "
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
                                f"shard_min_success_ratio: {len(last_ok)}/{plan_len} "
                                f"shards complete (need {min_ratio})"
                            ),
                            "blocking": True,
                        }
                    ],
                    "follow_up_investigations": [],
                    "reasoning_summary": f"Collate skipped — {last_failed} shard(s) failed.",
                },
                len(last_outputs),
            )

    collate_shards = last_ok if last_ok else last_outputs
    return _collate_shard_outputs(
        ctx,
        stage_key=stage_key,
        prompt_rel=prompt_rel,
        collate_shards=collate_shards,
        parent_attempt=parent_attempt,
        shard_count=len(last_outputs),
    )


def _run_shard_pass(
    ctx: RunContext,
    *,
    stage_key: str,
    prompt_rel: str,
    stage_input: dict[str, Any],
    shard_plan: list[dict[str, Any]],
    parent_attempt: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int]:
    shard_outputs: list[dict[str, Any]] = []
    ok_shards: list[dict[str, Any]] = []
    failed_count = 0
    trunc_fail_count = 0
    plan_len = max(len(shard_plan), 1)

    for shard_idx, shard in enumerate(shard_plan, start=1):
        shard_input = _slice_stage_input(stage_key, stage_input, shard)
        volley, _ = prepare_volley_for_llm(
            ctx, stage_key, shard_input, profile="shard", task_kind="shard"
        )
        volley_flags = truncation_flags_for_volley(volley)
        # Pre-call rebuild: if this shard volley is still truncated under current boost,
        # do not waste an OpenAI call — count as truncation fail so outer loop boosts.
        if volley_flags:
            env = {
                "status": "blocked",
                "artifacts": {},
                "memory_updates": {},
                "needs": [
                    {
                        "type": "decompose",
                        "stage": stage_key,
                        "reason": f"LLM input truncated: {', '.join(volley_flags[:3])}",
                        "blocking": True,
                    }
                ],
                "follow_up_investigations": [],
                "confidence": 0.0,
                "reasoning_summary": (
                    f"Blocked: truncated LLM input ({', '.join(volley_flags[:3])})"
                ),
                "_llm_meta": {
                    "task_kind": "shard",
                    "truncation_escalation": {
                        "rounds": 1,
                        "steps": ["pre_call_truncation_scan"],
                        "final_flags": list(volley_flags),
                        "provider": "openai",
                    },
                },
            }
        else:
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
        trunc_blocked = bool(
            ((env.get("_llm_meta") or {}).get("truncation_escalation") or {}).get("final_flags")
        ) or bool(volley_flags)
        if stage_key == "boundary_detection":
            from interview_mux.segment_timeline_standard import (
                normalize_shard_envelope,
                reject_or_repair_shard,
            )

            env = normalize_shard_envelope(env, shard)
            shard_entry["envelope"] = env
            schema_errors = validate_stage_artifacts(stage_key, env.get("artifacts") or {})
            reject = reject_or_repair_shard(stage_key, env)
            if reject.rejected:
                failed_count += 1
                ctx.log(
                    f"Shard {shard_idx}/{plan_len} for {stage_key} rejected after timeline normalize "
                    f"({reject.errors[:2]})",
                    level="warning",
                    stage=stage_key,
                    action_id="boundary.shard_rejected",
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
                    from interview_mux.context_resolver import (
                        append_shard_summary,
                        context_index_enabled,
                        write_on_accept,
                    )

                    if context_index_enabled() and write_on_accept():
                        append_shard_summary(
                            ctx,
                            stage_key=stage_key,
                            attempt=parent_attempt,
                            shard_label=str(shard.get("label") or f"shard_{shard_idx}"),
                            reasoning_summary=str(env.get("reasoning_summary") or ""),
                            segment_ids=list(shard.get("segment_ids") or []),
                            shard=shard,
                            envelope=env,
                        )
                except Exception:
                    pass
                continue

        if env.get("status") == "complete" and not schema_errors:
            ok_shards.append(shard_entry)
        else:
            failed_count += 1
            if trunc_blocked:
                trunc_fail_count += 1
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
                    shard=shard,
                    envelope=env,
                )
        except Exception:
            pass

    return shard_outputs, ok_shards, failed_count, trunc_fail_count


def _collate_shard_outputs(
    ctx: RunContext,
    *,
    stage_key: str,
    prompt_rel: str,
    collate_shards: list[dict[str, Any]],
    parent_attempt: int,
    shard_count: int,
) -> tuple[dict[str, Any], int]:
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
        from interview_mux.segment_timeline_standard import contract_ordered_segment_ids

        boundaries = None
        for shard in collate_shards:
            env = shard.get("envelope") if isinstance(shard, dict) else {}
            artifacts = env.get("artifacts") if isinstance(env, dict) else {}
            if isinstance(artifacts, dict) and artifacts.get("segments"):
                break
        contract_ids = None
        try:
            if ctx.artifact_exists("segments/boundaries.json"):
                boundaries = ctx.read_json("segments/boundaries.json")
                contract_ids = contract_ordered_segment_ids(boundaries if isinstance(boundaries, dict) else None)
        except Exception:
            contract_ids = None
        collate_env = _apply_deterministic_segment_collate(
            collate_env,
            collate_shards,
            contract_ids=contract_ids,
        )
    elif stage_key == "content_brief_reanchor":
        baseline_brief = None
        valid_ids: set[str] = set()
        for shard in collate_shards:
            env = shard.get("envelope") if isinstance(shard, dict) else {}
            arts = (env.get("artifacts") or {}) if isinstance(env, dict) else {}
            if isinstance(arts, dict) and arts.get("topics") and baseline_brief is None:
                baseline_brief = arts
        try:
            if ctx.artifact_exists("understanding/content_brief.json"):
                baseline_brief = ctx.read_json("understanding/content_brief.json")
            if ctx.artifact_exists("segments/manifest.json"):
                manifest = ctx.read_json("segments/manifest.json")
                valid_ids = {
                    str(s.get("segment_id"))
                    for s in (manifest.get("segments") or [])
                    if isinstance(s, dict) and s.get("segment_id")
                }
        except Exception:
            pass
        collate_env = merge_shard_content_brief(
            collate_env,
            collate_shards,
            baseline_brief=baseline_brief if isinstance(baseline_brief, dict) else None,
            valid_segment_ids=valid_ids,
        )
        routing = collate_env.get("_routing_meta") if isinstance(collate_env.get("_routing_meta"), dict) else {}
        if routing.get("deterministic_content_brief_collate"):
            topics = (collate_env.get("artifacts") or {}).get("topics") or []
            ctx.log(
                f"Deterministic content brief collate: {len(topics)} topic(s) with union segment_ids",
                level="info",
                stage=stage_key,
                action_id="reanchor.deterministic_collate",
            )
    elif stage_key == "boundary_detection":
        collate_env = _apply_deterministic_boundary_collate(collate_env, collate_shards, ctx=ctx)
        routing = collate_env.get("_routing_meta") if isinstance(collate_env.get("_routing_meta"), dict) else {}
        if routing.get("deterministic_boundary_collate"):
            actions = routing.get("deterministic_boundary_collate_actions") or []
            boundaries = (collate_env.get("artifacts") or {}).get("boundaries") or []
            ctx.log(
                f"Deterministic boundary collate: {len(boundaries)} row(s)"
                + (f", {len(actions)} timeline adjustment(s)" if actions else ""),
                level="info",
                stage=stage_key,
                action_id="boundary.deterministic_collate",
                detail={
                    "boundary_count": len(boundaries),
                    "adjustment_count": len(actions),
                },
            )
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
    return collate_env, shard_count


def _apply_deterministic_boundary_collate(
    collate_env: dict[str, Any],
    shard_outputs: list[dict[str, Any]],
    *,
    ctx: RunContext | None = None,
) -> dict[str, Any]:
    """Union shard boundary rows by timeline (deterministic fallback)."""
    from interview_mux.boundary_collate import boundary_coverage_errors, merge_shard_boundaries
    from interview_mux.interview_duration_policy import transcript_duration_ms
    from interview_mux.segment_timeline_standard import segmentation_cfg

    collate_artifacts = (collate_env.get("artifacts") or {}) if isinstance(collate_env, dict) else {}
    merged_rows, applied = merge_shard_boundaries(
        shard_outputs,
        collate_artifacts=(
            collate_artifacts
            if isinstance(collate_artifacts, dict)
            and not segmentation_cfg().get("deterministic_collate_authoritative", True)
            else None
        ),
    )
    if not merged_rows:
        return collate_env

    duration_ms = transcript_duration_ms(ctx) if ctx is not None else 0
    coverage_errors = boundary_coverage_errors(merged_rows, interview_duration_ms=duration_ms)

    merged = dict(collate_env)
    artifacts = dict(merged.get("artifacts") or {})
    artifacts["boundaries"] = merged_rows
    warnings = list(artifacts.get("warnings") or [])
    if applied:
        warnings.append(
            "Deterministic boundary collate normalized shard timelines "
            f"({len(applied)} adjustment(s))."
        )
    for err in coverage_errors:
        if err not in warnings:
            warnings.append(err)
    if warnings:
        artifacts["warnings"] = warnings
    merged["artifacts"] = artifacts

    routing = dict(merged.get("_routing_meta") or {})
    routing["deterministic_boundary_collate"] = True
    if applied:
        routing["deterministic_boundary_collate_actions"] = applied
    merged["_routing_meta"] = routing

    if coverage_errors:
        merged["status"] = "blocked"
        needs = list(merged.get("needs") or [])
        needs.append(
            {
                "type": "rerun_stage",
                "stage": "boundary_detection",
                "reason": coverage_errors[0],
                "blocking": True,
            }
        )
        merged["needs"] = needs
        if ctx is not None:
            ctx.log(
                f"Boundary collate blocked: {coverage_errors[0]}",
                level="error",
                stage="boundary_detection",
                action_id="boundary.collate_coverage_blocked",
                detail={"coverage_errors": coverage_errors[:3], "duration_ms": duration_ms},
            )
        return merged

    if merged.get("status") != "complete" and merged_rows:
        merged["status"] = "complete"
    return merged


def _apply_deterministic_segment_collate(
    collate_env: dict[str, Any],
    shard_outputs: list[dict[str, Any]],
    *,
    contract_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Union shard segment rows by segment_id (deterministic fallback)."""
    from interview_mux.segment_timeline_standard import segmentation_cfg

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
    order = contract_ids or sorted(by_id.keys())
    merged_segments = [by_id[sid] for sid in order if sid in by_id]
    if not merged_segments:
        return collate_env
    merged = dict(collate_env)
    artifacts = dict(merged.get("artifacts") or {})
    if segmentation_cfg().get("deterministic_classification_collate_authoritative", True):
        artifacts["segments"] = merged_segments
    else:
        llm_segments = artifacts.get("segments") or []
        if isinstance(llm_segments, list) and llm_segments:
            for row in llm_segments:
                if isinstance(row, dict) and row.get("segment_id"):
                    by_id[str(row["segment_id"])] = row
            artifacts["segments"] = [by_id[sid] for sid in order if sid in by_id]
        else:
            artifacts["segments"] = merged_segments
    merged["artifacts"] = artifacts
    routing = dict(merged.get("_routing_meta") or {})
    routing["deterministic_segment_collate"] = True
    merged["_routing_meta"] = routing
    if merged.get("status") != "complete" and merged_segments:
        merged["status"] = "complete"
    return merged


def _filter_segments_by_ids(raw: Any, segment_ids: set[Any]) -> Any:
    if isinstance(raw, dict):
        all_segments = raw.get("segments") or []
        return {
            **raw,
            "segments": [
                s
                for s in all_segments
                if isinstance(s, dict) and s.get("segment_id") in segment_ids
            ],
        }
    if isinstance(raw, list):
        return [s for s in raw if isinstance(s, dict) and s.get("segment_id") in segment_ids]
    return raw


def _slice_pause_ladder_hints(
    hints: dict[str, Any] | None,
    *,
    start_ms: int,
    end_ms: int,
    snap_tolerance_ms: int = 500,
) -> dict[str, Any] | None:
    if not isinstance(hints, dict):
        return hints
    window_start = int(start_ms) - snap_tolerance_ms
    window_end = int(end_ms) + snap_tolerance_ms
    sliced = dict(hints)
    for key in ("candidates", "pre_thin_candidates"):
        raw = hints.get(key)
        if not isinstance(raw, list):
            continue
        new_candidates: list[dict[str, Any]] = []
        for candidate in raw:
            if not isinstance(candidate, dict):
                continue
            times = [
                int(t)
                for t in (candidate.get("split_times_ms") or [])
                if window_start <= int(t) <= window_end
            ]
            new_candidates.append({**candidate, "split_times_ms": times, "count": len(times)})
        sliced[key] = new_candidates
    return sliced


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
        copied["boundary_shard_window"] = {
            "label": shard.get("label"),
            "start_ms": start_ms,
            "end_ms": end_ms,
            "absolute_timestamps_required": True,
        }
        hints = copied.get("pause_ladder_hints")
        if isinstance(hints, dict):
            copied["pause_ladder_hints"] = _slice_pause_ladder_hints(
                hints,
                start_ms=start_ms,
                end_ms=end_ms,
            )
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

    # Generic segment-id filtering for reanchor / classification / ranking / gaps / audits.
    if "segments" in copied:
        copied["segments"] = _filter_segments_by_ids(copied.get("segments"), segment_ids)

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
    return copied
