"""Mix engine — Flow 1 and Flow 2 assembly with VO, beds, stingers, ducking (BUILD-065)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from pydub import AudioSegment

from interview_mux.acoustic_profile import load_profile, mix_contract, placement_hints
from interview_mux.audio_timeline import append_with_crossfade, snap_cut_to_word_boundary
from interview_mux.config import merged_config
from interview_mux.disfluency.config import restore_settings
from interview_mux.master_qc import maybe_check_mix_intelligibility
from interview_mux.mix_completeness import enforce_mix_completeness
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.sonic_context import load_sonic_context

DEFAULT_FRAME_RATE = 48_000
MIN_DUCK_DB = 14.0


def _mix_cfg() -> dict[str, Any]:
    return merged_config().get("mix") or {}


def _transcript_words(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists("transcript/full.json"):
        return []
    full = ctx.read_json("transcript/full.json")
    words = full.get("words") or []
    return words if isinstance(words, list) else []


def _speech_slice_end_ms(ctx: RunContext, end_ms: int, words: list[dict[str, Any]]) -> int:
    if not bool(_mix_cfg().get("word_boundary_cuts", True)):
        return end_ms
    margin = int(_mix_cfg().get("word_boundary_margin_ms", 50))
    max_shift = int(_mix_cfg().get("word_boundary_max_shift_ms", 400))
    return snap_cut_to_word_boundary(end_ms, words, margin_ms=margin, max_shift_ms=max_shift)


def _append_mix_clip(
    base: AudioSegment,
    clip: AudioSegment,
    crossfade_ms: int,
) -> AudioSegment:
    adaptive = bool(_mix_cfg().get("adaptive_crossfade", True))
    return append_with_crossfade(base, clip, crossfade_ms, adaptive=adaptive)


def _disfluency_excluded_windows(edl: dict[str, Any]) -> list[tuple[int, int]]:
    windows: list[tuple[int, int]] = []
    for clip in edl.get("clips") or []:
        if not isinstance(clip, dict) or clip.get("type") != "disfluency":
            continue
        start = int(clip.get("timeline_start_ms") or 0)
        dur = int(clip.get("duration_ms") or 0)
        if dur > 0:
            windows.append((start, start + dur))
    return windows


def _overlaps_excluded(pos_ms: int, duration_ms: int, excluded: list[tuple[int, int]]) -> bool:
    end = pos_ms + max(0, duration_ms)
    for w0, w1 in excluded:
        if pos_ms < w1 and end > w0:
            return True
    return False


def _update_segment_timing(
    segment_timing: dict[str, tuple[int, int]],
    seg_id: str,
    t0: int,
    t1: int,
) -> None:
    if not seg_id:
        return
    if seg_id in segment_timing:
        prev_start, prev_end = segment_timing[seg_id]
        segment_timing[seg_id] = (min(prev_start, t0), max(prev_end, t1))
    else:
        segment_timing[seg_id] = (t0, t1)


def mix(ctx: RunContext, *, remux_cycle: int = 0) -> Path:
    """Build Flow 1 assembly: EDL speech + VO timeline with SDP overlays."""
    from interview_mux.placement_qa import maybe_run_placement_qa
    from interview_mux.soundscape_policy import soundscape_enabled
    from interview_mux.soundscape_verify import run_soundscape_verify

    with logged_step("mix/placement_qa", ctx=ctx, stage="mix"):
        maybe_run_placement_qa(ctx)
        contract = mix_contract(ctx)
        profile = load_profile(ctx)
        pace = (profile or {}).get("pacing", {}) if isinstance(profile, dict) else {}
        policy_hash = ""
        try:
            from interview_mux.soundscape_policy import load_policy

            pol = load_policy(ctx)
            if pol:
                policy_hash = str(pol.get("policy_hash") or "")[:12]
        except Exception:
            pass
        ctx.log(
            (
                f"mix: mix_contract pace={pace.get('pace_class', 'unknown')} "
                f"underscore={contract.get('underscore_policy')} duck={contract.get('duck_under_speech_db')}db"
                + (f" soundscape={policy_hash}" if policy_hash else "")
            ),
            level="info",
            stage="mix",
        )
        crossfade_ms = int(_mix_cfg().get("crossfade_ms_flow1", 100))
        disfluency_crossfade_ms = int(restore_settings().get("crossfade_ms") or 30)
        speech_join_crossfades = _flow1_speech_join_crossfades(ctx)
        words = _transcript_words(ctx)
        ctx.log("mix: loading EDL and ingest stem", level="info", stage="mix")
        edl = ctx.read_json("master/edl.json")
        excluded_windows = _disfluency_excluded_windows(edl)
        source = load_audio(ctx.read_path("ingest", "normalized.wav"))

    base = AudioSegment.silent(duration=0, frame_rate=DEFAULT_FRAME_RATE)
    segment_timing: dict[str, tuple[int, int]] = {}
    speech_count = 0
    vo_count = 0
    disfluency_count = 0
    missing_vo: list[str] = []
    prev_speech_seg_id = ""

    with logged_step("mix/build_base_timeline", ctx=ctx, stage="mix"):
        for clip in edl.get("clips") or []:
            ctype = str(clip.get("type") or "")
            if ctype == "speech":
                start = int(clip.get("source_start_ms", 0))
                end = _speech_slice_end_ms(ctx, int(clip.get("source_end_ms", start)), words)
                audio = source[max(0, start) : max(start, end)]
                seg_id = str(clip.get("segment_id") or "")
                if seg_id:
                    t0 = int(clip.get("timeline_start_ms", len(base)))
                    _update_segment_timing(segment_timing, seg_id, t0, t0 + len(audio))
                speech_count += 1
                join_key = (prev_speech_seg_id, seg_id) if prev_speech_seg_id and seg_id else None
                clip_crossfade = (
                    speech_join_crossfades[join_key]
                    if join_key and join_key in speech_join_crossfades
                    else crossfade_ms
                )
                if seg_id:
                    prev_speech_seg_id = seg_id
            elif ctype == "vo_pickup":
                src_rel = clip.get("source_path")
                line_id = str(clip.get("line_id") or "")
                if src_rel:
                    vo_path = ctx.read_path(str(src_rel))
                    if vo_path.is_file():
                        audio = load_audio(vo_path)
                    else:
                        audio = placeholder_from_clip(clip)
                        missing_vo.append(line_id or str(src_rel))
                else:
                    audio = placeholder_from_clip(clip)
                    missing_vo.append(line_id or "unknown")
                vo_count += 1
                clip_crossfade = crossfade_ms
            elif ctype == "disfluency":
                src_rel = clip.get("source_path")
                if src_rel:
                    fill_path = ctx.read_path(str(src_rel))
                    if fill_path.is_file():
                        audio = load_audio(fill_path)
                    else:
                        audio = placeholder_from_clip(clip)
                else:
                    audio = placeholder_from_clip(clip)
                disfluency_count += 1
                seg_id = str(clip.get("segment_id") or "")
                if seg_id:
                    t0 = int(clip.get("timeline_start_ms", len(base)))
                    _update_segment_timing(segment_timing, seg_id, t0, t0 + len(audio))
                clip_crossfade = disfluency_crossfade_ms
            else:
                continue
            if len(base) == 0:
                base = audio
            else:
                base = _append_mix_clip(base, audio, clip_crossfade)

        if missing_vo:
            ctx.log(
                f"mix: missing VO pickup WAV — inserted silence for {sorted(set(missing_vo))}",
                level="warning",
                stage="mix",
            )

        ctx.log(
            (
                f"mix: base timeline {len(base)} ms — "
                f"speech={speech_count}, vo={vo_count}, disfluency={disfluency_count}, "
                f"segments={len(segment_timing)}, crossfade_ms={crossfade_ms}"
            ),
            level="info",
            stage="mix",
        )

    with logged_step("mix/apply_overlays", ctx=ctx, stage="mix"):
        overlays, overlay_stats = build_flow1_overlays(
            ctx,
            segment_timing=segment_timing,
            timeline_ms=len(base),
            contract=contract,
            excluded_windows=excluded_windows,
        )
        mixed = base
        skipped_on_disfluency = 0
        for cue in overlays:
            clip_audio = cue["audio"]
            if not isinstance(clip_audio, AudioSegment):
                continue
            pos = max(0, int(cue.get("position_ms", 0)))
            if excluded_windows and _overlaps_excluded(pos, len(clip_audio), excluded_windows):
                skipped_on_disfluency += 1
                continue
            mixed = mixed.overlay(clip_audio, position=pos)

        if skipped_on_disfluency:
            ctx.log(
                f"mix: skipped {skipped_on_disfluency} overlay(s) overlapping disfluency clips",
                level="info",
                stage="mix",
            )

        ctx.log(
            (
                f"mix: applied overlays beds={overlay_stats['beds']}, "
                f"stingers={overlay_stats['stingers']}, bridges={overlay_stats['bridges']}, "
                f"missing_assets={overlay_stats['missing_assets']}"
            ),
            level="info",
            stage="mix",
        )

    assembly = ctx.path("master", "assembly.wav")
    with logged_step("mix/export_assembly", ctx=ctx, stage="mix"):
        mixed.export(str(assembly), format="wav")
        ctx.log(
            f"mix: assembly.wav ready ({len(mixed)} ms, VO + beds + stingers)",
            level="success",
            stage="mix",
            detail=str(assembly),
        )

    with logged_step("mix/post_mix_qc", ctx=ctx, stage="mix"):
        maybe_check_mix_intelligibility(
            ctx,
            assembly_path=assembly,
            flow="podcast",
            stage="mix",
            speech_stem=base,
            segment_timing=segment_timing,
            contract=contract,
        )
        if soundscape_enabled():
            report = run_soundscape_verify(ctx, remux_cycle=remux_cycle)
            if report.get("verdict") == "remediate":
                ctx.log(
                    f"mix: soundscape remux after remediation (cycle {remux_cycle})",
                    level="warning",
                    stage="mix",
                )
                return mix(ctx, remux_cycle=remux_cycle + 1)
            if report.get("verdict") == "fail_closed":
                raise RuntimeError(
                    "soundscape_verify fail_closed: " + "; ".join(report.get("failures") or [])
                )
        enforce_mix_completeness(
            ctx,
            flow="podcast",
            stage="mix",
            missing_vo=missing_vo,
            missing_sfx=list(overlay_stats.get("missing_assets") or []),
        )
    ctx.mark_done("mix")
    return assembly


def mix_flow2(ctx: RunContext) -> Path:
    """Build Flow 2 montage assembly: highlights + SDP cold open / transitions / outro."""
    from interview_mux.placement_qa import maybe_run_placement_qa

    with logged_step("mix_flow2/placement_qa", ctx=ctx, stage="mix_flow2"):
        maybe_run_placement_qa(ctx)
        contract = mix_contract(ctx)
        sonic = load_sonic_context(ctx) or {}
        mix_policy = sonic.get("mix_policy") if isinstance(sonic.get("mix_policy"), dict) else {}
        crossfade_ms = int(mix_policy.get("crossfade_ms_flow2") or _mix_cfg().get("crossfade_ms_flow2", 120))
        words = _transcript_words(ctx)
        ctx.log("mix_flow2: loading selection and segment manifest", level="info", stage="mix_flow2")
        selection = ctx.read_json("flow_2_highlights/selection.json")
        manifest = ctx.read_json("segments/manifest.json")
        by_id = {s["segment_id"]: s for s in (manifest.get("segments") or [])}
        source = load_audio(ctx.read_path("ingest", "normalized.wav"))
        highlights = selection.get("highlights") or []
        if not highlights:
            raise RuntimeError("mix_flow2: no highlight clips in selection")

        sdp = load_sound_design_plan(ctx)
        cue_plan = flow2_cues_from_sdp(ctx, sdp)

    mix = AudioSegment.silent(duration=0, frame_rate=DEFAULT_FRAME_RATE)
    speech_montage = AudioSegment.silent(duration=0, frame_rate=DEFAULT_FRAME_RATE)
    missing_assets: list[str] = []

    with logged_step("mix_flow2/build_montage", ctx=ctx, stage="mix_flow2"):
        if cue_plan.get("before_timeline") and contract.get("underscore_policy") != "skip":
            mix += cue_plan["before_timeline"][0].apply_gain(-14.0).fade_in(30).fade_out(80)
        elif cue_plan.get("before_timeline"):
            ctx.log("mix_flow2: cold_open skipped (underscore_policy=skip)", level="info", stage="mix_flow2")

        sfx_dir = ctx.final_path("flow_2_highlights", "sfx")
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
            end_cut = _speech_slice_end_ms(ctx, int(end_ms), words)
            slice_audio = source[int(start_ms) : end_cut]
            if len(mix) == 0:
                mix = slice_audio
                speech_montage = slice_audio
            else:
                rank = int(hl.get("rank") or (i + 1))
                prev_rank = int((highlights[i - 1] or {}).get("rank") or i)
                _, join_cf = resolve_between_clip_transition(cue_plan, prev_rank, rank)
                clip_crossfade = join_cf if join_cf is not None else crossfade_ms
                mix = _append_mix_clip(mix, slice_audio, clip_crossfade)
                speech_montage = _append_mix_clip(speech_montage, slice_audio, clip_crossfade)
            rank = int(hl.get("rank") or (i + 1))
            if i + 1 < len(highlights):
                next_rank = int((highlights[i + 1] or {}).get("rank") or (i + 2))
                trans, _trans_cf = resolve_between_clip_transition(cue_plan, rank, next_rank)
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
                level="warning",
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
    with logged_step("mix_flow2/export_assembly", ctx=ctx, stage="mix_flow2"):
        mix.export(str(assembly), format="wav")
        ctx.log(
            f"mix_flow2: assembly.wav ready (shared transition asset + cold open when planned)",
            level="success",
            stage="mix_flow2",
            detail=str(assembly),
        )

    with logged_step("mix_flow2/post_mix_qc", ctx=ctx, stage="mix_flow2"):
        maybe_check_mix_intelligibility(
            ctx,
            assembly_path=assembly,
            flow="flow2",
            stage="mix_flow2",
            speech_stem=speech_montage,
            segment_timing={},
            contract=contract,
        )
        enforce_mix_completeness(
            ctx,
            flow="flow2",
            stage="mix_flow2",
            missing_sfx=list(missing_assets),
        )
    ctx.mark_done("mix_flow2")
    return assembly


def build_flow1_overlays(
    ctx: RunContext,
    *,
    segment_timing: dict[str, tuple[int, int]],
    timeline_ms: int,
    contract: dict[str, Any] | None = None,
    excluded_windows: list[tuple[int, int]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    contract = contract or mix_contract(ctx)
    overlays = flow1_overlays_from_sdp(
        ctx,
        segment_timing=segment_timing,
        contract=contract,
        excluded_windows=excluded_windows or [],
    )
    stats = count_overlay_roles(overlays)
    if overlays:
        stats["missing_assets"] = 0
        return overlays, stats
    legacy = flow1_overlays_legacy(ctx, segment_timing=segment_timing, timeline_ms=timeline_ms)
    stats = count_overlay_roles(legacy)
    stats["missing_assets"] = 0
    return legacy, stats


def _flow_plan_cues(plan: dict[str, Any]) -> list[Any]:
    flow_plans = plan.get("flow_plans") if isinstance(plan.get("flow_plans"), dict) else {}
    flow = flow_plans.get("podcast") if isinstance(flow_plans.get("podcast"), dict) else {}
    if not flow and isinstance(flow_plans.get("flow1"), dict):
        flow = flow_plans["flow1"]
    cues = flow.get("cues") if isinstance(flow.get("cues"), list) else []
    return cues


def _flow1_speech_join_crossfades(ctx: RunContext) -> dict[tuple[str, str], int]:
    """Per-segment speech join crossfade overrides from SDP transition/stinger cues."""
    plan = load_sound_design_plan(ctx)
    if not plan:
        return {}
    cues = _flow_plan_cues(plan)
    from interview_mux.placement_qa import apply_placement_adjustments

    cues = apply_placement_adjustments(ctx, [c for c in cues if isinstance(c, dict)])
    out: dict[tuple[str, str], int] = {}
    for cue in cues:
        if not isinstance(cue, dict) or cue.get("crossfade_ms") is None:
            continue
        placement = str(cue.get("placement") or "")
        if placement not in {"after_segment", "before_segment"}:
            continue
        after = str(cue.get("after_segment_id") or "")
        before = str(cue.get("before_segment_id") or "")
        if placement == "after_segment" and not after:
            after = str(cue.get("segment_id") or "")
        if placement == "before_segment" and not before:
            before = str(cue.get("segment_id") or "")
        if after and before:
            out[(after, before)] = int(cue["crossfade_ms"])
    return out


def flow1_overlays_from_sdp(
    ctx: RunContext,
    *,
    segment_timing: dict[str, tuple[int, int]],
    contract: dict[str, Any] | None = None,
    excluded_windows: list[tuple[int, int]] | None = None,
) -> list[dict[str, Any]]:
    contract = contract or mix_contract(ctx)
    excluded = excluded_windows or []
    if contract.get("underscore_policy") == "skip":
        ctx.log("mix: underscore_skipped — no bed overlays", level="info", stage="mix")
        return []
    profile = load_profile(ctx)
    transcript = _load_transcript(ctx)
    segments_by_id = _segments_by_id(ctx)
    plan = load_sound_design_plan(ctx)
    if not plan:
        return []
    cues = _flow_plan_cues(plan)
    from interview_mux.placement_qa import apply_placement_adjustments

    cues = apply_placement_adjustments(ctx, [c for c in cues if isinstance(c, dict)])
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
    sonic = load_sonic_context(ctx) or {}
    scenario = sonic.get("scenario") if isinstance(sonic.get("scenario"), dict) else {}
    atlas_bucket = str(scenario.get("atlas_bucket") or "")
    segment_flags = sonic.get("segment_flags") if isinstance(sonic.get("segment_flags"), dict) else {}
    overlap_high = {str(x) for x in (segment_flags.get("overlap_high") or [])}

    for cue in cues:
        if not isinstance(cue, dict):
            continue
        asset_id = str(cue.get("asset_id") or "")
        asset = assets_by_id.get(asset_id, {})
        wav = resolve_asset_path(ctx, asset_id=asset_id, generated=plan.get("generated"))
        placement = str(cue.get("placement") or "")
        level_db = float(cue.get("level_db", -24.0))
        from interview_mux.tbiy_mix import apply_pan_position, tbiy_duck_db, tbiy_level_adjustment_db

        level_db += tbiy_level_adjustment_db(ctx, cue, asset)
        if cue.get("skip") is True:
            continue

        if wav is None:
            base = placeholder_audio(asset, cue=cue)
            ctx.log(
                f"mix: missing asset {asset_id!r} — placeholder silence",
                level="warning",
                stage="mix",
            )
        else:
            base = load_audio(wav)

        if placement == "under_segment":
            seg_id = str(cue.get("segment_id") or "")
            timing = segment_timing.get(seg_id)
            if not timing:
                continue
            if atlas_bucket == "panel" and seg_id in overlap_high:
                continue
            start_ms, end_ms = timing
            dur = max(0, end_ms - start_ms)
            if dur <= 0:
                continue
            if bool((_mix_cfg()).get("adaptive_level_from_sap", True)):
                level_db = _adaptive_bed_level_db(ctx, default_level_db=level_db)
            duck_db = max(MIN_DUCK_DB, tbiy_duck_db(ctx, cue, duck_default))
            fade_in = int(cue.get("crossfade_ms") or 120)
            fade_out = int(cue.get("crossfade_ms") or 150)
            bed = loop_to_duration(base, dur)
            bed = apply_pan_position(bed, cue.get("pan_position"))
            bed = bed.apply_gain(level_db - duck_db).fade_in(fade_in).fade_out(fade_out)
            out.append({"audio": bed, "position_ms": start_ms, "role": "bed"})
            continue

        asset_role = str(asset.get("role") or "")
        if _cue_uses_pause_alignment(cue, asset):
            if stinger_count >= max_stingers:
                ctx.log(
                    f"mix: stinger cap reached ({max_stingers}/timeline) — dropped {asset_id}",
                    level="warning",
                    stage="mix",
                )
                continue
            stinger_count += 1

        fade_in = int(cue.get("crossfade_ms") or 50)
        fade_out = int(cue.get("crossfade_ms") or 130)
        cue_audio = base.apply_gain(level_db).fade_in(fade_in).fade_out(fade_out)
        cue_audio = apply_pan_position(cue_audio, cue.get("pan_position"))
        pos = flow1_cue_position(cue=cue, segment_timing=segment_timing)
        if pos is None:
            pos = max(0, max((v[1] for v in segment_timing.values()), default=0) - 50)
        if _cue_uses_pause_alignment(cue, asset):
            dur_s = float(asset.get("duration_seconds") or 0.4)
            if asset_role in ("chapter_stinger", "transition_stinger", "transition_whoosh"):
                cue_audio = cue_audio[: int(dur_s * 1000)]
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
        if excluded and _overlaps_excluded(int(pos), len(cue_audio), excluded):
            continue
        if asset_role == "rhetorical_punctuator":
            role = "punctuator"
        else:
            role = "bridge" if placement == "before_segment" else "stinger"
        out.append({"audio": cue_audio, "position_ms": pos, "role": role})

    return out


def flow1_overlays_legacy(
    ctx: RunContext, *, segment_timing: dict[str, tuple[int, int]], timeline_ms: int
) -> list[dict[str, Any]]:
    sfx_dir = ctx.final_path("master", "sfx")
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
                        f"mix: stinger_aligned pause_tail segment={seg_id} pos={aligned}",
                        level="info",
                        stage="mix",
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


def _parse_transcript_words(transcript: dict[str, Any]) -> list[dict[str, Any]]:
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
        for w in _parse_transcript_words(transcript)
        if float(w["end_ms"]) > lo and float(w["start_ms"]) < end_ms
    ]


def _laughter_windows_from_value_features(value_features: dict[str, Any] | None) -> list[tuple[int, int]]:
    """Extract laughter window (start_ms, end_ms) tuples from value_features (fail-open)."""
    if not isinstance(value_features, dict):
        return []
    windows: list[tuple[int, int]] = []
    profiles = value_features.get("profiles") if isinstance(value_features.get("profiles"), dict) else {}
    transcript_profile = profiles.get("transcript")
    if isinstance(transcript_profile, dict):
        for row in transcript_profile.get("quality_trajectory_flags") or []:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label") or row.get("flag") or row.get("kind") or "").lower()
            if "laugh" not in label:
                continue
            start = int(row.get("start_ms") or 0)
            end = int(row.get("end_ms") or start + 400)
            if end > start:
                windows.append((start, end))
    audio_profile = profiles.get("audio")
    if isinstance(audio_profile, dict):
        for row in audio_profile.get("laughter_windows") or audio_profile.get("event_windows") or []:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label") or row.get("kind") or "").lower()
            if label and "laugh" not in label:
                continue
            start = int(row.get("start_ms") or 0)
            end = int(row.get("end_ms") or start + 400)
            if end > start:
                windows.append((start, end))
    return windows


def _overlaps_laughter_window(pos_ms: int, windows: list[tuple[int, int]], *, buffer_ms: int = 200) -> bool:
    for start, end in windows:
        lo = start - buffer_ms
        hi = end + buffer_ms
        if lo <= pos_ms <= hi:
            return True
    return False


def _nudge_away_from_laughter(
    pos_ms: int | None,
    windows: list[tuple[int, int]],
    *,
    buffer_ms: int = 200,
) -> int | None:
    if pos_ms is None or not windows:
        return pos_ms
    if not _overlaps_laughter_window(pos_ms, windows, buffer_ms=buffer_ms):
        return pos_ms
    for delta in (buffer_ms, buffer_ms * 2, buffer_ms * 3, -buffer_ms, -buffer_ms * 2):
        candidate = pos_ms + delta
        if candidate < 0:
            continue
        if not _overlaps_laughter_window(candidate, windows, buffer_ms=buffer_ms):
            return candidate
    return None


def resolve_stinger_position_ms(
    segment: dict[str, Any],
    transcript: dict[str, Any],
    profile: dict[str, Any] | None,
    *,
    placement: str = "before_segment",
    laughter_windows: list[tuple[int, int]] | None = None,
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
        pos = _last_pause_tail_ms(words, min_pause_ms=min_pause, bound_ms=seg_end)
    else:
        lookback = max(min_pause * 2, 2000)
        words = _words_in_segment_range(transcript, seg_start, seg_end, lookback_ms=lookback)
        pos = _pause_tail_before_segment(words, min_pause_ms=min_pause, seg_start=seg_start)

    return _nudge_away_from_laughter(pos, laughter_windows or [], buffer_ms=200)


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

    before_seg = [w for w in words if int(w.get("end_ms", 0)) <= seg_start]
    if before_seg:
        return int(before_seg[-1]["end_ms"])

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


def _cue_uses_pause_alignment(cue: dict[str, Any], asset: dict[str, Any]) -> bool:
    if str(cue.get("trigger") or "") == "pause":
        return True
    role = str(asset.get("role") or "")
    return role in (
        "chapter_stinger",
        "rhetorical_punctuator",
        "transition_stinger",
        "transition_whoosh",
    )


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
    value_features = (
        ctx.read_json("understanding/value_features.json")
        if ctx.artifact_exists("understanding/value_features.json")
        else {}
    )
    laughter_windows = _laughter_windows_from_value_features(value_features if isinstance(value_features, dict) else None)
    source_pos = resolve_stinger_position_ms(
        segment,
        transcript,
        profile,
        placement=placement if placement in {"before_segment", "after_segment"} else "before_segment",
        laughter_windows=laughter_windows,
    )
    mapped = _source_ms_to_timeline_ms(source_pos, segment, segment_timing)
    if mapped is None:
        return pos
    ctx.log(
        f"mix: stinger_aligned pause_tail segment={seg_id} pos={mapped}",
        level="info",
        stage="mix",
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
    from interview_mux.placement_qa import apply_placement_adjustments

    cues = apply_placement_adjustments(ctx, [c for c in cues if isinstance(c, dict)])
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
            row: dict[str, Any] = {
                "audio": audio,
                "from_clip_rank": int(cue.get("from_clip_rank") or 0),
                "to_clip_rank": int(cue.get("to_clip_rank") or 0),
                "role": asset.get("role"),
            }
            if cue.get("crossfade_ms") is not None:
                row["crossfade_ms"] = int(cue["crossfade_ms"])
            out["between_clips"].append(row)
    return out


def resolve_between_clip_transition(
    cues: dict[str, Any], from_rank: int, to_rank: int
) -> tuple[AudioSegment | None, int | None]:
    between = cues.get("between_clips") or []
    default: AudioSegment | None = None
    default_cf: int | None = None
    for item in between:
        if not isinstance(item, dict):
            continue
        audio = item.get("audio")
        if not isinstance(audio, AudioSegment):
            continue
        if default is None:
            default = audio
            if item.get("crossfade_ms") is not None:
                default_cf = int(item["crossfade_ms"])
        if int(item.get("from_clip_rank") or 0) == from_rank and int(item.get("to_clip_rank") or 0) == to_rank:
            cf = int(item["crossfade_ms"]) if item.get("crossfade_ms") is not None else None
            return audio, cf
    return default, default_cf


def load_sound_design_plan(ctx: RunContext) -> dict:
    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        return {}
    try:
        data = ctx.read_json("understanding/sound_design_plan.json")
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def resolve_asset_path(ctx: RunContext, *, asset_id: str, generated: object) -> Path | None:
    if isinstance(generated, dict):
        rel = generated.get(asset_id)
        if isinstance(rel, str):
            candidate = ctx.read_path(rel)
            if candidate.is_file():
                return candidate
    for path in (
        ctx.read_path("sound_design", "assets", f"{asset_id}.wav"),
        ctx.read_path("master", "sfx", f"{asset_id}.wav"),
        ctx.read_path("flow_2_highlights", "sfx", f"{asset_id}.wav"),
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


def _adaptive_bed_level_db(ctx: RunContext, *, default_level_db: float) -> float:
    profile = load_profile(ctx)
    if not isinstance(profile, dict):
        return default_level_db
    pacing = profile.get("pacing") if isinstance(profile.get("pacing"), dict) else {}
    speech_active_ratio = float(pacing.get("speech_active_ratio") or 0.0)
    if speech_active_ratio >= 0.75:
        return min(default_level_db, -26.0)
    if speech_active_ratio >= 0.6:
        return min(default_level_db, -24.0)
    return default_level_db


def _preview_cue_for_asset(ctx: RunContext, asset_id: str) -> tuple[int, float, str]:
    """Return (position_ms, level_db, role) for under-speech preview audition."""
    default = (30_000, -20.0, "")
    plan = load_sound_design_plan(ctx)
    if not plan:
        return default
    segments = _segments_by_id(ctx)
    flow_plans = plan.get("flow_plans") if isinstance(plan.get("flow_plans"), dict) else {}
    for flow_key in ("flow1", "flow2"):
        flow = flow_plans.get(flow_key) if isinstance(flow_plans.get(flow_key), dict) else {}
        cues = flow.get("cues") if isinstance(flow.get("cues"), list) else []
        for cue in cues:
            if not isinstance(cue, dict) or str(cue.get("asset_id") or "") != asset_id:
                continue
            if cue.get("skip") is True:
                continue
            level_db = float(cue.get("level_db", -20.0))
            role = str(cue.get("role") or "")
            if cue.get("position_ms") is not None:
                return int(cue["position_ms"]), level_db, role
            if cue.get("start_ms") is not None:
                return int(cue["start_ms"]), level_db, role
            seg_id = str(cue.get("segment_id") or "")
            seg = segments.get(seg_id)
            if seg and seg.get("start_ms") is not None:
                return int(seg["start_ms"]), level_db, role
    return default


def render_sfx_under_speech_preview(ctx: RunContext, asset_id: str) -> Path:
    """Render a short speech + SFX overlay preview for operator post-listen."""
    asset_path = resolve_asset_path(ctx, asset_id=asset_id, generated=None)
    if asset_path is None or not asset_path.is_file():
        raise FileNotFoundError(f"SFX asset not found: {asset_id}")

    preview_dir = ctx.path("sound_design", "previews")
    preview_dir.mkdir(parents=True, exist_ok=True)
    out = preview_dir / f"{asset_id}_under_speech.wav"
    if out.is_file() and out.stat().st_mtime >= asset_path.stat().st_mtime:
        return out

    speech_path = next(
        (
            p
            for p in (
                ctx.read_path("ingest", "normalized.wav"),
                ctx.input_audio(),
            )
            if p.is_file()
        ),
        None,
    )
    if speech_path is None:
        raise FileNotFoundError("No speech source for under-speech preview")

    position_ms, level_db, role = _preview_cue_for_asset(ctx, asset_id)
    speech = load_audio(speech_path)
    sfx = load_audio(asset_path)

    preview_window_ms = 30_000
    window_start = max(0, position_ms - 5_000)
    window_end = min(len(speech), window_start + preview_window_ms)
    if window_end - window_start < 5_000:
        window_start = 0
        window_end = min(len(speech), preview_window_ms)
    speech_slice = speech[window_start:window_end]
    overlay_pos = max(0, position_ms - window_start)

    applied_level = level_db
    if role in {"bed", "ambient_bed"} and bool(_mix_cfg().get("adaptive_level_from_sap", True)):
        applied_level = _adaptive_bed_level_db(ctx, default_level_db=level_db)

    mixed = speech_slice.overlay(sfx.apply_gain(applied_level), position=overlay_pos)
    mixed.export(out, format="wav")
    return out
