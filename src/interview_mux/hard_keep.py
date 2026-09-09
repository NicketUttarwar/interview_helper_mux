"""Union of segment IDs that ranking/pack/junction/fuse must never drop."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def _collapse_overlapping_keeps(ctx: RunContext, ids: set[str]) -> set[str]:
    """Keep one representative per overlapping same-family source span."""
    if len(ids) < 2:
        return set(ids)
    try:
        from interview_mux.artifact_sanitize.selection import (
            _base_family,
            _fragment_depth,
            _prefer_keep,
            _segment_starts,
            _spans_overlap_or_nested,
        )
    except Exception:
        return set(ids)
    starts = _segment_starts(ctx)
    if not starts:
        # No span map — still cap same-family hard-keeps to max_same_family_on_air.
        try:
            from interview_mux.artifact_sanitize.config import sanitize_selection_cfg
            from interview_mux.artifact_sanitize.selection import _base_family, _fragment_depth

            max_family = int(sanitize_selection_cfg().get("max_same_family_on_air") or 8)
        except Exception:
            return set(ids)
        by_fam: dict[str, list[str]] = {}
        for sid in ids:
            by_fam.setdefault(_base_family(sid), []).append(sid)
        out: set[str] = set()
        for members in by_fam.values():
            ranked = sorted(members, key=lambda x: (_fragment_depth(x), len(x), x))
            out.update(ranked[:max_family])
        return out
    survivors: list[str] = []
    hard = set(ids)
    for sid in sorted(ids, key=lambda x: (_fragment_depth(x), len(x), x)):
        span = starts.get(sid)
        if span is None:
            survivors.append(sid)
            continue
        collide_idx = None
        for i, other in enumerate(survivors):
            if _base_family(other) != _base_family(sid):
                continue
            other_span = starts.get(other)
            if other_span is None:
                continue
            if _spans_overlap_or_nested(span, other_span):
                collide_idx = i
                break
        if collide_idx is None:
            survivors.append(sid)
            continue
        other = survivors[collide_idx]
        keep = _prefer_keep(other, sid, hard)
        if keep != other:
            survivors[collide_idx] = sid
    # Family cap after span collapse
    try:
        from interview_mux.artifact_sanitize.config import sanitize_selection_cfg

        max_family = int(sanitize_selection_cfg().get("max_same_family_on_air") or 8)
    except Exception:
        max_family = 8
    by_fam2: dict[str, list[str]] = {}
    for sid in survivors:
        by_fam2.setdefault(_base_family(sid), []).append(sid)
    out2: set[str] = set()
    for members in by_fam2.values():
        ranked = sorted(members, key=lambda x: (_fragment_depth(x), len(x), x))
        out2.update(ranked[:max_family])
    return out2


def hard_keep_segment_ids(ctx: RunContext) -> set[str]:
    ids: set[str] = set()
    try:
        from interview_mux.gap_framing import load_gap_framing_plan

        plan = load_gap_framing_plan(ctx)
        if plan:
            for act in plan.get("acts") or []:
                if not isinstance(act, dict):
                    continue
                for block in act.get("impact_blocks") or []:
                    if not isinstance(block, dict):
                        continue
                    ids.update(str(s) for s in (block.get("source_segment_ids") or []) if s)
    except Exception:
        pass
    try:
        from interview_mux.stages.audio_probes import authoritative_must_keep_ids

        ids |= authoritative_must_keep_ids(ctx)
    except Exception:
        pass
    if ctx.artifact_exists("understanding/ideal_cuts.json"):
        try:
            cuts = ctx.read_json("understanding/ideal_cuts.json")
            if isinstance(cuts, dict):
                ids.update(str(s) for s in (cuts.get("must_keep_segment_ids") or []) if s)
                for row in cuts.get("cuts") or []:
                    if isinstance(row, dict) and row.get("must_keep"):
                        sid = str(row.get("segment_id") or row.get("cut_id") or "")
                        if sid:
                            ids.add(sid)
        except Exception:
            pass
    if ctx.artifact_exists("understanding/talking_points.json"):
        try:
            tps = ctx.read_json("understanding/talking_points.json")
            rows = tps.get("talking_points") if isinstance(tps, dict) else tps
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                if not row.get("must_keep"):
                    continue
                for key in ("segment_id", "cut_id", "source_segment_id"):
                    sid = str(row.get(key) or "")
                    if sid:
                        ids.add(sid)
                ids.update(str(s) for s in (row.get("segment_ids") or []) if s)
        except Exception:
            pass
    try:
        from interview_mux.media_ip_cta import admitted_story_segment_ids, never_touch_segment_ids

        banned = never_touch_segment_ids(ctx)
        story = admitted_story_segment_ids(ctx)
        # Parent hard-keep transfers onto the keepable recut remainder —
        # but only one representative per overlapping source span / family budget.
        if story and (ids & banned):
            ids |= _collapse_overlapping_keeps(ctx, set(story))
        ids -= banned
    except Exception:
        pass
    return _collapse_overlapping_keeps(ctx, {s for s in ids if s})


def enforce_hard_keeps(ctx: RunContext, selection: dict[str, Any]) -> dict[str, Any]:
    """Restore hard-keeps into ordered even if they vanished from excluded too."""
    out = dict(selection)
    keeps = hard_keep_segment_ids(ctx)
    if not keeps:
        return out
    # Never restore ids already excluded by sanitize / operator omit.
    excl_ids: set[str] = set()
    for row in out.get("excluded_segment_ids") or []:
        if isinstance(row, dict):
            sid = str(row.get("segment_id") or "")
        else:
            sid = str(row or "")
        if sid:
            excl_ids.add(sid)
    keeps = {s for s in keeps if s not in excl_ids}
    if not keeps:
        return out
    ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    seen = set(ordered)
    restored: list[str] = []
    for sid in sorted(keeps):
        if sid not in seen:
            ordered.append(sid)
            seen.add(sid)
            restored.append(sid)
    excl_raw = list(out.get("excluded_segment_ids") or [])
    kept_excl: list[Any] = []
    for row in excl_raw:
        sid = ""
        if isinstance(row, dict):
            sid = str(row.get("segment_id") or "")
        elif isinstance(row, str):
            sid = row
        if sid and sid in keeps:
            continue
        kept_excl.append(row)
    out["ordered_segment_ids"] = ordered
    out["excluded_segment_ids"] = kept_excl
    out, restored, omitted = _place_or_omit_restored_for_finale(ctx, out, restored)
    out, pulled = _pull_restored_before_finale(ctx, out, restored)
    if pulled:
        ctx.log(
            "hard_keep: pulled before sign-off " + ", ".join(pulled[:8]),
            level="info",
            stage="full_master_ranking",
        )
    if restored:
        ctx.log(
            "hard_keep: restored " + ", ".join(restored[:8]),
            level="info",
            stage="full_master_ranking",
        )
    if omitted:
        ctx.log(
            "hard_keep: finale-tail omit " + ", ".join(omitted[:8]),
            level="info",
            stage="full_master_ranking",
        )
    return out


def _early_chapter_ids(ctx: RunContext, ordered: list[str]) -> set[str]:
    if not ctx.artifact_exists("master/narrative_plan.json"):
        return set()
    try:
        plan = ctx.read_json("master/narrative_plan.json")
    except Exception:
        return set()
    if not isinstance(plan, dict):
        return set()
    chapters = [c for c in (plan.get("chapters") or []) if isinstance(c, dict)]
    if len(chapters) < 2:
        return set()
    latest: dict[str, int] = {}
    for idx, ch in enumerate(chapters):
        for sid in ch.get("segment_ids") or []:
            s = str(sid or "")
            if s:
                latest[s] = idx
    last_idx = len(chapters) - 1
    return {s for s, ci in latest.items() if ci < last_idx}


def _place_or_omit_restored_for_finale(
    ctx: RunContext,
    selection: dict[str, Any],
    restored: list[str],
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Do not append early-chapter hard-keeps after coda.

    When the episode already opens past the opening window (guest/company first),
    prefer prepending early host-intro hard-keeps to the front rather than
    excluding them as ``opening_skipped_duplicate``. True post-coda leftovers
    still get a typed omit.
    """
    if not restored:
        return selection, restored, []
    ordered = [str(s) for s in (selection.get("ordered_segment_ids") or []) if s]
    early = _early_chapter_ids(ctx, ordered)
    if not early:
        return selection, restored, []
    kept_restored: list[str] = []
    omitted: list[str] = []
    prepend_candidates: list[str] = []
    ordered_set = set(ordered)
    for sid in restored:
        if sid in early:
            ordered = [x for x in ordered if x != sid]
            ordered_set.discard(sid)
            omitted.append(sid)
            continue
        kept_restored.append(sid)

    guest_first = False
    starts: dict[str, int] = {}
    if omitted:
        from interview_mux.air_order_integrity import (
            opening_window_ms,
            resolved_segment_starts,
        )

        starts = resolved_segment_starts(ctx)
        window = opening_window_ms(ctx=ctx)
        ordered_list = [str(s) for s in (selection.get("ordered_segment_ids") or []) if s]
        if ordered_list and starts:
            first = starts.get(ordered_list[0])
            if first is None:
                from interview_mux.selection_order_repair import resolved_source_start_ms

                first = resolved_source_start_ms(ordered_list[0], starts)
            if first is not None and int(first) >= window:
                guest_first = True

        if guest_first:
            # Prefer native host intro on air: prepend early hard-keeps, do not trash.
            from interview_mux.selection_order_repair import resolved_source_start_ms

            prepend_candidates = list(omitted)
            family_sorted = sorted(
                prepend_candidates,
                key=lambda s: (
                    resolved_source_start_ms(s, starts) or starts.get(s) or 0,
                    prepend_candidates.index(s),
                ),
            )
            ordered = family_sorted + [s for s in ordered if s not in set(family_sorted)]
            kept_restored = list(dict.fromkeys(kept_restored + family_sorted))
            omitted = []
            # Drop stale opening_skipped_duplicate excludes for restored intros.
            excl = []
            for row in selection.get("excluded_segment_ids") or []:
                sid = str(row.get("segment_id") if isinstance(row, dict) else row)
                reason = (
                    str(row.get("reason") or "")
                    if isinstance(row, dict)
                    else str((selection.get("exclude_rationales") or {}).get(sid) or "")
                )
                if sid in set(family_sorted) and reason == "opening_skipped_duplicate":
                    continue
                excl.append(row)
            selection["excluded_segment_ids"] = excl
            rationales = (
                dict(selection.get("exclude_rationales") or {})
                if isinstance(selection.get("exclude_rationales"), dict)
                else {}
            )
            for sid in family_sorted:
                if rationales.get(sid) == "opening_skipped_duplicate":
                    rationales.pop(sid, None)
            selection["exclude_rationales"] = rationales
        else:
            excl = list(selection.get("excluded_segment_ids") or [])
            seen_ex = set()
            for row in excl:
                if isinstance(row, dict):
                    seen_ex.add(str(row.get("segment_id") or ""))
                elif isinstance(row, str):
                    seen_ex.add(row)
            for sid in omitted:
                if sid in seen_ex:
                    continue
                excl.append({"segment_id": sid, "reason": "finale_tail_leftover"})
                seen_ex.add(sid)
            rationales = (
                dict(selection.get("exclude_rationales") or {})
                if isinstance(selection.get("exclude_rationales"), dict)
                else {}
            )
            for sid in omitted:
                rationales[sid] = rationales.get(sid) or "finale_tail_leftover"
            selection["excluded_segment_ids"] = excl
            selection["exclude_rationales"] = rationales

    selection["ordered_segment_ids"] = ordered
    try:
        from interview_mux.air_order_integrity import repair_air_order_integrity

        selection, _ = repair_air_order_integrity(ctx, selection)
    except Exception:
        pass
    return selection, kept_restored, omitted


def _pull_restored_before_finale(
    ctx: RunContext,
    selection: dict[str, Any],
    restored: list[str],
) -> tuple[dict[str, Any], list[str]]:
    """Last-chapter hard-keeps must not remain after a later-tape sign-off."""
    if not restored:
        return selection, []
    from interview_mux.selection_order_repair import pull_earlier_source_ids_before_finale

    starts: dict[str, int] = {}
    for rel in ("segments/boundaries.json", "segments/segments.json"):
        if not ctx.artifact_exists(rel):
            continue
        try:
            doc = ctx.read_json(rel)
        except Exception:
            continue
        rows = []
        if isinstance(doc, dict):
            rows = list(doc.get("boundaries") or doc.get("segments") or [])
        for row in rows:
            if not isinstance(row, dict) or not row.get("segment_id"):
                continue
            try:
                starts[str(row["segment_id"])] = int(row.get("start_ms") or 0)
            except (TypeError, ValueError):
                continue
    ordered = [str(s) for s in (selection.get("ordered_segment_ids") or []) if s]
    pulled, moved = pull_earlier_source_ids_before_finale(
        ordered, source_start_ms=starts or None
    )
    if not moved:
        return selection, []
    moved_set = set(moved)
    if not any(sid in moved_set for sid in restored):
        return selection, []
    selection["ordered_segment_ids"] = pulled
    return selection, [sid for sid in moved if sid in set(restored)]
