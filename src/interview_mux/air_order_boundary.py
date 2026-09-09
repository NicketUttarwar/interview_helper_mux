"""Federated air-order boundary bus: constitution checkpoints + mutation lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from interview_mux.run_context import RunContext

CheckpointMode = Literal["detect", "repair", "block"]

_NLE_SOFTEN_CODES = frozenset(
    {"mid_arc_reverse_jump", "late_opening_cluster", "chapter_opening_mask"}
)

_PRODUCER_DETECT_ONLY = frozenset(
    {
        "edl_narrative_remutate",
        "junction_snip_qa",
        "air_order",
        "timeline_optimizer",
    }
)


@dataclass
class CheckpointResult:
    violations: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    critical_remaining: bool = False
    nle_overlay_softened: bool = False
    repaired: bool = False


def nle_overlay_active(ctx: RunContext) -> bool:
    try:
        from interview_mux.nle_state import load_nle, nle_has_operator_edits

        return nle_has_operator_edits(load_nle(ctx))
    except Exception:
        return False


def _effective_mode(producer: str, mode: CheckpointMode) -> CheckpointMode:
    if producer in _PRODUCER_DETECT_ONLY and mode in {"repair", "block"}:
        return "detect"
    return mode


def _critical_for_blocking(
    violations: list[dict[str, Any]],
    *,
    nle_softened: bool,
) -> list[dict[str, Any]]:
    from interview_mux.air_order_integrity import critical_violations

    critical = critical_violations(violations)
    if not nle_softened:
        return critical
    return [v for v in critical if str(v.get("code") or "") not in _NLE_SOFTEN_CODES]


def checkpoint_air_order(
    ctx: RunContext,
    selection: dict[str, Any],
    *,
    producer: str,
    mode: CheckpointMode = "repair",
) -> tuple[dict[str, Any], CheckpointResult]:
    """Run constitution checkpoint after stage domain logic, before persist."""
    from interview_mux.air_order_integrity import (
        collect_violations,
        repair_air_order_integrity,
        write_air_order_integrity_report,
    )

    effective = _effective_mode(producer, mode)
    out = dict(selection)
    actions: list[dict[str, Any]] = []
    repaired = False
    if effective in {"repair", "block"}:
        out, actions = repair_air_order_integrity(ctx, out)
        repaired = bool(actions)
    violations = collect_violations(ctx, out)
    nle_soft = nle_overlay_active(ctx)
    critical_remaining = bool(_critical_for_blocking(violations, nle_softened=nle_soft))
    result = CheckpointResult(
        violations=violations,
        actions=actions,
        critical_remaining=critical_remaining,
        nle_overlay_softened=nle_soft,
        repaired=repaired,
    )
    write_air_order_integrity_report(
        ctx,
        violations=violations,
        actions=actions,
        stage=producer,
        repaired=repaired,
    )
    return out, result


def should_block_commit(
    result: CheckpointResult,
    *,
    producer: str,
    mode: CheckpointMode,
) -> bool:
    from interview_mux.air_order_integrity import block_ranking_on_critical

    if _effective_mode(producer, mode) == "detect":
        return False
    if not block_ranking_on_critical():
        return False
    return result.critical_remaining


def _previous_selection(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists("master/selection.json"):
        return None
    try:
        doc = ctx.read_json("master/selection.json")
    except Exception:
        return None
    return dict(doc) if isinstance(doc, dict) else None


def commit_selection_mutation(
    ctx: RunContext,
    selection: dict[str, Any],
    *,
    producer: str,
    stage_key: str,
    checkpoint_mode: CheckpointMode = "repair",
    merge_from_disk: bool = False,
    write_committed: bool = False,
    skip_checkpoint: bool = False,
    skip_handoff: bool = False,
) -> dict[str, Any]:
    """Single write path: checkpoint, optional block, persist, lifecycle on order change."""
    from interview_mux.artifact_sanitize.one_writer import (
        admitting,
        begin_admit,
        end_admit,
    )

    nested_admit = admitting(ctx)
    if not nested_admit:
        begin_admit(ctx)
    try:
        previous = _previous_selection(ctx)
        out = dict(selection)
        result = CheckpointResult()
        if not skip_checkpoint:
            out, result = checkpoint_air_order(
                ctx, out, producer=producer, mode=checkpoint_mode
            )
            if should_block_commit(result, producer=producer, mode=checkpoint_mode):
                msgs = [
                    str(v.get("message") or v.get("code") or "")
                    for v in result.violations
                    if str(v.get("severity") or "").lower() == "critical"
                ][:3]
                raise ValueError(
                    f"air_order_boundary blocked {producer}: " + "; ".join(msgs)
                )

        # Sanitize-last: non-amplifying sanitize after any repair/checkpoint, before disk.
        from interview_mux.artifact_sanitize.selection import sanitize_master_selection

        sanitize_result = sanitize_master_selection(ctx, out)
        if not sanitize_result.ok:
            raise RuntimeError(
                "sanitize_refused:selection: "
                + "; ".join((sanitize_result.errors or ["unknown"])[:4])
            )
        out = sanitize_result.doc if isinstance(sanitize_result.doc, dict) else out

        try:
            from interview_mux.artifact_sanitize.reentry import sanitary_content_hash
            from interview_mux.thrash_hardening import note_authority_undo_attempt

            undo = note_authority_undo_attempt(
                ctx,
                artifact="master/selection.json",
                action_class=str(producer or stage_key or "selection_commit"),
                content_hash=sanitary_content_hash(
                    out, keys=["ordered_segment_ids", "order_content_hash"]
                ),
            )
            if undo.get("halt"):
                raise RuntimeError(
                    "authority_undo_thrash:master/selection.json: "
                    + str(undo.get("reason") or "oscillation")
                )
        except RuntimeError:
            raise
        except Exception:
            pass

        if write_committed:
            from interview_mux.write_staging import write_committed_json

            write_committed_json(ctx, "master/selection.json", out, stage_key=stage_key)
        elif skip_handoff:
            ctx.write_json(
                "master/selection.json", out, stage_key=stage_key, skip_handoff=True
            )
        else:
            # Prefer write_committed so write_validated cannot re-amplify after sanitize.
            from interview_mux.write_staging import write_committed_json

            write_committed_json(ctx, "master/selection.json", out, stage_key=stage_key)

        from interview_mux.air_order_integrity import on_selection_order_changed

        on_selection_order_changed(
            ctx,
            source=producer,
            previous=previous,
            current=out,
        )
        return out
    finally:
        if not nested_admit:
            end_admit(ctx)


def commit_selection_via(
    ctx: RunContext,
    selection: dict[str, Any],
    *,
    producer: str,
    stage_key: str,
    checkpoint_mode: CheckpointMode,
    writer: Callable[..., Any],
    writer_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Checkpoint + lifecycle wrapper for callers that need a custom writer."""
    previous = _previous_selection(ctx)
    out, result = checkpoint_air_order(
        ctx, dict(selection), producer=producer, mode=checkpoint_mode
    )
    if should_block_commit(result, producer=producer, mode=checkpoint_mode):
        raise ValueError(f"air_order_boundary blocked {producer}")
    kwargs = dict(writer_kwargs or {})
    writer(ctx, "master/selection.json", out, **kwargs)
    from interview_mux.air_order_integrity import on_selection_order_changed

    on_selection_order_changed(
        ctx, source=producer, previous=previous, current=out
    )
    return out
