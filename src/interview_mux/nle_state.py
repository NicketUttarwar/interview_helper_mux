from __future__ import annotations

from typing import Any

from interview_mux.file_store import read_json, write_json
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
    p = ctx.path(NLE_REL)
    if not p.is_file():
        return default_nle()
    data = read_json(p)
    base = default_nle()
    base.update(data)
    return base


def save_nle(ctx: RunContext, data: dict[str, Any]) -> None:
    write_json(ctx.path(NLE_REL), data)


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


def split_segment_at(ctx: RunContext, segment_id: str, at_ms: int) -> dict[str, Any]:
    nle = load_nle(ctx)
    manifest = ctx.read_json("segments/manifest.json")
    segments = manifest.get("segments") or []
    target = next((s for s in segments if s.get("segment_id") == segment_id), None)
    if not target:
        raise ValueError(f"Segment not found: {segment_id}")
    start = int(target["start_ms"])
    end = int(target["end_ms"])
    if at_ms <= start or at_ms >= end:
        raise ValueError("Split point must be inside the segment.")
    left_id = f"{segment_id}a"
    right_id = f"{segment_id}b"
    overrides = nle.setdefault("segment_overrides", {})
    overrides[segment_id] = {"excluded": True, "split_into": [left_id, right_id]}
    overrides[left_id] = {
        "start_ms": start,
        "end_ms": at_ms,
        "label": f"{segment_id} (part 1)",
        "parent_id": segment_id,
    }
    overrides[right_id] = {
        "start_ms": at_ms,
        "end_ms": end,
        "label": f"{segment_id} (part 2)",
        "parent_id": segment_id,
    }
    order = nle.get("sequence_order") or [s.get("segment_id") for s in segments]
    if segment_id in order:
        idx = order.index(segment_id)
        order[idx:idx + 1] = [left_id, right_id]
    nle["sequence_order"] = order
    save_nle(ctx, nle)
    return nle
