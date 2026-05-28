from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Callable

from pydub import AudioSegment

from interview_mux.nle_state import (
    apply_nle_to_selection,
    load_nle,
    nle_has_operator_edits,
    segments_by_id_with_nle,
)
from interview_mux.run_context import RunContext


def _segment_by_id(ctx: RunContext) -> dict[str, dict]:
    return segments_by_id_with_nle(ctx)


def _wav_duration_ms(path: Path) -> int:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return max(0, int(float(proc.stdout.strip()) * 1000))


def resolve_vo_pickup_path(ctx: RunContext, line: dict) -> Path | None:
    """Resolve pickup WAV for a gap line (clean/ preferred when present)."""
    pickup = ctx.path("vo_pickup")
    clean = pickup / "clean"
    lid = line.get("line_id", "")
    seg = line.get("targets_segment_id", "")
    bases = [clean, pickup] if clean.is_dir() else [pickup]
    for base in bases:
        for key in (lid, seg):
            if not key:
                continue
            candidate = base / f"{key}.wav"
            if candidate.is_file():
                return candidate
    return None


def vo_pickup_relpath(ctx: RunContext, path: Path) -> str:
    try:
        return path.relative_to(ctx.run_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _gap_lines_for_segment(
    gap_report: dict | None, segment_id: str, placement: str
) -> list[dict]:
    if not gap_report:
        return []
    out: list[dict] = []
    for line in gap_report.get("interviewer_lines") or []:
        if line.get("targets_segment_id") != segment_id:
            continue
        if line.get("placement", "before") != placement:
            continue
        if line.get("delivery") != "record":
            continue
        out.append(line)
    return out


def _transition_after_segment(
    transitions: dict | None, after_segment_id: str, before_segment_id: str
) -> dict | None:
    if not transitions:
        return None
    for item in transitions.get("transitions") or []:
        if (
            item.get("after_segment_id") == after_segment_id
            and item.get("before_segment_id") == before_segment_id
        ):
            return item
    return None


def build_flow1_edl(
    *,
    selection: dict,
    segments_by_id: dict[str, dict],
    gap_report: dict | None = None,
    transitions: dict | None = None,
    resolve_vo_path: Callable[[dict], Path | None] | None = None,
    vo_relpath: Callable[[Path], str] | None = None,
    vo_duration_ms: Callable[[Path], int] | None = None,
) -> dict:
    """Build Flow 1 EDL: speech order from selection, gap VO placements, transition anchors."""
    ordered = list(selection.get("ordered_segment_ids") or [])
    clips: list[dict] = []
    gap_placements: list[dict] = []
    timeline_ms = 0
    missing_vo: list[str] = []
    missing_targets: list[str] = []

    if gap_report:
        for line in gap_report.get("interviewer_lines") or []:
            if line.get("delivery") != "record":
                continue
            target = line.get("targets_segment_id", "")
            if target and target not in ordered:
                missing_targets.append(target)

    duration_fn = vo_duration_ms or _wav_duration_ms

    for idx, sid in enumerate(ordered):
        seg = segments_by_id.get(sid)
        if not seg:
            continue

        for line in _gap_lines_for_segment(gap_report, sid, "before"):
            vo_path = resolve_vo_path(line) if resolve_vo_path else None
            rel: str | None = None
            dur = 0
            if vo_path is None or not vo_path.is_file():
                missing_vo.append(line.get("line_id") or sid)
            else:
                rel = vo_relpath(vo_path) if vo_relpath else vo_path.as_posix()
                dur = duration_fn(vo_path)

            clip = {
                "type": "vo_pickup",
                "line_id": line.get("line_id"),
                "targets_segment_id": sid,
                "placement": "before",
                "gap_type": line.get("gap_type"),
                "source_path": rel,
                "duration_ms": dur,
                "timeline_start_ms": timeline_ms,
            }
            clips.append(clip)
            gap_placements.append(
                {
                    "line_id": line.get("line_id"),
                    "targets_segment_id": sid,
                    "placement": "before",
                    "timeline_start_ms": timeline_ms,
                }
            )
            timeline_ms += dur

        speech_dur = int(seg["end_ms"]) - int(seg["start_ms"])
        clips.append(
            {
                "segment_id": sid,
                "source_start_ms": seg["start_ms"],
                "source_end_ms": seg["end_ms"],
                "timeline_start_ms": timeline_ms,
                "duration_ms": speech_dur,
                "type": "speech",
            }
        )
        timeline_ms += speech_dur

        for line in _gap_lines_for_segment(gap_report, sid, "after"):
            vo_path = resolve_vo_path(line) if resolve_vo_path else None
            rel = None
            dur = 0
            if vo_path is None or not vo_path.is_file():
                missing_vo.append(line.get("line_id") or sid)
            else:
                rel = vo_relpath(vo_path) if vo_relpath else vo_path.as_posix()
                dur = duration_fn(vo_path)

            clip = {
                "type": "vo_pickup",
                "line_id": line.get("line_id"),
                "targets_segment_id": sid,
                "placement": "after",
                "gap_type": line.get("gap_type"),
                "source_path": rel,
                "duration_ms": dur,
                "timeline_start_ms": timeline_ms,
            }
            clips.append(clip)
            gap_placements.append(
                {
                    "line_id": line.get("line_id"),
                    "targets_segment_id": sid,
                    "placement": "after",
                    "timeline_start_ms": timeline_ms,
                }
            )
            timeline_ms += dur

        if idx + 1 < len(ordered):
            nxt = ordered[idx + 1]
            tr = _transition_after_segment(transitions, sid, nxt)
            if tr:
                clips.append(
                    {
                        "type": "transition",
                        "after_segment_id": sid,
                        "before_segment_id": nxt,
                        "text": tr.get("text", ""),
                        "transition_type": tr.get("type", "bridge"),
                        "duration_ms": 0,
                        "timeline_start_ms": timeline_ms,
                    }
                )

    return {
        "version": 1,
        "ordered_segment_ids": ordered,
        "clips": clips,
        "gap_placements": gap_placements,
        "timeline_duration_ms": timeline_ms,
        "gap_report_line_count": len((gap_report or {}).get("interviewer_lines") or []),
        "vo_pickup_clip_count": sum(1 for c in clips if c.get("type") == "vo_pickup"),
        "transition_clip_count": sum(1 for c in clips if c.get("type") == "transition"),
        "warnings": {
            "missing_vo_files": sorted(set(missing_vo)),
            "gap_targets_not_in_selection": sorted(set(missing_targets)),
        },
        "mux_scope": "speech_only",
    }


def run_edl(ctx: RunContext) -> None:
    selection = ctx.read_json("flow_1_master/selection.json")
    nle = load_nle(ctx)
    by_id = _segment_by_id(ctx)
    if nle_has_operator_edits(nle):
        selection = apply_nle_to_selection(
            selection, nle, segments_by_id=by_id
        )
        ctx.write_json("flow_1_master/selection.json", selection)
        ordered = selection.get("ordered_segment_ids") or []
        excluded = selection.get("excluded_segment_ids") or []
        ctx.log(
            f"EDL: applied NLE edits — {len(ordered)} segments, "
            f"{len(excluded)} excluded.",
            level="info",
            stage="edl_flow1",
        )
    gap_report = (
        ctx.read_json("understanding/gap_report.json")
        if ctx.artifact_exists("understanding/gap_report.json")
        else None
    )
    transitions = (
        ctx.read_json("flow_1_master/transitions.json")
        if ctx.artifact_exists("flow_1_master/transitions.json")
        else None
    )
    edl = build_flow1_edl(
        selection=selection,
        segments_by_id=by_id,
        gap_report=gap_report,
        transitions=transitions,
        resolve_vo_path=lambda line: resolve_vo_pickup_path(ctx, line),
        vo_relpath=lambda p: vo_pickup_relpath(ctx, p),
    )

    warnings = edl.get("warnings") or {}
    if warnings.get("missing_vo_files"):
        ctx.log(
            f"EDL: gap VO lines missing WAV (mux remains speech-only): "
            f"{warnings['missing_vo_files']}",
            level="warn",
            stage="edl_flow1",
        )
    if warnings.get("gap_targets_not_in_selection"):
        ctx.log(
            f"EDL: gap targets not in selection order: "
            f"{warnings['gap_targets_not_in_selection']}",
            level="warn",
            stage="edl_flow1",
        )

    vo_n = edl.get("vo_pickup_clip_count", 0)
    ctx.log(
        f"EDL built: {len(edl.get('clips') or [])} events, "
        f"{vo_n} vo_pickup, timeline {edl.get('timeline_duration_ms')} ms "
        f"(mux_flow1 speech-only until BUILD-065)",
        level="success",
        stage="edl_flow1",
    )
    ctx.write_json("flow_1_master/edl.json", edl)
    ctx.mark_done("edl_flow1")


def run_mux(ctx: RunContext) -> Path:
    edl = ctx.read_json("flow_1_master/edl.json")
    source = _load_audio(ctx.path("ingest", "normalized.wav"))
    base = AudioSegment.silent(duration=0, frame_rate=48000)
    segment_timing: dict[str, tuple[int, int]] = {}
    speech_count = 0
    vo_count = 0

    for clip in (edl.get("clips") or []):
        ctype = str(clip.get("type") or "")
        if ctype == "speech":
            start = int(clip.get("source_start_ms", 0))
            end = int(clip.get("source_end_ms", start))
            audio = source[max(0, start) : max(start, end)]
            seg_id = str(clip.get("segment_id") or "")
            if seg_id:
                t0 = int(clip.get("timeline_start_ms", len(base)))
                segment_timing[seg_id] = (t0, t0 + len(audio))
            speech_count += 1
        elif ctype == "vo_pickup":
            src_rel = clip.get("source_path")
            if src_rel:
                vo_path = ctx.path(str(src_rel))
                audio = _load_audio(vo_path) if vo_path.is_file() else AudioSegment.silent(duration=0)
            else:
                audio = AudioSegment.silent(duration=0)
            vo_count += 1
        else:
            continue
        base += audio

    mix = base
    overlays = _flow1_overlays(ctx, segment_timing, timeline_ms=len(base))
    for cue in overlays:
        clip_audio = cue["audio"]
        if not isinstance(clip_audio, AudioSegment):
            continue
        mix = mix.overlay(
            clip_audio,
            position=max(0, int(cue.get("position_ms", 0))),
        )

    ctx.log(
        (
            f"mux_flow1: mixed speech={speech_count}, vo={vo_count}, "
            f"sfx_overlays={len(overlays)} (beds + stingers with ducking)"
        ),
        level="info",
        stage="mux_flow1",
    )
    assembly = ctx.path("flow_1_master", "assembly.wav")
    mix.export(str(assembly), format="wav")
    ctx.mark_done("mux_flow1")
    return assembly


def _flow1_overlays(
    ctx: RunContext, segment_timing: dict[str, tuple[int, int]], timeline_ms: int
) -> list[dict]:
    overlays = _flow1_overlays_from_sdp(ctx, segment_timing=segment_timing)
    if overlays:
        return overlays
    return _flow1_overlays_legacy(ctx, segment_timing=segment_timing, timeline_ms=timeline_ms)


def _flow1_overlays_from_sdp(
    ctx: RunContext, *, segment_timing: dict[str, tuple[int, int]]
) -> list[dict]:
    plan_path = ctx.path("understanding", "sound_design_plan.json")
    if not plan_path.is_file():
        return []
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    flow_plans = plan.get("flow_plans") if isinstance(plan.get("flow_plans"), dict) else {}
    flow = flow_plans.get("flow1") if isinstance(flow_plans.get("flow1"), dict) else {}
    cues = flow.get("cues") if isinstance(flow.get("cues"), list) else []
    assets = plan.get("assets") if isinstance(plan.get("assets"), list) else []
    assets_by_id = {
        str(a.get("asset_id")): a for a in assets if isinstance(a, dict) and a.get("asset_id")
    }
    out: list[dict] = []
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        asset_id = str(cue.get("asset_id") or "")
        asset = assets_by_id.get(asset_id, {})
        wav = _resolve_asset_path(ctx, asset_id=asset_id, generated=plan.get("generated"))
        if wav is None:
            continue
        base = _load_audio(wav)
        placement = str(cue.get("placement") or "")
        level_db = float(cue.get("level_db", -24.0))
        if placement == "under_segment":
            seg_id = str(cue.get("segment_id") or "")
            timing = segment_timing.get(seg_id)
            if not timing:
                continue
            start_ms, end_ms = timing
            dur = max(0, end_ms - start_ms)
            if dur <= 0:
                continue
            bed = _loop_to_duration(base, dur)
            duck_db = float(cue.get("duck_under_speech_db", 16.0))
            bed = bed.apply_gain(level_db - duck_db).fade_in(120).fade_out(150)
            out.append({"audio": bed, "position_ms": start_ms})
            continue
        cue_audio = base.apply_gain(level_db).fade_in(50).fade_out(130)
        pos = _flow1_cue_position(cue=cue, segment_timing=segment_timing)
        if pos is None:
            # Fallback placement for sparse plans: append after known timeline sections.
            pos = max(0, max((v[1] for v in segment_timing.values()), default=0) - 50)
        if asset.get("role") == "chapter_stinger":
            cue_audio = cue_audio[: int(float(asset.get("duration_seconds", 1.8)) * 1000)]
        out.append({"audio": cue_audio, "position_ms": pos})
    return out


def _flow1_overlays_legacy(
    ctx: RunContext, *, segment_timing: dict[str, tuple[int, int]], timeline_ms: int
) -> list[dict]:
    sfx_dir = ctx.path("flow_1_master", "sfx")
    sfx_files = sorted(sfx_dir.glob("*.wav")) if sfx_dir.is_dir() else []
    if not sfx_files:
        return []
    out: list[dict] = []
    # Legacy fallback: first asset is a soft bed across the episode.
    bed = _loop_to_duration(_load_audio(sfx_files[0]), timeline_ms)
    out.append({"audio": bed.apply_gain(-36.0).fade_in(200).fade_out(250), "position_ms": 0})
    segment_ends = sorted(end for _start, end in segment_timing.values())
    for i, path in enumerate(sfx_files[1:]):
        pos = segment_ends[min(i, max(0, len(segment_ends) - 1))] if segment_ends else 0
        sting = _load_audio(path).apply_gain(-16.0).fade_in(40).fade_out(180)
        out.append({"audio": sting, "position_ms": max(0, pos - 40)})
    return out


def _flow1_cue_position(
    *, cue: dict, segment_timing: dict[str, tuple[int, int]]
) -> int | None:
    placement = str(cue.get("placement") or "")
    if placement in {"before_segment", "under_segment"}:
        sid = str(cue.get("segment_id") or cue.get("before_segment_id") or "")
        timing = segment_timing.get(sid)
        return timing[0] if timing else None
    if placement == "after_segment":
        sid = str(cue.get("after_segment_id") or cue.get("segment_id") or "")
        timing = segment_timing.get(sid)
        return timing[1] if timing else None
    return None


def _resolve_asset_path(ctx: RunContext, *, asset_id: str, generated: object) -> Path | None:
    if isinstance(generated, dict):
        rel = generated.get(asset_id)
        if isinstance(rel, str):
            candidate = ctx.path(rel)
            if candidate.is_file():
                return candidate
    candidates = [
        ctx.path("sound_design", "assets", f"{asset_id}.wav"),
        ctx.path("flow_1_master", "sfx", f"{asset_id}.wav"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _loop_to_duration(segment: AudioSegment, duration_ms: int) -> AudioSegment:
    if duration_ms <= 0:
        return AudioSegment.silent(duration=0, frame_rate=segment.frame_rate)
    if len(segment) <= 0:
        return AudioSegment.silent(duration=duration_ms, frame_rate=48000)
    loops = max(1, math.ceil(duration_ms / len(segment)))
    return (segment * loops)[:duration_ms]


def _load_audio(path: Path) -> AudioSegment:
    seg = AudioSegment.from_file(path)
    return seg.set_channels(1).set_frame_rate(48000)


def run_preview(ctx: RunContext) -> Path:
    """Build Flow 1 assembly preview: speech + recorded VO pickup, no SFX."""
    edl = ctx.read_json("flow_1_master/edl.json")
    source = ctx.path("ingest", "normalized.wav")
    work = ctx.path("flow_1_master", "_preview_clips")
    work.mkdir(parents=True, exist_ok=True)
    clip_paths: list[Path] = []
    skipped_missing: list[str] = []

    for i, clip in enumerate(edl.get("clips") or []):
        ctype = clip.get("type")
        out = work / f"clip_{i:04d}.wav"
        if ctype == "speech":
            start = max(0, float(clip.get("source_start_ms", 0)) / 1000.0)
            end = max(start, float(clip.get("source_end_ms", 0)) / 1000.0)
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(source),
                    "-ss",
                    str(start),
                    "-to",
                    str(end),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "48000",
                    "-c:a",
                    "pcm_s16le",
                    str(out),
                ],
                check=True,
                capture_output=True,
            )
            clip_paths.append(out)
            continue

        if ctype != "vo_pickup":
            continue

        src_rel = clip.get("source_path")
        if not src_rel:
            skipped_missing.append(clip.get("line_id") or "unknown")
            continue
        vo_src = ctx.path(src_rel)
        if not vo_src.is_file():
            skipped_missing.append(clip.get("line_id") or src_rel)
            continue
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(vo_src),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "48000",
                "-c:a",
                "pcm_s16le",
                str(out),
            ],
            check=True,
            capture_output=True,
        )
        clip_paths.append(out)

    if not clip_paths:
        raise SystemExit(
            "assembly_preview: no renderable speech/VO clips found in edl_flow1 output."
        )

    concat_list = work / "concat.txt"
    concat_list.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in clip_paths),
        encoding="utf-8",
    )
    preview = ctx.path("flow_1_master", "assembly_preview.wav")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-c:a",
            "pcm_s16le",
            str(preview),
        ],
        check=True,
        capture_output=True,
    )
    if skipped_missing:
        ctx.log(
            f"assembly_preview: skipped {len(skipped_missing)} missing VO pickup clip(s): {sorted(set(skipped_missing))}",
            level="warning",
            stage="assembly_preview",
        )
    ctx.log(
        "Assembly preview ready (speech + VO, no SFX) — listen before ElevenLabs spend.",
        level="success",
        stage="assembly_preview",
        detail=str(preview),
    )
    ctx.mark_done("assembly_preview")
    return preview
