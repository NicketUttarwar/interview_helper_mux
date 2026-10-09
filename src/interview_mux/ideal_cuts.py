"""Talking-points-first ideal cuts: snap, materialize boundaries, ranking seed.

Holistic flow (when ``analysis.ideal_cuts.enable``):
  content_context → talking_points_compose → ideal_cuts_propose
  → ideal_cuts_materialize → (optional boundary bind) → classification / ranking
"""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import heal_or_refuse_mark

TALKING_POINTS_REL = "understanding/talking_points.json"
IDEAL_CUTS_REL = "understanding/ideal_cuts.json"
MATERIALIZED_REL = "understanding/ideal_cuts_materialized.json"
SELECTION_SEED_REL = "understanding/ideal_cuts_selection_seed.json"
BOUNDARIES_REL = "segments/boundaries.json"


def ideal_cuts_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = ((cfg or merged_config()).get("analysis") or {}).get("ideal_cuts") or {}
    defaults = {
        "enable": True,
        # off | seed_ranking | boundaries | both
        "bind_mode": "both",
        "min_cut_ms": 2500,
        # Not a ceiling. A cut is as long as the concept it proves.
        "max_cut_ms": None,
        # Tight word snap only — large free shifts steal list items / leave hangs.
        "word_snap_margin_ms": 0,
        "word_snap_max_shift_ms": 150,
        "semantic_edge_buffer_ms": 30_000,
        "acoustic_edge_refine": True,
        "acoustic_search_ms": 120,
        # When a keep ends on a word and the next word is later, cut at mid-pause.
        "pause_midpoint_end": True,
        "pause_midpoint_min_gap_ms": 80,
        "pause_midpoint_max_pad_ms": 1000,
        # Max |anchored_ms - approx_ms| before treating the pair as mismatched.
        "anchor_max_delta_ms": 8_000,
        # Word indexes are exact when correct; keep a tight disagreement budget so
        # schema-forced 0/0 placeholders cannot collapse cuts onto word[0].
        "word_index_max_delta_ms": 2_000,
        "reject_unresolved_must_keep_anchors": True,
        "skip_boundary_llm_when_bound": True,
        # Ideal-cut windows are sole native keep authority — skip topic resplit.
        "skip_topic_resplit_when_bound": True,
        "skip_classification_llm_when_bound": True,
        "prefer_seed_over_ranking": True,
        # Talking-points-first air order beats Shape segment order when both bind.
        "prefer_seed_over_shape": True,
        # Reject propose / skip deterministic narrative when cut span is early-only.
        "min_span_coverage_ratio": 0.45,
        "overlap_map_min_ms": 500,
    }
    if isinstance(raw, dict):
        return {**defaults, **raw}
    return defaults


def cut_span_coverage_ratio(
    cuts_doc: dict[str, Any] | None,
    duration_ms: int,
) -> float:
    """Fraction of source span from earliest cut start to latest cut end."""
    if duration_ms <= 0:
        return 1.0
    cuts = [
        c
        for c in ((cuts_doc or {}).get("cuts") or [])
        if isinstance(c, dict)
    ]
    if not cuts:
        return 0.0
    starts: list[int] = []
    ends: list[int] = []
    for cut in cuts:
        try:
            s = int(cut.get("start_ms") or 0)
            e = int(cut.get("end_ms") or 0)
        except (TypeError, ValueError):
            continue
        if e > s:
            starts.append(s)
            ends.append(e)
    if not starts:
        return 0.0
    span = max(ends) - min(starts)
    return max(0.0, min(1.0, float(span) / float(duration_ms)))


def _word_window_around(
    words: list[dict[str, Any]],
    center_ms: int,
    *,
    want_ms: int,
    min_cut_ms: int,
    max_cut_ms: int | None = None,
) -> tuple[int, int, int, int] | None:
    """Concept around ``center_ms``.

    The window runs to the concept change on each side. A clock does not size
    it and does not reject it. ``want_ms`` and ``max_cut_ms`` are ignored.
    """
    del want_ms, max_cut_ms
    from interview_mux.gap_vo_prior_context import is_legal_conceptual_hinge

    indexed: list[tuple[int, int, int]] = []
    for i, word in enumerate(words):
        try:
            s = int(word.get("start_ms") or 0)
            e = int(word.get("end_ms") or 0)
        except (TypeError, ValueError):
            continue
        if e > s:
            indexed.append((i, s, e))
    if not indexed:
        return None
    nearest = min(indexed, key=lambda row: abs(row[1] - center_ms))
    by_i = {i: (s, e) for i, s, e in indexed}
    order = [i for i, _s, _e in indexed]
    pos = order.index(nearest[0])

    def _hinge_at(end_index: int) -> bool:
        lo_i = max(0, end_index - 16)
        hi_i = min(len(order), end_index + 17)
        text = " ".join(
            str(words[order[j]].get("text") or words[order[j]].get("word") or "")
            for j in range(lo_i, end_index + 1)
        ).strip()
        local = [words[order[j]] for j in range(lo_i, hi_i)]
        end_ms = by_i[order[end_index]][1]
        nxt = by_i[order[end_index + 1]][0] if end_index + 1 < len(order) else None
        pause = None if nxt is None else max(0, nxt - end_ms)
        return bool(
            is_legal_conceptual_hinge(text, words=local, end_ms=end_ms, next_pause_ms=pause)
        )

    lo_pos = pos
    while lo_pos > 0 and not _hinge_at(lo_pos - 1):
        lo_pos -= 1
    hi_pos = pos
    while hi_pos < len(order) - 1 and not _hinge_at(hi_pos):
        hi_pos += 1
    start_ms = by_i[order[lo_pos]][0]
    end_ms = by_i[order[hi_pos]][1]
    if end_ms - start_ms < min_cut_ms:
        return None
    return start_ms, end_ms, order[lo_pos], order[hi_pos]


def spread_talking_point_time_hints(
    talking_points: dict[str, Any] | None,
    duration_ms: int,
    *,
    floor: float | None = None,
) -> dict[str, Any]:
    """Re-spread early-clustered ``approx_time_hint_ms`` across a long tape."""
    doc = dict(talking_points or {})
    points = [dict(p) for p in (doc.get("talking_points") or []) if isinstance(p, dict)]
    if duration_ms < 900_000 or len(points) < 2:
        return talking_points if isinstance(talking_points, dict) else doc
    ratio_floor = floor
    if ratio_floor is None:
        ratio_floor = float(ideal_cuts_cfg().get("min_span_coverage_ratio") or 0.45)
    hints: list[int] = []
    for row in points:
        try:
            hints.append(int(row.get("approx_time_hint_ms") or 0))
        except (TypeError, ValueError):
            hints.append(0)
    span = (max(hints) - min(hints)) if hints else 0
    if duration_ms > 0 and (span / float(duration_ms)) >= ratio_floor:
        return talking_points if isinstance(talking_points, dict) else doc
    n = len(points)
    for i, row in enumerate(points):
        row["approx_time_hint_ms"] = int(duration_ms * (0.05 + 0.85 * i / max(n - 1, 1)))
    out = dict(doc)
    out["talking_points"] = points
    warnings = [str(w) for w in (out.get("warnings") or []) if w]
    note = "approx_time_hints_spread_across_source"
    if note not in warnings:
        warnings.append(note)
    out["warnings"] = warnings
    return out


def redistribute_clustered_cuts(
    artifacts: dict[str, Any] | None,
    duration_ms: int,
    *,
    talking_points: dict[str, Any] | None = None,
    transcript: dict[str, Any] | None = None,
    floor: float | None = None,
) -> dict[str, Any]:
    """Add mid/late native windows when propose clustered in the cold open."""
    out = dict(artifacts or {})
    cuts = [dict(c) for c in (out.get("cuts") or []) if isinstance(c, dict)]
    ratio_floor = floor
    if ratio_floor is None:
        ratio_floor = float(ideal_cuts_cfg().get("min_span_coverage_ratio") or 0.45)
    if duration_ms <= 0 or cut_span_coverage_ratio({"cuts": cuts}, duration_ms) >= ratio_floor:
        if cuts:
            out["cuts"] = cuts
        return out
    cfg = ideal_cuts_cfg()
    min_cut_ms = int(cfg.get("min_cut_ms") or 2500)
    raw_max = cfg.get("max_cut_ms")
    max_cut_ms = int(raw_max) if raw_max else None
    want_ms = min_cut_ms
    tps = [
        t
        for t in ((talking_points or {}).get("talking_points") or [])
        if isinstance(t, dict)
    ]
    ranked = [
        t
        for t in tps
        if str(t.get("importance") or "").lower() in {"must_keep", "should_keep"}
    ] or tps
    fallback_tp = str(
        (ranked[-1] if ranked else {}).get("talking_point_id")
        or (cuts[-1].get("talking_point_id") if cuts else "")
        or "tp_span"
    )
    words = [w for w in ((transcript or {}).get("words") or []) if isinstance(w, dict)]
    existing_ids = {str(c.get("cut_id") or "") for c in cuts}

    def _overlaps(start_ms: int, end_ms: int) -> bool:
        for cut in cuts:
            try:
                s = int(cut.get("start_ms") or 0)
                e = int(cut.get("end_ms") or 0)
            except (TypeError, ValueError):
                continue
            if e > s and not (end_ms <= s or start_ms >= e):
                return True
        return False

    added: list[str] = []
    for i, frac in enumerate((0.50, 0.82)):
        center = int(duration_ms * frac)
        window = _word_window_around(
            words,
            center,
            want_ms=want_ms,
            min_cut_ms=min_cut_ms,
            max_cut_ms=max_cut_ms,
        )
        if window is None:
            continue
        start_ms, end_ms, si, ei = window
        if _overlaps(start_ms, end_ms):
            # Keep the part of the concept that sits in the open gap around center.
            gap_lo = 0
            gap_hi = duration_ms
            for cut in cuts:
                try:
                    s = int(cut.get("start_ms") or 0)
                    e = int(cut.get("end_ms") or 0)
                except (TypeError, ValueError):
                    continue
                if e <= center:
                    gap_lo = max(gap_lo, e)
                elif s >= center:
                    gap_hi = min(gap_hi, s)
            start_ms = max(start_ms, gap_lo)
            end_ms = min(end_ms, gap_hi)
            if end_ms - start_ms < min_cut_ms or _overlaps(start_ms, end_ms):
                continue
        cid = f"cut_span_{i + 1}"
        if cid in existing_ids:
            cid = f"cut_span_{i + 1}_{start_ms}"
        row: dict[str, Any] = {
            "cut_id": cid,
            "talking_point_id": fallback_tp,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "priority": "should_keep",
            "rationale": (
                "Deterministic span redistribution: native window in a later third "
                "so proofs are not cold-open-only."
            ),
        }
        if words and window is not None:
            row["start_word_index"] = si
            row["end_word_index"] = ei
        cuts.append(row)
        existing_ids.add(cid)
        added.append(cid)
    cuts.sort(key=lambda c: int(c.get("start_ms") or 0))
    out["cuts"] = cuts
    if added:
        warnings = [str(w) for w in (out.get("warnings") or []) if w]
        note = f"span_redistributed:{','.join(added)}"
        if note not in warnings:
            warnings.append(note)
        out["warnings"] = warnings
        extra = "Added later-third native windows after propose clustered early."
        prev = str(out.get("coverage_notes") or "").strip()
        out["coverage_notes"] = f"{prev} {extra}".strip() if prev else extra
    return out


def strip_provisional_segment_ids(snapped: dict[str, Any]) -> dict[str, Any]:
    """Clear segment bindings stamped by a skipped boundary bind."""
    out = dict(snapped)
    cleaned: list[dict[str, Any]] = []
    for cut in snapped.get("cuts") or []:
        if not isinstance(cut, dict):
            continue
        row = dict(cut)
        row.pop("segment_id", None)
        row.pop("segment_ids", None)
        row.pop("overlap_ms", None)
        cleaned.append(row)
    out["cuts"] = cleaned
    return out


def bind_boundaries_enabled(cfg: dict[str, Any] | None = None) -> bool:
    conf = ideal_cuts_cfg(cfg)
    if not conf.get("enable", True):
        return False
    mode = str(conf.get("bind_mode") or "off").strip().lower()
    return mode in {"boundaries", "both"}


def bind_ranking_enabled(cfg: dict[str, Any] | None = None) -> bool:
    conf = ideal_cuts_cfg(cfg)
    if not conf.get("enable", True):
        return False
    mode = str(conf.get("bind_mode") or "off").strip().lower()
    return mode in {"seed_ranking", "both"}


def _usable_word_time(word: dict[str, Any]) -> bool:
    """Keep a word whose start is a whole millisecond. Skip a bad time."""
    value = word.get("start_ms", word.get("start"))
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return value == int(value)
    if isinstance(value, str):
        return value.strip().lstrip("-").isdigit()
    return False


def _word_list(transcript: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(transcript, dict):
        return []
    words = transcript.get("words") or []
    return [w for w in words if isinstance(w, dict)]


def _snap_ms(
    ms: int,
    words: list[dict[str, Any]],
    *,
    prefer: str,
    margin_ms: int,
    max_shift_ms: int,
) -> int:
    """Snap to the nearest word start (open) or word end (close) within max_shift.

    Margin padding is disabled by default — acoustic refine owns breath room.
    """
    if not words:
        return max(0, int(ms))
    best = int(ms)
    best_dist = max_shift_ms + 1
    for word in words:
        if not isinstance(word, dict):
            continue
        key = "start_ms" if prefer == "start" else "end_ms"
        try:
            boundary = int(float(word.get(key) or word.get("start_ms") or 0))
        except (TypeError, ValueError):
            continue
        if boundary < 0:
            continue
        dist = abs(boundary - int(ms))
        if dist <= max_shift_ms and dist < best_dist:
            best = max(0, boundary)
            best_dist = dist
    if prefer == "end" and margin_ms > 0:
        best = best + int(margin_ms)
    return max(0, best)


def _resolve_cut_edge_ms(
    cut: dict[str, Any],
    words: list[dict[str, Any]],
    *,
    prefer: str,
    approx_ms: int,
    margin_ms: int,
    max_shift_ms: int,
    anchor_max_delta_ms: int = 8_000,
    word_index_max_delta_ms: int = 2_000,
) -> tuple[int, dict[str, Any]]:
    """Prefer LLM word index / anchor quote, then tight word snap.

    Returns ``(ms, resolve_meta)``. Unresolved or far-off anchors fall back to
    approx snap instead of collapsing/dropping the cut; callers still enforce
    legal conceptual hinges.
    """
    from interview_mux.cut_edge_refine import (
        resolve_ms_from_anchor_text,
        resolve_ms_from_word_index,
    )

    idx_key = "start_word_index" if prefer == "start" else "end_word_index"
    anchor_key = "start_anchor" if prefer == "start" else "end_anchor"
    meta: dict[str, Any] = {
        "prefer": prefer,
        "approx_ms": int(approx_ms),
        "matched": False,
        "source": "approx_snap",
    }
    indexed = resolve_ms_from_word_index(
        words, cut.get(idx_key), prefer=prefer
    )
    if indexed is not None:
        delta = abs(int(indexed) - int(approx_ms))
        # Structured-output schemas often force start_word_index/end_word_index.
        # Models fill 0 (or other wrong indexes) when unsure — trusting those
        # collapses every cut onto the first transcript words. Ignore indexes
        # that disagree with the proposed clock beyond a tight tolerance, then
        # fall through to anchor / approx snap.
        if delta <= int(word_index_max_delta_ms):
            meta.update(
                {
                    "matched": True,
                    "source": "word_index",
                    "resolved_ms": int(indexed),
                    "delta_ms": delta,
                    "word_index": cut.get(idx_key),
                }
            )
            return indexed, meta
        meta["word_index_ignored"] = True
        meta["word_index_delta_ms"] = delta
        meta["word_index"] = cut.get(idx_key)

    anchor_raw = cut.get(anchor_key) if isinstance(cut.get(anchor_key), str) else None
    if anchor_raw and str(anchor_raw).strip():
        anchored = resolve_ms_from_anchor_text(
            words,
            anchor_raw,
            approx_ms=approx_ms,
            prefer=prefer,
            window_ms=max(1_000, int(anchor_max_delta_ms)),
        )
        if anchored is None:
            # Paraphrased / STT-mismatched anchors are common. Prefer the proposed
            # clock + approx snap over dropping the entire must_keep window.
            meta.update(
                {
                    "matched": False,
                    "source": "anchor_unresolved",
                    "anchor": str(anchor_raw).strip(),
                    "reason": "anchor_not_found_near_approx",
                    "fallback": "approx_snap",
                }
            )
        else:
            delta = abs(int(anchored) - int(approx_ms))
            meta.update(
                {
                    "matched": True,
                    "source": "anchor",
                    "anchor": str(anchor_raw).strip(),
                    "resolved_ms": int(anchored),
                    "delta_ms": delta,
                }
            )
            if delta <= int(anchor_max_delta_ms):
                return int(anchored), meta
            meta["reason"] = "anchor_delta_exceeds_tolerance"
            meta["fallback"] = "approx_snap"
            # Fall through to approx snap — do not hard-reject the cut solely
            # because a quote landed outside the tight window.

    snapped = _snap_ms(
        approx_ms,
        words,
        prefer=prefer,
        margin_ms=margin_ms,
        max_shift_ms=max_shift_ms,
    )
    # Preserve unresolved-anchor diagnostics when falling back to the clock.
    fallback = meta.get("fallback")
    reason = meta.get("reason")
    anchor = meta.get("anchor")
    meta.update(
        {
            "matched": True,
            "source": "approx_snap",
            "resolved_ms": int(snapped),
            "delta_ms": abs(int(snapped) - int(approx_ms)),
        }
    )
    if fallback:
        meta["fallback"] = fallback
    if reason:
        meta["reason"] = reason
    if anchor:
        meta["anchor"] = anchor
    return snapped, meta


def _anchors_inside_window(
    words: list[dict[str, Any]],
    cut: dict[str, Any],
    start_ms: int,
    end_ms: int,
) -> dict[str, Any]:
    """Verify start/end anchors (when present) land inside the selected window."""
    from interview_mux.cut_edge_refine import resolve_ms_from_anchor_text

    evidence: dict[str, Any] = {"ok": True, "checks": []}
    for prefer, key in (("start", "start_anchor"), ("end", "end_anchor")):
        anchor = cut.get(key)
        if not isinstance(anchor, str) or not anchor.strip():
            continue
        approx = start_ms if prefer == "start" else end_ms
        resolved = resolve_ms_from_anchor_text(
            words,
            anchor,
            approx_ms=approx,
            prefer=prefer,
            window_ms=max(2_000, end_ms - start_ms + 1_000),
        )
        check: dict[str, Any] = {
            "anchor": anchor.strip(),
            "prefer": prefer,
            "resolved_ms": resolved,
            "in_window": False,
        }
        if resolved is None:
            evidence["ok"] = False
            check["reason"] = "unresolved"
        elif not (start_ms - 80 <= int(resolved) <= end_ms + 80):
            evidence["ok"] = False
            check["reason"] = "outside_window"
        else:
            check["in_window"] = True
        evidence["checks"].append(check)
    return evidence


def _majority_speaker(words: list[dict[str, Any]], start_ms: int, end_ms: int) -> str | None:
    from interview_mux.boundary_enrich import majority_speaker_for_span

    return majority_speaker_for_span(words, start_ms, end_ms)


def _span_text(words: list[dict[str, Any]], start_ms: int, end_ms: int, *, max_chars: int = 240) -> str:
    parts: list[str] = []
    for word in words:
        try:
            w0 = int(float(word.get("start_ms") or 0))
            w1 = int(float(word.get("end_ms") or w0))
        except (TypeError, ValueError):
            continue
        if w1 < start_ms or w0 > end_ms:
            continue
        tok = str(word.get("word") or word.get("text") or "").strip()
        if tok:
            parts.append(tok)
    text = " ".join(parts).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0]
    return text


_CUT_PRIORITY_RANK = {"must_keep": 0, "should_keep": 1, "optional": 2}


def _snap_overlap_starts_to_words(
    rows: list[dict[str, Any]],
    words: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """A trim lands on end+80, which can be the middle of a word.

    If the previous segment already holds that word, this segment starts
    after it. Otherwise this segment takes the whole word. Silence stays put,
    so the 80 ms gap remains when no word is being cut.
    """
    ordered = sorted(rows, key=lambda r: int(r.get("start_ms") or 0))
    for index, row in enumerate(ordered):
        try:
            start = int(row.get("start_ms") or 0)
            end = int(row.get("end_ms") or start)
        except (TypeError, ValueError):
            continue
        prev_end = 0
        if index:
            try:
                prev_end = int(ordered[index - 1].get("end_ms") or 0)
            except (TypeError, ValueError):
                prev_end = 0
        next_start: int | None = None
        if index + 1 < len(ordered):
            try:
                next_start = int(ordered[index + 1].get("start_ms") or 0)
            except (TypeError, ValueError):
                next_start = None
        floor = prev_end + 80 if index else start
        for word in words:
            try:
                w0 = int(float(word.get("start_ms") or 0))
                w1 = int(float(word.get("end_ms") or w0))
            except (TypeError, ValueError):
                continue
            if not (w0 < start < w1):
                continue
            # Keep the 80 ms gap. A word the previous segment already holds
            # starts this piece after that word. A word this piece owns is
            # taken whole only when that still leaves the gap.
            candidate = w1 if w0 < prev_end else w0
            if candidate < floor:
                candidate = w1 if w1 >= floor else floor
            start = candidate
            break
        if next_start is not None and start >= next_start:
            start = int(row.get("start_ms") or 0)
        if start < floor < end and (next_start is None or floor < next_start):
            start = floor
        if start >= end:
            continue
        if start != int(row.get("start_ms") or 0):
            row["start_ms"] = start
            row["end_ms"] = end
            row["duration_ms"] = end - start
            row["text_excerpt"] = _span_text(words, start, end)
    return ordered


def resolve_cut_overlaps(
    snapped: list[dict[str, Any]],
    warnings: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Keep higher-priority, then longer cuts; drop a cut only on a real overlap.

    Rows are taken best priority first, so every kept row outranks or ties the
    current one. Comparing against the last kept row's end dropped any
    lower-tier cut that started before the last must_keep ended, however far
    apart on tape (ISSUES 179).
    """
    rank = _CUT_PRIORITY_RANK
    rows = sorted(
        (r for r in snapped if isinstance(r, dict)),
        key=lambda r: (
            rank.get(str(r.get("priority")), 9),
            int(r.get("start_ms") or 0),
            -int(r.get("duration_ms") or 0),
        ),
    )
    resolved: list[dict[str, Any]] = []
    for row in rows:
        r0 = int(row.get("start_ms") or 0)
        r1 = int(row.get("end_ms") or r0)
        blockers = [
            k
            for k in resolved
            if r0 < int(k.get("end_ms") or 0) and int(k.get("start_ms") or 0) < r1
        ]
        if blockers:
            # The 80 ms gap stays on each side of the earlier window. Words
            # that belong only to this cut, before that window and after it,
            # stay their own segments. A cut that lies entirely inside is
            # still dropped, because those words are already on the earlier cut.
            label = row.get("cut_id") or row.get("talking_point_id")
            covered: list[tuple[int, int]] = []
            for blocker in blockers:
                b0 = max(r0, int(blocker.get("start_ms") or 0))
                b1 = min(r1, int(blocker.get("end_ms") or 0))
                if b1 > b0:
                    covered.append((b0, b1))
            covered.sort()
            merged: list[tuple[int, int]] = []
            for b0, b1 in covered:
                if merged and b0 <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], b1))
                else:
                    merged.append((b0, b1))
            pieces: list[tuple[int, int]] = []
            cursor = r0
            for b0, b1 in merged:
                left = b0 - 80
                if left - cursor >= 80:
                    pieces.append((cursor, left))
                cursor = b1 + 80
            if r1 - cursor >= 80:
                pieces.append((cursor, r1))
            if not pieces:
                if warnings is not None:
                    warnings.append(f"dropped overlapping cut {label}")
                continue
            for index, (piece_start, piece_end) in enumerate(pieces):
                kept = dict(row)
                if index == 1 and kept.get("cut_id"):
                    kept["cut_id"] = f"{kept.get('cut_id')}__tail"
                elif index > 1 and kept.get("cut_id"):
                    kept["cut_id"] = f"{kept.get('cut_id')}__part{index + 1}"
                kept["start_ms"] = piece_start
                kept["end_ms"] = piece_end
                kept["duration_ms"] = piece_end - piece_start
                resolved.append(kept)
            if warnings is not None and any(piece[0] == r0 for piece in pieces):
                warnings.append(f"kept words before overlap on cut {label}")
            if warnings is not None and any(piece[0] > r0 for piece in pieces):
                warnings.append(
                    f"trimmed overlapping cut {label} to keep words after {pieces[-1][0]}"
                )
            continue
        resolved.append(row)
    return resolved


def snap_ideal_cuts(
    cuts_doc: dict[str, Any],
    transcript: dict[str, Any],
    *,
    cfg: dict[str, Any] | None = None,
    wav_path: Any | None = None,
) -> dict[str, Any]:
    """Snap proposed cut windows to word hinges, repair illegal opens/ends, acoustic refine."""
    from pathlib import Path

    conf = ideal_cuts_cfg(cfg)
    words = [w for w in _word_list(transcript) if _usable_word_time(w)]
    min_ms = int(conf.get("min_cut_ms") or 2500)
    margin = int(conf.get("word_snap_margin_ms") or 0)
    max_shift = int(conf.get("word_snap_max_shift_ms") or 150)
    edge_buf = int(conf.get("semantic_edge_buffer_ms") or 30_000)
    acoustic_on = bool(conf.get("acoustic_edge_refine", True))
    acoustic_search = int(conf.get("acoustic_search_ms") or 120)
    anchor_max_delta = int(conf.get("anchor_max_delta_ms") or 8_000)
    word_index_max_delta = int(conf.get("word_index_max_delta_ms") or 2_000)
    reject_unresolved = bool(conf.get("reject_unresolved_must_keep_anchors", True))

    raw_cuts = list(cuts_doc.get("cuts") or []) if isinstance(cuts_doc, dict) else []
    snapped: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, cut in enumerate(raw_cuts):
        if not isinstance(cut, dict):
            continue
        try:
            start = int(cut.get("start_ms") or 0)
            end = int(cut.get("end_ms") or 0)
        except (TypeError, ValueError):
            warnings.append(f"cut[{index}] invalid times")
            continue
        if end <= start:
            warnings.append(f"cut[{index}] end<=start")
            continue
        working = dict(cut)
        try:
            swi = working.get("start_word_index")
            ewi = working.get("end_word_index")
            same_idx = (
                swi is not None
                and ewi is not None
                and int(swi) == int(ewi)
            )
        except (TypeError, ValueError):
            same_idx = False
        # Identical start/end indexes on a real span are almost always schema
        # placeholders (commonly 0/0), not a valid one-word keep window.
        if same_idx and (end - start) > min_ms:
            working.pop("start_word_index", None)
            working.pop("end_word_index", None)
            warnings.append(
                f"cut[{index}] ignored identical start/end word_index placeholders"
            )
        start, start_meta = _resolve_cut_edge_ms(
            working,
            words,
            prefer="start",
            approx_ms=start,
            margin_ms=margin,
            max_shift_ms=max_shift,
            anchor_max_delta_ms=anchor_max_delta,
            word_index_max_delta_ms=word_index_max_delta,
        )
        end, end_meta = _resolve_cut_edge_ms(
            working,
            words,
            prefer="end",
            approx_ms=end,
            margin_ms=margin,
            max_shift_ms=max_shift,
            anchor_max_delta_ms=anchor_max_delta,
            word_index_max_delta_ms=word_index_max_delta,
        )
        priority = str(cut.get("priority") or "should_keep").strip().lower()
        if priority not in {"must_keep", "should_keep", "optional"}:
            priority = "should_keep"
        anchor_reject = bool(start_meta.get("reject") or end_meta.get("reject"))
        if anchor_reject:
            reason = start_meta.get("reason") or end_meta.get("reason") or "anchor_mismatch"
            warnings.append(
                f"cut[{index}] anchor verification failed ({reason}) "
                f"start={start_meta.get('source')} end={end_meta.get('source')}"
            )
            if reject_unresolved:
                warnings.append(
                    f"cut[{index}] rejected: anchor/time mismatch"
                    + (" (must_keep)" if priority == "must_keep" else "")
                )
                continue
        if end <= start:
            end = start + min_ms
        dur = end - start
        if dur < min_ms:
            end = start + min_ms
            warnings.append(f"cut[{index}] padded to min_cut_ms")
        from interview_mux.gap_vo_prior_context import (
            clause_continues_after,
            clause_continues_before,
            is_legal_conceptual_hinge,
            is_legal_conceptual_open,
        )

        # Start-side: walk back when the open drops mid-list / mid-clause.
        start_text = _span_text(words, start, min(end, start + 30_000), max_chars=400)
        if not is_legal_conceptual_open(
            start_text, words=words, start_ms=start, prev_pause_ms=None
        ) or clause_continues_before(words, start):
            fixed_start = first_legal_open_start_ms(
                words,
                from_ms=start,
                hard_floor_ms=max(0, start - edge_buf),
                hard_ceil_ms=end,
            )
            if fixed_start is not None and end - fixed_start >= min_ms:
                start = fixed_start
                warnings.append(
                    f"cut[{index}] auto-fixed illegal open start → {start}"
                )
            else:
                warnings.append(
                    f"cut[{index}] open may be mid-clause (could not walk back)"
                )

        kept_prior_end = False
        # Hard-reject / auto-fix hanging-setup ends after snap.
        end_text = _span_text(words, max(start, end - 30_000), end, max_chars=400)
        legal = is_legal_conceptual_hinge(
            end_text, words=words, end_ms=end, next_pause_ms=None
        )
        if not legal or clause_continues_after(words, end):
            fixed = last_complete_thought_end_ms(
                words, start_ms=start, end_ms=end
            )
            if fixed is None:
                fixed = next_legal_hinge_end_ms(
                    words, from_ms=end, max_extend_ms=max(edge_buf, 30_000)
                )
            if fixed is not None and fixed - start >= min_ms:
                end = fixed
                warnings.append(
                    f"cut[{index}] auto-fixed illegal hang end → {end}"
                )
            else:
                warnings.append(
                    f"cut[{index}] kept prior end {end}; no later legal hinge"
                )
                kept_prior_end = True

        from interview_mux.gap_vo_prior_context import investigate_forward_cut

        if not kept_prior_end:
            later_starts = []
            for other in raw_cuts:
                if other is cut or not isinstance(other, dict):
                    continue
                try:
                    other_start = int(other.get("start_ms") or 0)
                except (TypeError, ValueError):
                    continue
                if other_start > end:
                    later_starts.append(other_start)
            forward_cap = min(later_starts) - 80 if later_starts else None
            investigated = investigate_forward_cut(words, end, hard_cap_ms=forward_cap)
            if investigated - start >= min_ms and investigated != end:
                end = investigated
                warnings.append(
                    f"cut[{index}] forward 30s investigation → {end}"
                )

        window_check = _anchors_inside_window(words, cut, start, end)
        # Only fail must_keep when an anchor *resolves* outside the window.
        # Unresolved paraphrases already fell back to clocks above.
        resolved_outside = [
            c
            for c in (window_check.get("checks") or [])
            if isinstance(c, dict)
            and c.get("reason") == "outside_window"
            and c.get("resolved_ms") is not None
        ]
        if resolved_outside and reject_unresolved and priority == "must_keep":
            warnings.append(
                f"cut[{index}] rejected: must_keep anchors not in window"
            )
            continue
        if not window_check.get("ok"):
            warnings.append(
                f"cut[{index}] anchors outside selected window after snap"
            )

        # Exact word pins + optional acoustic silence valley (no large free shift).
        from interview_mux.cut_edge_refine import refine_cut_edges

        path = Path(wav_path) if wav_path else None
        start, end, edge_meta = refine_cut_edges(
            start_ms=start,
            end_ms=end,
            words=words,
            wav_path=path if path and path.is_file() else None,
            search_ms=acoustic_search,
            apply_exact_words=True,
            apply_acoustic=acoustic_on,
            pause_midpoint_end=bool(conf.get("pause_midpoint_end", True)),
            pause_midpoint_min_gap_ms=int(conf.get("pause_midpoint_min_gap_ms") or 80),
            pause_midpoint_max_pad_ms=int(conf.get("pause_midpoint_max_pad_ms") or 1000),
        )
        if end - start < min_ms:
            end = start + min_ms
        row = {
            **cut,
            "start_ms": int(start),
            "end_ms": int(end),
            "duration_ms": int(end - start),
            "priority": priority,
            "speaker_id": cut.get("speaker_id")
            or _majority_speaker(words, start, end),
            "text_excerpt": cut.get("text_excerpt")
            or _span_text(words, start, end),
            "snapped": True,
            "legal_conceptual_hinge": bool(legal) and not kept_prior_end,
            "legal_conceptual_open": True,
            "edge_refine": edge_meta,
            "anchor_resolve": {
                "start": start_meta,
                "end": end_meta,
                "window_check": window_check,
            },
        }
        snapped.append(row)

    resolved = resolve_cut_overlaps(snapped, warnings)
    resolved = _snap_overlap_starts_to_words(resolved, words)
    resolved.sort(key=lambda r: int(r.get("start_ms") or 0))

    out = dict(cuts_doc) if isinstance(cuts_doc, dict) else {}
    out["cuts"] = resolved
    out["snap_warnings"] = warnings
    out["cut_count"] = len(resolved)
    return out


def boundaries_from_snapped_cuts(
    snapped: dict[str, Any],
    *,
    publisher_stage: str = "ideal_cuts_materialize",
    fallback_speaker_id: str = "spk_0",
) -> dict[str, Any]:
    """Build a contract-valid boundaries document from snapped ideal cuts."""
    from interview_mux.stage_coupling import publish_boundary_contract

    boundaries: list[dict[str, Any]] = []
    for index, cut in enumerate(snapped.get("cuts") or []):
        if not isinstance(cut, dict):
            continue
        sid = f"seg_{index + 1:03d}"
        reason = str(cut.get("split_reason") or "talking_point_ideal_cut")
        row: dict[str, Any] = {
            "segment_id": sid,
            "start_ms": int(cut["start_ms"]),
            "end_ms": int(cut["end_ms"]),
            "proposed_split_reason": reason,
            "talking_point_id": cut.get("talking_point_id"),
            "cut_id": cut.get("cut_id") or f"cut_{index + 1:03d}",
            "priority": cut.get("priority"),
        }
        if cut.get("speaker_id"):
            row["speaker_id"] = str(cut.get("speaker_id"))
        elif boundaries and boundaries[-1].get("speaker_id"):
            row["speaker_id"] = boundaries[-1]["speaker_id"]
        else:
            row["speaker_id"] = fallback_speaker_id or "spk_0"
        boundaries.append(row)
        cut["segment_id"] = sid

    doc = {"boundaries": boundaries, "warnings": list(snapped.get("snap_warnings") or [])}
    return publish_boundary_contract(doc, publisher_stage=publisher_stage)


def _segment_ids_from_cut(cut: dict[str, Any]) -> list[str]:
    """Primary + multi-overlap segment ids for a cut (deduped, primary first)."""
    out: list[str] = []
    seen: set[str] = set()
    primary = str(cut.get("segment_id") or "").strip()
    if primary:
        out.append(primary)
        seen.add(primary)
    for sid in cut.get("segment_ids") or []:
        s = str(sid).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def selection_seed_from_snapped(snapped: dict[str, Any]) -> dict[str, Any]:
    """Preferred air order: must/should keep cuts in timeline order."""
    cuts = [c for c in (snapped.get("cuts") or []) if isinstance(c, dict)]
    must = [c for c in cuts if str(c.get("priority")) == "must_keep"]
    should = [c for c in cuts if str(c.get("priority")) == "should_keep"]
    optional = [c for c in cuts if str(c.get("priority")) == "optional"]
    # Keep narrative chronology for kept cuts (must + should), not tier-then-time.
    kept = [c for c in cuts if str(c.get("priority")) in {"must_keep", "should_keep"}]
    kept.sort(key=lambda r: int(r.get("start_ms") or 0))
    ordered_ids: list[str] = []
    seen: set[str] = set()
    for cut in kept:
        primary = str(cut.get("segment_id") or "").strip()
        ids = [primary] if primary else _segment_ids_from_cut(cut)[:1]
        for sid in ids:
            if sid not in seen:
                seen.add(sid)
                ordered_ids.append(sid)

    def _ids(rows: list[dict[str, Any]]) -> list[str]:
        ids: list[str] = []
        seen_local: set[str] = set()
        for cut in rows:
            primary = str(cut.get("segment_id") or "").strip()
            local = [primary] if primary else _segment_ids_from_cut(cut)[:1]
            for sid in local:
                if sid not in seen_local:
                    seen_local.add(sid)
                    ids.append(sid)
        return ids

    return {
        "version": 1,
        "authority": "ideal_cuts",
        "ordered_segment_ids": ordered_ids,
        "must_keep_segment_ids": _ids(must),
        "should_keep_segment_ids": _ids(should),
        "optional_segment_ids": _ids(optional),
        "cut_count": len(cuts),
    }


def map_cuts_onto_existing_boundaries(
    snapped: dict[str, Any],
    boundaries_doc: dict[str, Any],
    *,
    min_overlap_ms: int | None = None,
) -> dict[str, Any]:
    """Map each cut onto overlapping boundary segments (threshold + best primary)."""
    conf = ideal_cuts_cfg()
    threshold = int(
        min_overlap_ms
        if min_overlap_ms is not None
        else (conf.get("overlap_map_min_ms") or 500)
    )
    bounds = [
        b
        for b in (boundaries_doc.get("boundaries") or [])
        if isinstance(b, dict) and b.get("segment_id")
    ]

    def overlap(a0: int, a1: int, b0: int, b1: int) -> int:
        return max(0, min(a1, b1) - max(a0, b0))

    mapped: list[dict[str, Any]] = []
    for cut in snapped.get("cuts") or []:
        if not isinstance(cut, dict):
            continue
        c0, c1 = int(cut["start_ms"]), int(cut["end_ms"])
        overlaps: list[tuple[int, dict[str, Any]]] = []
        for b in bounds:
            ov = overlap(c0, c1, int(b.get("start_ms") or 0), int(b.get("end_ms") or 0))
            if ov >= threshold or ov > 0:
                overlaps.append((ov, b))
        overlaps.sort(key=lambda t: t[0], reverse=True)
        row = dict(cut)
        prior_id = str(cut.get("segment_id") or "").strip()
        row.pop("segment_id", None)
        row.pop("segment_ids", None)
        if overlaps:
            # Prefer all overlaps meeting the threshold; fall back to best > 0.
            strong = [b for ov, b in overlaps if ov >= threshold]
            chosen = strong or [overlaps[0][1]]
            ids = [str(b["segment_id"]) for b in chosen]
            row["segment_id"] = ids[0]
            row["segment_ids"] = ids
            row["overlap_ms"] = int(overlaps[0][0])
        elif prior_id:
            near = False
            for boundary in bounds:
                b0 = int(boundary.get("start_ms") or 0)
                b1 = int(boundary.get("end_ms") or 0)
                if 0 < b0 - c1 <= 80 or 0 < c0 - b1 <= 80:
                    near = True
                    break
            if near:
                row["segment_id"] = prior_id
        mapped.append(row)
    out = dict(snapped)
    out["cuts"] = mapped
    return out


def committed_boundaries_publisher(ctx: RunContext) -> str:
    """publisher_stage of a valid committed segment contract, else ""."""
    if not ctx.artifact_exists(BOUNDARIES_REL):
        return ""
    doc = ctx.read_json(BOUNDARIES_REL)
    if not isinstance(doc, dict):
        return ""
    meta = doc.get("_meta") if isinstance(doc.get("_meta"), dict) else {}
    contract = meta.get("segment_contract") if isinstance(meta, dict) else {}
    if not isinstance(contract, dict):
        return ""
    if not contract.get("timeline_valid") or int(contract.get("segment_count") or 0) < 1:
        return ""
    return str(contract.get("publisher_stage") or "")


def boundaries_already_from_ideal_cuts(ctx: RunContext) -> bool:
    return committed_boundaries_publisher(ctx) in {
        "ideal_cuts_materialize",
        "chapter_close_hitch",
    }


def retract_own_boundaries(ctx: RunContext) -> bool:
    """Drop a coarse segment contract this stage published on an earlier walk.

    Deleting a committed artifact is a mutation like any other, so it goes
    through the ownership constitution (``verb="invalidate"``) instead of a raw
    ``unlink``. It only ever retracts ``ideal_cuts_materialize``'s own
    publication: a ``chapter_close_hitch`` contract belongs to that stage and
    must survive a materialize re-walk.
    """
    from interview_mux.artifact_ownership import assert_write

    if committed_boundaries_publisher(ctx) != "ideal_cuts_materialize":
        return False
    assert_write(
        ctx,
        BOUNDARIES_REL,
        "ideal_cuts_materialize",
        role="producer",
        verb="invalidate",
    )
    try:
        (ctx.run_dir / BOUNDARIES_REL).unlink(missing_ok=True)
    except OSError:
        return False
    return True


def resolve_ideal_cuts_air_order(
    *,
    seed: dict[str, Any] | None,
    selection_ordered: list[str] | None,
    kept_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Prefer ideal-cuts seed order when it covers kept ids."""
    sel = [str(s) for s in (selection_ordered or []) if s]
    kept = set(kept_ids) if kept_ids is not None else set(sel)
    if not isinstance(seed, dict):
        return {
            "order_authority": "ranking",
            "ordered_segment_ids": sel,
            "bind_reason": "no_ideal_cuts_seed",
        }
    raw = [str(s) for s in (seed.get("ordered_segment_ids") or []) if s]
    if not raw:
        return {
            "order_authority": "ranking",
            "ordered_segment_ids": sel,
            "bind_reason": "empty_ideal_cuts_seed",
        }
    filtered = [s for s in raw if not kept or s in kept]
    if kept and not filtered:
        mk = [
            str(s)
            for s in (seed.get("must_keep_segment_ids") or [])
            if s and str(s) in kept
        ]
        ordered = list(dict.fromkeys([*mk, *sel]))
        return {
            "order_authority": "ideal_cuts",
            "ordered_segment_ids": ordered or sel,
            "bind_reason": "ideal_cuts_seed_union_must_keep",
        }
    # Append any kept ids missing from seed (preserve ranking relative order)
    missing = [s for s in sel if s not in set(filtered)]
    ordered = filtered + missing
    return {
        "order_authority": "ideal_cuts",
        "ordered_segment_ids": ordered,
        "bind_reason": "ideal_cuts_seed_ok",
    }


def refresh_selection_seed_from_boundaries(ctx: RunContext) -> dict[str, Any] | None:
    """Map snapped cuts onto existing boundaries and rewrite the ranking seed.

    When boundaries were published by ideal_cuts_materialize, trust existing
    segment_ids. Otherwise always remap — provisional ids from a skipped
    boundary bind must not poison the seed.
    """
    if not bind_ranking_enabled():
        return None
    if not ctx.artifact_exists(MATERIALIZED_REL) or not ctx.artifact_exists(BOUNDARIES_REL):
        return None
    mat = ctx.read_json(MATERIALIZED_REL)
    bounds = ctx.read_json(BOUNDARIES_REL)
    if not isinstance(mat, dict) or not isinstance(bounds, dict):
        return None
    if boundaries_already_from_ideal_cuts(ctx) and bool(mat.get("wrote_boundaries")):
        seed = selection_seed_from_snapped(mat)
        if seed.get("ordered_segment_ids"):
            ctx.write_json(SELECTION_SEED_REL, seed, stage_key="ideal_cuts_materialize")
            return seed
    mapped = map_cuts_onto_existing_boundaries(mat, bounds)
    seed = selection_seed_from_snapped(mapped)
    mat = dict(mat)
    mat["cuts"] = mapped.get("cuts") or []
    mat["selection_seed"] = seed
    mat["wrote_selection_seed"] = bool(seed.get("ordered_segment_ids"))
    ctx.write_json(MATERIALIZED_REL, mat, stage_key="ideal_cuts_materialize")
    if seed.get("ordered_segment_ids"):
        ctx.write_json(SELECTION_SEED_REL, seed, stage_key="ideal_cuts_materialize")
    return seed


def run_ideal_cuts_materialize(ctx: RunContext) -> None:
    """Process stage: snap cuts, optionally publish boundaries + ranking seed."""
    conf = ideal_cuts_cfg()
    if not conf.get("enable", True):
        ctx.write_json(
            MATERIALIZED_REL,
            {"version": 1, "enabled": False, "cuts": [], "note": "analysis.ideal_cuts.enable=false"},
        )
        heal_or_refuse_mark(ctx, "ideal_cuts_materialize", force=True)
        return

    if not ctx.artifact_exists(IDEAL_CUTS_REL):
        raise RuntimeError(f"{IDEAL_CUTS_REL} required before ideal_cuts_materialize")
    cuts_doc = ctx.read_json(IDEAL_CUTS_REL)
    transcript = (
        ctx.read_json("transcript/full.json")
        if ctx.artifact_exists("transcript/full.json")
        else {}
    )
    wav_path = None
    try:
        wav_path = ctx.read_path("ingest", "normalized.wav")
    except Exception:
        wav_path = None
    snapped = snap_ideal_cuts(
        cuts_doc if isinstance(cuts_doc, dict) else {},
        transcript if isinstance(transcript, dict) else {},
        cfg=conf,
        wav_path=wav_path,
    )

    wrote_boundaries = False
    boundary_skip_reason = None
    bind_mode_used = conf.get("bind_mode")
    if bind_boundaries_enabled(conf) and not snapped.get("cuts"):
        # Demote to ranking-only: boundary_detection owns segments.
        boundary_skip_reason = "empty_snap_demote"
        bind_mode_used = "off"
        ctx.log(
            "ideal_cuts_materialize: empty snap — demoting bind_mode to off "
            "(boundary_detection owns segments)",
            level="warning",
            stage="ideal_cuts_materialize",
        )
    elif bind_boundaries_enabled(conf):
        fallback_speaker = "spk_0"
        if ctx.artifact_exists("understanding/speakers.json"):
            speakers_doc = ctx.read_json("understanding/speakers.json")
            speaker_ids = [
                str(row.get("speaker_id"))
                for row in ((speakers_doc or {}).get("speakers") or [])
                if isinstance(row, dict) and row.get("speaker_id")
            ]
            if speaker_ids and "spk_0" not in speaker_ids:
                fallback_speaker = speaker_ids[0]
        boundaries = boundaries_from_snapped_cuts(
            snapped, fallback_speaker_id=fallback_speaker
        )
        # Sparse keep-windows must not become the full segment contract.
        # When metrics fail, leave boundaries for LLM boundary_detection and
        # keep ranking seed only (remap after real boundaries land).
        try:
            from interview_mux.interview_duration_policy import transcript_duration_ms
            from interview_mux.segment_timeline_standard import segmentation_cfg
            from interview_mux.stages.segmentation import evaluate_boundary_quality

            duration_ms = int(transcript_duration_ms(ctx) or 0)
            report = evaluate_boundary_quality(boundaries, duration_ms=duration_ms)
            if report.get("reject") and bool(segmentation_cfg().get("reject_coarse_fallback", True)):
                boundary_skip_reason = (
                    f"coarse_ideal_cuts_bind n={report.get('segment_count')} "
                    f"coverage={report.get('coverage_ratio')} "
                    f"expected_min≈{report.get('expected_min_segments')}"
                )
                ctx.log(
                    f"ideal_cuts_materialize: skipping boundary bind — {boundary_skip_reason}",
                    level="warning",
                    stage="ideal_cuts_materialize",
                )
                # Provisional seg_* from boundaries_from_snapped_cuts are invalid
                # against the forthcoming full-tape boundaries — strip them and
                # defer the ranking seed until refresh_selection_seed_from_boundaries.
                snapped = strip_provisional_segment_ids(snapped)
                # Drop a prior coarse ideal-cuts contract so boundary_detection runs LLM.
                retract_own_boundaries(ctx)
            else:
                from interview_mux.shared_path_commit import commit_boundaries_doc

                commit_boundaries_doc(
                    ctx,
                    boundaries,
                    stage_key="ideal_cuts_materialize",
                    claim_producer=True,
                )
                wrote_boundaries = True
                if ctx.artifact_exists(BOUNDARIES_REL):
                    saved = ctx.read_json(BOUNDARIES_REL)
                    if isinstance(saved, dict) and saved.get("boundaries"):
                        snapped = map_cuts_onto_existing_boundaries(snapped, saved)
        except Exception as exc:
            if wrote_boundaries:
                ctx.log(
                    f"ideal_cuts_materialize: saved boundaries kept after {exc}",
                    level="warning",
                    stage="ideal_cuts_materialize",
                )
            else:
                # Fail-closed (DEEP-CUTS-01): never publish coarse keep-windows when
                # quality eval itself breaks. Materialize still completes so
                # boundary_detection owns the full-tape map.
                boundary_skip_reason = f"quality_eval_failed:{type(exc).__name__}"
                ctx.log(
                    f"ideal_cuts_materialize: quality check failed ({exc}) — "
                    "skipping boundary bind (boundary_detection owns segments)",
                    level="warning",
                    stage="ideal_cuts_materialize",
                )
                snapped = strip_provisional_segment_ids(snapped)
                retract_own_boundaries(ctx)
    elif ctx.artifact_exists(BOUNDARIES_REL):
        # Seed-ranking path with legacy boundaries already present (rare at this point)
        existing = ctx.read_json(BOUNDARIES_REL)
        if isinstance(existing, dict):
            snapped = map_cuts_onto_existing_boundaries(snapped, existing)

    write_seed = bool(bind_ranking_enabled(conf) and wrote_boundaries and not boundary_skip_reason)
    # Also write seed when mapping onto existing boundaries already attached ids.
    if bind_ranking_enabled(conf) and not write_seed and not boundary_skip_reason:
        if any(
            isinstance(c, dict) and c.get("segment_id")
            for c in (snapped.get("cuts") or [])
        ):
            write_seed = True
    seed = selection_seed_from_snapped(snapped) if write_seed else None
    if write_seed and seed and seed.get("ordered_segment_ids"):
        ctx.write_json(SELECTION_SEED_REL, seed, stage_key="ideal_cuts_materialize")
    elif boundary_skip_reason:
        try:
            (ctx.run_dir / SELECTION_SEED_REL).unlink(missing_ok=True)
        except OSError:
            pass
    elif not write_seed:
        stub = {
            "version": 1,
            "ordered_segment_ids": [],
            "deferred": True,
            "reason": boundary_skip_reason or "bind_demoted",
        }
        ctx.write_json(SELECTION_SEED_REL, stub, stage_key="ideal_cuts_materialize")

    materialized = {
        "version": 1,
        "enabled": True,
        "bind_mode": conf.get("bind_mode"),
        "bind_mode_used": bind_mode_used,
        "wrote_boundaries": wrote_boundaries,
        "wrote_selection_seed": bool(write_seed and seed and seed.get("ordered_segment_ids")),
        "cuts": snapped.get("cuts") or [],
        "snap_warnings": snapped.get("snap_warnings") or [],
        "selection_seed": seed if write_seed else None,
    }
    if boundary_skip_reason:
        materialized["boundary_bind_skipped"] = boundary_skip_reason
        materialized["boundary_skip_reason"] = boundary_skip_reason
    ctx.write_json(MATERIALIZED_REL, materialized, stage_key="ideal_cuts_materialize")
    if not ctx.is_done("ideal_cuts_materialize"):
        heal_or_refuse_mark(ctx, "ideal_cuts_materialize", force=True)
    ctx.log(
        f"ideal_cuts_materialize: cuts={len(snapped.get('cuts') or [])} "
        f"boundaries={wrote_boundaries} seed={bool(write_seed)}",
        level="info",
        stage="ideal_cuts_materialize",
    )


def _overlap_ms(a0: int, a1: int, b0: int, b1: int) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def _cuts_list(cuts_doc: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
    if isinstance(cuts_doc, list):
        return [c for c in cuts_doc if isinstance(c, dict)]
    if not isinstance(cuts_doc, dict):
        return []
    for key in ("cuts", "talking_points"):
        rows = cuts_doc.get(key)
        if isinstance(rows, list):
            return [c for c in rows if isinstance(c, dict)]
    return []


def overlapping_ideal_window(
    *,
    source_start_ms: int,
    source_end_ms: int,
    cuts_doc: dict[str, Any] | list[Any] | None,
    segment_id: str | None = None,
) -> tuple[int, int] | None:
    """Best overlapping ideal-cut / talking-point window for a keeper slab."""
    best: tuple[int, int, int] | None = None  # overlap, start, end
    for cut in _cuts_list(cuts_doc):
        try:
            c0 = int(cut.get("start_ms") or 0)
            c1 = int(cut.get("end_ms") or 0)
        except (TypeError, ValueError):
            continue
        if c1 <= c0:
            continue
        ids = _segment_ids_from_cut(cut)
        ov = _overlap_ms(source_start_ms, source_end_ms, c0, c1)
        if ov <= 0:
            continue
        # Prefer cuts bound to this segment when present.
        bound_bonus = 0
        if segment_id and (
            segment_id in ids or str(cut.get("segment_id") or "") == segment_id
        ):
            bound_bonus = 1_000_000
        score = ov + bound_bonus
        if best is None or score > best[0]:
            best = (score, c0, c1)
    if best is None:
        return None
    return best[1], best[2]


def first_legal_open_start_ms(
    words: list[dict[str, Any]],
    *,
    from_ms: int,
    hard_floor_ms: int = 0,
    hard_ceil_ms: int | None = None,
    max_lookback_ms: int | None = None,
) -> int | None:
    """Walk backward from ``from_ms`` to the nearest legal conceptual open."""
    from interview_mux.gap_vo_prior_context import (
        coerce_word_times,
        is_legal_conceptual_open,
    )

    words = coerce_word_times(words)
    floor = max(0, int(hard_floor_ms))
    if max_lookback_ms is not None:
        floor = max(floor, int(from_ms) - int(max_lookback_ms))
    ceil = int(hard_ceil_ms) if hard_ceil_ms is not None else int(from_ms)
    if ceil <= floor:
        return None
    window = [
        w
        for w in words
        if isinstance(w, dict)
        and floor <= int(w.get("start_ms") or 0) <= int(from_ms)
        and str(w.get("text") or w.get("word") or "").strip()
    ]
    if not window:
        return None
    window.sort(key=lambda w: int(w.get("start_ms") or 0))
    # Nearest earlier legal open (do not jump to the earliest word in the buffer).
    for i in range(len(window) - 1, -1, -1):
        w = window[i]
        cand = int(w.get("start_ms") or 0)
        if cand > ceil:
            continue
        pause: int | None = None
        if i > 0:
            pause = max(
                0,
                cand - int(window[i - 1].get("end_ms") or cand),
            )
        else:
            prev = None
            for x in words:
                if not isinstance(x, dict):
                    continue
                xe = int(x.get("end_ms") or 0)
                if xe <= cand and str(x.get("text") or x.get("word") or "").strip():
                    if prev is None or xe > int(prev.get("end_ms") or 0):
                        prev = x
            if prev is not None:
                pause = max(0, cand - int(prev.get("end_ms") or cand))
        ahead = [
            str(x.get("text") or x.get("word") or "").strip()
            for x in window[i : i + 12]
            if str(x.get("text") or x.get("word") or "").strip()
        ]
        text = " ".join(ahead)
        if is_legal_conceptual_open(
            text, words=words, start_ms=cand, prev_pause_ms=pause
        ):
            return cand
    return None


def last_complete_thought_end_ms(
    words: list[dict[str, Any]],
    *,
    start_ms: int,
    end_ms: int,
    max_lookback_ms: int | None = None,
) -> int | None:
    """Walk backward from ``end_ms`` to the last legal conceptual hinge in-span.

    Span end without a following word is **not** fabricated as a pause — that
    alone does not prove a finished idea.
    """
    from interview_mux.gap_vo_prior_context import (
        coerce_word_times,
        is_legal_conceptual_hinge,
    )

    words = coerce_word_times(words)
    if end_ms <= start_ms + 300:
        return None
    lookback = max_lookback_ms if max_lookback_ms is not None else max(0, end_ms - start_ms)
    window = [
        w
        for w in words
        if isinstance(w, dict)
        and end_ms - lookback <= int(w.get("end_ms") or 0) <= end_ms
        and int(w.get("end_ms") or 0) > start_ms
    ]
    if not window:
        return None
    for i in range(len(window) - 1, -1, -1):
        toks = [
            str(w.get("text") or w.get("word") or "").strip()
            for w in window[: i + 1]
            if str(w.get("text") or w.get("word") or "").strip()
        ]
        if not toks:
            continue
        text = " ".join(toks)
        pause: int | None
        if i + 1 < len(window):
            pause = max(
                0,
                int(window[i + 1].get("start_ms") or 0)
                - int(window[i].get("end_ms") or 0),
            )
        else:
            # No following word *inside the lookback window* — check full word
            # list for a real next pause; never fabricate DEFAULT_PAUSE_SPLIT_MS.
            cand_end = int(window[i].get("end_ms") or 0)
            nxt = next(
                (
                    w
                    for w in words
                    if isinstance(w, dict) and int(w.get("start_ms") or 0) > cand_end
                ),
                None,
            )
            if nxt is not None:
                pause = max(0, int(nxt.get("start_ms") or 0) - cand_end)
            else:
                pause = None
        cand = int(window[i].get("end_ms") or 0)
        if is_legal_conceptual_hinge(
            text, words=words, end_ms=cand, next_pause_ms=pause
        ):
            if cand > start_ms + 300:
                return cand
    return None


def next_legal_hinge_end_ms(
    words: list[dict[str, Any]],
    *,
    from_ms: int,
    max_extend_ms: int,
    hard_cap_ms: int | None = None,
) -> int | None:
    """Extend forward from ``from_ms`` to the next legal conceptual hinge."""
    from interview_mux.gap_vo_prior_context import (
        coerce_word_times,
        is_legal_conceptual_hinge,
    )

    words = coerce_word_times(words)
    cap = from_ms + max(0, int(max_extend_ms))
    if hard_cap_ms is not None:
        cap = min(cap, int(hard_cap_ms))
    if cap <= from_ms:
        return None
    window = [
        w
        for w in words
        if isinstance(w, dict) and from_ms < int(w.get("end_ms") or 0) <= cap
    ]
    if not window:
        return None
    accumulated: list[str] = []
    for i, w in enumerate(window):
        tok = str(w.get("text") or w.get("word") or "").strip()
        bare = tok.lower().strip(".,!?;:\"'")
        prev_bare = accumulated[-1].lower().strip(".,!?;:\"'") if accumulated else ""
        if bare in {"next", "well", "anyway", "however", "meanwhile"} and prev_bare in {"so", "and", "but", ""}:
            break
        if tok:
            accumulated.append(tok)
        if not accumulated:
            continue
        candidate = " ".join(accumulated)
        cand_end = int(w.get("end_ms") or 0)
        pause: int | None = None
        if i + 1 < len(window):
            pause = max(
                0,
                int(window[i + 1].get("start_ms") or 0) - cand_end,
            )
        else:
            nxt = next(
                (
                    x
                    for x in words
                    if isinstance(x, dict) and int(x.get("start_ms") or 0) > cand_end
                ),
                None,
            )
            if nxt is not None:
                pause = max(0, int(nxt.get("start_ms") or 0) - cand_end)
        if is_legal_conceptual_hinge(
            candidate, words=words, end_ms=cand_end, next_pause_ms=pause
        ):
            return cand_end
    return None


def resolve_keeper_air_bounds(
    *,
    source_start_ms: int,
    source_end_ms: int,
    cuts_doc: dict[str, Any] | list[Any] | None = None,
    words: list[dict[str, Any]] | None = None,
    segment_id: str | None = None,
    max_keep_ms: int | None = None,
    min_keep_ms: int = 2500,
    max_extend_ms: int = 30_000,
    next_keeper_start_ms: int | None = None,
    prev_keeper_end_ms: int | None = None,
    never_touch_cap_ms: int | None = None,
    same_story: bool = False,
    meta_out: dict[str, Any] | None = None,
    wav_path: Any | None = None,
) -> tuple[int, int]:
    """Tighten keeper source bounds to a legal conceptual hinge.

    Ideal-window match is optional; boundary trim is not — every keeper with
    words runs the legal-hinge path. Keepers stay disjoint: open never walks
    before ``prev_keeper_end_ms``. Extend does not cross the next keeper
    except to finish an outgoing last word that the turn-cap would snap back.
    ``never_touch_cap_ms`` hard-stops extends before media-IP CTA / never-touch
    tape even when the next keeper sits after that hole.
    ``max_keep_ms`` is accepted and ignored: segment length does not place the cut.
    """
    del max_keep_ms
    from pathlib import Path

    from interview_mux.gap_vo_prior_context import (
        SOURCE_ADJACENT_COMPLETES_MAX_GAP_MS,
        clause_continues_after,
        clause_continues_before,
        coerce_word_times,
        is_legal_conceptual_hinge,
        is_legal_conceptual_open,
        source_adjacent_completes_at,
    )

    words = coerce_word_times(words)

    conf = ideal_cuts_cfg()
    edge_buf = int(conf.get("semantic_edge_buffer_ms") or 30_000)
    acoustic_on = bool(conf.get("acoustic_edge_refine", True))
    acoustic_search = int(conf.get("acoustic_search_ms") or 120)

    orig_start = int(source_start_ms)
    orig_end = int(source_end_ms)
    start = orig_start
    end = orig_end
    meta: dict[str, Any] = {
        "air_bound_reason": "unchanged",
        "before_start_ms": orig_start,
        "before_end_ms": orig_end,
        "ideal_window_id": None,
    }
    if end <= start:
        if meta_out is not None:
            meta_out.update(meta)
        return start, end

    ideal_id: str | None = None
    window = overlapping_ideal_window(
        source_start_ms=start,
        source_end_ms=end,
        cuts_doc=cuts_doc,
        segment_id=segment_id,
    )
    if window is not None:
        w0, w1 = window
        start = max(start, w0)
        end = min(end, w1)
        meta["air_bound_reason"] = "ideal_window_clamp"
        # Best-effort ideal id from overlapping cut.
        for cut in _cuts_list(cuts_doc):
            if not isinstance(cut, dict):
                continue
            try:
                c0 = int(cut.get("start_ms") or 0)
                c1 = int(cut.get("end_ms") or 0)
            except (TypeError, ValueError):
                continue
            if c0 == w0 and c1 == w1:
                ideal_id = str(
                    cut.get("cut_id") or cut.get("talking_point_id") or ""
                ) or None
                break
        meta["ideal_window_id"] = ideal_id
        if end <= start:
            start, end = orig_start, orig_end
            meta["air_bound_reason"] = "ideal_window_rejected"

    # A neighbour bound only applies to a tape neighbour: a "next" keeper that
    # starts before this one, or a "previous" keeper that ends after this one,
    # is an air-order neighbour from a reorder and would empty the keeper
    # (exec_025 seg_021; ISSUES 178).
    if next_keeper_start_ms is not None and int(next_keeper_start_ms) <= orig_start:
        next_keeper_start_ms = None
    if prev_keeper_end_ms is not None and int(prev_keeper_end_ms) + 80 >= orig_end:
        prev_keeper_end_ms = None
    hard_cap = None
    if next_keeper_start_ms is not None:
        hard_cap = int(next_keeper_start_ms)
    if never_touch_cap_ms is not None:
        nt_cap = int(never_touch_cap_ms)
        hard_cap = nt_cap if hard_cap is None else min(hard_cap, nt_cap)
    prev_floor = None
    if prev_keeper_end_ms is not None:
        prev_floor = int(prev_keeper_end_ms) + 80

    # The ideal window is the seed. The open may still walk back 30s when the
    # concept starts earlier than that window.
    open_floor = max(0, start - edge_buf)
    if prev_floor is not None:
        open_floor = max(open_floor, prev_floor)
        if start < prev_floor:
            start = prev_floor
            meta["air_bound_reason"] = "disjoint_prev_floor"

    if words:
        # Start-side: walk back when open is mid-list / mid-clause.
        start_toks = [
            str(w.get("text") or w.get("word") or "").strip()
            for w in words
            if isinstance(w, dict)
            and start <= int(w.get("start_ms") or 0) <= min(end, start + 30_000)
            and str(w.get("text") or w.get("word") or "").strip()
        ]
        start_text = " ".join(start_toks[:16]) if start_toks else ""
        if (
            start_text
            and (
                not is_legal_conceptual_open(
                    start_text, words=words, start_ms=start, prev_pause_ms=None
                )
                or clause_continues_before(words, start)
            )
        ):
            fixed_start = first_legal_open_start_ms(
                words,
                from_ms=start,
                hard_floor_ms=open_floor,
                hard_ceil_ms=end,
            )
            if fixed_start is not None and end - fixed_start >= min_keep_ms:
                start = fixed_start
                meta["air_bound_reason"] = "extend_open_to_legal_hinge"

        # Always snap end to a legal hinge inside the current slab when possible.
        snapped = last_complete_thought_end_ms(words, start_ms=start, end_ms=end)
        if snapped is not None and snapped - start >= min_keep_ms:
            if snapped != end:
                meta["air_bound_reason"] = (
                    "ideal_hinge_snap"
                    if meta["air_bound_reason"] == "ideal_window_clamp"
                    else "conceptual_hinge_trim"
                )
            end = snapped

        # Lookahead: if clause continues after end, extend then retreat.
        end_toks = [
            str(w.get("text") or w.get("word") or "").strip()
            for w in words
            if isinstance(w, dict)
            and start <= int(w.get("end_ms") or 0) <= end
            and str(w.get("text") or w.get("word") or "").strip()
        ]
        end_text = " ".join(end_toks[-16:]) if end_toks else ""
        continues = clause_continues_after(words, end) or (
            end_text
            and not is_legal_conceptual_hinge(
                end_text, words=words, end_ms=end, next_pause_ms=None
            )
        )
        if continues:
            extended = next_legal_hinge_end_ms(
                words,
                from_ms=end,
                max_extend_ms=max(int(max_extend_ms), edge_buf),
                hard_cap_ms=hard_cap,
            )
            if extended is not None and extended - start >= min_keep_ms:
                end = extended
                meta["air_bound_reason"] = "extend_to_legal_hinge"
            elif (
                next_keeper_start_ms is not None
                and 0 < int(next_keeper_start_ms) - end <= 1_000
            ):
                # STT missed the last word: keep through the nearby turn so
                # residual outgoing audio is not snapped back off a hanging tail.
                end = int(next_keeper_start_ms)
                meta["air_bound_reason"] = "outgoing_hanging_to_turn"
            else:
                retreated = last_complete_thought_end_ms(
                    words, start_ms=start, end_ms=max(start + min_keep_ms, end - 200)
                )
                if retreated is not None and retreated - start >= min_keep_ms:
                    from interview_mux.gap_vo_prior_context import end_is_hanging_clause as _hang

                    if not _hang(words, retreated):
                        end = retreated
                        meta["air_bound_reason"] = "retreat_to_legal_hinge"

        from interview_mux.gap_vo_prior_context import investigate_forward_cut

        # The checks above may stop at 4 seconds. This pass reads every word
        # in the next 30 seconds and leaves the cut where this concept ends.
        investigated = investigate_forward_cut(
            words, end, hard_cap_ms=hard_cap
        )
        if (
            investigated != end
            and investigated - start >= min_keep_ms
            and (hard_cap is None or investigated <= int(hard_cap))
        ):
            end = investigated
            meta["air_bound_reason"] = "forward_window_30s"

    owned_end: int | None = None
    last_word_cross_ms = 800
    if words and (hard_cap is not None or next_keeper_start_ms is not None):
        from interview_mux.cut_edge_refine import (
            OUTGOING_LAST_WORD_MAX_CROSS_MS,
            lift_end_for_outgoing_last_word,
            outgoing_last_word_end_ms,
        )
        from interview_mux.gap_vo_prior_context import end_is_hard_hang

        last_word_cross_ms = int(OUTGOING_LAST_WORD_MAX_CROSS_MS)
        owned_end = outgoing_last_word_end_ms(
            words,
            clip_start_ms=start,
            proposed_end_ms=hard_cap if hard_cap is not None else end,
            next_keeper_start_ms=next_keeper_start_ms,
        )
        if owned_end is not None:
            # Reuse lift policy: may extend through a legal hinge instead of
            # freezing on an incomplete tail ("and" before "then").
            lifted, used = lift_end_for_outgoing_last_word(
                end,
                words,
                clip_start_ms=start,
                next_keeper_start_ms=next_keeper_start_ms,
                proposed_end_ms=hard_cap if hard_cap is not None else end,
            )
            if used:
                owned_end = lifted
            elif end_is_hard_hang(words, int(owned_end)):
                owned_end = None

    if hard_cap is not None and end > hard_cap:
        if owned_end is not None and owned_end >= start + min_keep_ms:
            end = owned_end
            meta["air_bound_reason"] = "outgoing_last_word"
        elif meta.get("air_bound_reason") == "outgoing_hanging_to_turn":
            pass
        else:
            end = hard_cap
            if words:
                from interview_mux.gap_vo_prior_context import end_is_hanging_clause

                retreated = last_complete_thought_end_ms(
                    words, start_ms=start, end_ms=end
                )
                if (
                    retreated is not None
                    and retreated - start >= min_keep_ms
                    and not end_is_hanging_clause(words, retreated)
                ):
                    end = retreated
            meta["air_bound_reason"] = "disjoint_cap"

    # Exact word pins + acoustic valley micro-nudge (no large free shift).
    if words or (wav_path and acoustic_on):
        from interview_mux.cut_edge_refine import refine_cut_edges

        path = Path(wav_path) if wav_path else None
        start, end, edge_meta = refine_cut_edges(
            start_ms=start,
            end_ms=end,
            words=words or [],
            wav_path=path if path and path.is_file() else None,
            search_ms=acoustic_search,
            apply_exact_words=bool(words),
            apply_acoustic=acoustic_on,
            pause_midpoint_end=bool(conf.get("pause_midpoint_end", True)),
            pause_midpoint_min_gap_ms=int(conf.get("pause_midpoint_min_gap_ms") or 80),
            pause_midpoint_max_pad_ms=int(conf.get("pause_midpoint_max_pad_ms") or 1000),
        )
        meta["edge_refine"] = edge_meta
        if edge_meta.get("steps"):
            if meta["air_bound_reason"] == "unchanged":
                meta["air_bound_reason"] = "edge_refine"
            else:
                meta["air_bound_reason"] = f"{meta['air_bound_reason']}+edge_refine"

    # Re-assert keeper disjointness after edge refine (acoustic can walk open back).
    # Outgoing last-word ownership wins over turn-cap snap-back when the cut is
    # still at that last word (not an earlier legal hinge).
    if prev_floor is not None and start < prev_floor:
        start = prev_floor
        meta["air_bound_reason"] = f"{meta['air_bound_reason']}+disjoint_prev_floor"
    if prev_floor is not None and start < prev_floor:
        start = prev_floor
        meta["air_bound_reason"] = f"{meta['air_bound_reason']}+disjoint_prev_floor"
    if "outgoing_hanging_to_turn" in str(meta.get("air_bound_reason") or ""):
        if next_keeper_start_ms is not None:
            end = min(end, int(next_keeper_start_ms))
    elif (
        owned_end is not None
        and end < owned_end
        and owned_end - end <= last_word_cross_ms + 200
    ):
        end = owned_end
        if next_keeper_start_ms is not None:
            end = min(end, int(next_keeper_start_ms))
        meta["air_bound_reason"] = f"{meta['air_bound_reason']}+outgoing_last_word"
    elif hard_cap is not None and end > hard_cap:
        if owned_end is not None:
            end = owned_end
            if next_keeper_start_ms is not None:
                end = min(end, int(next_keeper_start_ms))
            meta["air_bound_reason"] = f"{meta['air_bound_reason']}+outgoing_last_word"
        elif "outgoing_hanging_to_turn" in str(meta.get("air_bound_reason") or ""):
            pass
        else:
            end = hard_cap
            meta["air_bound_reason"] = f"{meta['air_bound_reason']}+disjoint_cap"
    if end < start + min_keep_ms and hard_cap is not None and hard_cap > start:
        # Prefer a short keep over reverting into an overlapping slab.
        end = min(int(hard_cap), max(end, start + min_keep_ms))

    # Absolute: never air media-IP CTA / never-touch tape via hinge or last-word extend.
    if never_touch_cap_ms is not None and end > int(never_touch_cap_ms):
        end = int(never_touch_cap_ms)
        meta["air_bound_reason"] = f"{meta['air_bound_reason']}+never_touch_cap"

    # Incomplete-seam preserve: if raising start would drop a prefix that finishes
    # the previous tape clause ("provision" → "called LDT"), refuse the raise and
    # keep the prefix on this keeper. Order-lock ensures A airs before B so the
    # completion is heard once; no dual source ownership.
    if words and start > orig_start:
        if source_adjacent_completes_at(
            words,
            orig_start,
            max_gap_ms=SOURCE_ADJACENT_COMPLETES_MAX_GAP_MS,
        ):
            start = orig_start
            meta["air_bound_reason"] = (
                f"{meta['air_bound_reason']}+incomplete_seam_preserve"
            )
            # Ideal window may have clamped end into a distant hinge; if keeping
            # the open empties the legal span, restore original end too.
            if end <= start:
                end = orig_end

    meta["after_start_ms"] = start
    meta["after_end_ms"] = end
    if end - start < min_keep_ms:
        # Prefer a truncated keep that stays out of never-touch over reverting into CTA.
        if never_touch_cap_ms is not None and end <= int(never_touch_cap_ms) and end > start:
            meta["air_bound_reason"] = f"{meta['air_bound_reason']}+never_touch_short_keep"
            if meta_out is not None:
                meta_out.update(meta)
            return start, end
        meta["air_bound_reason"] = "min_keep_revert"
        meta["after_start_ms"] = orig_start
        meta["after_end_ms"] = orig_end
        if meta_out is not None:
            meta_out.update(meta)
        # Still refuse CTA bleed if the original slab invaded never-touch.
        if never_touch_cap_ms is not None and orig_end > int(never_touch_cap_ms):
            safe_end = max(orig_start + 1, min(orig_end, int(never_touch_cap_ms)))
            meta["air_bound_reason"] = "min_keep_revert+never_touch_cap"
            meta["after_end_ms"] = safe_end
            if meta_out is not None:
                meta_out.update(meta)
            return orig_start, safe_end
        if next_keeper_start_ms is not None and orig_end > int(next_keeper_start_ms):
            safe_end = int(next_keeper_start_ms)
            if safe_end > orig_start:
                meta["air_bound_reason"] = "min_keep_revert+disjoint_cap"
                meta["after_end_ms"] = safe_end
                if meta_out is not None:
                    meta_out.update(meta)
                return orig_start, safe_end
            return start, end
        return orig_start, orig_end
    if meta_out is not None:
        meta_out.update(meta)
    return start, end


def load_air_bound_inputs(ctx: RunContext) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Load ideal-cut / materialized windows and transcript words for EDL air bounds."""
    cuts: dict[str, Any] | None = None
    for rel in (MATERIALIZED_REL, IDEAL_CUTS_REL, TALKING_POINTS_REL):
        if not ctx.artifact_exists(rel):
            continue
        doc = ctx.read_json(rel)
        if isinstance(doc, dict) and _cuts_list(doc):
            cuts = doc
            break
    words: list[dict[str, Any]] = []
    if ctx.artifact_exists("transcript/full.json"):
        tr = ctx.read_json("transcript/full.json")
        if isinstance(tr, dict):
            words = [w for w in (tr.get("words") or []) if isinstance(w, dict)]
    return cuts, words

