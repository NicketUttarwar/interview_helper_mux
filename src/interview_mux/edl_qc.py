"""Deterministic validators for Flow 1 EDL timeline coherence."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

_AUDIO_CLIP_TYPES = frozenset({"speech", "vo_pickup"})


def _gap_vo_line_ids(
    ctx: RunContext,
    gap_report: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Index gap VO lines that produce vo_pickup clips (record or synthesize)."""
    report = gap_report
    if not isinstance(report, dict):
        if not ctx.artifact_exists("understanding/gap_report.json"):
            return {}
        loaded = ctx.read_json("understanding/gap_report.json")
        report = loaded if isinstance(loaded, dict) else {}
    out: dict[str, dict[str, Any]] = {}
    for line in (report.get("interviewer_lines") or []) if isinstance(report, dict) else []:
        if not isinstance(line, dict):
            continue
        delivery = str(line.get("delivery") or "").lower()
        if delivery not in {"record", "synthesize"}:
            continue
        if line.get("skipped_optional"):
            continue
        lid = line.get("line_id")
        if isinstance(lid, str) and lid.strip():
            out[lid] = line
    return out


def _gap_record_line_ids(ctx: RunContext) -> dict[str, dict[str, Any]]:
    # Backward-compatible alias used by older callers/tests.
    return {
        lid: row
        for lid, row in _gap_vo_line_ids(ctx).items()
        if str(row.get("delivery") or "").lower() == "record"
    }


def _segment_ids_from_manifest(ctx: RunContext) -> set[str]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return set()
    manifest = ctx.read_json("segments/manifest.json")
    ids: set[str] = set()
    for seg in (manifest.get("segments") or []) if isinstance(manifest, dict) else []:
        if isinstance(seg, dict):
            sid = seg.get("segment_id") or seg.get("id")
            if sid:
                ids.add(str(sid))
    try:
        from interview_mux.artifact_repairs import _live_split_child_ids

        ids |= _live_split_child_ids(ctx)
    except Exception:
        pass
    try:
        from interview_mux.nle_state import load_nle

        nle = load_nle(ctx)
        for sid, ov in (nle.get("segment_overrides") or {}).items():
            if not isinstance(ov, dict):
                continue
            if ov.get("parent_id") or ov.get("start_ms") is not None:
                ids.add(str(sid))
            for child in ov.get("split_into") or []:
                if child:
                    ids.add(str(child))
    except Exception:
        pass
    return ids


def _clip_end_ms(clip: dict[str, Any]) -> int:
    return int(clip.get("timeline_start_ms", 0)) + int(clip.get("duration_ms", 0))


def _validate_vo_line_ids(
    clips: list[Any],
    gap_lines: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    for index, clip in enumerate(clips):
        if not isinstance(clip, dict) or clip.get("type") != "vo_pickup":
            continue
        line_id = clip.get("line_id")
        if not isinstance(line_id, str) or not line_id.strip():
            errors.append(f"clips[{index}]: vo_pickup missing line_id")
            continue
        gap_line = gap_lines.get(line_id)
        if gap_line is None:
            errors.append(
                f'clips[{index}]: vo_pickup line_id "{line_id}" not found in gap_report '
                "(delivery=record|synthesize)"
            )
            continue
        target = clip.get("targets_segment_id")
        expected = gap_line.get("targets_segment_id")
        if expected and target != expected:
            errors.append(
                f'clips[{index}]: vo_pickup line_id "{line_id}" targets_segment_id '
                f'"{target}" does not match gap_report "{expected}"'
            )
    return errors


def _validate_no_overlapping_speech(clips: list[Any]) -> list[str]:
    errors: list[str] = []
    audio_clips: list[tuple[int, dict[str, Any]]] = []
    for index, clip in enumerate(clips):
        if not isinstance(clip, dict):
            continue
        if clip.get("type") not in _AUDIO_CLIP_TYPES:
            continue
        duration = int(clip.get("duration_ms", 0))
        if duration <= 0:
            continue
        audio_clips.append((index, clip))

    for i in range(len(audio_clips) - 1):
        idx_a, clip_a = audio_clips[i]
        idx_b, clip_b = audio_clips[i + 1]
        start_a = int(clip_a.get("timeline_start_ms", 0))
        end_a = _clip_end_ms(clip_a)
        start_b = int(clip_b.get("timeline_start_ms", 0))
        end_b = _clip_end_ms(clip_b)
        overlap_ms = min(end_a, end_b) - max(start_a, start_b)
        allowed = max(
            int(clip_a.get("mix_overlap_ms") or 0),
            int(clip_b.get("mix_overlap_ms") or 0),
        )
        if start_a < end_b and start_b < end_a and overlap_ms > allowed:
            label_a = clip_a.get("line_id") or clip_a.get("segment_id") or f"clips[{idx_a}]"
            label_b = clip_b.get("line_id") or clip_b.get("segment_id") or f"clips[{idx_b}]"
            errors.append(
                f"Overlapping speech: {label_a} [{start_a},{end_a}ms) overlaps "
                f"{label_b} [{start_b},{end_b}ms)"
            )
    return errors


def _validate_no_overlapping_source_ranges(clips: list[Any]) -> list[str]:
    """Fail when speech clips share intersecting source media ranges.

    Timeline-adjacent speech can still loop in the listener's ear when junction
    extends push one clip's source_end into the next keep's source_start.
    """
    errors: list[str] = []
    speech: list[tuple[int, dict[str, Any]]] = []
    for index, clip in enumerate(clips):
        if not isinstance(clip, dict) or clip.get("type") != "speech":
            continue
        try:
            ss = int(clip.get("source_start_ms", 0))
            se = int(clip.get("source_end_ms", ss))
        except (TypeError, ValueError):
            continue
        if se <= ss:
            continue
        speech.append((index, clip))

    for i in range(len(speech)):
        idx_a, clip_a = speech[i]
        ss_a = int(clip_a.get("source_start_ms", 0))
        se_a = int(clip_a.get("source_end_ms", ss_a))
        label_a = clip_a.get("segment_id") or f"clips[{idx_a}]"
        for j in range(i + 1, len(speech)):
            idx_b, clip_b = speech[j]
            ss_b = int(clip_b.get("source_start_ms", 0))
            se_b = int(clip_b.get("source_end_ms", ss_b))
            if ss_a < se_b and ss_b < se_a:
                label_b = clip_b.get("segment_id") or f"clips[{idx_b}]"
                errors.append(
                    f"Overlapping source range: {label_a} "
                    f"[{ss_a},{se_a}ms) intersects {label_b} [{ss_b},{se_b}ms)"
                )
    return errors


def _validate_timeline_monotonic(edl: dict[str, Any], clips: list[Any]) -> list[str]:
    errors: list[str] = []
    prev_start: int | None = None
    for index, clip in enumerate(clips):
        if not isinstance(clip, dict):
            continue
        if int(clip.get("duration_ms") or 0) <= 0:
            continue
        start = int(clip.get("timeline_start_ms", 0))
        if prev_start is not None and start < prev_start:
            errors.append(
                f"clips[{index}]: timeline_start_ms {start} is before previous clip at {prev_start}"
            )
        prev_start = start

    declared = int(edl.get("timeline_duration_ms", 0))
    if clips:
        computed = max(_clip_end_ms(c) for c in clips if isinstance(c, dict))
        if declared != computed:
            errors.append(
                f"timeline_duration_ms {declared} does not match computed timeline end {computed}"
            )
    elif declared != 0:
        errors.append(f"timeline_duration_ms {declared} but clips list is empty")

    return errors


def _validate_speech_clips(
    edl: dict[str, Any],
    clips: list[Any],
    *,
    valid_segment_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    ordered = [str(s) for s in (edl.get("ordered_segment_ids") or [])]
    speech_order: list[str] = []

    for index, clip in enumerate(clips):
        if not isinstance(clip, dict) or clip.get("type") != "speech":
            continue
        sid = clip.get("segment_id")
        if not isinstance(sid, str) or not sid.strip():
            errors.append(f"clips[{index}]: speech clip missing segment_id")
            continue
        if valid_segment_ids and sid not in valid_segment_ids:
            errors.append(f'clips[{index}]: unknown segment_id "{sid}"')
        source_start = int(clip.get("source_start_ms", 0))
        source_end = int(clip.get("source_end_ms", source_start))
        duration = int(clip.get("duration_ms", 0))
        expected = source_end - source_start
        if duration != expected:
            errors.append(
                f'clips[{index}]: speech segment "{sid}" duration_ms {duration} '
                f"does not match source span {expected}"
            )
        speech_order.append(sid)

    if ordered and speech_order != ordered:
        errors.append(
            f"speech clip order {speech_order} does not match ordered_segment_ids {ordered}"
        )
    return errors


def _validate_no_never_touch_cta_bleed(
    ctx: RunContext,
    clips: list[Any],
) -> list[str]:
    """Speech source ranges must not invade media-IP CTA / never-touch tape."""
    errors: list[str] = []
    try:
        from interview_mux.media_ip_cta import never_touch_source_intervals
    except Exception:
        return errors
    try:
        intervals = never_touch_source_intervals(ctx)
    except Exception:
        return errors
    if not intervals:
        return errors
    for index, clip in enumerate(clips):
        if not isinstance(clip, dict) or clip.get("type") != "speech":
            continue
        try:
            ss = int(clip.get("source_start_ms", 0))
            se = int(clip.get("source_end_ms", ss))
        except (TypeError, ValueError):
            continue
        if se <= ss:
            continue
        label = clip.get("segment_id") or f"clips[{index}]"
        for nt_s, nt_e, nt_sid in intervals:
            if ss < nt_e and nt_s < se:
                errors.append(
                    f"Never-touch CTA bleed: {label} [{ss},{se}ms) intersects "
                    f"{nt_sid} [{nt_s},{nt_e}ms)"
                )
                break
    return errors


def validate_flow1_edl(
    ctx: RunContext,
    edl: dict[str, Any] | None = None,
    gap_report: dict[str, Any] | None = None,
) -> list[str]:
    """Return actionable Flow 1 EDL QC errors (empty list = pass)."""
    if edl is None:
        if not ctx.artifact_exists("master/edl.json"):
            return ["Missing master/edl.json"]
        edl = ctx.read_json("master/edl.json")

    if not isinstance(edl, dict):
        return ["master/edl.json root must be an object"]

    errors: list[str] = []
    clips = edl.get("clips") or []
    if not isinstance(clips, list):
        return ["clips must be an array"]

    gap_lines = _gap_vo_line_ids(ctx, gap_report)
    valid_segments = _segment_ids_from_manifest(ctx)
    errors.extend(_validate_vo_line_ids(clips, gap_lines))
    errors.extend(_validate_no_overlapping_speech(clips))
    errors.extend(_validate_no_overlapping_source_ranges(clips))
    errors.extend(_validate_no_never_touch_cta_bleed(ctx, clips))
    errors.extend(_validate_timeline_monotonic(edl, clips))
    errors.extend(
        _validate_speech_clips(edl, clips, valid_segment_ids=valid_segments)
    )
    return errors
