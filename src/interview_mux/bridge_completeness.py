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
    if isinstance(gap_report, dict):
        for ln in gap_report.get("interviewer_lines") or []:
            if not isinstance(ln, dict) or ln.get("skipped_optional"):
                continue
            delivery = str(ln.get("delivery") or "").lower()
            if delivery and delivery not in {"record", "synthesize"}:
                continue
            if str(ln.get("placement") or "before").strip() != "before":
                continue
            tid = str(ln.get("targets_segment_id") or "").strip()
            if tid:
                vo_before_targets.add(tid)
    missing: list[dict[str, Any]] = []
    for pair in reorder_bridges.get("pairs") or []:
        if not isinstance(pair, dict):
            continue
        a = str(pair.get("after_id") or pair.get("after_segment_id") or "")
        b = str(pair.get("before_id") or pair.get("before_segment_id") or "")
        if not a or not b:
            continue
        if (a, b) in bridged or b in vo_before_targets or b in skip_before:
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
