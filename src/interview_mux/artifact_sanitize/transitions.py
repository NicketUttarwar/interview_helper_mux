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

    required: set[str] = set()
    try:
        from interview_mux.bridge_completeness import (
            justified_skip_before_ids,
            missing_reorder_bridges,
        )

        bridges = (
            ctx.read_json("understanding/reorder_bridges.json")
            if ctx.artifact_exists("understanding/reorder_bridges.json")
            else {"pairs": []}
        )
        gap = (
            ctx.read_json("understanding/gap_report.json")
            if ctx.artifact_exists("understanding/gap_report.json")
            else None
        )
        disk_tr = (
            ctx.read_json(REL)
            if ctx.artifact_exists(REL)
            else {"transitions": []}
        )
        for miss in missing_reorder_bridges(
            bridges if isinstance(bridges, dict) else {"pairs": []},
            gap_report=gap if isinstance(gap, dict) else None,
            transitions=disk_tr if isinstance(disk_tr, dict) else None,
            justified_skip_before_ids=justified_skip_before_ids(ctx),
        ):
            if not isinstance(miss, dict):
                continue
            pk = _pair_key(
                str(miss.get("after_segment_id") or ""),
                str(miss.get("before_segment_id") or ""),
            )
            if "->" in pk and not pk.startswith("->") and not pk.endswith("->"):
                required.add(pk)
    except Exception:
        required = set()

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
            if pk in required and (not adj or (after, before) in adj):
                kept.append(row)
                actions.append({"action": "admit_required_bridge", "pair": pk})
                continue
            deferred_row = dict(row)
            deferred_row["beyond_pair_freeze"] = True
            deferred_row["deferred_reason"] = "beyond_pair_freeze"
            deferred.append(deferred_row)
            actions.append({"action": "defer_beyond_freeze", "pair": pk})
            continue
        kept.append(row)

    # Stale LLM rewrite under pair freeze can emit only new adjacencies and
    # empty ``kept``. Restore on-order frozen pairs from committed disk so
    # pending flush does not wipe a landed transitions.json (exec_002).
    # Also union-restore when mint admitted a required new pair (exec_002 i11).
    if frozen and ctx.artifact_exists(REL):
        try:
            disk = ctx.read_json(REL)
            disk_pairs = []
            if isinstance(disk, dict):
                disk_pairs = list(
                    disk.get(key)
                    or disk.get("transitions")
                    or disk.get("pairs")
                    or []
                )
            for row in disk_pairs:
                if not isinstance(row, dict):
                    continue
                after = str(row.get("after_segment_id") or row.get("after") or "")
                before = str(row.get("before_segment_id") or row.get("before") or "")
                pk = _pair_key(after, before)
                if pk not in frozen or not after or not before:
                    continue
                if any(
                    _pair_key(
                        str(k.get("after_segment_id") or k.get("after") or ""),
                        str(k.get("before_segment_id") or k.get("before") or ""),
                    )
                    == pk
                    for k in kept
                    if isinstance(k, dict)
                ):
                    continue
                if order_set and (after not in order_set or before not in order_set):
                    continue
                if adj and (after, before) not in adj:
                    continue
                kept.append(row)
                actions.append({"action": "restore_frozen_pair", "pair": pk})
        except Exception:
            pass

    # Reverse-jump / late-opening prune (owner: artifact_repairs).
    # Wrong gap_framing import + silent except was a dead path (exec_11630 #7).
    try:
        from interview_mux.artifact_repairs import prune_reverse_jump_transitions

        pruned_doc, prune_notes = prune_reverse_jump_transitions(
            ctx, {key: kept}, list(order)
        )
        if isinstance(pruned_doc, dict) and isinstance(pruned_doc.get(key), list):
            if len(pruned_doc[key]) != len(kept):
                actions.append(
                    {
                        "action": "prune_reverse_jump",
                        "notes": list(prune_notes or [])[:8],
                    }
                )
            kept = list(pruned_doc[key])
        if required:
            kept_keys = {
                _pair_key(
                    str(r.get("after_segment_id") or r.get("after") or ""),
                    str(r.get("before_segment_id") or r.get("before") or ""),
                )
                for r in kept
                if isinstance(r, dict)
            }
            for row in pairs:
                if not isinstance(row, dict):
                    continue
                after = str(row.get("after_segment_id") or row.get("after") or "")
                before = str(row.get("before_segment_id") or row.get("before") or "")
                pk = _pair_key(after, before)
                if pk not in required or pk in kept_keys:
                    continue
                if adj and (after, before) not in adj:
                    continue
                kept.append(row)
                kept_keys.add(pk)
                actions.append(
                    {"action": "restore_required_after_reverse_prune", "pair": pk}
                )
    except Exception as exc:
        errors.append(f"prune_reverse_jump_failed:{type(exc).__name__}:{exc}")
        actions.append({"action": "prune_reverse_jump_failed", "error": str(exc)[:200]})

    # Framing dedupe — drop spoken bridges already covered by layup VO.
    # Must import from gap_framing (not transition_vo); wrong import was
    # silently swallowing ImportError so freeze resurrected redundant pairs
    # (exec_11630: seg_018→seg_020 thrash).
    try:
        from interview_mux.gap_framing import dedupe_transitions_for_framing

        gap: dict[str, Any] | None = None
        if ctx.artifact_exists("understanding/gap_report.json"):
            loaded = ctx.read_json("understanding/gap_report.json")
            if isinstance(loaded, dict):
                gap = loaded
        before_n = len(kept)
        deduped = dedupe_transitions_for_framing(gap, {key: kept}, ctx=ctx)
        if isinstance(deduped, dict) and isinstance(deduped.get(key), list):
            kept = list(deduped[key])
            if len(kept) != before_n:
                actions.append(
                    {
                        "action": "framing_dedupe",
                        "dropped": before_n - len(kept),
                    }
                )
                # Keep freeze aligned so later sanitize cannot re-admit.
                if frozen:
                    kept_keys = {
                        _pair_key(
                            str(r.get("after_segment_id") or r.get("after") or ""),
                            str(r.get("before_segment_id") or r.get("before") or ""),
                        )
                        for r in kept
                        if isinstance(r, dict)
                    }
                    new_freeze = sorted(k for k in frozen if k in kept_keys)
                    if len(new_freeze) != len(frozen):
                        try:
                            ctx.write_json(
                                FREEZE_REL,
                                {
                                    "version": 1,
                                    "pairs": new_freeze,
                                    "count": len(new_freeze),
                                    "source": "artifact_sanitize.transitions.framing_dedupe",
                                },
                                skip_handoff=True,
                            )
                            frozen = set(new_freeze)
                            actions.append(
                                {
                                    "action": "trim_pair_freeze",
                                    "count": len(new_freeze),
                                }
                            )
                        except Exception:
                            pass
    except Exception as exc:
        # Loud like prune_reverse_jump — silent pass resurrected redundant
        # framing pairs under freeze (exec_11630 #9 residual).
        errors.append(f"framing_dedupe_failed:{type(exc).__name__}:{exc}")
        actions.append({"action": "framing_dedupe_failed", "error": str(exc)[:200]})

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

    admitted = [a.get("pair") for a in actions if a.get("action") == "admit_required_bridge"]
    if admitted and frozen:
        try:
            extra = [str(p) for p in admitted if p]
            merged = list(dict.fromkeys([*sorted(frozen), *extra]))
            ctx.write_json(
                FREEZE_REL,
                {
                    "version": 1,
                    "pairs": merged,
                    "count": len(merged),
                    "source": "artifact_sanitize.transitions",
                },
                skip_handoff=True,
            )
            actions.append({"action": "extend_pair_freeze", "added": extra})
        except Exception:
            pass

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
