from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from interview_mux.gates import check_edl_narrative_qc, check_edl_qc, check_narrative_qc
from interview_mux.nle_state import (
    apply_nle_to_selection,
    load_nle,
    nle_has_operator_edits,
    segments_by_id_with_nle,
)
from interview_mux.prompt_validation import validate_edl_flow1
from interview_mux.disfluency.config import disfluency_restore_enabled, restore_settings
from interview_mux.disfluency.extract import confirmed_events, load_disfluencies
from interview_mux.disfluency.restore import build_restore_plan, split_speech_with_disfluencies
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
    normalized = pickup / "normalized"
    lid = line.get("line_id", "")
    seg = line.get("targets_segment_id", "")
    bases: list[Path] = []
    for candidate in (normalized, clean, pickup):
        if candidate.is_dir():
            bases.append(candidate)
    if not bases:
        bases = [pickup]
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
    disfluency_events: list[dict] | None = None,
    restore_enabled: bool = False,
    restore_cfg: dict | None = None,
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
    disfluency_cfg = restore_cfg or restore_settings()
    use_restore = bool(restore_enabled and disfluency_events)

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
        if use_restore:
            speech_clips, timeline_ms = split_speech_with_disfluencies(
                segment_id=sid,
                seg_start_ms=int(seg["start_ms"]),
                seg_end_ms=int(seg["end_ms"]),
                events=disfluency_events or [],
                timeline_ms=timeline_ms,
                settings=disfluency_cfg,
            )
            clips.extend(speech_clips)
        else:
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

    disfluency_clip_count = sum(1 for c in clips if c.get("type") == "disfluency")
    return {
        "version": 1,
        "ordered_segment_ids": ordered,
        "clips": clips,
        "gap_placements": gap_placements,
        "timeline_duration_ms": timeline_ms,
        "gap_report_line_count": len((gap_report or {}).get("interviewer_lines") or []),
        "vo_pickup_clip_count": sum(1 for c in clips if c.get("type") == "vo_pickup"),
        "transition_clip_count": sum(1 for c in clips if c.get("type") == "transition"),
        "disfluency_clip_count": disfluency_clip_count,
        "disfluency_restore_enabled": use_restore,
        "warnings": {
            "missing_vo_files": sorted(set(missing_vo)),
            "gap_targets_not_in_selection": sorted(set(missing_targets)),
        },
        "mux_scope": "full_mix",
    }


def run_edl(ctx: RunContext) -> None:
    if ctx.artifact_exists("flow_1_master/edl_narrative_audit.json"):
        audit = ctx.read_json("flow_1_master/edl_narrative_audit.json")
        if str(audit.get("verdict", "")).strip().lower() == "fail":
            raise SystemExit(
                "edl_narrative_audit verdict is fail — fix blocking issues and re-run "
                "edl_narrative_audit before edl_flow1."
            )
    check_narrative_qc(ctx, stage="edl_flow1", require_selection=True)

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
    run_meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    restore_on = disfluency_restore_enabled(run_meta=run_meta)
    disfluencies = load_disfluencies(ctx) if ctx.artifact_exists("transcript/disfluencies.json") else {}
    confirmed = confirmed_events(disfluencies) if restore_on else []
    restore_cfg = restore_settings()
    plan = build_restore_plan(
        ordered_segment_ids=list(selection.get("ordered_segment_ids") or []),
        segments_by_id=by_id,
        disfluencies=disfluencies,
        settings=restore_cfg,
    )
    ctx.write_json("flow_1_master/disfluency_restore_plan.json", plan)
    edl = build_flow1_edl(
        selection=selection,
        segments_by_id=by_id,
        gap_report=gap_report,
        transitions=transitions,
        resolve_vo_path=lambda line: resolve_vo_pickup_path(ctx, line),
        vo_relpath=lambda p: vo_pickup_relpath(ctx, p),
        disfluency_events=confirmed,
        restore_enabled=restore_on and bool(confirmed),
        restore_cfg=restore_cfg,
    )

    warnings = edl.get("warnings") or {}
    if warnings.get("missing_vo_files"):
        ctx.log(
            f"EDL: gap VO lines missing WAV (mux remains speech-only): "
            f"{warnings['missing_vo_files']}",
            level="warning",
            stage="edl_flow1",
        )
    if warnings.get("gap_targets_not_in_selection"):
        ctx.log(
            f"EDL: gap targets not in selection order: "
            f"{warnings['gap_targets_not_in_selection']}",
            level="warning",
            stage="edl_flow1",
        )

    vo_n = edl.get("vo_pickup_clip_count", 0)
    fill_n = edl.get("disfluency_clip_count", 0)
    ctx.log(
        f"EDL built: {len(edl.get('clips') or [])} events, "
        f"{vo_n} vo_pickup, {fill_n} disfluency, timeline {edl.get('timeline_duration_ms')} ms "
        f"(mix_flow1: speech + VO + SDP overlays)",
        level="success",
        stage="edl_flow1",
    )
    check_edl_qc(ctx, stage="edl_flow1", edl=edl, strict=True)
    check_edl_narrative_qc(ctx, stage="edl_flow1", edl=edl)

    edl_errors = validate_edl_flow1(edl)
    if edl_errors:
        for err in edl_errors:
            ctx.log(
                f"flow_1_master/edl.json: {err}",
                level="error",
                stage="edl_flow1",
            )
        raise SystemExit(
            f"edl_flow1: edl.json failed schema validation ({len(edl_errors)} error(s))"
        )
    ctx.write_json("flow_1_master/edl.json", edl)
    ctx.mark_done("edl_flow1")


def run_mix_flow1(ctx: RunContext) -> Path:
    from interview_mux.llm_flow_hardening import require_spend_artifacts_complete

    require_spend_artifacts_complete(ctx, "mix_flow1")
    """Flow 1 assembly mix — speech + VO + SDP overlays (canonical stage id)."""
    from interview_mux.sound_design import mix_flow1

    check_edl_qc(ctx, stage="mix_flow1", strict=False)
    return mix_flow1(ctx)


def run_mux(ctx: RunContext) -> Path:
    """Backward-compatible alias for mix_flow1 (v1 pipeline stage id)."""
    assembly = run_mix_flow1(ctx)
    ctx.mark_done("mux_flow1")
    return assembly


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

        if ctype != "vo_pickup" and ctype != "disfluency":
            continue

        if ctype == "disfluency":
            src_rel = clip.get("source_path")
            if not src_rel:
                skipped_missing.append(clip.get("event_id") or "unknown")
                continue
            fill_src = ctx.path(str(src_rel))
            if not fill_src.is_file():
                skipped_missing.append(clip.get("event_id") or src_rel)
                continue
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(fill_src),
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

    from interview_mux.audio_timeline import concat_clips_with_crossfade
    from interview_mux.config import merged_config
    from interview_mux.sound_design import load_audio

    crossfade_ms = int((merged_config().get("mix") or {}).get("crossfade_ms_assembly_preview", 80))
    clips = [load_audio(p) for p in clip_paths]
    preview_audio = concat_clips_with_crossfade(clips, crossfade_ms)
    preview = ctx.path("flow_1_master", "assembly_preview.wav")
    preview_audio.export(str(preview), format="wav")
    if skipped_missing:
        ctx.log(
            f"assembly_preview: skipped {len(skipped_missing)} missing VO pickup clip(s): {sorted(set(skipped_missing))}",
            level="warning",
            stage="assembly_preview",
        )
    ctx.log(
        f"Assembly preview ready (speech + VO, crossfade_ms={crossfade_ms}, clips={len(clips)}) — listen before ElevenLabs spend.",
        level="success",
        stage="assembly_preview",
        detail=str(preview),
    )
    ctx.mark_done("assembly_preview")
    return preview
