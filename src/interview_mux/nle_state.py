from __future__ import annotations

from typing import Any

from interview_mux.file_store import read_json
from interview_mux.run_context import RunContext

NLE_REL = "segments/nle_edits.json"


def default_nle() -> dict[str, Any]:
    return {
        "playhead_ms": 0,
        "zoom": 1.0,
        "sequence_order": [],
        "segment_overrides": {},
        "markers": [],
    }


def load_nle(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists(NLE_REL):
        return default_nle()
    data = read_json(ctx.read_path(NLE_REL))
    base = default_nle()
    base.update(data)
    return base


def _words_text_before_ms(
    words: list[dict[str, Any]], end_ms: int, *, lookback_ms: int = 4000
) -> str:
    start_ms = max(0, end_ms - lookback_ms)
    parts: list[str] = []
    for w in words:
        if not isinstance(w, dict):
            continue
        ws = int(w.get("start_ms") or 0)
        we = int(w.get("end_ms") or 0)
        if we <= start_ms or ws >= end_ms:
            continue
        t = str(w.get("text") or w.get("word") or "").strip()
        if t:
            parts.append(t)
    return " ".join(parts)


def incomplete_trim_ends(ctx: RunContext, data: dict[str, Any]) -> list[str]:
    """Segment ids whose NLE trim end lands mid-clause per ``ends_complete_thought``.

    Best-effort: returns ``[]`` when the transcript is unavailable so a missing
    upstream artifact never blocks a save. Only overrides carrying an explicit
    ``end_ms`` (an operator trim) are checked — full-segment excludes/reorders
    are not clause boundaries.
    """
    overrides = data.get("segment_overrides") or {}
    if not overrides or not ctx.artifact_exists("transcript/full.json"):
        return []
    try:
        from interview_mux.gap_vo_prior_context import ends_complete_thought

        transcript = ctx.read_json("transcript/full.json")
    except Exception:
        return []
    words = [w for w in (transcript.get("words") or []) if isinstance(w, dict)]
    if not words:
        return []
    flagged: list[str] = []
    for seg_id, ov in overrides.items():
        if not isinstance(ov, dict) or ov.get("excluded") or "end_ms" not in ov:
            continue
        try:
            end_ms = int(ov["end_ms"])
        except (TypeError, ValueError):
            continue
        text = _words_text_before_ms(words, end_ms)
        if text and not ends_complete_thought(text):
            flagged.append(str(seg_id))
    return sorted(flagged)


def save_nle(ctx: RunContext, data: dict[str, Any]) -> None:
    from interview_mux.config import merged_config
    from interview_mux.prompt_validation import validate_nle_edits

    errors = validate_nle_edits(data)
    if errors:
        strict = bool((merged_config().get("nle_edits") or {}).get("strict"))
        if strict:
            raise ValueError(f"nle_edits schema invalid: {'; '.join(errors[:4])}")
        ctx.log(f"nle_edits schema warnings: {errors[:2]}", level="warning", stage="full_master_ranking")

    incomplete = incomplete_trim_ends(ctx, data)
    if incomplete:
        nle_cfg = merged_config().get("nle_edits") or {}
        block = bool(nle_cfg.get("block_incomplete_ends"))
        msg = (
            "NLE trim end lands mid-clause (incomplete thought) for segment(s): "
            f"{', '.join(incomplete[:6])}"
        )
        if block:
            raise ValueError(msg)
        ctx.log(msg, level="warning", stage="full_master_ranking", detail={"segment_ids": incomplete})

    ctx.write_json(NLE_REL, data, stage_key="full_master_ranking")
    from interview_mux.operator_snapshots import persist_operator_nle

    persist_operator_nle(ctx, source="nle_save")


MIN_TRIM_DURATION_MS = 300


def nle_has_operator_edits(nle: dict[str, Any]) -> bool:
    overrides = nle.get("segment_overrides") or {}
    order = nle.get("sequence_order") or []
    if order:
        return True
    for ov in overrides.values():
        if ov.get("excluded") or ov.get("mark_redo"):
            return True
        if "start_ms" in ov or "end_ms" in ov or ov.get("split_into"):
            return True
    return False


def nle_edit_categories(nle: dict[str, Any]) -> dict[str, bool]:
    """Classify NLE edits for apply-cascade routing."""
    overrides = nle.get("segment_overrides") or {}
    order = nle.get("sequence_order") or []
    structural = bool(order)
    has_trim = False
    for ov in overrides.values():
        if ov.get("excluded") or ov.get("mark_redo") or ov.get("split_into"):
            structural = True
        if "start_ms" in ov or "end_ms" in ov:
            has_trim = True
    return {
        "structural": structural,
        "trim_only": has_trim and not structural,
        "has_any": nle_has_operator_edits(nle),
    }


def manifest_segment_bounds(
    ctx: RunContext,
    segment_id: str,
) -> tuple[int, int]:
    manifest = ctx.read_json("segments/manifest.json")
    for seg in manifest.get("segments") or []:
        if seg.get("segment_id") == segment_id:
            return int(seg["start_ms"]), int(seg["end_ms"])
    nle = load_nle(ctx)
    ov = (nle.get("segment_overrides") or {}).get(segment_id) or {}
    if "start_ms" in ov and "end_ms" in ov:
        return int(ov["start_ms"]), int(ov["end_ms"])
    raise ValueError(f"Segment not found: {segment_id}")


def clamp_trim_bounds(
    *,
    manifest_start: int,
    manifest_end: int,
    start_ms: int,
    end_ms: int,
    min_duration_ms: int = MIN_TRIM_DURATION_MS,
) -> tuple[int, int]:
    start = max(manifest_start, min(start_ms, manifest_end - min_duration_ms))
    end = min(manifest_end, max(end_ms, manifest_start + min_duration_ms))
    if end - start < min_duration_ms:
        raise ValueError(f"Trim must be at least {min_duration_ms}ms.")
    return start, end


def snap_boundary_for_segment(
    ctx: RunContext,
    *,
    segment_id: str,
    ms: int,
    edge: str,
) -> int:
    from interview_mux.audio_timeline import snap_cut_to_word_boundary
    from interview_mux.config import merged_config

    manifest_start, manifest_end = manifest_segment_bounds(ctx, segment_id)
    if not ctx.artifact_exists("transcript/full.json"):
        return ms
    transcript = ctx.read_json("transcript/full.json")
    words = [
        w
        for w in (transcript.get("words") or [])
        if isinstance(w, dict)
        and int(w.get("end_ms", 0)) > manifest_start
        and int(w.get("start_ms", 0)) < manifest_end
    ]
    mix_cfg = (merged_config().get("mix") or {})
    margin = int(mix_cfg.get("word_boundary_margin_ms", 50))
    max_shift = int(mix_cfg.get("word_boundary_max_shift_ms", 400))
    snapped = snap_cut_to_word_boundary(ms, words, margin_ms=margin, max_shift_ms=max_shift)
    if edge == "start":
        snapped = max(manifest_start, min(snapped, manifest_end - MIN_TRIM_DURATION_MS))
    else:
        snapped = max(manifest_start + MIN_TRIM_DURATION_MS, min(snapped, manifest_end))
    return snapped


def _insert_index_by_start(
    ordered: list[str],
    sid: str,
    segments_by_id: dict[str, dict[str, Any]] | None,
) -> int:
    if not segments_by_id:
        return len(ordered)
    try:
        start = int((segments_by_id.get(sid) or {}).get("start_ms") or 0)
    except (TypeError, ValueError):
        return len(ordered)
    for i, other in enumerate(ordered):
        try:
            other_start = int((segments_by_id.get(other) or {}).get("start_ms") or 0)
        except (TypeError, ValueError):
            continue
        if start < other_start:
            return i
    return len(ordered)


def _excluded_entries(selection: dict[str, Any]) -> list[dict[str, str]]:
    raw = selection.get("excluded_segment_ids") or []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            sid, reason = item, "operator"
        elif isinstance(item, dict):
            sid = item.get("segment_id", "")
            reason = item.get("reason", "operator")
        else:
            continue
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append({"segment_id": sid, "reason": reason})
    return out


def apply_nle_to_selection(
    selection: dict[str, Any],
    nle: dict[str, Any],
    *,
    segments_by_id: dict[str, dict[str, Any]] | None = None,
    ctx: RunContext | None = None,
) -> dict[str, Any]:
    """Merge operator NLE exclude/split/reorder into a selection artifact."""
    if not nle_has_operator_edits(nle):
        return selection

    overrides = nle.get("segment_overrides") or {}
    order = list(nle.get("sequence_order") or [])
    result = dict(selection)
    excluded = _excluded_entries(result)
    excluded_ids = {e["segment_id"] for e in excluded}

    if ctx is not None:
        try:
            from interview_mux.media_ip_cta import never_touch_segment_ids

            for sid in never_touch_segment_ids(ctx):
                if sid not in excluded_ids:
                    excluded.append({"segment_id": sid, "reason": "never_touch_cta"})
                    excluded_ids.add(sid)
        except Exception:
            pass

    for seg_id, ov in overrides.items():
        if not ov.get("excluded"):
            continue
        if seg_id not in excluded_ids:
            excluded.append({"segment_id": seg_id, "reason": "nle_operator"})
            excluded_ids.add(seg_id)

    # App auto arrangement is the base; NLE overlays user-touched moves only.
    base_order = [str(s) for s in (result.get("ordered_segment_ids") or []) if s]
    for sid in excluded_ids:
        while sid in base_order:
            base_order.remove(sid)

    operator_moved = [
        str(s)
        for s in order
        if s
        and s not in excluded_ids
        and not (overrides.get(s) or {}).get("excluded")
        and (segments_by_id is None or s in segments_by_id or s in overrides)
    ]

    # ``sequence_order`` is the operator-touched *subset* (tests use
    # ``["seg_c", "seg_a"]``). A long auto-mirrored spine that covers every keep
    # (often with extras) must not lock the whole ranking order
    # (exec_13177: 018↔014 / 059↔053 → edl_narrative_qc thrash). Exclude/split
    # overlays still apply. Short full-cover lists (operator reordered all
    # remaining keeps) still honor sequence_order.
    if operator_moved and base_order:
        base_set = set(base_order)
        moved_in_base = [s for s in operator_moved if s in base_set]
        full_cover = (
            len(moved_in_base) >= len(base_order)
            and base_set.issubset(set(moved_in_base))
        )
        long_dump = len(order) >= max(len(base_order) + 1, int(len(base_order) * 1.25))
        if full_cover and long_dump:
            operator_moved = []

    if operator_moved:
        # Overlay: keep app relative order for untouched ids; splice operator
        # sequence as an ordered block at the first operator-touched index in base,
        # or append block positionally by walking operator list as locks.
        locked = [s for s in operator_moved if s not in excluded_ids]
        locked_set = set(locked)
        untouched = [s for s in base_order if s not in locked_set and s not in excluded_ids]
        # Place locked ids in operator order; fill gaps with untouched in app order.
        # Strategy: start from untouched app spine; insert each locked id at the
        # index of its nearest preceding base neighbor that remains, else at end.
        merged: list[str] = list(untouched)
        for sid in locked:
            if sid in merged:
                continue
            # Prefer position after previous locked peer if that peer is present
            prev_locked = None
            for cand in locked:
                if cand == sid:
                    break
                prev_locked = cand
            if prev_locked and prev_locked in merged:
                merged.insert(merged.index(prev_locked) + 1, sid)
                continue
            # Else: position relative to original base neighbors
            if sid in base_order:
                bi = base_order.index(sid)
                # find nearest earlier base id still in merged
                placed = False
                for j in range(bi - 1, -1, -1):
                    neighbor = base_order[j]
                    if neighbor in merged:
                        merged.insert(merged.index(neighbor) + 1, sid)
                        placed = True
                        break
                if not placed:
                    merged.insert(0, sid)
            else:
                # Split child / new id — after parent if present, else end
                parent = str((overrides.get(sid) or {}).get("parent_id") or "")
                if parent and parent in merged:
                    merged.insert(merged.index(parent) + 1, sid)
                else:
                    merged.append(sid)
        ordered = merged
    else:
        ordered = [s for s in base_order if s not in excluded_ids]

    # Parent splits: drop the parent and offer keepable children even when the
    # parent never made the air order (ranking saw only the mixed parent).
    for seg_id, ov in overrides.items():
        children = [str(c) for c in (ov.get("split_into") or []) if c]
        if not children:
            continue
        keep_kids = [c for c in children if c not in excluded_ids]
        if not keep_kids:
            if seg_id in ordered and any(c in ordered for c in children):
                while seg_id in ordered:
                    ordered.remove(seg_id)
            continue
        if seg_id in ordered:
            insert_at = ordered.index(seg_id)
            while seg_id in ordered:
                ordered.remove(seg_id)
        else:
            insert_at = _insert_index_by_start(ordered, keep_kids[0], segments_by_id)
        offset = 0
        for child in keep_kids:
            if child in ordered:
                continue
            ordered.insert(min(insert_at + offset, len(ordered)), child)
            offset += 1

    seen_order: set[str] = set()
    deduped: list[str] = []
    for sid in ordered:
        if sid in seen_order or sid in excluded_ids:
            continue
        seen_order.add(sid)
        deduped.append(sid)

    result["ordered_segment_ids"] = deduped
    result["excluded_segment_ids"] = excluded
    result["nle_applied"] = True
    result["nle_merge"] = {
        "mode": "app_base_plus_operator_overlay",
        "operator_moved_ids": operator_moved,
        "excluded_ids": sorted(excluded_ids),
    }
    return result


def segments_by_id_with_nle(ctx: RunContext) -> dict[str, dict[str, Any]]:
    manifest = ctx.read_json("segments/manifest.json")
    nle = load_nle(ctx)
    applied = apply_segments_with_nle(manifest.get("segments") or [], nle)
    out: dict[str, dict[str, Any]] = {}
    for seg in applied:
        sid = seg.get("segment_id")
        if not sid:
            continue
        clean = {k: v for k, v in seg.items() if not str(k).startswith("_")}
        out[sid] = clean
    return out


def apply_segments_with_nle(segments: list[dict[str, Any]], nle: dict[str, Any]) -> list[dict[str, Any]]:
    overrides = nle.get("segment_overrides") or {}
    order = nle.get("sequence_order") or []
    by_id = {s["segment_id"]: dict(s) for s in segments if s.get("segment_id")}

    # Synthetic segments from splits / NLE-only ids
    for seg_id, ov in overrides.items():
        if seg_id in by_id:
            continue
        if "start_ms" in ov and "end_ms" in ov:
            parent = by_id.get(ov.get("parent_id", ""), {})
            by_id[seg_id] = {
                "segment_id": seg_id,
                "start_ms": int(ov["start_ms"]),
                "end_ms": int(ov["end_ms"]),
                "speaker_id": parent.get("speaker_id", "unknown"),
                "speaker_role": parent.get("speaker_role", "unknown"),
                "type": parent.get("type", "interviewee_answer"),
                "text": ov.get("label") or parent.get("text", "")[:80],
            }

    for seg_id, ov in overrides.items():
        if seg_id not in by_id:
            continue
        seg = by_id[seg_id]
        if ov.get("excluded"):
            seg["_excluded"] = True
        if ov.get("mark_redo"):
            seg["_mark_redo"] = True
        if "start_ms" in ov:
            seg["start_ms"] = int(ov["start_ms"])
        if "end_ms" in ov:
            seg["end_ms"] = int(ov["end_ms"])
        if ov.get("label"):
            seg["_nle_label"] = ov["label"]

    if order:
        ordered = [by_id[sid] for sid in order if sid in by_id and not by_id[sid].get("_excluded")]
        rest = [s for sid, s in by_id.items() if sid not in order and not s.get("_excluded")]
        return ordered + rest
    return [s for s in by_id.values() if not s.get("_excluded")]


def _child_suffix(index: int) -> str:
    """0 -> a, 25 -> z, 26 -> aa (vernacular-style)."""
    if index < 0:
        raise ValueError("index must be >= 0")
    n = index
    chars: list[str] = []
    while True:
        chars.append(chr(ord("a") + (n % 26)))
        n = n // 26 - 1
        if n < 0:
            break
    return "".join(reversed(chars))


def _child_span_text(ctx: RunContext, start_ms: int, end_ms: int) -> str:
    for rel in (
        "transcript/full.json",
        "operator/transcript_corrected.json",
        "ingest/transcript.json",
    ):
        if not ctx.artifact_exists(rel):
            continue
        try:
            tr = ctx.read_json(rel)
        except Exception:
            continue
        words = tr.get("words") if isinstance(tr, dict) else None
        if not isinstance(words, list):
            continue
        parts = [
            str(w.get("text") or w.get("word") or "").strip()
            for w in words
            if isinstance(w, dict)
            and int(w.get("end_ms") or 0) > start_ms
            and int(w.get("start_ms") or 0) < end_ms
        ]
        text = " ".join(p for p in parts if p).strip()
        if text:
            return text
    return ""


def materialize_split_children_into_manifest(
    ctx: RunContext,
    parent_id: str,
    child_ids: list[str],
    *,
    stage_key: str | None = None,
    mutation_class: str | None = None,
) -> list[str]:
    """Persist NLE/CTA split children as first-class ``segments/manifest.json`` rows.

    Ranking, shape, repair, and duration all treat the manifest as the candidate
    universe. Children that exist only as NLE overrides get orphan-dropped.
    """
    if not parent_id or not child_ids or not ctx.artifact_exists("segments/manifest.json"):
        return []
    try:
        from interview_mux.seat_authority import hard_freeze_active

        if hard_freeze_active(ctx):
            # Under hard freeze: skip inventing new rows; existing orphans are
            # covered into excluded by ``cover_ranking_manifest_membership``.
            return []
    except Exception:
        pass
    man = ctx.read_json("segments/manifest.json")
    if not isinstance(man, dict):
        return []
    segs = [s for s in (man.get("segments") or []) if isinstance(s, dict)]
    by_id = {str(s.get("segment_id") or ""): s for s in segs if s.get("segment_id")}
    parent = by_id.get(parent_id)
    if not isinstance(parent, dict):
        return []
    nle = load_nle(ctx)
    overrides = nle.get("segment_overrides") or {}
    inserted: list[str] = []
    for cid in child_ids:
        sid = str(cid or "").strip()
        if not sid:
            continue
        ov = overrides.get(sid) if isinstance(overrides.get(sid), dict) else {}
        try:
            start = int((ov or {}).get("start_ms") if ov else parent.get("start_ms") or 0)
            end = int((ov or {}).get("end_ms") if ov else parent.get("end_ms") or 0)
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue
        label = str((ov or {}).get("label") or "").strip()
        if not label or label.startswith(parent_id):
            label = _child_span_text(ctx, start, end) or str(parent.get("text") or "").strip()
        row = dict(by_id.get(sid) or {})
        role = str(row.get("speaker_role") or parent.get("speaker_role") or "unknown")
        if role not in {"interviewer", "interviewee", "unknown"}:
            role = "unknown"
        seg_type = str(row.get("type") or parent.get("type") or "interviewee_answer")
        if seg_type not in {
            "interviewer_question",
            "interviewee_answer",
            "interviewer_reaction",
            "setup",
            "aside",
            "coda",
        }:
            seg_type = "interviewee_answer"
        row.update(
            {
                "segment_id": sid,
                "start_ms": start,
                "end_ms": end,
                "speaker_id": str(row.get("speaker_id") or parent.get("speaker_id") or "spk_unknown"),
                "speaker_role": role,
                "type": seg_type,
                "topic_tags": list(row.get("topic_tags") or parent.get("topic_tags") or []),
                "text": label,
                "parent_id": parent_id,
            }
        )
        if sid in by_id:
            for i, existing in enumerate(segs):
                if str(existing.get("segment_id") or "") == sid:
                    segs[i] = row
                    break
        else:
            parent_idx = next(
                (i for i, existing in enumerate(segs) if str(existing.get("segment_id") or "") == parent_id),
                len(segs) - 1,
            )
            segs.insert(parent_idx + 1 + len(inserted), row)
        by_id[sid] = row
        inserted.append(sid)
    parent_row = dict(parent)
    parent_row["split_into"] = [str(x) for x in child_ids if x]
    for i, existing in enumerate(segs):
        if str(existing.get("segment_id") or "") == parent_id:
            segs[i] = parent_row
            break
    man["segments"] = segs
    write_kw: dict[str, Any] = {"skip_handoff": True}
    if stage_key:
        write_kw["stage_key"] = stage_key
    if mutation_class:
        write_kw["mutation_class"] = mutation_class
    try:
        ctx.write_json("segments/manifest.json", man, **write_kw)
    except Exception:
        # Side write must never abort ranking selection commit (exec_13168/13170).
        try:
            ctx.log(
                "materialize_split_children_into_manifest: manifest write failed "
                f"(stage_key={stage_key!r}); continuing without child rows",
                level="warning",
                stage=stage_key or "nle_state",
            )
        except Exception:
            pass
        return []
    return inserted


def materialize_all_nle_split_children(ctx: RunContext) -> int:
    """Write every NLE/CTA split child into the manifest before EDL extract."""
    nle = load_nle(ctx)
    overrides = nle.get("segment_overrides") or {}
    if not isinstance(overrides, dict):
        return 0
    by_parent: dict[str, list[str]] = {}
    for sid, ov in overrides.items():
        if not isinstance(ov, dict):
            continue
        parent = str(sid)
        kids = [str(c) for c in (ov.get("split_into") or []) if c]
        if not kids:
            parent = str(ov.get("parent_id") or "").strip()
            if not parent:
                continue
            kids = [str(sid)]
        by_parent.setdefault(parent, [])
        for kid in kids:
            if kid not in by_parent[parent]:
                by_parent[parent].append(kid)
    inserted = 0
    for parent, kids in by_parent.items():
        inserted += len(materialize_split_children_into_manifest(ctx, parent, kids))
    return inserted


def split_segment_at(ctx: RunContext, segment_id: str, at_ms: int) -> dict[str, Any]:
    return split_segment_at_cuts(ctx, segment_id, [at_ms])


def split_segment_at_cuts(ctx: RunContext, segment_id: str, cut_ms: list[int]) -> dict[str, Any]:
    """N-way split at sorted cut points (exclusive end boundaries)."""
    nle = load_nle(ctx)
    manifest = ctx.read_json("segments/manifest.json")
    segments = manifest.get("segments") or []
    target = next((s for s in segments if s.get("segment_id") == segment_id), None)
    if not target:
        raise ValueError(f"Segment not found: {segment_id}")
    start = int(target["start_ms"])
    end = int(target["end_ms"])
    cuts = sorted({int(c) for c in cut_ms if start < int(c) < end})
    if not cuts:
        raise ValueError("Split point(s) must be inside the segment.")
    bounds = [start, *cuts, end]
    child_ids: list[str] = []
    overrides = nle.setdefault("segment_overrides", {})
    for i in range(len(bounds) - 1):
        cid = f"{segment_id}{_child_suffix(i)}"
        child_ids.append(cid)
        overrides[cid] = {
            "start_ms": bounds[i],
            "end_ms": bounds[i + 1],
            "label": f"{segment_id} (part {i + 1})",
            "parent_id": segment_id,
        }
    overrides[segment_id] = {"excluded": True, "split_into": child_ids}
    order = nle.get("sequence_order") or [s.get("segment_id") for s in segments]
    if segment_id in order:
        idx = order.index(segment_id)
        order[idx : idx + 1] = child_ids
    nle["sequence_order"] = order
    save_nle(ctx, nle)
    materialize_split_children_into_manifest(ctx, segment_id, child_ids)
    from interview_mux.artifact_repairs import propagate_nle_split_segment_refs

    propagate_nle_split_segment_refs(ctx, segment_id, child_ids)
    try:
        from interview_mux.split_plan import mark_split_rerank_cascade

        mark_split_rerank_cascade(ctx, reason=f"nle_split:{segment_id}")
    except Exception:
        pass
    try:
        from interview_mux.asset_transcripts import sync_speech_sidecars

        sync_speech_sidecars(ctx)
    except Exception:
        pass
    return nle