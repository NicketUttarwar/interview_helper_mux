"""v2 simplified LLM gateway: schema validate + one retry, then hard stop."""

from __future__ import annotations

import json
from typing import Any, Callable

from interview_mux.analysis_memory import ensure_analysis_workspace
from interview_mux.prompt_validation import validate_stage_artifacts
from interview_mux.run_context import RunContext
from interview_mux.stages.llm_runner import run_prompt_envelope

PersistFn = Callable[[RunContext, dict[str, Any]], None]
SyncFn = Callable[[RunContext, dict[str, Any]], None]


class StageError(RuntimeError):
    """LLM stage failed after retry budget exhausted."""

    def __init__(
        self,
        stage_key: str,
        message: str,
        *,
        schema_errors: list[str] | None = None,
    ) -> None:
        self.stage_key = stage_key
        self.schema_errors = list(schema_errors or [])
        super().__init__(message)


def _auto_complete_or_raise(ctx: RunContext, stage_key: str) -> None:
    """Footgun #5: auto_complete refuse must not look like stage success."""
    from interview_mux.done_authority import try_mark_done

    if try_mark_done(ctx, stage_key):
        return
    raise StageError(
        stage_key,
        f"LLM stage {stage_key}: auto_complete mark_done refused (Done Authority)",
    )


def _is_retryable_persist_runtime(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return (
        "span coverage" in msg
        or "clustered early" in msg
        or "redistribute across" in msg
    )


def _handle_persist_runtime_error(
    ctx: "RunContext",
    stage_key: str,
    exc: RuntimeError,
    *,
    attempt: int,
) -> bool:
    """Span/quality persist gates: retry once, then StageError (ICP-B4).

    Returns True when the caller should ``continue`` the attempt loop.
    """
    msg = str(exc)
    if _is_retryable_persist_runtime(exc) and attempt < 2:
        ctx.log(
            f"{msg} — retrying LLM (attempt {attempt + 1})",
            level="warning",
            stage=stage_key,
        )
        return True
    if _is_retryable_persist_runtime(exc):
        raise StageError(stage_key, msg) from exc
    raise


def _is_locked_order_rerun_need(need: Any) -> bool:
    """Transitions cannot rerun ranking; locked ordered_segment_ids is air authority."""
    if not isinstance(need, dict):
        return False
    if str(need.get("type") or "").strip() != "rerun_stage":
        return False
    if str(need.get("stage") or "").strip() != "full_master_ranking":
        return False
    reason = str(need.get("reason") or "").lower()
    return any(
        token in reason
        for token in ("exclu", "order", "hard-keep", "must_keep", "locked", "hard keep")
    )


_FAIL_OPEN_PARTIAL_STAGES = frozenset(
    {
        "edl_narrative_audit",
        "sound_design_plan",
        "music_palette_compose",
        "episode_meta_build",
        "episode_cover_prompt_craft",
    }
)


def _fail_open_artifacts(stage_key: str, artifacts: dict[str, Any] | None) -> dict[str, Any]:
    arts = artifacts if isinstance(artifacts, dict) else {}
    if stage_key == "edl_narrative_audit":
        return {
            "verdict": "warn",
            "blocking_issues": list(arts.get("blocking_issues") or []),
            "warnings": list(arts.get("warnings") or []),
            "recommended_actions": list(
                arts.get("recommended_actions")
                or ["fail-open persist after incomplete LLM"]
            ),
            "reasoning_summary": str(
                arts.get("reasoning_summary")
                or "Fail-open persist so EDL is not blocked on an audit loop."
            ),
            "findings": list(arts.get("findings") or []),
        }
    if stage_key == "sound_design_plan":
        if arts.get("assets") or arts.get("flow_plans"):
            return arts
        return {"assets": [], "flow_plans": {"podcast": {"cues": []}}}
    if stage_key == "music_palette_compose":
        if isinstance(arts.get("cues"), list):
            return arts
        return {"cues": []}
    if stage_key == "episode_meta_build":
        return arts
    if stage_key == "episode_cover_prompt_craft":
        return arts
    return arts


def _try_fail_open_partial(
    ctx: RunContext,
    stage_key: str,
    envelope: dict[str, Any],
    persist_artifacts: PersistFn,
    sync_fn: SyncFn | None,
    auto_complete: bool,
    msg: str,
) -> dict[str, Any] | None:
    if stage_key not in _FAIL_OPEN_PARTIAL_STAGES:
        return None
    payload = _fail_open_artifacts(stage_key, envelope.get("artifacts") if isinstance(envelope, dict) else None)
    try:
        return _commit_partial_artifacts(
            ctx,
            stage_key,
            {**envelope, "artifacts": payload, "status": envelope.get("status") or "partial"},
            payload,
            persist_artifacts,
            sync_fn,
            auto_complete,
            msg,
            note="fail-open persist so downstream delivery is not blocked",
        )
    except Exception as exc:
        ctx.log(
            f"{stage_key} fail-open persist failed: {exc}",
            level="warning",
            stage=stage_key,
        )
        return None


def _commit_partial_artifacts(
    ctx: RunContext,
    stage_key: str,
    envelope: dict[str, Any],
    artifacts: dict[str, Any],
    persist_artifacts: PersistFn,
    sync_fn: SyncFn | None,
    auto_complete: bool,
    msg: str,
    *,
    note: str,
) -> dict[str, Any]:
    ctx.log(f"{msg} — {note}", level="warning", stage=stage_key)
    _warn_only_lint(ctx, stage_key, envelope)
    persist_artifacts(ctx, artifacts)
    if sync_fn is not None:
        sync_fn(ctx, envelope)
    if auto_complete:
        _auto_complete_or_raise(ctx, stage_key)
    return envelope


def _warn_only_lint(ctx: RunContext, stage_key: str, envelope: dict[str, Any]) -> None:
    try:
        from interview_mux.deterministic_lint import deterministic_lint

        lint_errors = deterministic_lint(stage_key, envelope, ctx)
        if lint_errors:
            from interview_mux.air_order_integrity import block_ranking_on_critical

            critical_markers = (
                "reverse",
                "opening-tape",
                "opening_tape",
                "hard-keep",
                "late_opening",
                "mid_arc",
            )
            has_critical = any(
                any(m in str(e).lower() for m in critical_markers) for e in lint_errors
            )
            if has_critical and block_ranking_on_critical():
                raise ValueError(
                    "Blocking lint (air order integrity): " + "; ".join(lint_errors[:4])
                )
            ctx.log(
                f"Lint warnings (non-blocking): {'; '.join(lint_errors[:4])}",
                level="warning",
                stage=stage_key,
                detail={"layer": "lint", "blocking": False},
            )
    except Exception:
        return

    try:
        from interview_mux.artifact_cross_validate import validate_cross_artifacts

        checkpoint = {
            "content_brief_reanchor": "post_reanchor",
            "boundary_topic_resplit": "post_boundary_detection",
            "boundary_detection": "post_boundary_detection",
            "segment_classification": "post_segmentation",
        }.get(stage_key)
        if checkpoint:
            cross = validate_cross_artifacts(ctx, checkpoint)
            if cross:
                ctx.log(
                    f"Cross-validate warnings (non-blocking): {'; '.join(cross[:4])}",
                    level="warning",
                    stage=stage_key,
                    detail={"layer": "cross", "checkpoint": checkpoint, "blocking": False},
                )
    except Exception:
        return


def run_llm_stage_simple(
    ctx: RunContext,
    stage_key: str,
    prompt_rel: str,
    build_stage_input: Callable[[RunContext], dict[str, Any]],
    persist_artifacts: PersistFn,
    *,
    sync_fn: SyncFn | None = None,
    auto_complete: bool = True,
) -> dict[str, Any]:
    """Run one LLM stage with at most two attempts (initial + one retry)."""
    ensure_analysis_workspace(ctx)
    base_input = build_stage_input(ctx)
    try:
        from interview_mux.gap_packet_guard import (
            GAP_PACKET_STAGES,
            assert_gap_packet_richness,
            merge_last_volley_input,
            persist_last_volley_input,
        )
        from interview_mux.volley_packet_lint import lint_llm_user_payload

        if isinstance(base_input, dict):
            if stage_key in GAP_PACKET_STAGES:
                base_input = merge_last_volley_input(ctx, stage_key, base_input)
            base_input = lint_llm_user_payload(base_input)
            if isinstance(base_input, dict) and stage_key in GAP_PACKET_STAGES:
                assert_gap_packet_richness(stage_key, base_input)
                persist_last_volley_input(ctx, stage_key, base_input)
    except Exception as exc:
        from interview_mux.gap_packet_guard import GAP_PACKET_STAGES

        if stage_key in GAP_PACKET_STAGES and isinstance(exc, ValueError):
            msg = str(exc)
            ctx.log(msg, level="error", stage=stage_key)
            raise StageError(stage_key, msg) from exc
    user_payload = json.dumps(base_input, indent=2, ensure_ascii=False)
    last_schema_errors: list[str] = []
    envelope: dict[str, Any] = {}

    framing = None
    try:
        from interview_mux.local_volley_framer import prepare_volley_for_llm

        framing = prepare_volley_for_llm(ctx, stage_key, base_input)
    except Exception as exc:
        ctx.log(
            f"Local framer hook skipped for {stage_key}: {exc}",
            level="warning",
            stage=stage_key,
        )
        framing = None

    for attempt in (1, 2):
        retry_note = ""
        if attempt == 2 and last_schema_errors:
            retry_note = (
                "\n\n---\nRETRY: fix schema validation errors from previous attempt:\n"
                + "\n".join(f"- {e}" for e in last_schema_errors[:12])
            )
        user_content = user_payload + retry_note
        volley_messages: list[dict[str, str]] = []
        if framing and framing.used_local and framing.volley_turns:
            volley_messages = list(framing.volley_turns)
        # Plan 1: sequential prior-native-beat turns for gap framing compose/related.
        try:
            from interview_mux.gap_vo_prior_context import (
                GAP_FRAMING_PRIOR_STAGES,
                build_prior_context_volley_turns,
            )

            if stage_key in GAP_FRAMING_PRIOR_STAGES and isinstance(base_input, dict):
                prior_turns = build_prior_context_volley_turns(base_input)
                if prior_turns:
                    volley_messages = [*volley_messages, *prior_turns]
        except Exception as exc:
            ctx.log(
                f"Prior-native volley turns skipped for {stage_key}: {exc}",
                level="warning",
                stage=stage_key,
            )
        messages = [*volley_messages, {"role": "user", "content": user_content}]
        try:
            envelope = run_prompt_envelope(
                stage_key,
                prompt_rel,
                user_content,
                ctx=ctx,
                call_attempt=attempt,
                messages=messages,
                bump_tier=bool(attempt == 2 and stage_key == "gap_framing_compose"),
            )
        except Exception as exc:
            from interview_mux.safe_pruning import SafePruneExhausted

            if isinstance(exc, SafePruneExhausted):
                msg = f"LLM stage {stage_key} failed after safe prune: {exc}"
                ctx.log(msg, level="error", stage=stage_key)
                raise StageError(stage_key, msg) from exc
            if attempt == 2:
                msg = f"LLM stage {stage_key} failed: {exc}"
                ctx.log(msg, level="error", stage=stage_key)
                raise StageError(stage_key, msg) from exc
            last_schema_errors = [str(exc)]
            continue

        if str(envelope.get("status") or "").lower() != "complete":
            needs = envelope.get("needs") or []
            if stage_key == "speaker_roles":
                from interview_mux.speaker_role_evidence import is_unfulfillable_diarization_need

                needs = [
                    ({**n, "blocking": False} if is_unfulfillable_diarization_need(n) else n)
                    if isinstance(n, dict)
                    else n
                    for n in needs
                ]
                envelope = {**envelope, "needs": needs}
            if stage_key == "transitions":
                needs = [
                    ({**n, "blocking": False} if _is_locked_order_rerun_need(n) else n)
                    if isinstance(n, dict)
                    else n
                    for n in needs
                ]
                envelope = {**envelope, "needs": needs}
            if stage_key == "nugget_layup_compose":
                from interview_mux.media_ip_cta import (
                    execute_cta_omit_from_needs,
                    is_selection_cta_omit_need,
                    omit_locked_degraded_cta_scraps,
                )

                dropped = execute_cta_omit_from_needs(ctx, needs)
                extra = omit_locked_degraded_cta_scraps(ctx)
                dropped = list(dict.fromkeys([*(dropped or []), *(extra or [])]))
                if dropped:
                    needs = [
                        ({**n, "blocking": False} if is_selection_cta_omit_need(n) else n)
                        if isinstance(n, dict)
                        else n
                        for n in needs
                    ]
                    envelope = {**envelope, "needs": needs}
                    ctx.log(
                        "nugget_layup_compose: host-executed media-IP CTA omit "
                        + ",".join(dropped[:12]),
                        level="warning",
                        stage=stage_key,
                        detail={"dropped_segment_ids": dropped[:12]},
                    )
                    still_blocking = [
                        n
                        for n in needs
                        if isinstance(n, dict)
                        and n.get("blocking")
                        and n.get("type") != "operator"
                    ]
                    if not still_blocking:
                        raise StageError(
                            stage_key,
                            "LLM stage nugget_layup_compose incomplete: "
                            f"cta_omit_applied dropped {','.join(dropped[:8])}",
                        )
            msg = f"LLM stage {stage_key} incomplete: status={envelope.get('status')} needs={needs[:3]}"
            artifacts = envelope.get("artifacts")
            # Ranking persist is deterministic (CTA omit + hard-keep). A usable
            # ordered_segment_ids list must commit even when the model returns
            # partial/needs_input/blocked over must-keep vs CTA. Do not spend a
            # second 50-shard pass or leave selection.json unwritten.
            if stage_key == "full_master_ranking" and isinstance(artifacts, dict):
                ordered = [
                    str(s) for s in (artifacts.get("ordered_segment_ids") or []) if str(s).strip()
                ]
                if ordered:
                    try:
                        return _commit_partial_artifacts(
                            ctx,
                            stage_key,
                            envelope,
                            artifacts,
                            persist_artifacts,
                            sync_fn,
                            auto_complete,
                            msg,
                            note="persisting usable ranking order; needs demoted to warnings (CTA omit applied in persist)",
                        )
                    except Exception as exc:
                        ctx.log(
                            f"ranking persist of partial failed: {exc}",
                            level="warning",
                            stage=stage_key,
                        )
                        if attempt == 2:
                            raise StageError(stage_key, f"{msg}; persist failed: {exc}") from exc
                        last_schema_errors = [str(exc)]
                        continue
            # Transitions: locked air order is authority. Persist a valid transitions
            # array (empty is allowed) instead of looping on ranking-rerun needs.
            if stage_key == "transitions":
                rows = artifacts.get("transitions") if isinstance(artifacts, dict) else None
                if isinstance(rows, list):
                    try:
                        return _commit_partial_artifacts(
                            ctx,
                            stage_key,
                            envelope,
                            artifacts if isinstance(artifacts, dict) else {"transitions": rows},
                            persist_artifacts,
                            sync_fn,
                            auto_complete,
                            msg,
                            note="persisting transitions; ranking-rerun needs are not blocking",
                        )
                    except Exception as exc:
                        ctx.log(
                            f"transitions persist of partial failed: {exc}",
                            level="warning",
                            stage=stage_key,
                        )
                        if attempt == 2:
                            raise StageError(stage_key, f"{msg}; persist failed: {exc}") from exc
                        last_schema_errors = [str(exc)]
                        continue
                if attempt == 2:
                    empty = {"transitions": []}
                    try:
                        return _commit_partial_artifacts(
                            ctx,
                            stage_key,
                            {**envelope, "artifacts": empty},
                            empty,
                            persist_artifacts,
                            sync_fn,
                            auto_complete,
                            msg,
                            note="persisting empty transitions so sound_design_plan is not blocked",
                        )
                    except Exception as exc:
                        raise StageError(stage_key, f"{msg}; empty persist failed: {exc}") from exc
            # Final attempt: accept when artifacts validate and every need is non-blocking.
            # Long-tape boundary/detection often returns status=partial with a soft
            # "rerun_stage" need even after producing usable segments.
            if attempt == 2:
                artifacts = envelope.get("artifacts")
                soft_needs = [
                    n
                    for n in needs
                    if isinstance(n, dict) and n.get("blocking") is not False
                ]
                if isinstance(artifacts, dict) and not soft_needs:
                    schema_errors = validate_stage_artifacts(stage_key, artifacts)
                    if not schema_errors:
                        ctx.log(
                            f"{msg} — accepting non-blocking partial with valid artifacts",
                            level="warning",
                            stage=stage_key,
                        )
                        _warn_only_lint(ctx, stage_key, envelope)
                        try:
                            persist_artifacts(ctx, artifacts)
                        except RuntimeError as exc:
                            # Attempt 2 only here — wrap span gates as StageError (ICP-B4).
                            if _handle_persist_runtime_error(
                                ctx, stage_key, exc, attempt=attempt
                            ):
                                last_schema_errors = [str(exc)]
                                continue
                        if sync_fn is not None:
                            sync_fn(ctx, envelope)
                        if auto_complete:
                            _auto_complete_or_raise(ctx, stage_key)
                        return envelope
                if stage_key == "speaker_roles":
                    from interview_mux.speaker_role_evidence import (
                        fallback_speakers_artifact,
                    )

                    stage_in = build_stage_input(ctx)
                    fallback = fallback_speakers_artifact(
                        stage_in.get("speaker_talk_stats"),
                        notes=(
                            "LLM requested locked diarization re-run; assigned "
                            "dominant roles from talk stats after G0."
                        ),
                    )
                    if fallback:
                        ctx.log(
                            f"{msg} — mixed-diarization fallback from talk stats",
                            level="warning",
                            stage=stage_key,
                        )
                        persist_artifacts(ctx, fallback)
                        if sync_fn is not None:
                            sync_fn(ctx, fallback)
                        if auto_complete:
                            _auto_complete_or_raise(ctx, stage_key)
                        return {**envelope, "status": "complete", "artifacts": fallback}
                ctx.log(msg, level="error", stage=stage_key)
                committed = _try_fail_open_partial(
                    ctx, stage_key, envelope, persist_artifacts, sync_fn, auto_complete, msg
                )
                if committed is not None:
                    return committed
                raise StageError(stage_key, msg)
            last_schema_errors = [msg]
            continue

        artifacts = envelope.get("artifacts")
        if not isinstance(artifacts, dict):
            msg = f"LLM stage {stage_key} missing artifacts object"
            if attempt == 2:
                committed = _try_fail_open_partial(
                    ctx, stage_key, envelope, persist_artifacts, sync_fn, auto_complete, msg
                )
                if committed is not None:
                    return committed
                raise StageError(stage_key, msg)
            last_schema_errors = [msg]
            continue

        last_schema_errors = validate_stage_artifacts(stage_key, artifacts)
        if last_schema_errors:
            if attempt == 2:
                msg = f"Schema validation failed for {stage_key}: {'; '.join(last_schema_errors[:6])}"
                ctx.log(msg, level="error", stage=stage_key, detail={"schema_errors": last_schema_errors[:8]})
                committed = _try_fail_open_partial(
                    ctx, stage_key, envelope, persist_artifacts, sync_fn, auto_complete, msg
                )
                if committed is not None:
                    return committed
                raise StageError(stage_key, msg, schema_errors=last_schema_errors)
            continue

        _warn_only_lint(ctx, stage_key, envelope)
        try:
            persist_artifacts(ctx, artifacts)
        except RuntimeError as exc:
            # Persist-time quality gates (e.g. ideal_cuts span coverage) should
            # consume the same one-retry budget as schema errors — not abort the
            # whole analysis batch and force an e2e clear_from rewind.
            # After attempt 2: raise StageError (ICP-B4) — never fail-open ideal_cuts.
            if _handle_persist_runtime_error(ctx, stage_key, exc, attempt=attempt):
                last_schema_errors = [str(exc)]
                continue
        if sync_fn is not None:
            sync_fn(ctx, envelope)
        if auto_complete:
            _auto_complete_or_raise(ctx, stage_key)
        ctx.log(
            f"LLM stage {stage_key} complete (v2 simple path, attempt {attempt})",
            level="success",
            stage=stage_key,
        )
        return envelope

    raise StageError(stage_key, f"LLM stage {stage_key} exhausted attempts")
