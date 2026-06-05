"""Build assembly-timeline API payload from EDL and related artifacts."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext


def _segment_text_lookup(ctx: RunContext) -> dict[str, dict[str, Any]]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return {}
    manifest = ctx.read_json("segments/manifest.json")
    return {
        s["segment_id"]: s
        for s in (manifest.get("segments") or [])
        if s.get("segment_id")
    }


def _vo_recorded_file(ctx: RunContext, line_id: str, target_seg: str) -> str | None:
    pickup = ctx.path("vo_pickup")
    for name in (f"{line_id}.wav", f"{target_seg}.wav"):
        p = pickup / name
        if p.is_file():
            return name
    return None


def _chapters_from_narrative_plan(
    ctx: RunContext,
    *,
    speech_clips: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not ctx.artifact_exists("flow_1_master/narrative_plan.json"):
        return []
    plan = ctx.read_json("flow_1_master/narrative_plan.json")
    seg_to_timeline = {
        c["segment_id"]: int(c.get("timeline_start_ms", 0))
        for c in speech_clips
        if c.get("segment_id")
    }
    chapters: list[dict[str, Any]] = []
    for ch in plan.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        anchor = ch.get("anchor_segment_id") or ch.get("opens_with_segment_id")
        if not anchor or anchor not in seg_to_timeline:
            continue
        chapters.append(
            {
                "title": ch.get("title") or ch.get("chapter_title") or "",
                "anchor_segment_id": anchor,
                "timeline_start_ms": seg_to_timeline[anchor],
            }
        )
    return chapters


def build_assembly_timeline(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists("flow_1_master/edl.json"):
        return {"ready": False, "reason": "EDL not built — run edl_flow1 first."}

    edl = ctx.read_json("flow_1_master/edl.json")
    seg_lookup = _segment_text_lookup(ctx)
    clips_out: list[dict[str, Any]] = []

    for clip in edl.get("clips") or []:
        if not isinstance(clip, dict):
            continue
        ctype = clip.get("type")
        if ctype == "speech":
            sid = clip.get("segment_id", "")
            seg = seg_lookup.get(sid, {})
            clips_out.append(
                {
                    "type": "speech",
                    "segment_id": sid,
                    "timeline_start_ms": int(clip.get("timeline_start_ms", 0)),
                    "duration_ms": int(clip.get("duration_ms", 0)),
                    "source_start_ms": int(clip.get("source_start_ms", 0)),
                    "source_end_ms": int(clip.get("source_end_ms", 0)),
                    "text": (seg.get("text") or "")[:200],
                    "speaker_role": seg.get("speaker_role"),
                    "segment_type": seg.get("type"),
                }
            )
        elif ctype == "vo_pickup":
            lid = clip.get("line_id", "")
            target = clip.get("targets_segment_id", "")
            clips_out.append(
                {
                    "type": "vo_pickup",
                    "line_id": lid,
                    "targets_segment_id": target,
                    "placement": clip.get("placement"),
                    "timeline_start_ms": int(clip.get("timeline_start_ms", 0)),
                    "duration_ms": int(clip.get("duration_ms", 0)),
                    "recorded_file": _vo_recorded_file(ctx, lid, target),
                    "source_path": clip.get("source_path"),
                }
            )
        elif ctype == "transition":
            clips_out.append(
                {
                    "type": "transition",
                    "after_segment_id": clip.get("after_segment_id"),
                    "before_segment_id": clip.get("before_segment_id"),
                    "timeline_start_ms": int(clip.get("timeline_start_ms", 0)),
                    "duration_ms": int(clip.get("duration_ms", 0)),
                    "text": (clip.get("text") or "")[:120],
                }
            )

    speech_clips = [c for c in clips_out if c.get("type") == "speech"]
    preview = (
        "flow_1_master/assembly_preview.wav"
        if ctx.artifact_exists("flow_1_master/assembly_preview.wav")
        else None
    )
    return {
        "ready": True,
        "timeline_duration_ms": int(edl.get("timeline_duration_ms", 0)),
        "ordered_segment_ids": list(edl.get("ordered_segment_ids") or []),
        "clips": clips_out,
        "chapters": _chapters_from_narrative_plan(ctx, speech_clips=speech_clips),
        "warnings": edl.get("warnings") or {},
        "preview_audio": preview,
    }
