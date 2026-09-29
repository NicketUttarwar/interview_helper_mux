"""Single authority for taking a segment off air.

Many producers remove segments: ranking, junction QA, overlap repair, media-IP
CTA, the NLE, sanitize repairs. Each carried its own "not if it is a hard
keep" guard, and the guards disagreed about what a hard keep was once a keep's
tape moved under another segment (ISSUES entries 64 and 73: the carrier of a
retired keep was cut by a producer whose local guard saw no keep). Every guard
was locally right and the run still shipped without the keep.

Two writes can take a segment off air: an air-order write that drops it from
``ordered_segment_ids`` and an NLE override that sets ``excluded``. Both go
through here, judged against the state the write would produce, not the state
on disk. Producers keep their local refusals for early, cheaper exits; the
decision that counts is this one.
"""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def protected_segment_ids(
    ctx: RunContext,
    *,
    overrides: dict[str, Any] | None = None,
    on_air: list[str] | None = None,
) -> set[str]:
    """Ids that may not leave the air under the proposed state.

    A keep whose tape a proposed carrier covers is released, and the carrier is
    protected in its place, so a legitimate retire (entry 64) still passes.
    """
    try:
        from interview_mux.hard_keep import hard_keep_segment_ids

        return set(hard_keep_segment_ids(ctx, overrides=overrides, on_air=on_air) or [])
    except Exception:
        return set()


def removal_block_reason(
    ctx: RunContext,
    segment_id: str,
    *,
    overrides: dict[str, Any] | None = None,
    on_air: list[str] | None = None,
) -> str | None:
    """Reason ``segment_id`` may not come off air under the proposed state."""
    sid = str(segment_id or "")
    if not sid:
        return None
    if sid in protected_segment_ids(ctx, overrides=overrides, on_air=on_air):
        return "hard_keep"
    return None


def refuse_selection_removals(
    ctx: RunContext,
    previous: dict[str, Any] | None,
    proposed: dict[str, Any],
    *,
    producer: str,
) -> dict[str, Any]:
    """Put back any protected id the proposed order drops.

    Restored ids go back after their nearest surviving predecessor from the
    previous order, so a repair that cut one segment does not reshuffle the
    rest. The refusal is logged with the producer so the operator can see who
    tried.
    """
    prev_ids = [str(s) for s in ((previous or {}).get("ordered_segment_ids") or []) if s]
    cur_ids = [str(s) for s in (proposed.get("ordered_segment_ids") or []) if s]
    if not prev_ids or not isinstance(proposed.get("ordered_segment_ids"), list):
        return proposed
    cur_set = set(cur_ids)
    dropped = [s for s in prev_ids if s not in cur_set]
    if not dropped:
        return proposed
    # Judge under both states: a carrier is protected only while its retired
    # keep is covered, which is the previous order (with the carrier on air),
    # not the proposed one (where the keep is bare and the carrier looks free).
    protected = protected_segment_ids(ctx, on_air=cur_ids) | protected_segment_ids(
        ctx, on_air=prev_ids
    )
    blocked = [s for s in dropped if s in protected]
    if not blocked:
        return proposed
    restored = list(cur_ids)
    for sid in blocked:
        if sid in restored:
            continue
        at = len(restored)
        pos = prev_ids.index(sid)
        for prior in reversed(prev_ids[:pos]):
            if prior in restored:
                at = restored.index(prior) + 1
                break
        else:
            at = 0
        restored.insert(at, sid)
    out = dict(proposed)
    out["ordered_segment_ids"] = restored
    excl = [
        e
        for e in (out.get("excluded_segment_ids") or [])
        if (e if isinstance(e, str) else str((e or {}).get("segment_id") or "")) not in blocked
    ]
    out["excluded_segment_ids"] = excl
    try:
        from interview_mux.order_hash import bump_order_lock

        out = bump_order_lock(out, source=f"{producer}:removal_refused")
    except Exception:
        pass
    try:
        ctx.log(
            "removal_authority: refused to take must-air segment(s) off the order: "
            + ", ".join(blocked[:8])
            + f" (producer={producer})",
            level="warning",
            stage=str(producer or "selection"),
            detail={"segment_ids": blocked, "producer": producer},
        )
    except Exception:
        pass
    return out


def refuse_nle_excludes(
    ctx: RunContext,
    data: dict[str, Any],
    *,
    producer: str,
) -> dict[str, Any]:
    """Clear a proposed ``excluded`` flag on any id that must air.

    Judged against the proposed overrides: a keep the proposed state retires
    under a carrier is released; the carrier itself cannot be excluded.
    """
    overrides = data.get("segment_overrides") if isinstance(data, dict) else None
    if not isinstance(overrides, dict) or not overrides:
        return data
    newly = [
        str(sid)
        for sid, row in overrides.items()
        if isinstance(row, dict) and row.get("excluded") and not row.get("split_into")
    ]
    if not newly:
        return data
    protected = protected_segment_ids(ctx, overrides=overrides)
    blocked = [s for s in newly if s in protected]
    if not blocked:
        return data
    out = dict(data)
    ov = dict(overrides)
    for sid in blocked:
        row = dict(ov.get(sid) or {})
        row.pop("excluded", None)
        row.pop("exclude_reason", None)
        row["removal_refused"] = "hard_keep"
        ov[sid] = row
    out["segment_overrides"] = ov
    try:
        ctx.log(
            "removal_authority: refused NLE exclude of must-air segment(s): "
            + ", ".join(blocked[:8])
            + f" (producer={producer})",
            level="warning",
            stage=str(producer or "nle"),
            detail={"segment_ids": blocked, "producer": producer},
        )
    except Exception:
        pass
    return out
