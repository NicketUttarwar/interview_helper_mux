"""Deterministic story-order repair: constraints + chapter spans, no finale-tail dump."""

from __future__ import annotations

import re
from typing import Any

_SEG_NUM_RE = re.compile(r"^seg_(\d+)([a-z]+)?$", re.IGNORECASE)


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
    source_start_ms: dict[str, int] | None = None,
    membership_ceiling: set[str] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Return a repaired order that prefers chapter spans and satisfies constraints.

    Never appends unassigned early-chapter leftovers after the last act: leftovers
    are inserted into the best matching chapter span or before the finale block.

    ``membership_ceiling`` (when set) forbids growing the id set beyond that set.
    """
    applied: list[dict[str, Any]] = []
    ceiling = {str(s) for s in (membership_ceiling or set()) if s}
    base = [_as_id(s) for s in ordered if _as_id(s)]
    if ceiling:
        base = [s for s in base if s in ceiling]
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
        # Opening-tape leftovers prepend to first span; body leftovers before finale.
        opening_leftovers: list[str] = []
        body_leftovers: list[str] = []
        if source_start_ms:
            window = 180_000
            try:
                from interview_mux.air_order_integrity import opening_window_ms

                window = opening_window_ms()
            except Exception:
                pass
            for sid in leftovers:
                start = resolved_source_start_ms(sid, source_start_ms)
                if start is not None and int(start) < window:
                    opening_leftovers.append(sid)
                else:
                    body_leftovers.append(sid)
        else:
            body_leftovers = list(leftovers)
        if opening_leftovers and spans:
            spans[0] = opening_leftovers + spans[0]
            applied.append(
                {
                    "action": "prepend_opening_leftovers",
                    "count": len(opening_leftovers),
                    "ids": opening_leftovers[:12],
                }
            )
        pack = body_leftovers if body_leftovers else []
        if pack:
            if len(spans) >= 2:
                spans.insert(len(spans) - 1, pack)
            else:
                spans[0] = pack + spans[0]
            applied.append(
                {
                    "action": "insert_leftovers_before_finale_span",
                    "count": len(pack),
                    "ids": pack[:12],
                }
            )
    elif leftovers:
        spans.append(leftovers)

    new_order = [sid for block in spans for sid in block]
    if ceiling:
        new_order = [s for s in new_order if s in ceiling]

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

    from interview_mux.air_order_integrity import pull_mid_arc_reverse_jumps

    mid_pulled, mid_moved, mid_drop = pull_mid_arc_reverse_jumps(
        new_order, source_start_ms=source_start_ms
    )
    if mid_drop:
        applied.append(
            {"action": "pull_mid_arc_reverse_jumps_drop", "ids": mid_drop[:12]}
        )
        new_order = [s for s in mid_pulled if s not in set(mid_drop)]
    elif mid_moved or mid_pulled != new_order:
        new_order = mid_pulled
        applied.append(
            {
                "action": "pull_mid_arc_reverse_jumps",
                "count": len(mid_moved),
                "ids": mid_moved[:12],
            }
        )

    pulled, moved = pull_earlier_source_ids_before_finale(
        new_order, source_start_ms=source_start_ms
    )
    if moved:
        new_order = pulled
        applied.append(
            {
                "action": "pull_earlier_source_ids_before_finale",
                "count": len(moved),
                "ids": moved[:12],
            }
        )
    return new_order, applied


def _seg_num_suffix(sid: str) -> tuple[int, str] | None:
    match = _SEG_NUM_RE.match(_as_id(sid))
    if not match:
        return None
    return int(match.group(1)), str(match.group(2) or "")


def _parent_seg_id(sid: str) -> str:
    match = re.match(r"^(seg_\d+)[a-z]+$", _as_id(sid), flags=re.IGNORECASE)
    return match.group(1) if match else _as_id(sid)


def resolved_source_start_ms(sid: str, source_start_ms: dict[str, int] | None) -> int | None:
    if not source_start_ms:
        return None
    key = _as_id(sid)
    if key in source_start_ms:
        return int(source_start_ms[key])
    parent = _parent_seg_id(key)
    if parent in source_start_ms:
        return int(source_start_ms[parent])
    return None


def pull_earlier_source_ids_before_finale(
    ordered: list[str],
    source_start_ms: dict[str, int] | None = None,
) -> tuple[list[str], list[str]]:
    """Keep the latest-in-tape selected id last; never drop ids.

    Live mohan: 045/047/049/050 (earlier tape) were appended after recut sign-off
    ``seg_051i``. Letter-split families share a parent start when only ``seg_051``
    exists in boundaries.
    """
    base = [_as_id(sid) for sid in ordered if _as_id(sid)]
    starts = {
        sid: resolved_source_start_ms(sid, source_start_ms)
        for sid in base
    }
    known = [sid for sid in base if starts.get(sid) is not None]
    if len(known) >= 2:
        finale = max(known, key=lambda sid: (int(starts[sid] or 0), base.index(sid)))
        fi = base.index(finale)
        earlier = [
            sid
            for sid in base[fi + 1 :]
            if starts.get(sid) is not None and int(starts[sid] or 0) < int(starts[finale] or 0)
        ]
        stay = [sid for sid in base[fi + 1 :] if sid not in set(earlier)]
        if earlier:
            parent = _parent_seg_id(finale)
            insert_at = fi
            for idx, sid in enumerate(base[: fi + 1]):
                if _parent_seg_id(sid) == parent:
                    insert_at = idx
                    break
            rest = [sid for sid in base[insert_at:] if sid not in set(earlier)]
            return base[:insert_at] + earlier + rest, earlier
    return pull_earlier_ids_before_letter_split_signoff(base)


def pull_earlier_ids_before_letter_split_signoff(
    ordered: list[str],
) -> tuple[list[str], list[str]]:
    """Keep recut sign-off last when earlier-number hard-keeps were appended after it.

    Live failure: ``seg_051a``…``seg_051i`` then ``seg_045``/``047``/``049``/``050``.
    Selection chapters listed those four as their own last chapter, so chapter-span
    repair left them after the 051 sign-off. Move them immediately before the last
    letter-split member. Never drop ids.
    """
    base = [_as_id(sid) for sid in ordered if _as_id(sid)]
    if len(base) < 3:
        return base, []
    parsed = [_seg_num_suffix(sid) for sid in base]
    last_split_idx = -1
    for idx in range(len(base) - 1, -1, -1):
        row = parsed[idx]
        if row and row[1]:
            last_split_idx = idx
            break
    if last_split_idx < 0 or last_split_idx >= len(base) - 1:
        return base, []
    family_num = parsed[last_split_idx][0]
    move: list[str] = []
    stay: list[str] = []
    for sid, row in zip(base[last_split_idx + 1 :], parsed[last_split_idx + 1 :]):
        if row and row[0] < family_num:
            move.append(sid)
        else:
            stay.append(sid)
    if not move:
        return base, []
    first_family = next(
        (idx for idx, row in enumerate(parsed) if row and row[0] == family_num),
        last_split_idx,
    )
    before = [sid for sid in base[:first_family] if sid not in set(move)]
    rest = [sid for sid in base[first_family:] if sid not in set(move)]
    return before + move + rest, move


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
    source_start_ms: dict[str, int] | None = None,
    *,
    banned_readmit_ids: set[str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Apply topo repair to selection.ordered_segment_ids.

    ``banned_readmit_ids`` (sanitize drops / exclusions) are stripped from the
    order and never reintroduced by leftovers/topo rebuild.
    """
    out = dict(selection)
    ban = {str(s) for s in (banned_readmit_ids or set()) if s}
    # Also honor on-doc exclusions as non-readmit.
    for row in out.get("excluded_segment_ids") or []:
        if isinstance(row, dict):
            sid = str(row.get("segment_id") or "")
        else:
            sid = str(row or "")
        if sid:
            ban.add(sid)
    ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s and s not in ban]
    applied: list[dict[str, Any]] = []
    if ban:
        dropped = [
            str(s)
            for s in (selection.get("ordered_segment_ids") or [])
            if str(s) in ban
        ]
        if dropped:
            applied.append(
                {
                    "action": "strip_banned_from_order",
                    "count": len(dropped),
                    "ids": dropped[:24],
                }
            )
    chapters = out.get("chapters") if isinstance(out.get("chapters"), list) else None
    new_order, topo_applied = topo_satisfy_order(
        ordered,
        narrative_plan=narrative_plan,
        selection_chapters=chapters if isinstance(chapters, list) else None,
        source_start_ms=source_start_ms,
        membership_ceiling=set(ordered) if ordered else None,
    )
    applied.extend(topo_applied)
    # Topo must not grow past the post-ban membership set.
    if new_order:
        ceiling = set(ordered)
        grown = [s for s in new_order if s not in ceiling]
        if grown:
            new_order = [s for s in new_order if s in ceiling]
            applied.append(
                {
                    "action": "drop_topo_membership_growth",
                    "count": len(grown),
                    "ids": grown[:12],
                }
            )
        out["ordered_segment_ids"] = new_order
        chapters = out.get("chapters") if isinstance(out.get("chapters"), list) else None
        if chapters:
            contiguous, moved = make_chapter_membership_contiguous(
                [ch for ch in chapters if isinstance(ch, dict)],
                new_order,
            )
            if moved:
                applied.append(
                    {
                        "action": "make_chapter_membership_contiguous",
                        "count": len(moved),
                        "ids": moved[:12],
                    }
                )
            pos = {sid: idx for idx, sid in enumerate(new_order)}

            def _chapter_air_key(ch: dict[str, Any]) -> int:
                ids = [_as_id(s) for s in (ch.get("segment_ids") or []) if _as_id(s) in pos]
                return min((pos[s] for s in ids), default=10**9)

            out["chapters"] = sorted(contiguous, key=_chapter_air_key)
            applied.append({"action": "sort_selection_chapters_to_air_order"})
    return out, applied


def make_chapter_membership_contiguous(
    chapters: list[dict[str, Any]],
    ordered: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Keep each chapter as one air-order span; rehome isolated members.

    Live mohan: trials listed 040/044 and 051a–i while validation 045–050 sat in
    the hole — narrative QC treated that as a split chapter.
    """
    pos = {sid: idx for idx, sid in enumerate(ordered)}
    out = [dict(ch) for ch in chapters]
    owned: dict[str, int] = {}
    for idx, ch in enumerate(out):
        keep: list[str] = []
        for sid in ch.get("segment_ids") or []:
            s = _as_id(sid)
            if s in pos and s not in owned:
                keep.append(s)
                owned[s] = idx
        ch["segment_ids"] = keep
    moved: list[str] = []
    for idx, ch in enumerate(out):
        members = [_as_id(s) for s in (ch.get("segment_ids") or []) if _as_id(s) in pos]
        if len(members) < 2:
            continue
        idxs = sorted(pos[s] for s in members)
        clusters: list[list[int]] = []
        run = [idxs[0]]
        for value in idxs[1:]:
            if value == run[-1] + 1:
                run.append(value)
            else:
                clusters.append(run)
                run = [value]
        clusters.append(run)
        if len(clusters) < 2:
            continue
        main = max(clusters, key=len)
        main_set = set(main)
        isolated = [s for s in members if pos[s] not in main_set]
        if not isolated:
            continue
        ch["segment_ids"] = [s for s in members if s not in set(isolated)]
        for sid in isolated:
            owned.pop(sid, None)
            prev = next((ordered[j] for j in range(pos[sid] - 1, -1, -1) if ordered[j] in owned), "")
            dest = owned.get(prev, max(0, idx - 1))
            dest_ids = [_as_id(s) for s in (out[dest].get("segment_ids") or [])]
            if sid not in dest_ids:
                dest_ids.append(sid)
                dest_ids.sort(key=lambda item: pos.get(item, 10**9))
                out[dest]["segment_ids"] = dest_ids
            owned[sid] = dest
            moved.append(sid)
    return out, moved
