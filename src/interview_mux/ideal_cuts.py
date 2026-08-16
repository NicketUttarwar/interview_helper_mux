"""Talking-points-first ideal cuts: snap, materialize boundaries, ranking seed.

Holistic flow (when ``analysis.ideal_cuts.enable``):
  content_context → talking_points_compose → ideal_cuts_propose
  → ideal_cuts_materialize → (optional boundary bind) → classification / ranking
"""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

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
        "max_cut_ms": 180_000,
        # Tight word snap only — large free shifts steal list items / leave hangs.
        "word_snap_margin_ms": 0,
        "word_snap_max_shift_ms": 150,
        "semantic_edge_buffer_ms": 5_000,
        "acoustic_edge_refine": True,
        "acoustic_search_ms": 120,
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
    counts: dict[str, int] = {}
    for word in words:
        try:
            w0 = int(float(word.get("start_ms") or 0))
            w1 = int(float(word.get("end_ms") or w0))
        except (TypeError, ValueError):
            continue
        if w1 < start_ms or w0 > end_ms:
            continue
        sid = str(word.get("speaker_id") or word.get("speaker") or "").strip()
        if not sid:
            continue
        counts[sid] = counts.get(sid, 0) + max(1, w1 - w0)
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]


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
    words = _word_list(transcript)
    min_ms = int(conf.get("min_cut_ms") or 2500)
    max_ms = int(conf.get("max_cut_ms") or 180_000)
    margin = int(conf.get("word_snap_margin_ms") or 0)
    max_shift = int(conf.get("word_snap_max_shift_ms") or 150)
    edge_buf = int(conf.get("semantic_edge_buffer_ms") or 5_000)
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
        elif dur > max_ms:
            end = start + max_ms
            warnings.append(f"cut[{index}] clamped to max_cut_ms")
        from interview_mux.gap_vo_prior_context import (
            clause_continues_after,
            clause_continues_before,
            is_legal_conceptual_hinge,
            is_legal_conceptual_open,
        )

        # Start-side: walk back when the open drops mid-list / mid-clause.
        start_text = _span_text(words, start, min(end, start + 8_000), max_chars=400)
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

        # Hard-reject / auto-fix hanging-setup ends after snap.
        end_text = _span_text(words, max(start, end - 8_000), end, max_chars=400)
        legal = is_legal_conceptual_hinge(
            end_text, words=words, end_ms=end, next_pause_ms=None
        )
        if not legal or clause_continues_after(words, end):
            fixed = last_complete_thought_end_ms(
                words, start_ms=start, end_ms=end
            )
            if fixed is None:
                fixed = next_legal_hinge_end_ms(
                    words, from_ms=end, max_extend_ms=max(edge_buf, 12_000)
                )
            if fixed is not None and fixed - start >= min_ms:
                end = fixed
                warnings.append(
                    f"cut[{index}] auto-fixed illegal hang end → {end}"
                )
            else:
                warnings.append(
                    f"cut[{index}] rejected: illegal hanging / unfinished end"
                )
                continue

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
            "legal_conceptual_hinge": True,
            "legal_conceptual_open": True,
            "edge_refine": edge_meta,
            "anchor_resolve": {
                "start": start_meta,
                "end": end_meta,
                "window_check": window_check,
            },
        }
        snapped.append(row)

    # Sort + resolve overlaps (keep higher priority, then longer)
    rank = {"must_keep": 0, "should_keep": 1, "optional": 2}
    snapped.sort(
        key=lambda r: (
            rank.get(str(r.get("priority")), 9),
            int(r.get("start_ms") or 0),
            -int(r.get("duration_ms") or 0),
        )
    )
    resolved: list[dict[str, Any]] = []
    for row in snapped:
        if not resolved:
            resolved.append(row)
            continue
        prev = resolved[-1]
        if int(row["start_ms"]) < int(prev["end_ms"]):
            # Overlap: keep prev if better/equal priority, else replace end or drop
            if rank.get(str(row.get("priority")), 9) >= rank.get(str(prev.get("priority")), 9):
                warnings.append(
                    f"dropped overlapping cut {row.get('cut_id') or row.get('talking_point_id')}"
                )
                continue
            resolved[-1] = row
            warnings.append(
                f"replaced overlapping cut with higher-priority {row.get('cut_id')}"
            )
            continue
        resolved.append(row)
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
        else:
            row["speaker_id"] = "spk_0"
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
        mapped.append(row)
    out = dict(snapped)
    out["cuts"] = mapped
    return out


def boundaries_already_from_ideal_cuts(ctx: RunContext) -> bool:
    if not ctx.artifact_exists(BOUNDARIES_REL):
        return False
    doc = ctx.read_json(BOUNDARIES_REL)
    if not isinstance(doc, dict):
        return False
    meta = doc.get("_meta") if isinstance(doc.get("_meta"), dict) else {}
    contract = meta.get("segment_contract") if isinstance(meta, dict) else {}
    if not isinstance(contract, dict):
        return False
    return (
        str(contract.get("publisher_stage") or "") == "ideal_cuts_materialize"
        and bool(contract.get("timeline_valid"))
        and int(contract.get("segment_count") or 0) > 0
    )


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
        ctx.mark_done("ideal_cuts_materialize", force=True)
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
        boundaries = boundaries_from_snapped_cuts(snapped)
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
                if boundaries_already_from_ideal_cuts(ctx):
                    try:
                        (ctx.run_dir / BOUNDARIES_REL).unlink(missing_ok=True)
                    except OSError:
                        pass
            else:
                ctx.write_json(BOUNDARIES_REL, boundaries, stage_key="ideal_cuts_materialize")
                wrote_boundaries = True
        except Exception as exc:
            # Fail open toward writing when quality eval itself breaks.
            ctx.log(
                f"ideal_cuts_materialize: quality check failed ({exc}) — writing boundaries",
                level="warning",
                stage="ideal_cuts_materialize",
            )
            ctx.write_json(BOUNDARIES_REL, boundaries, stage_key="ideal_cuts_materialize")
            wrote_boundaries = True
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
        ctx.mark_done("ideal_cuts_materialize", force=True)
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
    from interview_mux.gap_vo_prior_context import is_legal_conceptual_open

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
    from interview_mux.gap_vo_prior_context import is_legal_conceptual_hinge

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
        last = toks[-1]
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
        if last[-1:] in ".!?…" or is_legal_conceptual_hinge(
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
    from interview_mux.gap_vo_prior_context import is_legal_conceptual_hinge

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
    max_extend_ms: int = 12_000,
    next_keeper_start_ms: int | None = None,
    prev_keeper_end_ms: int | None = None,
    meta_out: dict[str, Any] | None = None,
    wav_path: Any | None = None,
) -> tuple[int, int]:
    """Tighten keeper source bounds to a legal conceptual hinge.

    Ideal-window match is optional; boundary trim is not — every keeper with
    words runs the legal-hinge path. Keepers stay disjoint: extend never
    crosses ``next_keeper_start_ms``, and open never walks before
    ``prev_keeper_end_ms``.
    """
    from pathlib import Path

    from interview_mux.gap_vo_prior_context import (
        clause_continues_after,
        clause_continues_before,
        is_legal_conceptual_hinge,
        is_legal_conceptual_open,
    )

    conf = ideal_cuts_cfg()
    edge_buf = int(conf.get("semantic_edge_buffer_ms") or 5_000)
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

    hard_cap = None
    if next_keeper_start_ms is not None:
        hard_cap = int(next_keeper_start_ms) - 80
    prev_floor = None
    if prev_keeper_end_ms is not None:
        prev_floor = int(prev_keeper_end_ms) + 80

    # After ideal-window clamp, do not walk the open earlier than the clamped start.
    open_floor = (
        start
        if meta.get("air_bound_reason") == "ideal_window_clamp"
        else max(0, start - edge_buf)
    )
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
            and start <= int(w.get("start_ms") or 0) <= min(end, start + 8_000)
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
                hard_cap_ms=hard_cap if hard_cap is not None else (
                    start + int(max_keep_ms) if max_keep_ms else None
                ),
            )
            if extended is not None and extended - start >= min_keep_ms:
                end = extended
                meta["air_bound_reason"] = "extend_to_legal_hinge"
            else:
                retreated = last_complete_thought_end_ms(
                    words, start_ms=start, end_ms=max(start + min_keep_ms, end - 200)
                )
                if retreated is not None and retreated - start >= min_keep_ms:
                    end = retreated
                    meta["air_bound_reason"] = "retreat_to_legal_hinge"

    span = end - start
    budget = int(max_keep_ms) if max_keep_ms is not None else None
    if budget is not None and span > budget and words:
        target_end = start + budget
        snapped = last_complete_thought_end_ms(
            words,
            start_ms=start,
            end_ms=min(end, target_end + 2_000),
            max_lookback_ms=max(budget, 12_000),
        )
        if snapped is not None and snapped - start >= min_keep_ms:
            if snapped <= start + budget:
                end = snapped
            else:
                earlier = last_complete_thought_end_ms(
                    words, start_ms=start, end_ms=start + budget
                )
                if earlier is not None and earlier - start >= min_keep_ms:
                    end = earlier
            meta["air_bound_reason"] = "budget_hinge_trim"
        elif snapped is not None and snapped - start >= min_keep_ms:
            end = snapped
            meta["air_bound_reason"] = "budget_hinge_trim"

    if hard_cap is not None and end > hard_cap:
        end = hard_cap
        if words:
            retreated = last_complete_thought_end_ms(
                words, start_ms=start, end_ms=end
            )
            if retreated is not None and retreated - start >= min_keep_ms:
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
        )
        meta["edge_refine"] = edge_meta
        if edge_meta.get("steps"):
            if meta["air_bound_reason"] == "unchanged":
                meta["air_bound_reason"] = "edge_refine"
            else:
                meta["air_bound_reason"] = f"{meta['air_bound_reason']}+edge_refine"

    # Re-assert keeper disjointness after edge refine (acoustic can walk open back).
    if prev_floor is not None and start < prev_floor:
        start = prev_floor
        meta["air_bound_reason"] = f"{meta['air_bound_reason']}+disjoint_prev_floor"
    if hard_cap is not None and end > hard_cap:
        end = hard_cap
        meta["air_bound_reason"] = f"{meta['air_bound_reason']}+disjoint_cap"
    if end < start + min_keep_ms and hard_cap is not None and hard_cap > start:
        # Prefer a short keep over reverting into an overlapping slab.
        end = min(hard_cap, max(end, start + min_keep_ms))

    meta["after_start_ms"] = start
    meta["after_end_ms"] = end
    if end - start < min_keep_ms:
        meta["air_bound_reason"] = "min_keep_revert"
        meta["after_start_ms"] = orig_start
        meta["after_end_ms"] = orig_end
        if meta_out is not None:
            meta_out.update(meta)
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

