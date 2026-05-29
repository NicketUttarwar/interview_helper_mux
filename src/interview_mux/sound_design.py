"""Mix engine — Flow 1 and Flow 2 assembly with VO, beds, stingers, ducking (BUILD-065)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from pydub import AudioSegment

from interview_mux.acoustic_profile import load_profile, mix_contract, placement_hints
from interview_mux.audio_timeline import append_with_crossfade
from interview_mux.config import merged_config
from interview_mux.master_qc import maybe_check_mix_intelligibility
from interview_mux.run_context import RunContext

DEFAULT_FRAME_RATE = 48_000
MIN_DUCK_DB = 14.0


def _mix_cfg() -> dict[str, Any]:
    return merged_config().get("mix") or {}


def mix_flow1(ctx: RunContext) -> Path:
    """Build Flow 1 assembly: EDL speech + VO timeline with SDP overlays."""
    contract = mix_contract(ctx)
    profile = load_profile(ctx)
    pace = (profile or {}).get("pacing", {}) if isinstance(profile, dict) else {}
    ctx.log(
        (
            f"mix_flow1: mix_contract pace={pace.get('pace_class', 'unknown')} "
            f"underscore={contract.get('underscore_policy')} duck={contract.get('duck_under_speech_db')}db"
        ),
        level="info",
        stage="mix_flow1",
    )
    crossfade_ms = int(_mix_cfg().get("crossfade_ms_flow1", 100))
    ctx.log("mix_flow1: loading EDL and ingest stem", level="info", stage="mix_flow1")
    edl = ctx.read_json("flow_1_master/edl.json")
    source = load_audio(ctx.path("ingest", "normalized.wav"))
    base = AudioSegment.silent(duration=0, frame_rate=DEFAULT_FRAME_RATE)
    segment_timing: dict[str, tuple[int, int]] = {}
    speech_count = 0
    vo_count = 0
    missing_vo: list[str] = []

    for clip in edl.get("clips") or []:
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
            line_id = str(clip.get("line_id") or "")
            if src_rel:
                vo_path = ctx.path(str(src_rel))
                if vo_path.is_file():
                    audio = load_audio(vo_path)
                else:
                    audio = placeholder_from_clip(clip)
                    missing_vo.append(line_id or str(src_rel))
            else:
                audio = placeholder_from_clip(clip)
                missing_vo.append(line_id or "unknown")
            vo_count += 1
        else:
            continue
        if len(base) == 0:
            base = audio
        else:
            base = append_with_crossfade(base, audio, crossfade_ms)

    if missing_vo:
        ctx.log(
            f"mix_flow1: missing VO pickup WAV — inserted silence for {sorted(set(missing_vo))}",
            level="warn",
            stage="mix_flow1",
        )

    ctx.log(
        (
            f"mix_flow1: base timeline {len(base)} ms — "
            f"speech={speech_count}, vo={vo_count}, segments={len(segment_timing)}, "
            f"crossfade_ms={crossfade_ms}"
        ),
        level="info",
        stage="mix_flow1",
    )

    overlays, overlay_stats = build_flow1_overlays(
        ctx, segment_timing=segment_timing, timeline_ms=len(base), contract=contract
    )
    mix = base
    for cue in overlays:
        clip_audio = cue["audio"]
        if not isinstance(clip_audio, AudioSegment):
            continue
        mix = mix.overlay(clip_audio, position=max(0, int(cue.get("position_ms", 0))))

    ctx.log(
        (
            f"mix_flow1: applied overlays beds={overlay_stats['beds']}, "
            f"stingers={overlay_stats['stingers']}, bridges={overlay_stats['bridges']}, "
            f"missing_assets={overlay_stats['missing_assets']}"
        ),
        level="info",
        stage="mix_flow1",
    )

    assembly = ctx.path("flow_1_master", "assembly.wav")
    mix.export(str(assembly), format="wav")
    ctx.log(
        f"mix_flow1: assembly.wav ready ({len(mix)} ms, VO + beds + stingers)",
        level="success",
        stage="mix_flow1",
        detail=str(assembly),
    )
    maybe_check_mix_intelligibility(
        ctx,
        assembly_path=assembly,
        flow="flow1",
        stage="mix_flow1",
        speech_stem=base,
        segment_timing=segment_timing,
        contract=contract,
    )
    ctx.mark_done("mix_flow1")
    return assembly


def mix_flow2(ctx: RunContext) -> Path:
    """Build Flow 2 montage assembly: highlights + SDP cold open / transitions / outro."""
    contract = mix_contract(ctx)
    crossfade_ms = int(_mix_cfg().get("crossfade_ms_flow2", 120))
    ctx.log("mix_flow2: loading selection and segment manifest", level="info", stage="mix_flow2")
    selection = ctx.read_json("flow_2_highlights/selection.json")
    manifest = ctx.read_json("segments/manifest.json")
    by_id = {s["segment_id"]: s for s in (manifest.get("segments") or [])}
    source = load_audio(ctx.path("ingest", "normalized.wav"))
    highlights = selection.get("highlights") or []
    if not highlights:
        raise RuntimeError("mix_flow2: no highlight clips in selection")

    sdp = load_sound_design_plan(ctx)
    cue_plan = flow2_cues_from_sdp(ctx, sdp)
    mix = AudioSegment.silent(duration=0, frame_rate=DEFAULT_FRAME_RATE)
    speech_montage = AudioSegment.silent(duration=0, frame_rate=DEFAULT_FRAME_RATE)
    missing_assets: list[str] = []

    if cue_plan.get("before_timeline") and contract.get("underscore_policy") != "skip":
        mix += cue_plan["before_timeline"][0].apply_gain(-14.0).fade_in(30).fade_out(80)
    elif cue_plan.get("before_timeline"):
        ctx.log("mix_flow2: cold_open skipped (underscore_policy=skip)", level="info", stage="mix_flow2")

    sfx_dir = ctx.path("flow_2_highlights", "sfx")
    legacy_sfx = sorted(sfx_dir.glob("*.wav")) if sfx_dir.is_dir() else []
    legacy_idx = 0
    rendered = 0
    transition_count = 0

    for i, hl in enumerate(highlights):
        sid = hl.get("segment_id")
        seg = by_id.get(sid) if sid else None
        start_ms = hl.get("start_ms") or (seg and seg["start_ms"])
        end_ms = hl.get("end_ms") or (seg and seg["end_ms"])
        if start_ms is None or end_ms is None:
            continue
        rendered += 1
        slice_audio = source[int(start_ms) : int(end_ms)]
        if len(mix) == 0:
            mix = slice_audio
            speech_montage = slice_audio
        else:
            mix = append_with_crossfade(mix, slice_audio, crossfade_ms)
            speech_montage = append_with_crossfade(speech_montage, slice_audio, crossfade_ms)
        rank = int(hl.get("rank") or (i + 1))
        if i + 1 < len(highlights):
            next_rank = int((highlights[i + 1] or {}).get("rank") or (i + 2))
            trans = resolve_between_clip_transition(cue_plan, rank, next_rank)
            if trans is not None:
                mix += trans.apply_gain(-12.0).fade_in(25).fade_out(100)
                transition_count += 1
            elif legacy_idx < len(legacy_sfx):
                mix += load_audio(legacy_sfx[legacy_idx]).apply_gain(-12.0).fade_in(25).fade_out(100)
                legacy_idx += 1
                transition_count += 1

    if cue_plan.get("after_timeline"):
        mix += cue_plan["after_timeline"][0].apply_gain(-14.0).fade_in(25).fade_out(110)

    if rendered == 0:
        raise RuntimeError("mix_flow2: no highlight clips extracted")

    missing_assets = list(cue_plan.get("missing_assets") or [])
    if missing_assets:
        ctx.log(
            f"mix_flow2: missing SFX assets (skipped): {sorted(set(missing_assets))}",
            level="warn",
            stage="mix_flow2",
        )

    ctx.log(
        (
            f"mix_flow2: montage {len(mix)} ms — highlights={rendered}, "
            f"transitions={transition_count}, crossfade_ms={crossfade_ms}, "
            f"cold_open={bool(cue_plan.get('before_timeline'))}, "
            f"outro={bool(cue_plan.get('after_timeline'))}"
        ),
        level="info",
        stage="mix_flow2",
    )

    assembly = ctx.path("flow_2_highlights", "assembly.wav")
    mix.export(str(assembly), format="wav")
    ctx.log(
        f"mix_flow2: assembly.wav ready (shared transition asset + cold open when planned)",
        level="success",
        stage="mix_flow2",
        detail=str(assembly),
    )
    maybe_check_mix_intelligibility(
        ctx,
        assembly_path=assembly,
        flow="flow2",
        stage="mix_flow2",
        speech_stem=speech_montage,
        segment_timing={},
        contract=contract,
    )
    ctx.mark_done("mix_flow2")
    return assembly


def build_flow1_overlays(
    ctx: RunContext,
    *,
    segment_timing: dict[str, tuple[int, int]],
    timeline_ms: int,
    contract: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    contract = contract or mix_contract(ctx)
    overlays = flow1_overlays_from_sdp(ctx, segment_timing=segment_timing, contract=contract)
    stats = count_overlay_roles(overlays)
    if overlays:
        stats["missing_assets"] = 0
        return overlays, stats
    legacy = flow1_overlays_legacy(ctx, segment_timing=segment_timing, timeline_ms=timeline_ms)
    stats = count_overlay_roles(legacy)
    stats["missing_assets"] = 0
    return legacy, stats


def flow1_overlays_from_sdp(
    ctx: RunContext,
    *,
    segment_timing: dict[str, tuple[int, int]],
    contract: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    contract = contract or mix_contract(ctx)
    if contract.get("underscore_policy") == "skip":
        ctx.log("mix_flow1: underscore_skipped — no bed overlays", level="info", stage="mix_flow1")
        return []
    profile = load_profile(ctx)
    transcript = _load_transcript(ctx)
    segments_by_id = _segments_by_id(ctx)
    plan = load_sound_design_plan(ctx)
    if not plan:
        return []
    flow_plans = plan.get("flow_plans") if isinstance(plan.get("flow_plans"), dict) else {}
    flow = flow_plans.get("flow1") if isinstance(flow_plans.get("flow1"), dict) else {}
    cues = flow.get("cues") if isinstance(flow.get("cues"), list) else []
    assets = plan.get("assets") if isinstance(plan.get("assets"), list) else []
    assets_by_id = {
        str(a.get("asset_id")): a for a in assets if isinstance(a, dict) and a.get("asset_id")
    }
    out: list[dict[str, Any]] = []
    stinger_cap = int(contract.get("stinger_max_per_minute", 4))
    timeline_minutes = max(1, max((end for _s, end in segment_timing.values()), default=60000) // 60000)
    max_stingers = stinger_cap * timeline_minutes
    stinger_count = 0
    duck_default = float(contract.get("duck_under_speech_db", 16.0))

    for cue in cues:
        if not isinstance(cue, dict):
            continue
        asset_id = str(cue.get("asset_id") or "")
        asset = assets_by_id.get(asset_id, {})
        wav = resolve_asset_path(ctx, asset_id=asset_id, generated=plan.get("generated"))
        placement = str(cue.get("placement") or "")
        level_db = float(cue.get("level_db", -24.0))

        if wav is None:
            base = placeholder_audio(asset, cue=cue)
            ctx.log(
                f"mix_flow1: missing asset {asset_id!r} — placeholder silence",
                level="warn",
                stage="mix_flow1",
            )
        else:
            base = load_audio(wav)

        if placement == "under_segment":
            seg_id = str(cue.get("segment_id") or "")
            timing = segment_timing.get(seg_id)
            if not timing:
                continue
            start_ms, end_ms = timing
            dur = max(0, end_ms - start_ms)
            if dur <= 0:
                continue
            duck_db = max(MIN_DUCK_DB, float(cue.get("duck_under_speech_db", duck_default)))
            bed = loop_to_duration(base, dur)
            bed = bed.apply_gain(level_db - duck_db).fade_in(120).fade_out(150)
            out.append({"audio": bed, "position_ms": start_ms, "role": "bed"})
            continue

        if asset.get("role") == "chapter_stinger":
            if stinger_count >= max_stingers:
                ctx.log(
                    f"mix_flow1: stinger cap reached ({max_stingers}/timeline) — dropped {asset_id}",
                    level="warn",
                    stage="mix_flow1",
                )
                continue
            stinger_count += 1

        cue_audio = base.apply_gain(level_db).fade_in(50).fade_out(130)
        pos = flow1_cue_position(cue=cue, segment_timing=segment_timing)
        if pos is None:
            pos = max(0, max((v[1] for v in segment_timing.values()), default=0) - 50)
        if asset.get("role") == "chapter_stinger":
            cue_audio = cue_audio[: int(float(asset.get("duration_seconds", 1.8)) * 1000)]
            pos = _align_stinger_to_pause_tail(
                ctx,
                pos=pos,
                cue=cue,
                placement=placement,
                profile=profile,
                transcript=transcript,
                segments_by_id=segments_by_id,
                segment_timing=segment_timing,
            )
        role = "bridge" if placement == "before_segment" else "stinger"
        out.append({"audio": cue_audio, "position_ms": pos, "role": role})

    return out


def flow1_overlays_legacy(
    ctx: RunContext, *, segment_timing: dict[str, tuple[int, int]], timeline_ms: int
) -> list[dict[str, Any]]:
    sfx_dir = ctx.path("flow_1_master", "sfx")
    sfx_files = sorted(sfx_dir.glob("*.wav")) if sfx_dir.is_dir() else []
    if not sfx_files:
        return []
    profile = load_profile(ctx)
    transcript = _load_transcript(ctx)
    segments_by_id = _segments_by_id(ctx)
    ordered_seg_ids = sorted(segment_timing.keys(), key=lambda sid: segment_timing[sid][0])
    out: list[dict[str, Any]] = []
    bed = loop_to_duration(load_audio(sfx_files[0]), timeline_ms)
    out.append({"audio": bed.apply_gain(-36.0).fade_in(200).fade_out(250), "position_ms": 0, "role": "bed"})
    segment_ends = sorted(end for _start, end in segment_timing.values())
    for i, path in enumerate(sfx_files[1:]):
        pos = segment_ends[min(i, max(0, len(segment_ends) - 1))] if segment_ends else 0
        fallback = max(0, pos - 40)
        aligned = fallback
        if ordered_seg_ids:
            seg_id = ordered_seg_ids[min(i, len(ordered_seg_ids) - 1)]
            segment = segments_by_id.get(seg_id)
            if segment:
                source_pos = resolve_stinger_position_ms(
                    segment,
                    transcript,
                    profile,
                    placement="after_segment",
                )
                mapped = _source_ms_to_timeline_ms(source_pos, segment, segment_timing)
                if mapped is not None:
                    aligned = mapped
                    ctx.log(
                        f"mix_flow1: stinger_aligned pause_tail segment={seg_id} pos={aligned}",
                        level="info",
                        stage="mix_flow1",
                    )
        sting = load_audio(path).apply_gain(-16.0).fade_in(40).fade_out(180)
        out.append({"audio": sting, "position_ms": aligned, "role": "stinger"})
    return out


def _load_transcript(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists("transcript/full.json"):
        return {}
    data = ctx.read_json("transcript/full.json")
    return data if isinstance(data, dict) else {}


def _segments_by_id(ctx: RunContext) -> dict[str, dict[str, Any]]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return {}
    manifest = ctx.read_json("segments/manifest.json")
    if not isinstance(manifest, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for seg in manifest.get("segments") or []:
        if isinstance(seg, dict) and seg.get("segment_id"):
            out[str(seg["segment_id"])] = seg
    return out


def _transcript_words(transcript: dict[str, Any]) -> list[dict[str, Any]]:
    words = [
        w
        for w in (transcript.get("words") or [])
        if isinstance(w, dict)
        and isinstance(w.get("start_ms"), (int, float))
        and isinstance(w.get("end_ms"), (int, float))
    ]
    words.sort(key=lambda w: float(w["start_ms"]))
    return words


def _words_in_segment_range(
    transcript: dict[str, Any],
    start_ms: int,
    end_ms: int,
    *,
    lookback_ms: int = 0,
) -> list[dict[str, Any]]:
    lo = start_ms - lookback_ms
    return [
        w
        for w in _transcript_words(transcript)
        if float(w["end_ms"]) > lo and float(w["start_ms"]) < end_ms
    ]


def resolve_stinger_position_ms(
    segment: dict[str, Any],
    transcript: dict[str, Any],
    profile: dict[str, Any] | None,
    *,
    placement: str = "before_segment",
) -> int | None:
    """Return source-time ms at a pause tail near the segment boundary, or None."""
    hints = placement_hints(profile)
    if not hints.get("prefer_stinger_after_pause_tail", True):
        return None

    min_pause = int(hints.get("stinger_min_pause_after_speech_ms", 400))
    seg_start = int(segment.get("start_ms", 0))
    seg_end = int(segment.get("end_ms", seg_start))
    if seg_end <= seg_start:
        return None

    if placement == "after_segment":
        words = _words_in_segment_range(transcript, seg_start, seg_end)
        return _last_pause_tail_ms(words, min_pause_ms=min_pause, bound_ms=seg_end)

    lookback = max(min_pause * 2, 2000)
    words = _words_in_segment_range(transcript, seg_start, seg_end, lookback_ms=lookback)
    return _pause_tail_before_segment(words, min_pause_ms=min_pause, seg_start=seg_start)


def _last_pause_tail_ms(
    words: list[dict[str, Any]],
    *,
    min_pause_ms: int,
    bound_ms: int,
) -> int | None:
    best: int | None = None
    for i in range(len(words) - 1):
        end_i = int(words[i]["end_ms"])
        gap = int(words[i + 1]["start_ms"]) - end_i
        if gap >= min_pause_ms and end_i <= bound_ms:
            best = end_i
    if words:
        last_end = int(words[-1]["end_ms"])
        if bound_ms - last_end >= min_pause_ms:
            best = last_end
    return best


def _pause_tail_before_segment(
    words: list[dict[str, Any]],
    *,
    min_pause_ms: int,
    seg_start: int,
) -> int | None:
    if not words:
        return None

    first_idx = 0
    for i, w in enumerate(words):
        if int(w["start_ms"]) >= seg_start - 50:
            first_idx = i
            break

    if first_idx > 0:
        prev_end = int(words[first_idx - 1]["end_ms"])
        gap = int(words[first_idx]["start_ms"]) - prev_end
        if gap >= min_pause_ms and int(words[first_idx]["start_ms"]) <= seg_start + min_pause_ms:
            return prev_end

    scan_until = min(len(words), first_idx + 4)
    for i in range(first_idx, scan_until - 1):
        end_i = int(words[i]["end_ms"])
        gap = int(words[i + 1]["start_ms"]) - end_i
        if gap >= min_pause_ms and end_i >= seg_start - min_pause_ms:
            return end_i

    return _last_pause_tail_ms(
        words,
        min_pause_ms=min_pause_ms,
        bound_ms=seg_start + min_pause_ms,
    )


def _source_ms_to_timeline_ms(
    source_ms: int | None,
    segment: dict[str, Any],
    segment_timing: dict[str, tuple[int, int]],
) -> int | None:
    if source_ms is None:
        return None
    sid = str(segment.get("segment_id") or "")
    timing = segment_timing.get(sid)
    if not timing:
        return None
    t0, _t1 = timing
    seg_start = int(segment.get("start_ms", 0))
    return t0 + (int(source_ms) - seg_start)


def _stinger_segment_id(cue: dict[str, Any], placement: str) -> str:
    if placement in {"before_segment", "under_segment"}:
        return str(cue.get("segment_id") or cue.get("before_segment_id") or "")
    if placement == "after_segment":
        return str(cue.get("after_segment_id") or cue.get("segment_id") or "")
    return str(cue.get("segment_id") or "")


def _align_stinger_to_pause_tail(
    ctx: RunContext,
    *,
    pos: int,
    cue: dict[str, Any],
    placement: str,
    profile: dict[str, Any] | None,
    transcript: dict[str, Any],
    segments_by_id: dict[str, dict[str, Any]],
    segment_timing: dict[str, tuple[int, int]],
) -> int:
    seg_id = _stinger_segment_id(cue, placement)
    segment = segments_by_id.get(seg_id)
    if not segment:
        return pos
    source_pos = resolve_stinger_position_ms(
        segment,
        transcript,
        profile,
        placement=placement if placement in {"before_segment", "after_segment"} else "before_segment",
    )
    mapped = _source_ms_to_timeline_ms(source_pos, segment, segment_timing)
    if mapped is None:
        return pos
    ctx.log(
        f"mix_flow1: stinger_aligned pause_tail segment={seg_id} pos={mapped}",
        level="info",
        stage="mix_flow1",
    )
    return mapped


def flow1_cue_position(*, cue: dict, segment_timing: dict[str, tuple[int, int]]) -> int | None:
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


def flow2_cues_from_sdp(ctx: RunContext, sdp: dict) -> dict[str, Any]:
    out: dict[str, Any] = {
        "before_timeline": [],
        "after_timeline": [],
        "between_clips": [],
        "missing_assets": [],
    }
    flow_plans = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    flow = flow_plans.get("flow2") if isinstance(flow_plans.get("flow2"), dict) else {}
    cues = flow.get("cues") if isinstance(flow.get("cues"), list) else []
    assets = sdp.get("assets") if isinstance(sdp.get("assets"), list) else []
    assets_by_id = {
        str(item.get("asset_id")): item
        for item in assets
        if isinstance(item, dict) and item.get("asset_id")
    }
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        asset_id = str(cue.get("asset_id") or "")
        if not asset_id:
            continue
        asset = assets_by_id.get(asset_id, {})
        wav = resolve_asset_path(ctx, asset_id=asset_id, generated=sdp.get("generated"))
        if wav is None:
            out["missing_assets"].append(asset_id)
            audio = placeholder_audio(asset, cue=cue)
        else:
            audio = load_audio(wav)
        level_db = float(cue.get("level_db", -12.0))
        if level_db:
            audio = audio.apply_gain(level_db)
        placement = str(cue.get("placement") or "")
        if placement in {"before_timeline", "after_timeline"}:
            out[placement].append(audio)
        elif placement == "between_clips":
            out["between_clips"].append(
                {
                    "audio": audio,
                    "from_clip_rank": int(cue.get("from_clip_rank") or 0),
                    "to_clip_rank": int(cue.get("to_clip_rank") or 0),
                    "role": asset.get("role"),
                }
            )
    return out


def resolve_between_clip_transition(
    cues: dict[str, Any], from_rank: int, to_rank: int
) -> AudioSegment | None:
    between = cues.get("between_clips") or []
    default: AudioSegment | None = None
    for item in between:
        if not isinstance(item, dict):
            continue
        audio = item.get("audio")
        if not isinstance(audio, AudioSegment):
            continue
        if default is None:
            default = audio
        if int(item.get("from_clip_rank") or 0) == from_rank and int(item.get("to_clip_rank") or 0) == to_rank:
            return audio
    return default


def load_sound_design_plan(ctx: RunContext) -> dict:
    path = ctx.path("understanding", "sound_design_plan.json")
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def resolve_asset_path(ctx: RunContext, *, asset_id: str, generated: object) -> Path | None:
    if isinstance(generated, dict):
        rel = generated.get(asset_id)
        if isinstance(rel, str):
            candidate = ctx.path(rel)
            if candidate.is_file():
                return candidate
    for path in (
        ctx.path("sound_design", "assets", f"{asset_id}.wav"),
        ctx.path("flow_1_master", "sfx", f"{asset_id}.wav"),
        ctx.path("flow_2_highlights", "sfx", f"{asset_id}.wav"),
    ):
        if path.is_file():
            return path
    return None


def load_audio(path: Path) -> AudioSegment:
    seg = AudioSegment.from_file(path)
    return seg.set_channels(1).set_frame_rate(DEFAULT_FRAME_RATE)


def loop_to_duration(segment: AudioSegment, duration_ms: int) -> AudioSegment:
    if duration_ms <= 0:
        return AudioSegment.silent(duration=0, frame_rate=segment.frame_rate)
    if len(segment) <= 0:
        return AudioSegment.silent(duration=duration_ms, frame_rate=DEFAULT_FRAME_RATE)
    loops = max(1, math.ceil(duration_ms / len(segment)))
    return (segment * loops)[:duration_ms]


def placeholder_from_clip(clip: dict) -> AudioSegment:
    dur = int(clip.get("duration_ms") or 0)
    if dur <= 0:
        dur = 500
    return AudioSegment.silent(duration=dur, frame_rate=DEFAULT_FRAME_RATE)


def placeholder_audio(asset: dict, *, cue: dict | None = None) -> AudioSegment:
    dur_s = asset.get("duration_seconds")
    if dur_s is None and cue:
        dur_s = cue.get("duration_seconds")
    try:
        dur_ms = int(float(dur_s or 1.0) * 1000)
    except (TypeError, ValueError):
        dur_ms = 1000
    return AudioSegment.silent(duration=max(1, dur_ms), frame_rate=DEFAULT_FRAME_RATE)


def count_overlay_roles(overlays: list[dict[str, Any]]) -> dict[str, int]:
    stats = {"beds": 0, "stingers": 0, "bridges": 0, "missing_assets": 0}
    for cue in overlays:
        role = cue.get("role")
        if role == "bed":
            stats["beds"] += 1
        elif role == "bridge":
            stats["bridges"] += 1
        elif role == "stinger":
            stats["stingers"] += 1
    return stats
