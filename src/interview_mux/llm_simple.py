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


def _warn_only_lint(ctx: RunContext, stage_key: str, envelope: dict[str, Any]) -> None:
    try:
        from interview_mux.deterministic_lint import deterministic_lint

        lint_errors = deterministic_lint(stage_key, envelope, ctx)
        if lint_errors:
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
            )
        except Exception as exc:
            if attempt == 2:
                msg = f"LLM stage {stage_key} failed: {exc}"
                ctx.log(msg, level="error", stage=stage_key)
                raise StageError(stage_key, msg) from exc
            last_schema_errors = [str(exc)]
            continue

        if str(envelope.get("status") or "").lower() != "complete":
            needs = envelope.get("needs") or []
            msg = f"LLM stage {stage_key} incomplete: status={envelope.get('status')} needs={needs[:3]}"
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
                        persist_artifacts(ctx, artifacts)
                        if sync_fn is not None:
                            sync_fn(ctx, envelope)
                        if auto_complete:
                            ctx.mark_done(stage_key)
                        return envelope
                ctx.log(msg, level="error", stage=stage_key)
                raise StageError(stage_key, msg)
            last_schema_errors = [msg]
            continue

        artifacts = envelope.get("artifacts")
        if not isinstance(artifacts, dict):
            msg = f"LLM stage {stage_key} missing artifacts object"
            if attempt == 2:
                raise StageError(stage_key, msg)
            last_schema_errors = [msg]
            continue

        last_schema_errors = validate_stage_artifacts(stage_key, artifacts)
        if last_schema_errors:
            if attempt == 2:
                msg = f"Schema validation failed for {stage_key}: {'; '.join(last_schema_errors[:6])}"
                ctx.log(msg, level="error", stage=stage_key, detail={"schema_errors": last_schema_errors[:8]})
                raise StageError(stage_key, msg, schema_errors=last_schema_errors)
            continue

        _warn_only_lint(ctx, stage_key, envelope)
        persist_artifacts(ctx, artifacts)
        if sync_fn is not None:
            sync_fn(ctx, envelope)
        if auto_complete:
            ctx.mark_done(stage_key)
        ctx.log(
            f"LLM stage {stage_key} complete (v2 simple path, attempt {attempt})",
            level="success",
            stage=stage_key,
        )
        return envelope

    raise StageError(stage_key, f"LLM stage {stage_key} exhausted attempts")
