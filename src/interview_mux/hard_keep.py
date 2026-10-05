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


#: Exclusion reasons written by the selection sanitizer's own lattice steps.
LATTICE_DROP_REASONS: frozenset[str] = frozenset(
    {"cap_same_family_on_air", "sanitize_duplicate_source_span"}
)


def lattice_dropped_ids(ctx: RunContext) -> set[str]:
    """Ids the committed selection excludes for a lattice reason.

    The family cap keeps at most ``max_same_family_on_air`` children of one
    parent on air and prefers hard keeps when it chooses. The transferred
    keep list is cut to the same budget, but from the whole admitted story
    set, so the two can pick different members: on the one-hour source an
    overlap union folded seg_002h into seg_002g, the keep list's eighth slot
    moved to seg_002i, which the cap had excluded, and every later selection
    commit was refused with ``hard_keep_missing_from_order:seg_002i``.
    """
    if not ctx.artifact_exists("master/selection.json"):
        return set()
    try:
        sel = ctx.read_json("master/selection.json")
    except Exception:
        return set()
    out: set[str] = set()
    for row in (sel or {}).get("excluded_segment_ids") or [] if isinstance(sel, dict) else []:
        if not isinstance(row, dict):
            continue
        if str(row.get("reason") or "") in LATTICE_DROP_REASONS:
            sid = str(row.get("segment_id") or "")
            if sid:
                out.add(sid)
    return out


def editorial_excluded_ids(ctx: RunContext) -> set[str]:
    """Every id the committed selection excludes for a CTA, outro, blank or fragment reason."""
    if not ctx.artifact_exists("master/selection.json"):
        return set()
    try:
        from interview_mux.media_ip_cta import is_editorial_exclude_reason

        sel = ctx.read_json("master/selection.json")
    except Exception:
        return set()
    if not isinstance(sel, dict):
        return set()
    rationales = sel.get("exclude_rationales") if isinstance(sel.get("exclude_rationales"), dict) else {}
    out: set[str] = set()
    for row in sel.get("excluded_segment_ids") or []:
        if isinstance(row, dict):
            sid = str(row.get("segment_id") or "")
            reason = str(row.get("reason") or rationales.get(sid) or "")
        else:
            sid = str(row or "")
            reason = str(rationales.get(sid) or "")
        if sid and is_editorial_exclude_reason(reason):
            out.add(sid)
    return out


def editorial_dropped_cta_children(ctx: RunContext, parents: set[str]) -> set[str]:
    """Children of banned CTA parents the committed selection excludes as CTA scraps.

    A keep inherited from a CTA parent is a guess that some of the recut is
    story. When the selection has since excluded a child for a CTA, outro or
    blank reason, that is a ruling on the family; handing it back as a demand
    refused every later selection commit (exec_003: the sponsor outro seg_035,
    children g/h/i "empty, heavily degraded transcript after the CTA cut",
    ``hard_keep_missing_from_order:seg_035g,seg_035h,seg_035i``).
    """
    if not parents or not ctx.artifact_exists("master/selection.json"):
        return set()
    try:
        from interview_mux.media_ip_cta import _is_nle_child, is_editorial_exclude_reason

        sel = ctx.read_json("master/selection.json")
    except Exception:
        return set()
    if not isinstance(sel, dict):
        return set()
    rationales = sel.get("exclude_rationales") if isinstance(sel.get("exclude_rationales"), dict) else {}
    out: set[str] = set()
    for row in sel.get("excluded_segment_ids") or []:
        if isinstance(row, dict):
            sid = str(row.get("segment_id") or "")
            reason = str(row.get("reason") or rationales.get(sid) or "")
        else:
            sid = str(row or "")
            reason = str(rationales.get(sid) or "")
        if not sid or not is_editorial_exclude_reason(reason):
            continue
        if any(_is_nle_child(sid, parent) for parent in parents):
            out.add(sid)
    return out


def _blank_excluded_ids(ctx: RunContext) -> set[str]:
    """IDs already dropped as blank/unusable — delegates to playability SSOT."""
    try:
        from interview_mux.playability import blank_excluded_ids

        return blank_excluded_ids(ctx)
    except Exception:
        return set()


def _manifest_segment_ids(ctx: RunContext) -> set[str] | None:
    """Live segment IDs from segments/manifest.json, or None if unavailable."""
    if not ctx.artifact_exists("segments/manifest.json"):
        return None
    try:
        man = ctx.read_json("segments/manifest.json")
    except Exception:
        return None
    if not isinstance(man, dict):
        return None
    out = {
        str(s.get("segment_id") or "")
        for s in (man.get("segments") or [])
        if isinstance(s, dict) and s.get("segment_id")
    }
    return out or None


def _drop_orphan_keeps_not_in_manifest(ctx: RunContext, ids: set[str]) -> set[str]:
    """Drop hard-keeps absent from the live segment manifest (exec_11165 class).

    Authoritative low-conf / vernacular lists can retain IDs after resplit or
    hitch remap removed them from ``segments/manifest.json``. Ranking then sees
    must-keep∉manifest and returns partial→limit_exhausted spin.
    """
    live = _manifest_segment_ids(ctx)
    if live is None:
        return ids
    return {s for s in ids if s in live}


def _drop_blank_unusable_keeps(ctx: RunContext, ids: set[str]) -> set[str]:
    """Unplayable / packaging IDs cannot stay hard-keep (playability SSOT).

    Live blank heuristics are intentionally NOT applied here — short-but-valid
    speech was a footgun for primary-impact/hard-keep drift.
    """
    if not ids:
        return ids
    try:
        from interview_mux.playability import unplayable_segment_ids

        drop = unplayable_segment_ids(ctx)
    except Exception:
        drop = set(_blank_excluded_ids(ctx))
    return {s for s in ids if s not in drop}


def hard_keep_segment_ids(
    ctx: RunContext,
    *,
    overrides: dict[str, Any] | None = None,
    on_air: list[str] | None = None,
) -> set[str]:
    """Ids that must air. ``overrides`` / ``on_air`` judge a proposed write
    (NLE overrides, air order) before it lands; disk state otherwise."""
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
        from interview_mux.media_ip_cta import (
            _is_nle_child,
            admitted_story_segment_ids,
            never_touch_segment_ids,
            ranking_cta_omit_ids,
            selection_cta_exclude_ids,
        )

        # Selection CTA excludes count even when mastering/media_ip_cta.json is thin.
        # ranking_cta_omit_ids also drops tape-scan sponsor CTAs before media_ip exists
        # (exec_11165: hard_keep∩CTA → seal hard_keep_missing_from_order).
        banned = (
            never_touch_segment_ids(ctx)
            | selection_cta_exclude_ids(ctx)
            | ranking_cta_omit_ids(ctx)
        )
        story = admitted_story_segment_ids(ctx)
        # Parent hard-keep transfers onto on-air NLE children / admitted story.
        if ctx.artifact_exists("master/selection.json"):
            try:
                sel = ctx.read_json("master/selection.json")
                ordered = [
                    str(s)
                    for s in ((sel or {}).get("ordered_segment_ids") or [])
                    if s
                ]
                for parent in sorted(ids & banned):
                    kids = {c for c in ordered if _is_nle_child(c, parent)}
                    story_kids: set[str] = set()
                    for child in kids:
                        try:
                            from interview_mux.media_ip_cta import (
                                looks_like_orphaned_cta_scrap,
                            )

                            text = ""
                            if ctx.artifact_exists("segments/manifest.json"):
                                man = ctx.read_json("segments/manifest.json")
                                rows = (man or {}).get("segments") or []
                                if isinstance(rows, dict):
                                    text = str((rows.get(child) or {}).get("text") or "")
                                else:
                                    for row in rows:
                                        if (
                                            isinstance(row, dict)
                                            and str(row.get("segment_id") or "") == child
                                        ):
                                            text = str(row.get("text") or "")
                                            break
                            if looks_like_orphaned_cta_scrap(text):
                                continue
                        except Exception:
                            pass
                        story_kids.add(child)
                    if story_kids:
                        story |= story_kids
            except Exception:
                pass
        # Parent hard-keep transfers onto the keepable recut remainder —
        # but only one representative per overlapping source span / family budget.
        if story and (ids & banned):
            # A child the selection lattice itself took off air (family cap,
            # duplicate source span) is not part of the transfer: the lattice
            # ruled on the family with the keeps in hand, and the transfer
            # must not hand its ruling back as a demand (ISSUES 132).
            # Same for a child the selection excluded as a CTA / outro scrap of a
            # banned parent (ISSUES 136).
            # The transfer offers the whole admitted story set, not only the
            # kept parent's children, so check against every banned parent.
            # Any editorial exclusion is a ruling, whichever family the id
            # belongs to: the transfer offers the whole story set.
            ruled_out = lattice_dropped_ids(ctx) | editorial_excluded_ids(ctx)
            # The closing outro tail of a sponsor parent is credits, not story;
            # transferring the parent's keep onto it made removal_authority
            # refuse the CTA omit on every pass (exec_011 seg_032g-k, ISSUES 148).
            try:
                from interview_mux.media_ip_cta import closing_outro_tail_segment_ids

                ruled_out |= closing_outro_tail_segment_ids(ctx)
            except Exception:
                pass
            ids |= _collapse_overlapping_keeps(ctx, set(story) - ruled_out)
        ids -= banned
    except Exception:
        pass
    ids = _drop_blank_unusable_keeps(ctx, {s for s in ids if s})
    ids = _drop_orphan_keeps_not_in_manifest(ctx, ids)
    ids = _drop_tape_tail_scrap_keeps(ctx, ids)
    # A keep whose tape a fuse union folded into an on-air survivor is kept:
    # its audio airs under the survivor's id. Junction and overlap repair both
    # retire such ids; without this every consumer of the keep list refused the
    # retire and the EDL and selection diverged (exec_052 seg_060, ISSUES 64).
    try:
        from interview_mux.edl_overlap_repair import (
            consumed_carrier_ids,
            consumed_segment_ids,
        )

        consumed = consumed_segment_ids(ctx, overrides=overrides, on_air=on_air) & ids
        ids -= consumed
        # The carrier inherits the keep: it is the only way the kept tape
        # still airs (exec_055 seg_059 carrying seg_060, ISSUES 73).
        if consumed:
            ids |= consumed_carrier_ids(ctx, consumed, overrides=overrides, on_air=on_air)
    except Exception:
        pass
    return _collapse_overlapping_keeps(ctx, ids)


def _drop_tape_tail_scrap_keeps(ctx: RunContext, ids: set[str]) -> set[str]:
    """No keep source may protect a scrap after the tape's closing sponsor read.

    exec_026: the low-conf island scan hard-included seg_033, the undecodable
    last 5 s of tape after the closing sponsor read ("You are listening to
    usHS\ufffd bone..."), at its top decile. As a keep it was protected from
    the outro-tail omit and aired as the episode's last line (ISSUES 180).
    Whatever flagged it, a scrap after the closing CTA is credits, not story.
    """
    if not ids:
        return ids
    try:
        from interview_mux.media_ip_cta import (
            _cta_exclude_parent_ids,
            _all_segments_by_id,
            _segments_by_id,
            _tape_tail_scrap_ids,
            never_touch_segment_ids,
        )

        sel: dict[str, Any] = {}
        if ctx.artifact_exists("master/selection.json"):
            loaded = ctx.read_json("master/selection.json")
            sel = loaded if isinstance(loaded, dict) else {}
        parents = _cta_exclude_parent_ids(sel) | never_touch_segment_ids(ctx)
        if not parents:
            return ids
        scraps = _tape_tail_scrap_ids(
            _segments_by_id(ctx), sorted(ids), parents, _all_segments_by_id(ctx)
        )
    except Exception:
        return ids
    return ids - scraps


# Framing VO cover beats hard-keep restore but is not an "unplayable" class.
_HARD_KEEP_FRAMING_EXEMPT = frozenset({"covered_by_framing_vo"})


def _hard_keep_exempt_reasons() -> frozenset[str]:
    try:
        from interview_mux.playability import UNPLAYABLE_EXCLUDE_REASONS

        return UNPLAYABLE_EXCLUDE_REASONS | _HARD_KEEP_FRAMING_EXEMPT
    except Exception:
        return _HARD_KEEP_FRAMING_EXEMPT | frozenset(
            {
                "blank_or_unusable_answer_audio",
                "finale_tail_leftover",
                "opening_skipped_duplicate",
                "never_touch_unplayable",
                "cta_omit",
                "media_ip_cta",
                "selection_cta_exclude",
            }
        )


def enforce_hard_keeps(ctx: RunContext, selection: dict[str, Any]) -> dict[str, Any]:
    """Restore hard-keeps into ordered even if they vanished from excluded too."""
    out = dict(selection)
    keeps = hard_keep_segment_ids(ctx)
    if not keeps:
        return out
    # Lattice: blank/CTA/never-touch excludes beat hard-keep; other excludes restore.
    excl_ids: set[str] = set()
    excl_reasons: dict[str, str] = {}
    rationales = (
        out.get("exclude_rationales")
        if isinstance(out.get("exclude_rationales"), dict)
        else {}
    )
    for row in out.get("excluded_segment_ids") or []:
        if isinstance(row, dict):
            sid = str(row.get("segment_id") or "")
            reason = str(row.get("reason") or rationales.get(sid) or "").strip()
        else:
            sid = str(row or "")
            reason = str(rationales.get(sid) or "").strip()
        if not sid:
            continue
        excl_reasons[sid] = reason
        exempt = _hard_keep_exempt_reasons()
        if reason in exempt or reason.startswith("cta_"):
            excl_ids.add(sid)
    # Playability SSOT: unplayable/CTA even without a local exclude row.
    try:
        from interview_mux.playability import unplayable_segment_ids

        excl_ids |= unplayable_segment_ids(ctx, out)
    except Exception:
        try:
            excl_ids |= _blank_excluded_ids(ctx)
        except Exception:
            pass
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
