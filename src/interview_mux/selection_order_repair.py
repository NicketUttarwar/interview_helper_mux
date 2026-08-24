"""Deterministic story-order repair: constraints + chapter spans, no finale-tail dump."""

from __future__ import annotations

from typing import Any


def _as_id(value: Any) -> str:
    return str(value or "").strip()


def constraint_pairs(narrative_plan: dict[str, Any] | None) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if not isinstance(narrative_plan, dict):
        return pairs
    for row in narrative_plan.get("ordering_constraints") or []:
        if not isinstance(row, dict):
            continue
        before = _as_id(
            row.get("before_segment_id") or row.get("before") or row.get("setup_segment_id")
        )
        after = _as_id(
            row.get("after_segment_id") or row.get("after") or row.get("payoff_segment_id")
        )
        if before and after and before != after:
            pairs.append((before, after))
    return pairs


def ordering_constraint_errors(
    ordered: list[str],
    narrative_plan: dict[str, Any] | None,
) -> list[str]:
    """Return human-readable constraint violations for an ordered id list.

    Constraints that mention segments outside the current selection are ignored.
    Selection is the air-order authority; narrative constraints cannot force
    excluded material back into the episode.
    """
    positions = {sid: idx for idx, sid in enumerate(ordered)}
    errors: list[str] = []
    for index, (before, after) in enumerate(constraint_pairs(narrative_plan)):
        if before not in positions or after not in positions:
            continue
        if positions[before] >= positions[after]:
            errors.append(
                f'ordering constraint violated: "{before}" must appear before "{after}"'
            )
    return errors


def finale_tail_errors(
    ordered: list[str],
    narrative_plan: dict[str, Any] | None,
) -> list[str]:
    """Flag early-chapter segments parked after the last act's members.

    Overlapping chapter membership resolves to the *latest* chapter so shared
    finale anchors are not treated as early-chapter ids.
    """
    if not isinstance(narrative_plan, dict) or len(ordered) < 3:
        return []
    chapters = [c for c in (narrative_plan.get("chapters") or []) if isinstance(c, dict)]
    if len(chapters) < 2:
        return []
    # Latest chapter wins on overlaps (finale membership takes priority).
    latest_chapter: dict[str, int] = {}
    for idx, ch in enumerate(chapters):
        for sid in ch.get("segment_ids") or []:
            s = _as_id(sid)
            if s:
                latest_chapter[s] = idx
    last_idx = len(chapters) - 1
    last_ids = {s for s, ci in latest_chapter.items() if ci == last_idx}
    early = {s for s, ci in latest_chapter.items() if ci < last_idx}
    if not last_ids or not early:
        return []
    positions = {sid: idx for idx, sid in enumerate(ordered)}
    last_positions = [positions[s] for s in last_ids if s in positions]
    if not last_positions:
        return []
    last_end = max(last_positions)
    bad = [
        sid
        for sid in ordered
        if sid in early and positions.get(sid, -1) > last_end
    ]
    if not bad:
        return []
    return [
        f"early-chapter segment(s) after finale block: {bad[:8]}"
        + ("…" if len(bad) > 8 else "")
    ]


def _chapter_member_lists(
    narrative_plan: dict[str, Any] | None,
    ordered_set: set[str],
) -> list[list[str]]:
    """Build per-chapter id lists with latest-chapter-wins on overlaps."""
    if not isinstance(narrative_plan, dict):
        return []
    raw_chapters = [c for c in (narrative_plan.get("chapters") or []) if isinstance(c, dict)]
    if not raw_chapters:
        return []
    # Assign each segment to the latest chapter that lists it.
    latest_chapter: dict[str, int] = {}
    for idx, ch in enumerate(raw_chapters):
        for sid in ch.get("segment_ids") or []:
            s = _as_id(sid)
            if s and s in ordered_set:
                latest_chapter[s] = idx
    out: list[list[str]] = [[] for _ in raw_chapters]
    for idx, ch in enumerate(raw_chapters):
        seen: set[str] = set()
        for sid in ch.get("segment_ids") or []:
            s = _as_id(sid)
            if not s or s not in ordered_set or latest_chapter.get(s) != idx:
                continue
            if s in seen:
                continue
            seen.add(s)
            out[idx].append(s)
    return [block for block in out if block]


def topo_satisfy_order(
    ordered: list[str],
    *,
    narrative_plan: dict[str, Any] | None = None,
    selection_chapters: list[dict[str, Any]] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Return a repaired order that prefers chapter spans and satisfies constraints.

    Never appends unassigned early-chapter leftovers after the last act: leftovers
    are inserted into the best matching chapter span or before the finale block.
    """
    applied: list[dict[str, Any]] = []
    base = [_as_id(s) for s in ordered if _as_id(s)]
    if not base:
        return [], applied

    # Dedupe preserve first
    seen: set[str] = set()
    deduped: list[str] = []
    for sid in base:
        if sid in seen:
            continue
        seen.add(sid)
        deduped.append(sid)

    order_set = set(deduped)
    chapter_lists = _chapter_member_lists(narrative_plan, order_set)
    if selection_chapters:
        # Prefer selection chapter membership when present
        sel_lists: list[list[str]] = []
        for ch in selection_chapters:
            if not isinstance(ch, dict):
                continue
            ids = [_as_id(s) for s in (ch.get("segment_ids") or []) if _as_id(s) in order_set]
            if ids:
                sel_lists.append(ids)
        if sel_lists:
            chapter_lists = sel_lists

    assigned: set[str] = set()
    spans: list[list[str]] = []
    for members in chapter_lists:
        # Keep relative order from current ranking among chapter members
        pos = {sid: idx for idx, sid in enumerate(deduped)}
        block = sorted(
            [s for s in members if s not in assigned],
            key=lambda sid: pos.get(sid, 10**9),
        )
        for sid in block:
            assigned.add(sid)
        if block:
            spans.append(block)

    leftovers = [sid for sid in deduped if sid not in assigned]
    if leftovers and spans:
        # Insert a dedicated block *before* the finale span (never append onto it).
        if len(spans) >= 2:
            spans.insert(len(spans) - 1, leftovers)
        else:
            spans[0] = leftovers + spans[0]
        applied.append(
            {
                "action": "insert_leftovers_before_finale_span",
                "count": len(leftovers),
                "ids": leftovers[:12],
            }
        )
    elif leftovers:
        spans.append(leftovers)

    new_order = [sid for block in spans for sid in block]

    # Satisfy pairwise constraints via adjacent swaps / moves (bounded)
    pairs = constraint_pairs(narrative_plan)
    if pairs:
        changed = False
        for _ in range(max(8, len(pairs) * 2)):
            positions = {sid: idx for idx, sid in enumerate(new_order)}
            moved = False
            for before, after in pairs:
                if before not in positions or after not in positions:
                    continue
                bi, ai = positions[before], positions[after]
                if bi < ai:
                    continue
                # Move `before` just ahead of `after`
                new_order.pop(bi)
                # after index may have shifted if before was before it — recompute
                positions = {sid: idx for idx, sid in enumerate(new_order)}
                ai2 = positions[after]
                new_order.insert(ai2, before)
                moved = True
                changed = True
                break
            if not moved:
                break
        if changed:
            applied.append({"action": "topo_satisfy_ordering_constraints", "pairs": len(pairs)})

    if new_order != deduped:
        applied.append({"action": "topo_rebuild_order", "count": len(new_order)})
    return new_order, applied


def fill_chapter_list_membership_gaps(
    chapters: list[dict[str, Any]],
    ordered: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Assign leftover air-order ids into the nearest existing chapter.

    Does not change air order. Each leftover is inserted into the chapter that
    currently owns the nearest already-assigned neighbor (prefer previous
    neighbor so leftovers stay in the earlier span, never dumped onto finale).
    Returns ``(chapters, filled_ids)``. Empty ``filled_ids`` means no assignment.
    """
    if not isinstance(chapters, list) or not ordered:
        return [dict(ch) for ch in (chapters or []) if isinstance(ch, dict)], []
    pos = {_as_id(sid): idx for idx, sid in enumerate(ordered) if _as_id(sid)}
    if not pos:
        return [dict(ch) for ch in chapters if isinstance(ch, dict)], []

    out: list[dict[str, Any]] = []
    owned: dict[str, int] = {}
    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        row = dict(ch)
        ids = [_as_id(s) for s in (row.get("segment_ids") or []) if _as_id(s) in pos]
        deduped: list[str] = []
        seen: set[str] = set()
        for sid in ids:
            if sid in seen:
                continue
            seen.add(sid)
            deduped.append(sid)
        deduped.sort(key=lambda sid: pos[sid])
        row["segment_ids"] = deduped
        ch_idx = len(out)
        out.append(row)
        for sid in deduped:
            owned[sid] = ch_idx
    if not out:
        return [], []

    leftovers = [sid for sid in (_as_id(s) for s in ordered) if sid and sid not in owned]
    if not leftovers:
        return out, []
    if not owned:
        out[0]["segment_ids"] = [sid for sid in (_as_id(s) for s in ordered) if sid]
        return out, list(out[0]["segment_ids"])

    filled: list[str] = []
    ordered_ids = [sid for sid in (_as_id(s) for s in ordered) if sid]
    for sid in leftovers:
        i = pos[sid]
        prev = next((ordered_ids[j] for j in range(i - 1, -1, -1) if ordered_ids[j] in owned), "")
        nxt = next(
            (ordered_ids[j] for j in range(i + 1, len(ordered_ids)) if ordered_ids[j] in owned),
            "",
        )
        if prev:
            ch_idx = owned[prev]
        elif nxt:
            ch_idx = owned[nxt]
        else:
            ch_idx = 0 if len(out) == 1 else max(0, len(out) - 2)
        ids = list(out[ch_idx].get("segment_ids") or [])
        if sid not in ids:
            ids.append(sid)
            ids.sort(key=lambda item: pos.get(item, 10**9))
            out[ch_idx]["segment_ids"] = ids
        owned[sid] = ch_idx
        filled.append(sid)
    return out, filled


def repair_selection_order(
    selection: dict[str, Any],
    narrative_plan: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Apply topo repair to selection.ordered_segment_ids."""
    out = dict(selection)
    ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    chapters = out.get("chapters") if isinstance(out.get("chapters"), list) else None
    new_order, applied = topo_satisfy_order(
        ordered,
        narrative_plan=narrative_plan,
        selection_chapters=chapters if isinstance(chapters, list) else None,
    )
    if new_order:
        out["ordered_segment_ids"] = new_order
    return out, applied
