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
        "word_snap_margin_ms": 40,
        "word_snap_max_shift_ms": 600,
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
    from interview_mux.audio_timeline import snap_cut_to_word_boundary

    snapped = snap_cut_to_word_boundary(
        int(ms),
        words,
        margin_ms=margin_ms,
        max_shift_ms=max_shift_ms,
    )
    if prefer == "start":
        # Prefer nearby word starts for open cuts.
        best = snapped
        best_dist = max_shift_ms + 1
        for word in words:
            boundary = int(word.get("start_ms") or 0)
            if boundary <= 0:
                continue
            dist = abs(boundary - int(ms))
            if dist <= max_shift_ms and dist < best_dist:
                best = max(0, boundary)
                best_dist = dist
        return best
    return max(0, snapped)


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
) -> dict[str, Any]:
    """Snap proposed cut windows to word boundaries and clamp durations."""
    conf = ideal_cuts_cfg(cfg)
    words = _word_list(transcript)
    min_ms = int(conf.get("min_cut_ms") or 2500)
    max_ms = int(conf.get("max_cut_ms") or 180_000)
    margin = int(conf.get("word_snap_margin_ms") or 40)
    max_shift = int(conf.get("word_snap_max_shift_ms") or 600)

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
        start = _snap_ms(start, words, prefer="start", margin_ms=margin, max_shift_ms=max_shift)
        end = _snap_ms(end, words, prefer="end", margin_ms=margin, max_shift_ms=max_shift)
        if end <= start:
            end = start + min_ms
        dur = end - start
        if dur < min_ms:
            end = start + min_ms
            warnings.append(f"cut[{index}] padded to min_cut_ms")
        elif dur > max_ms:
            end = start + max_ms
            warnings.append(f"cut[{index}] clamped to max_cut_ms")
        priority = str(cut.get("priority") or "should_keep").strip().lower()
        if priority not in {"must_keep", "should_keep", "optional"}:
            priority = "should_keep"
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
        return {
            "order_authority": "ranking",
            "ordered_segment_ids": sel,
            "bind_reason": "ideal_cuts_seed_misses_kept",
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
    snapped = snap_ideal_cuts(
        cuts_doc if isinstance(cuts_doc, dict) else {},
        transcript if isinstance(transcript, dict) else {},
        cfg=conf,
    )

    wrote_boundaries = False
    boundary_skip_reason = None
    if bind_boundaries_enabled(conf):
        if not snapped.get("cuts"):
            raise RuntimeError(
                "ideal_cuts_materialize: bind_mode requires boundaries but no valid cuts after snap"
            )
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
        "wrote_boundaries": wrote_boundaries,
        "wrote_selection_seed": bool(write_seed and seed and seed.get("ordered_segment_ids")),
        "cuts": snapped.get("cuts") or [],
        "snap_warnings": snapped.get("snap_warnings") or [],
        "selection_seed": seed if write_seed else None,
    }
    if boundary_skip_reason:
        materialized["boundary_bind_skipped"] = boundary_skip_reason
    ctx.write_json(MATERIALIZED_REL, materialized, stage_key="ideal_cuts_materialize")
    if not ctx.is_done("ideal_cuts_materialize"):
        ctx.mark_done("ideal_cuts_materialize", force=True)
    ctx.log(
        f"ideal_cuts_materialize: cuts={len(snapped.get('cuts') or [])} "
        f"boundaries={wrote_boundaries} seed={bool(write_seed)}",
        level="info",
        stage="ideal_cuts_materialize",
    )
