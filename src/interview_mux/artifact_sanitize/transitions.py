"""Sanitize master/transitions.json — selection-class (W4)."""

from __future__ import annotations

from typing import Any

from interview_mux.artifact_sanitize.reentry import stamp_sanitize_meta
from interview_mux.artifact_sanitize.types import SanitizeResult

REL = "master/transitions.json"
FREEZE_REL = "master/transitions_pair_freeze.json"


def _selection_order(ctx: Any) -> list[str]:
    if not ctx.artifact_exists("master/selection.json"):
        return []
    try:
        sel = ctx.read_json("master/selection.json")
    except Exception:
        return []
    if not isinstance(sel, dict):
        return []
    return [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]


def _pair_key(after: str, before: str) -> str:
    return f"{after}->{before}"


def sanitize_transitions(ctx: Any, doc: dict[str, Any]) -> SanitizeResult:
    actions: list[dict[str, Any]] = []
    errors: list[str] = []
    out = dict(doc or {})
    order = _selection_order(ctx)
    order_set = set(order)
    adj = {(order[i], order[i + 1]) for i in range(len(order) - 1)} if len(order) > 1 else set()

    pairs = out.get("transitions") or out.get("pairs") or out.get("items")
    key = (
        "transitions"
        if "transitions" in out
        else ("pairs" if "pairs" in out else ("items" if "items" in out else "transitions"))
    )
    if pairs is None:
        out[key] = []
        pairs = out[key]
    if not isinstance(pairs, list):
        return SanitizeResult(
            doc=out,
            ok=False,
            errors=["transitions list invalid"],
            artifact_rel=REL,
        )

    # Load freeze
    frozen: set[str] = set()
    if ctx.artifact_exists(FREEZE_REL):
        try:
            fr = ctx.read_json(FREEZE_REL)
            if isinstance(fr, dict):
                for p in fr.get("pairs") or []:
                    if isinstance(p, str) and "->" in p:
                        frozen.add(p)
                    elif isinstance(p, dict):
                        frozen.add(_pair_key(str(p.get("after") or ""), str(p.get("before") or "")))
        except Exception:
            pass

    kept: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in pairs:
        if not isinstance(row, dict):
            continue
        after = str(row.get("after_segment_id") or row.get("after") or "")
        before = str(row.get("before_segment_id") or row.get("before") or "")
        if not after and not before:
            continue
        if after and before and after == before:
            actions.append({"action": "drop_self_loop", "after": after})
            continue
        if order_set:
            if after and after not in order_set:
                actions.append({"action": "drop_off_air", "after": after, "before": before})
                continue
            if before and before not in order_set:
                actions.append({"action": "drop_off_air", "after": after, "before": before})
                continue
            if after and before and adj and (after, before) not in adj:
                actions.append({"action": "drop_non_adjacent", "after": after, "before": before})
                continue
        sig = (after, before)
        if sig in seen and after and before:
            actions.append({"action": "dedupe_adjacency", "after": after, "before": before})
            continue
        if after and before:
            seen.add(sig)
        pk = _pair_key(after, before)
        if frozen and pk not in frozen and after and before:
            deferred.append(row)
            actions.append({"action": "defer_beyond_freeze", "pair": pk})
            continue
        kept.append(row)

    # Reverse-jump prune if helper exists
    try:
        from interview_mux.gap_framing import prune_reverse_jump_transitions

        pruned = prune_reverse_jump_transitions(ctx, {key: kept})
        if isinstance(pruned, dict) and isinstance(pruned.get(key), list):
            if len(pruned[key]) != len(kept):
                actions.append({"action": "prune_reverse_jump"})
            kept = list(pruned[key])
    except Exception:
        pass

    # Framing dedupe
    try:
        from interview_mux.transition_vo import dedupe_transitions_for_framing

        deduped = dedupe_transitions_for_framing(ctx, {key: kept})
        if isinstance(deduped, dict) and isinstance(deduped.get(key), list):
            if len(deduped[key]) != len(kept):
                actions.append({"action": "framing_dedupe"})
            kept = list(deduped[key])
    except Exception:
        pass

    out[key] = kept
    if deferred:
        existing_def = out.get("deferred_transition_pairs")
        prev = list(existing_def) if isinstance(existing_def, list) else []
        out["deferred_transition_pairs"] = prev + deferred

    # Refuse leftovers
    for row in kept:
        after = str(row.get("after_segment_id") or row.get("after") or "")
        before = str(row.get("before_segment_id") or row.get("before") or "")
        if after and before and after == before:
            errors.append(f"self_loop_remaining:{after}")
        if order_set and after and after not in order_set:
            errors.append(f"off_air_remaining:{after}")

    if order and kept and not order_set:
        errors.append("selection_empty_with_transitions")

    ok = not errors
    out = stamp_sanitize_meta(
        out,
        ok=ok,
        source="artifact_sanitize.transitions",
        actions_n=len(actions),
    )

    # Stamp freeze ONLY if absent — string format a->b
    if ok and not frozen and kept:
        try:
            from interview_mux.transition_vo import stamp_transitions_pair_freeze

            stamp_transitions_pair_freeze(ctx, out)
            actions.append({"action": "stamp_pair_freeze", "count": len(kept)})
        except Exception:
            try:
                pairs_s = []
                for row in kept:
                    a = str(row.get("after_segment_id") or row.get("after") or "")
                    b = str(row.get("before_segment_id") or row.get("before") or "")
                    if a and b:
                        pairs_s.append(_pair_key(a, b))
                if pairs_s and not ctx.artifact_exists(FREEZE_REL):
                    ctx.write_json(
                        FREEZE_REL,
                        {
                            "version": 1,
                            "pairs": pairs_s,
                            "count": len(pairs_s),
                            "source": "artifact_sanitize.transitions",
                        },
                        skip_handoff=True,
                    )
                    actions.append({"action": "stamp_pair_freeze", "count": len(pairs_s)})
            except Exception:
                pass

    return SanitizeResult(
        doc=out,
        actions=actions,
        ok=ok,
        errors=errors,
        artifact_rel=REL,
        metrics={"actions": len(actions), "kept": len(kept), "deferred": len(deferred)},
    )


def transitions_sanitary_errors(ctx: Any) -> list[str]:
    from interview_mux.artifact_sanitize.config import block_consumers_on_unsanitary
    from interview_mux.artifact_sanitize.reentry import stamp_matches

    if not block_consumers_on_unsanitary():
        return []
    if not ctx.artifact_exists(REL):
        return []
    try:
        doc = ctx.read_json(REL)
    except Exception as exc:
        return [f"{REL} unreadable: {exc}"]
    if not isinstance(doc, dict):
        return [f"{REL} invalid"]
    if stamp_matches(doc):
        return []
    result = sanitize_transitions(ctx, doc)
    if result.ok and not result.actions:
        return []
    if not result.ok:
        return list(result.errors or ["transitions sanitize refused"])
    return [
        "transitions_needs_sanitize:"
        + ",".join(str(a.get("action") or "") for a in (result.actions or [])[:6])
    ]
