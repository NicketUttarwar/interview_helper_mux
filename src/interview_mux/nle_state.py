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


def save_nle(ctx: RunContext, data: dict[str, Any]) -> None:
    from interview_mux.config import merged_config
    from interview_mux.prompt_validation import validate_nle_edits

    errors = validate_nle_edits(data)
    if errors:
        strict = bool((merged_config().get("nle_edits") or {}).get("strict"))
        if strict:
            raise ValueError(f"nle_edits schema invalid: {'; '.join(errors[:4])}")
        ctx.log(f"nle_edits schema warnings: {errors[:2]}", level="warning", stage="full_master_ranking")
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
) -> dict[str, Any]:
    """Merge operator NLE exclude/split/reorder into a selection artifact."""
    if not nle_has_operator_edits(nle):
        return selection

    overrides = nle.get("segment_overrides") or {}
    order = list(nle.get("sequence_order") or [])
    result = dict(selection)
    excluded = _excluded_entries(result)
    excluded_ids = {e["segment_id"] for e in excluded}

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

    # Drop stale parent ids replaced by splits (children already in order).
    for seg_id, ov in overrides.items():
        children = [str(c) for c in (ov.get("split_into") or []) if c]
        if not children:
            continue
        if seg_id in ordered and any(c in ordered for c in children):
            while seg_id in ordered:
                ordered.remove(seg_id)
            # Ensure children appear (replace parent slot with children order)
            # If children missing from ordered, insert at parent former neighbors
            for child in children:
                if child not in ordered and child not in excluded_ids:
                    ordered.append(child)

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
    from interview_mux.artifact_repairs import propagate_nle_split_segment_refs

    propagate_nle_split_segment_refs(ctx, segment_id, child_ids)
    try:
        from interview_mux.split_plan import mark_split_rerank_cascade

        mark_split_rerank_cascade(ctx, reason=f"nle_split:{segment_id}")
    except Exception:
        pass
    return nle