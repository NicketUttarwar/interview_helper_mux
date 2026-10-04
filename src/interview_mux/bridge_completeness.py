"""Hard-require pair-specific gap VO or spoken transition for every reorder adjacency."""

from __future__ import annotations

from typing import Any

# Known generic filler lines that satisfy "audible glue" but aren't pair-specific
# (e.g. the timeline optimizer's retired "Meanwhile—" default, seam_glue's canned
# fallback, and the old category-only default_bridge_text templates). Kept in sync
# manually — these are deliberately narrow, known stock phrases rather than a
# broad style judgment.
_GENERIC_STUB_PHRASES = frozenset(
    {
        "meanwhile—",
        "meanwhile,",
        "meanwhile…",
        "meanwhile...",
        "there is more to that story.",
        "and then—what happened next?",
        "and then—what happened next",
        "next, the focus shifts.",
        "next, the focus shifts",
        "that connects to something earlier.",
        "that connects to something earlier",
        "meanwhile, another thread opens.",
        "meanwhile, another thread opens",
        "stepping back—here's what led there.",
        "stepping back—here's what led there",
        "and then—into the next beat.",
        "and then—into the next beat",
    }
)

# Verbatim bridge text reused across this many (or more) distinct pairs reads as
# canned filler pasted everywhere, not glue written for that specific seam.
_REPEATED_TEXT_STUB_THRESHOLD = 2


def _normalize_bridge_text(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def deferred_pair_is_durable(row: dict[str, Any]) -> bool:
    """End-C: deferred spoken text alone is not durable glue.

    Counts only when WAV is seated, spoken is explicitly omitted/hitched, or the
    row was deferred beyond pair freeze (mix last-chance owns synth).
    """
    if not isinstance(row, dict):
        return False
    if row.get("wav_path") or row.get("audio_path"):
        return True
    if row.get("omit_spoken") or row.get("hitch_cover") or row.get("hitch_covered"):
        return True
    if row.get("beyond_pair_freeze") or row.get("defer_beyond_freeze"):
        return True
    reason = str(row.get("deferred_reason") or row.get("defer_reason") or "").lower()
    if reason in {"beyond_pair_freeze", "pair_freeze", "defer_beyond_freeze"}:
        return True
    return False


def bridge_heal_may_soft_complete(*, waivers_enabled: bool) -> bool:
    """End-C: forge complete / resume EDL only under e2e quality waivers."""
    return bool(waivers_enabled)


def _bridged_pairs(
    gap_report: dict[str, Any] | None,
    transitions: dict[str, Any] | None,
) -> set[tuple[str, str]]:
    """Return (after, before) pairs that have intentional spoken/transition glue.

    Silence-only markers are excluded. Gap ``placement: before`` VO on the
    destination covers the seam via ``missing_reorder_bridges`` (one host turn).
    """
    bridged: set[tuple[str, str]] = set()
    if isinstance(gap_report, dict):
        for ln in gap_report.get("interviewer_lines") or []:
            if not isinstance(ln, dict):
                continue
            if ln.get("skipped_optional"):
                continue
            text = str(ln.get("text") or "").strip()
            if not text and not ln.get("audio_path") and not ln.get("wav_path"):
                continue
            delivery = str(ln.get("delivery") or "").lower()
            if delivery and delivery not in {"record", "synthesize"}:
                continue
            after = str(ln.get("after_segment_id") or "")
            before = str(ln.get("before_segment_id") or "")
            target = str(ln.get("targets_segment_id") or "")
            prior = str(ln.get("prior_segment_id") or "")
            placement = str(ln.get("placement") or "before").strip() or "before"
            # Pair-specific only: require explicit after→before (or after→target).
            if after and before:
                bridged.add((after, before))
            elif after and target:
                bridged.add((after, target))
            elif placement == "before" and prior and target:
                bridged.add((prior, target))
    if isinstance(transitions, dict):
        for tr in transitions.get("transitions") or []:
            if not isinstance(tr, dict):
                continue
            a = str(tr.get("after_segment_id") or "")
            b = str(tr.get("before_segment_id") or "")
            text = str(tr.get("text") or "").strip()
            # Spoken text required — silence_ms alone is not audible glue.
            if a and b and text:
                bridged.add((a, b))
        # End-C: deferred text is temporary heal intent — durable only when
        # WAV / omit / hitch / beyond-pair-freeze is stamped (mix last-chance).
        for tr in transitions.get("deferred_transition_pairs") or []:
            if not isinstance(tr, dict):
                continue
            if not deferred_pair_is_durable(tr):
                continue
            a = str(tr.get("after_segment_id") or "")
            b = str(tr.get("before_segment_id") or "")
            text = str(tr.get("text") or tr.get("spoken_text") or "").strip()
            if a and b and (text or tr.get("omit_spoken") or tr.get("hitch_cover")):
                bridged.add((a, b))
    return bridged


def justified_skip_before_ids(ctx: Any) -> set[str]:
    """Destinations whose layup skip or native handoff already covers the seam.

    Mint, Done Authority, and the EDL preflight must share this set. Calling
    ``missing_reorder_bridges`` without it reports hollow hinges that mint
    already treats as covered (exec_002: 7 missing vs persist n=6).
    """
    skip: set[str] = set()
    try:
        from interview_mux.nugget_layup import (
            PLAN_REL,
            is_justified_skip_row,
            nugget_layup_enabled,
        )

        if nugget_layup_enabled() and ctx.artifact_exists(PLAN_REL):
            plan = ctx.read_json(PLAN_REL)
            if isinstance(plan, dict):
                for row in plan.get("layups") or []:
                    if not isinstance(row, dict) or not row.get("skip"):
                        continue
                    tid = str(row.get("target_segment_id") or "").strip()
                    if tid and is_justified_skip_row(row, soft_migrate=True):
                        skip.add(tid)
    except Exception:
        pass
    try:
        from interview_mux.air_script import native_handoff_segment_ids
        from interview_mux.mastering_plan_loader import load_plan_raw

        skip |= native_handoff_segment_ids(load_plan_raw(ctx))
    except Exception:
        pass
    return skip


def forbidden_bridge_pairs(ctx: Any, pairs: list[dict[str, Any]] | None = None) -> set[tuple[str, str]]:
    """Pairs a spoken transition may never glue, by the transitions lint's own rules.

    The transitions stage drops model rows that jump back on tape or land on late
    opening tape, and ``_lint_transitions`` refuses them. Completeness and the
    mint must agree, or the mint re-creates the dropped row and the lint refuses
    it on every attempt (ISSUES 151).
    """
    try:
        from interview_mux.air_order_integrity import (
            opening_body_start_index,
            opening_tape_segment_ids,
            pair_source_gap_ms,
            resolved_segment_starts,
            reverse_jump_margin_ms,
        )

        sel = ctx.read_json("master/selection.json") if ctx.artifact_exists("master/selection.json") else {}
        order = [str(s) for s in ((sel or {}).get("ordered_segment_ids") or []) if s]
        if not order:
            return set()
        starts = resolved_segment_starts(ctx)
        from interview_mux.air_order_integrity import family_air_positions

        pos = family_air_positions(order)
        opening = opening_tape_segment_ids(order, starts)
        margin = reverse_jump_margin_ms(ctx=ctx)
        body_start = opening_body_start_index(ctx=ctx)
    except Exception:
        return set()
    rows = pairs if pairs is not None else [
        {"after_segment_id": a, "before_segment_id": b} for a, b in zip(order, order[1:])
    ]
    out: set[tuple[str, str]] = set()
    for row in rows:
        a = str(row.get("after_segment_id") or row.get("after_id") or "")
        b = str(row.get("before_segment_id") or row.get("before_id") or "")
        if not a or not b:
            continue
        gap = pair_source_gap_ms(a, b, starts)
        if (gap is not None and int(gap) < -margin) or (b in opening and pos.get(b, 0) >= body_start):
            out.add((a, b))
    return out


def missing_reorder_bridges(
    reorder_bridges: dict[str, Any] | None,
    *,
    gap_report: dict[str, Any] | None = None,
    transitions: dict[str, Any] | None = None,
    justified_skip_before_ids: set[str] | frozenset[str] | None = None,
    edl: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return unresolved reorder pairs that still need VO/transition glue.

    Destinations with a typed justified layup skip (credits, clone adjacency,
    unhealable spoken copy, etc.) are exempt: minting a canned hinge there would
    fight layup authority, and the skip already records the coverage decision.
    Hitch air already seated between the natives (clone-safe musical glue) also
    covers the pair — do not mint a spoken clone hinge on top.
    """
    if not isinstance(reorder_bridges, dict):
        return []
    bridged = _bridged_pairs(gap_report, transitions)
    if isinstance(edl, dict):
        from interview_mux.assembly_ledger import hitch_covered_pairs

        clips = [c for c in (edl.get("clips") or []) if isinstance(c, dict)]
        bridged |= hitch_covered_pairs(clips)
    skip_before = {str(x) for x in (justified_skip_before_ids or set()) if str(x).strip()}
    vo_before_targets: set[str] = set()
    vo_after_targets: set[str] = set()
    if isinstance(gap_report, dict):
        for ln in gap_report.get("interviewer_lines") or []:
            if not isinstance(ln, dict) or ln.get("skipped_optional"):
                continue
            delivery = str(ln.get("delivery") or "").lower()
            if delivery and delivery not in {"record", "synthesize"}:
                continue
            tid = str(ln.get("targets_segment_id") or "").strip()
            if not tid:
                continue
            placement = str(ln.get("placement") or "before").strip()
            if placement == "before":
                vo_before_targets.add(tid)
            elif placement == "after":
                # A line seated after A covers A->B exactly as
                # gap_framing._gap_line_covers_seam counts it; clone adjacency
                # moves layup lines there (ISSUES 151).
                vo_after_targets.add(tid)
    missing: list[dict[str, Any]] = []
    for pair in reorder_bridges.get("pairs") or []:
        if not isinstance(pair, dict):
            continue
        a = str(pair.get("after_id") or pair.get("after_segment_id") or "")
        b = str(pair.get("before_id") or pair.get("before_segment_id") or "")
        if not a or not b:
            continue
        if (a, b) in bridged or b in vo_before_targets or a in vo_after_targets or b in skip_before:
            continue
        missing.append(
            {
                "after_segment_id": a,
                "before_segment_id": b,
                "kind": pair.get("kind"),
                "source_gap_ms": pair.get("source_gap_ms"),
                "suggested_line_category": pair.get("suggested_line_category"),
                "suggested_pov": pair.get("suggested_pov"),
                "max_words": pair.get("max_words"),
            }
        )
    return missing


def stub_reorder_bridges(
    gap_report: dict[str, Any] | None,
    transitions: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Advisory (non-blocking): bridges that count as "bridged" but read as
    canned filler rather than pair-specific glue — a known generic stub phrase,
    or verbatim text pasted across several distinct pairs.
    """
    by_text: dict[str, list[tuple[str, str]]] = {}
    stubs: list[dict[str, Any]] = []

    def _scan(rows: Any) -> None:
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            a = str(row.get("after_segment_id") or "")
            b = str(row.get("before_segment_id") or "")
            if not a or not b:
                continue
            norm = _normalize_bridge_text(text)
            by_text.setdefault(norm, []).append((a, b))
            if norm in _GENERIC_STUB_PHRASES:
                stubs.append(
                    {
                        "after_segment_id": a,
                        "before_segment_id": b,
                        "reason": "generic_stub_phrase",
                        "text": text,
                    }
                )

    if isinstance(transitions, dict):
        _scan(transitions.get("transitions"))
        _scan(transitions.get("deferred_transition_pairs"))
    if isinstance(gap_report, dict):
        _scan(gap_report.get("interviewer_lines"))

    for norm, pairs in by_text.items():
        if norm in _GENERIC_STUB_PHRASES:
            continue
        distinct = sorted(set(pairs))
        if len(distinct) >= _REPEATED_TEXT_STUB_THRESHOLD:
            for a, b in distinct:
                stubs.append(
                    {
                        "after_segment_id": a,
                        "before_segment_id": b,
                        "reason": "repeated_verbatim_text",
                        "text": norm,
                    }
                )
    return stubs


def assert_bridges_complete(
    reorder_bridges: dict[str, Any] | None,
    *,
    gap_report: dict[str, Any] | None = None,
    transitions: dict[str, Any] | None = None,
    justified_skip_before_ids: set[str] | frozenset[str] | None = None,
    edl: dict[str, Any] | None = None,
    soft: bool = False,
) -> dict[str, Any]:
    """Return completeness doc; raise SystemExit when incomplete and not soft.

    Stub bridges (known stock phrases, or the same verbatim line pasted across
    ≥2 distinct pairs) count as incomplete — they are audible filler, not
    pair-specific glue.
    """
    missing = missing_reorder_bridges(
        reorder_bridges,
        gap_report=gap_report,
        transitions=transitions,
        justified_skip_before_ids=justified_skip_before_ids,
        edl=edl,
    )
    stubs = stub_reorder_bridges(gap_report, transitions)
    doc = {
        "version": 1,
        "complete": not missing and not stubs,
        "missing_count": len(missing),
        "missing": missing,
        "pair_specific": True,
        "stub_count": len(stubs),
        "stub_pairs": stubs,
    }
    if soft:
        return doc
    if missing:
        sample = ", ".join(
            f"{m['after_segment_id']}->{m['before_segment_id']}" for m in missing[:6]
        )
        raise SystemExit(
            f"bridge_completeness: {len(missing)} reorder join(s) lack pair-specific "
            f"gap/transition glue before EDL — fix transitions or gap_report ({sample})"
        )
    if stubs:
        sample = ", ".join(
            f"{s['after_segment_id']}->{s['before_segment_id']}" for s in stubs[:6]
        )
        raise SystemExit(
            f"bridge_completeness: {len(stubs)} reorder join(s) use canned/repeated "
            f"stub bridge text — rewrite with pair-specific glue ({sample})"
        )
    return doc


def required_bridge_keys(
    reorder_bridges: dict[str, Any] | None,
) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    if not isinstance(reorder_bridges, dict):
        return keys
    for pair in reorder_bridges.get("pairs") or []:
        if not isinstance(pair, dict):
            continue
        a = str(pair.get("after_id") or pair.get("after_segment_id") or "")
        b = str(pair.get("before_id") or pair.get("before_segment_id") or "")
        if a and b:
            keys.add((a, b))
    return keys


def mint_needs_spoken_glue_placeholders(
    ctx: Any,
    reorder_bridges: dict[str, Any] | None,
    *,
    ordered: list[str] | None = None,
) -> dict[str, Any]:
    """Tag incomplete reorder pairs with needs_spoken_glue (never claim complete).

    Does not invent spoken stub text — transitions/layup must supply real glue.
    """
    del ctx, ordered  # reserved for future context-aware tagging
    bridges = dict(reorder_bridges or {}) if isinstance(reorder_bridges, dict) else {"pairs": []}
    pairs = [dict(p) for p in (bridges.get("pairs") or []) if isinstance(p, dict)]
    tagged = 0
    for pair in pairs:
        a = str(pair.get("after_id") or pair.get("after_segment_id") or "")
        b = str(pair.get("before_id") or pair.get("before_segment_id") or "")
        if not a or not b:
            continue
        if pair.get("complete") is True or pair.get("bridged") is True:
            continue
        text = str(pair.get("text") or pair.get("spoken_text") or "").strip()
        if text and _normalize_bridge_text(text) not in _GENERIC_STUB_PHRASES:
            continue
        pair["needs_spoken_glue"] = True
        pair["complete"] = False
        # Strip any stub text so assert_bridges_complete does not soft-green.
        if text and _normalize_bridge_text(text) in _GENERIC_STUB_PHRASES:
            pair.pop("text", None)
            pair.pop("spoken_text", None)
        tagged += 1
    bridges["pairs"] = pairs
    bridges["needs_spoken_glue_count"] = tagged
    return bridges
