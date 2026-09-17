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


def _drop_blank_segments_under_freeze(
    ctx: RunContext, selection: dict[str, Any]
) -> dict[str, Any]:
    """After seat-freeze order restore, still drop blank/unusable air ids.

    Freeze protects creative order thrash — not silent blank clips that split
    chapters and block EDL narrative QC (exec_11630 seg_041).
    """
    from interview_mux.artifact_repairs import _segment_is_blank_or_unusable
    from interview_mux.artifact_repairs import reconcile_ordered_vs_excluded

    out = dict(selection)
    order = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    blank = [s for s in order if _segment_is_blank_or_unusable(ctx, s)]
    if not blank:
        return out
    kept = [s for s in order if s not in set(blank)]
    if not kept:
        return out
    out["ordered_segment_ids"] = kept
    excl = list(out.get("excluded_segment_ids") or [])
    have = {str(r.get("segment_id") if isinstance(r, dict) else r) for r in excl}
    rat = dict(out.get("exclude_rationales") or {})
    for sid in blank:
        if sid not in have:
            excl.append({"segment_id": sid, "reason": "blank_or_unusable_answer_audio"})
            have.add(sid)
        rat[sid] = str(rat.get(sid) or "blank_or_unusable_answer_audio")
    out["excluded_segment_ids"] = excl
    out["exclude_rationales"] = rat
    keep = set(kept)
    for ch in out.get("chapters") or []:
        if isinstance(ch, dict):
            ch["segment_ids"] = [
                str(x) for x in (ch.get("segment_ids") or []) if str(x) in keep
            ]
    out = reconcile_ordered_vs_excluded(out)
    try:
        from interview_mux.order_hash import bump_order_lock

        out = bump_order_lock(out, source="air_order_boundary.drop_blank_under_freeze")
    except Exception:
        pass
    return out


_SHIP_BLOCKING_OMIT_KINDS = (
    "on_a_roll",
    "incomplete_clause",
    "chapter_bleed_incomplete",
)


_INTEGRITY_OMIT_PRODUCERS = frozenset({"edl_overlap_repair", "segment_id_remap"})


def _ship_blocking_omit_ids(
    ctx: RunContext,
    *,
    prev_ids: list[str],
    cur_ids: list[str],
    selection: dict[str, Any],
    producer: str = "",
) -> list[str]:
    """Ids seat freeze must let leave air: junction incomplete-cut omit/fuse.

    Freeze protects creative order thrash. An omit-only delta (survivors keep
    their relative order) whose ids carry a junction incomplete-cut reason is a
    ship-blocking repair: if freeze restores them, the EDL drops the clip while
    selection keeps it, the divergence rebuild puts it back, and mix refuses
    forever on a residual nobody can clear (exec_11871 seg_014 / seg_071).
    """
    prev = [str(s) for s in (prev_ids or []) if s]
    cur = [str(s) for s in (cur_ids or []) if s]
    cur_set = set(cur)
    removed = [s for s in prev if s not in cur_set]
    if not removed:
        return []
    # Any true reordering (or additions) stays the freeze owner's call.
    if [s for s in prev if s in cur_set] != cur:
        return []
    # A fuse / overlap-union pass retires a consumed id into a survivor whose span
    # already covers the tape — nothing leaves air, so freeze has nothing to
    # protect. Restoring it strands selection at n+1 vs the EDL and mix refuses on
    # `speech/selection order` forever (exec_11871 seg_073→seg_071).
    if str(producer or "") in _INTEGRITY_OMIT_PRODUCERS:
        return removed
    reasons: dict[str, str] = {}
    for row in selection.get("excluded_segment_ids") or []:
        if isinstance(row, dict):
            reasons[str(row.get("segment_id") or "")] = str(row.get("reason") or "")
    rationales = selection.get("exclude_rationales")
    if isinstance(rationales, dict):
        for sid, why in rationales.items():
            reasons.setdefault(str(sid), str(why or ""))
    exempt = [
        sid
        for sid in removed
        if reasons.get(sid, "").startswith("junction_snip_qa:")
        and any(kind in reasons.get(sid, "") for kind in _SHIP_BLOCKING_OMIT_KINDS)
    ]
    if not exempt:
        return []
    try:
        from interview_mux.junction_snip_qa import (
            live_incomplete_cut_critical_findings,
        )

        if not live_incomplete_cut_critical_findings(ctx):
            return []
    except Exception:
        return []
    return exempt


def _preserve_frozen_selection_order(
    out: dict[str, Any],
    *,
    previous: dict[str, Any] | None,
    prev_ids: list[str],
    producer: str,
    stage_key: str,
    refuse_reason: str,
    ctx: RunContext,
) -> dict[str, Any]:
    """Keep frozen air order and restamp so sanitize stamp cannot go stale."""
    restored = dict(out)
    restored["ordered_segment_ids"] = list(prev_ids)
    if isinstance(previous, dict):
        for key in ("order_content_hash", "order_lock", "order_lock_source"):
            if key in previous:
                restored[key] = previous.get(key)
    try:
        from interview_mux.artifact_sanitize.reentry import stamp_sanitize_meta

        restored = stamp_sanitize_meta(
            restored,
            ok=True,
            source=f"seat_freeze_preserve:{producer}",
            actions_n=0,
            extra={
                "preserved_order": True,
                "refused": str(refuse_reason or "")[:120],
            },
            content_keys=["ordered_segment_ids", "order_content_hash"],
        )
    except Exception:
        pass
    try:
        ctx.log(
            "seat_freeze: preserved selection order "
            f"(refused:{refuse_reason or 'meta_gate'}; producer={producer})",
            level="warning",
            stage=stage_key or producer,
        )
    except Exception:
        pass
    # Restoring prior order can leave exclude_rationales pointing at air ids.
    try:
        from interview_mux.artifact_repairs import prune_stale_exclude_rationales

        restored, _ = prune_stale_exclude_rationales(restored)
        # Drop dual membership rows so lint/excluded stay coherent under freeze.
        order_set = {str(s) for s in (restored.get("ordered_segment_ids") or []) if s}
        if isinstance(restored.get("excluded_segment_ids"), list) and order_set:
            restored["excluded_segment_ids"] = [
                row
                for row in restored["excluded_segment_ids"]
                if str(
                    row.get("segment_id") if isinstance(row, dict) else row or ""
                )
                not in order_set
            ]
            restored, _ = prune_stale_exclude_rationales(restored)
    except Exception:
        pass
    return restored


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

        # b8: under seat freeze, order-changing selection commits need meta-gate
        # allow. On refuse: preserve frozen order (no-op) — same pattern as
        # framing/omit writers. Raising here spins full-auto forever because
        # heuristic opportunity for empty-ops order_change stays below threshold.
        try:
            from interview_mux.seat_authority import (
                hard_freeze_active,
                request_seat_rewrite,
                soft_freeze_active,
            )

            if soft_freeze_active(ctx) or hard_freeze_active(ctx):
                prev_ids = [
                    str(s)
                    for s in ((previous or {}).get("ordered_segment_ids") or [])
                    if s
                ]
                cur_ids = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
                exempt_omits = _ship_blocking_omit_ids(
                    ctx,
                    prev_ids=prev_ids,
                    cur_ids=cur_ids,
                    selection=out,
                    producer=producer,
                )
                if prev_ids and prev_ids != cur_ids and exempt_omits:
                    ctx.log(
                        "seat_freeze: honoring ship-blocking omit under freeze "
                        f"({', '.join(exempt_omits[:6])}; producer={producer})",
                        level="warning",
                        stage=stage_key or producer,
                    )
                elif prev_ids and prev_ids != cur_ids:
                    dec = request_seat_rewrite(
                        ctx,
                        proposed_delta={
                            "ops": [],
                            "order_change": True,
                            "source": producer,
                            "stage_key": stage_key,
                        },
                        reason=f"selection_commit:{producer}",
                        symptoms=["order_change", "selection_commit"],
                    )
                    if not dec.get("allow"):
                        out = _preserve_frozen_selection_order(
                            out,
                            previous=previous if isinstance(previous, dict) else None,
                            prev_ids=prev_ids,
                            producer=producer,
                            stage_key=stage_key,
                            refuse_reason=str(
                                dec.get("refuse_reason") or "meta_gate"
                            ),
                            ctx=ctx,
                        )
                        # Blank/unusable must still leave air under freeze — otherwise
                        # chapter continuity QC sees leftover blanks as interlopers
                        # (exec_11630 seg_041) and seat freeze undoes every heal write.
                        out = _drop_blank_segments_under_freeze(ctx, out)
        except Exception:
            try:
                from interview_mux.seat_authority import (
                    hard_freeze_active,
                    soft_freeze_active,
                )

                if soft_freeze_active(ctx) or hard_freeze_active(ctx):
                    prev_ids = [
                        str(s)
                        for s in ((previous or {}).get("ordered_segment_ids") or [])
                        if s
                    ]
                    cur_ids = [
                        str(s) for s in (out.get("ordered_segment_ids") or []) if s
                    ]
                    if (
                        prev_ids
                        and prev_ids != cur_ids
                        and not _ship_blocking_omit_ids(
                            ctx,
                            prev_ids=prev_ids,
                            cur_ids=cur_ids,
                            selection=out,
                            producer=producer,
                        )
                    ):
                        out = _preserve_frozen_selection_order(
                            out,
                            previous=previous if isinstance(previous, dict) else None,
                            prev_ids=prev_ids,
                            producer=producer,
                            stage_key=stage_key,
                            refuse_reason="fail_closed",
                            ctx=ctx,
                        )
                        out = _drop_blank_segments_under_freeze(ctx, out)
            except Exception:
                pass

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


SELECTION_COMMIT_REFUSED_REL = "operator/selection_commit_refused.json"


def stamp_selection_commit_refused(
    ctx: RunContext, *, stage_key: str, error: str
) -> None:
    """HR-2: sidecar so seed-complete cannot mark the writer after a bus refuse."""
    try:
        ctx.write_json(
            SELECTION_COMMIT_REFUSED_REL,
            {
                "version": 1,
                "active": True,
                "stage": str(stage_key or ""),
                "error": str(error or "")[:240],
            },
            skip_handoff=True,
        )
    except Exception:
        pass


def clear_selection_commit_refused(ctx: RunContext, *, stage_key: str) -> None:
    if not ctx.artifact_exists(SELECTION_COMMIT_REFUSED_REL):
        return
    try:
        doc = ctx.read_json(SELECTION_COMMIT_REFUSED_REL)
    except Exception:
        return
    if not isinstance(doc, dict):
        return
    if str(doc.get("stage") or "") != str(stage_key or ""):
        return
    if not doc.get("active"):
        return
    out = dict(doc)
    out["active"] = False
    try:
        ctx.write_json(SELECTION_COMMIT_REFUSED_REL, out, skip_handoff=True)
    except Exception:
        pass


def selection_commit_refused_reason(ctx: RunContext, stage_id: str) -> str | None:
    """Incompleteness prose when this writer last failed an on-bus selection commit."""
    sid = str(stage_id or "").strip()
    if not sid or not ctx.artifact_exists(SELECTION_COMMIT_REFUSED_REL):
        return None
    try:
        doc = ctx.read_json(SELECTION_COMMIT_REFUSED_REL)
    except Exception:
        return None
    if not isinstance(doc, dict) or not doc.get("active"):
        return None
    if str(doc.get("stage") or "") != sid:
        return None
    err = str(doc.get("error") or "commit_refused")
    return f"selection_commit_refused — resume {sid}: {err}"


def commit_selection_or_refuse(
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
    """HR-2: on-bus persist or raise a pin-able refuse (never off-bus write_json)."""
    try:
        out = commit_selection_mutation(
            ctx,
            selection,
            producer=producer,
            stage_key=stage_key,
            checkpoint_mode=checkpoint_mode,
            merge_from_disk=merge_from_disk,
            write_committed=write_committed,
            skip_checkpoint=skip_checkpoint,
            skip_handoff=skip_handoff,
        )
    except Exception as exc:
        stamp_selection_commit_refused(ctx, stage_key=stage_key, error=str(exc))
        raise RuntimeError(
            f"selection_commit_refused — resume {stage_key}: {exc}"
        ) from exc
    clear_selection_commit_refused(ctx, stage_key=stage_key)
    return out


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
