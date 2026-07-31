"""Hard-require a gap line or transition for every reorder_bridges adjacency."""

from __future__ import annotations

from typing import Any


def _bridged_pairs(
    gap_report: dict[str, Any] | None,
    transitions: dict[str, Any] | None,
) -> set[tuple[str, str]]:
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
            target = str(ln.get("targets_segment_id") or "")
            if target:
                bridged.add(("*", target))
            after = str(ln.get("after_segment_id") or "")
            before = str(ln.get("before_segment_id") or target)
            if after and before:
                bridged.add((after, before))
    if isinstance(transitions, dict):
        for tr in transitions.get("transitions") or []:
            if not isinstance(tr, dict):
                continue
            a = str(tr.get("after_segment_id") or "")
            b = str(tr.get("before_segment_id") or "")
            text = str(tr.get("text") or "").strip()
            # Silence-only transitions still count as intentional glue
            if a and b and (text or tr.get("kind") or tr.get("silence_ms")):
                bridged.add((a, b))
    return bridged


def missing_reorder_bridges(
    reorder_bridges: dict[str, Any] | None,
    *,
    gap_report: dict[str, Any] | None = None,
    transitions: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return unresolved reorder pairs that still need VO/transition glue."""
    if not isinstance(reorder_bridges, dict):
        return []
    bridged = _bridged_pairs(gap_report, transitions)
    missing: list[dict[str, Any]] = []
    for pair in reorder_bridges.get("pairs") or []:
        if not isinstance(pair, dict):
            continue
        a = str(pair.get("after_id") or pair.get("after_segment_id") or "")
        b = str(pair.get("before_id") or pair.get("before_segment_id") or "")
        if not a or not b:
            continue
        if (a, b) in bridged or ("*", b) in bridged:
            continue
        missing.append(
            {
                "after_segment_id": a,
                "before_segment_id": b,
                "kind": pair.get("kind"),
                "suggested_line_category": pair.get("suggested_line_category"),
                "suggested_pov": pair.get("suggested_pov"),
                "max_words": pair.get("max_words"),
            }
        )
    return missing


def assert_bridges_complete(
    reorder_bridges: dict[str, Any] | None,
    *,
    gap_report: dict[str, Any] | None = None,
    transitions: dict[str, Any] | None = None,
    soft: bool = False,
) -> dict[str, Any]:
    """Return completeness doc; raise SystemExit when incomplete and not soft."""
    missing = missing_reorder_bridges(
        reorder_bridges, gap_report=gap_report, transitions=transitions
    )
    doc = {
        "version": 1,
        "complete": not missing,
        "missing_count": len(missing),
        "missing": missing,
    }
    if missing and not soft:
        sample = ", ".join(
            f"{m['after_segment_id']}->{m['before_segment_id']}" for m in missing[:6]
        )
        raise SystemExit(
            f"bridge_completeness: {len(missing)} reorder join(s) lack gap/transition "
            f"glue before EDL — fix transitions or gap_report ({sample})"
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
