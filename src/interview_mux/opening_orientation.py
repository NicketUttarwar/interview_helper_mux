"""Mandatory early episode orientation and opening-sequence validation."""

from __future__ import annotations

import re
from typing import Any

from interview_mux.run_context import RunContext


ORIENTATION_LINE_ID = "vo_preface_episode_orientation"
OPENING_MUSIC_AIR_KIND = "opening_music"
SEQUENCE_COLD_OPEN = "native_hook_music_intro_body"
SEQUENCE_STRAIGHT = "intro_music_body"


def is_episode_orientation(line: dict[str, Any] | None) -> bool:
    if not isinstance(line, dict):
        return False
    line_id = str(line.get("line_id") or "").lower()
    return (
        bool(line.get("episode_orientation"))
        or bool(line.get("opening_sequence"))
        or "episode_orientation" in line_id
        or bool(line.get("cold_open"))
    )


def native_cold_open_segment_id(
    ctx: RunContext, ordered_segment_ids: list[str]
) -> str | None:
    """Return the explicit native hook only when it actually opens the selection."""
    if not ordered_segment_ids:
        return None
    first = str(ordered_segment_ids[0])
    selection = (
        ctx.read_json("master/selection.json")
        if ctx.artifact_exists("master/selection.json")
        else {}
    )
    candidates = [
        (selection or {}).get("native_cold_open_segment_id"),
        (selection or {}).get("hook_segment_id"),
    ]
    if ctx.artifact_exists("mastering/mastering_plan.json"):
        plan = ctx.read_json("mastering/mastering_plan.json")
        cold = plan.get("cold_open") if isinstance(plan, dict) else {}
        if isinstance(cold, dict) and str(cold.get("kind") or "none") != "none":
            candidates.extend([cold.get("segment_id"), cold.get("hook_segment_id")])
    if ctx.artifact_exists("understanding/episode_structure.json"):
        structure = ctx.read_json("understanding/episode_structure.json")
        if isinstance(structure, dict):
            candidates.append(structure.get("hook_segment_id"))
            cold = structure.get("cold_open")
            if isinstance(cold, dict):
                candidates.append(cold.get("segment_id"))
    return first if first in {str(x) for x in candidates if x} else None


def _first_text(value: dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = str(value.get(key) or "").strip()
        if text:
            return " ".join(text.split())
    return ""


def _topic_label(brief: dict[str, Any]) -> str:
    topics = brief.get("topics")
    if not isinstance(topics, list):
        return ""
    for topic in topics:
        if isinstance(topic, dict):
            text = _first_text(topic, "name", "label", "title", "summary")
        else:
            text = str(topic or "").strip()
        if text:
            return text
    return ""


def _fallback_orientation_text(ctx: RunContext) -> tuple[str, dict[str, Any]]:
    """Build grounded copy only from already-approved understanding artifacts."""
    brief = (
        ctx.read_json("understanding/content_brief.json")
        if ctx.artifact_exists("understanding/content_brief.json")
        else {}
    )
    brief = brief if isinstance(brief, dict) else {}
    thesis = _first_text(brief, "episode_promise", "logline", "thesis", "subtitle")
    guest = _first_text(brief, "guest_name", "interviewee_name", "subject_name")
    topic = _topic_label(brief) or _first_text(brief, "title")

    if thesis:
        core = thesis
        if not re.match(r"(?i)^(this|in this|today|we|our)\b", core):
            core = f"In this conversation, {core[0].lower() + core[1:]}"
    elif guest and topic:
        core = f"This is a conversation with {guest} about {topic}."
    elif topic:
        core = f"This conversation explores {topic}."
    elif guest:
        core = f"This is a conversation with {guest}."
    else:
        core = "This conversation follows the people, decisions, and stakes on the tape."

    if core[-1:] not in ".!?":
        core += "."
    # Spoken-copy guard treats bare "stage" as production jargon ("growth stage").
    core = re.sub(r"\bstage\b", "chapter", core, flags=re.IGNORECASE)
    text = f"{core} Let’s hear how it unfolded."
    words = text.split()
    if len(words) > 105:
        text = " ".join(words[:102]).rstrip(" ,;:") + ". Let’s hear how it unfolded."
    return text, {
        "artifact": "understanding/content_brief.json",
        "path": "episode_promise|logline|thesis|guest_name|topics",
    }


def ensure_episode_orientation(
    ctx: RunContext,
    gap_report: dict[str, Any],
    ordered_segment_ids: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Ensure one selection-independent orientation, retargeted to the final open."""
    if not ordered_segment_ids or not isinstance(gap_report, dict):
        return gap_report, []
    try:
        from interview_mux.gap_vo_gates import gap_framing_enabled

        if not gap_framing_enabled(ctx):
            return gap_report, []
    except Exception:
        pass

    ordered = [str(x) for x in ordered_segment_ids if x]
    first = ordered[0]
    hook = native_cold_open_segment_id(ctx, ordered)
    sequence = SEQUENCE_COLD_OPEN if hook else SEQUENCE_STRAIGHT
    placement = "after" if hook else "before"
    target = hook or first
    lines = [dict(x) for x in (gap_report.get("interviewer_lines") or []) if isinstance(x, dict)]
    orientations = [x for x in lines if is_episode_orientation(x)]
    if not orientations:
        orientations = [
            x
            for x in lines
            if str(x.get("line_category") or "") == "episode_preface"
            and str(x.get("targets_segment_id") or "") == target
        ]
    actions: list[dict[str, Any]] = []

    if orientations:
        preferred = next(
            (x for x in orientations if str(x.get("origin") or "") == "operator"),
            orientations[0],
        )
    else:
        text, extracted_from = _fallback_orientation_text(ctx)
        delivery = "record"
        try:
            from interview_mux.gap_vo_gates import resolve_gap_vo_delivery

            delivery = (
                "synthesize"
                if resolve_gap_vo_delivery(ctx) == "chatterbox"
                else "record"
            )
        except Exception:
            if any(str(x.get("delivery") or "") == "synthesize" for x in lines):
                delivery = "synthesize"
        preferred = {
            "line_id": ORIENTATION_LINE_ID,
            "gap_type": "missing_setup",
            "line_category": "episode_preface",
            "text": text,
            "targets_segment_id": target,
            "placement": placement,
            "delivery": delivery,
            "supports_segment_ids": [target],
            "rationale": "Orient the listener to the guest, topic, and stakes before the body.",
            "extracted_from": extracted_from,
            "origin": "deterministic_orientation_guard",
        }
        actions.append({"action": "mint_episode_orientation", "line_id": preferred["line_id"]})

    chosen = dict(preferred)
    prior_contract = {
        key: chosen.get(key)
        for key in (
            "line_category",
            "episode_orientation",
            "opening_sequence",
            "targets_segment_id",
            "placement",
            "supports_segment_ids",
            "allow_music_bed_overlap",
            "orientation_missions",
        )
    }
    old_target = str(chosen.get("targets_segment_id") or "")
    chosen["line_id"] = str(chosen.get("line_id") or ORIENTATION_LINE_ID)
    chosen["line_category"] = "episode_preface"
    chosen["episode_orientation"] = True
    chosen["opening_sequence"] = sequence
    chosen["targets_segment_id"] = target
    chosen["placement"] = placement
    chosen["supports_segment_ids"] = [target]
    chosen["allow_music_bed_overlap"] = True
    chosen["orientation_missions"] = [
        "guest_identity",
        "conversation_topic",
        "listener_stakes",
    ]
    # Retargeting / courtesy rewrites can leave a 1–4 word hinge that fails the
    # opening contract (<6 words). Replace with grounded fallback copy.
    if len(str(chosen.get("text") or "").split()) < 6:
        text, extracted_from = _fallback_orientation_text(ctx)
        if len(text.split()) >= 6:
            chosen["text"] = text
            if extracted_from:
                chosen["extracted_from"] = extracted_from
            actions.append(
                {
                    "action": "thicken_episode_orientation_text",
                    "line_id": chosen["line_id"],
                    "words": len(text.split()),
                }
            )
    chosen["recompose_action"] = "retargeted" if old_target != target else "kept"
    if old_target != target:
        actions.append(
            {
                "action": "retarget_episode_orientation",
                "line_id": chosen["line_id"],
                "from": old_target or None,
                "to": target,
                "placement": placement,
            }
        )
    elif prior_contract != {
        key: chosen.get(key)
        for key in prior_contract
    }:
        actions.append(
            {
                "action": "normalize_episode_orientation",
                "line_id": chosen["line_id"],
                "sequence": sequence,
            }
        )
    if len(orientations) > 1:
        actions.append(
            {
                "action": "dedupe_episode_orientation",
                "kept": chosen["line_id"],
                "removed_count": len(orientations) - 1,
            }
        )

    orientation_ids = {
        str(x.get("line_id") or "") for x in orientations if x.get("line_id")
    }
    non_orientation = [
        x
        for x in lines
        if not is_episode_orientation(x)
        and str(x.get("line_id") or "") not in orientation_ids
    ]
    out = dict(gap_report)
    out["interviewer_lines"] = [chosen, *non_orientation]
    out["opening_orientation"] = {
        "line_id": chosen["line_id"],
        "sequence": sequence,
        "native_cold_open_segment_id": hook,
        "target_segment_id": target,
        "required": True,
    }
    return out, actions


def validate_opening_orientation(
    *,
    gap_report: dict[str, Any] | None,
    edl: dict[str, Any] | None,
    max_non_silence_index: int = 3,
) -> list[str]:
    """Validate exactly one audible orientation and the declared opening grammar."""
    errors: list[str] = []
    report_lines = [
        x
        for x in ((gap_report or {}).get("interviewer_lines") or [])
        if isinstance(x, dict) and is_episode_orientation(x) and not x.get("skipped_optional")
    ]
    if len(report_lines) != 1:
        return [f"opening_orientation_count={len(report_lines)} expected=1"]
    line = report_lines[0]
    line_id = str(line.get("line_id") or "")
    missions = {str(x) for x in (line.get("orientation_missions") or []) if x}
    required_missions = {
        "guest_identity",
        "conversation_topic",
        "listener_stakes",
    }
    if not required_missions.issubset(missions):
        errors.append(
            "opening_orientation_missions_missing="
            + ",".join(sorted(required_missions - missions))
        )
    if len(str(line.get("text") or "").split()) < 6:
        errors.append("opening_orientation_text_too_thin")
    clips = [x for x in ((edl or {}).get("clips") or []) if isinstance(x, dict)]
    audible = [
        x
        for x in clips
        if x.get("type") == "vo_pickup" and str(x.get("line_id") or "") == line_id
    ]
    if len(audible) != 1:
        errors.append(f"opening_orientation_audible_count={len(audible)} expected=1")
        return errors
    non_silence = [x for x in clips if x.get("type") != "silence"]
    intro_index = non_silence.index(audible[0])
    if intro_index > max_non_silence_index:
        errors.append(f"opening_orientation_too_late index={intro_index}")
    sequence = str(line.get("opening_sequence") or SEQUENCE_STRAIGHT)
    music_markers = [
        i
        for i, clip in enumerate(clips)
        if clip.get("type") == "silence"
        and str(clip.get("air_kind") or "") == OPENING_MUSIC_AIR_KIND
    ]
    if len(music_markers) != 1:
        errors.append(f"opening_music_marker_count={len(music_markers)} expected=1")
        return errors
    marker_index = music_markers[0]
    intro_clip_index = clips.index(audible[0])
    first_speech_index = next(
        (i for i, clip in enumerate(clips) if clip.get("type") == "speech"),
        None,
    )
    if sequence == SEQUENCE_COLD_OPEN:
        body_after_intro = any(
            i > intro_clip_index and clip.get("type") == "speech"
            for i, clip in enumerate(clips)
        )
        if first_speech_index is None or not (
            first_speech_index < marker_index < intro_clip_index
        ) or not body_after_intro:
            errors.append("opening_sequence must be native_hook→music→intro→body")
    elif first_speech_index is None or not (
        intro_clip_index < marker_index < first_speech_index
    ):
        errors.append("opening_sequence must be intro→music→body")
    return errors
