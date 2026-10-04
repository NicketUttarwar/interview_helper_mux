"""Mix engine — full-master assembly with VO, beds, stingers, ducking (BUILD-065)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from pydub import AudioSegment

from interview_mux.acoustic_profile import load_profile, mix_contract, placement_hints
from interview_mux.audio_timeline import (
    append_with_crossfade,
    junction_crossfade_ms,
    organic_fade_in,
    organic_fade_out,
    snap_cut_to_word_boundary,
)
from interview_mux.config import merged_config
from interview_mux.master_qc import maybe_check_mix_intelligibility
from interview_mux.mix_completeness import enforce_mix_completeness
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.sonic_context import load_sonic_context

DEFAULT_FRAME_RATE = 48_000
MIN_DUCK_DB = 12.0


def _mix_cfg() -> dict[str, Any]:
    return merged_config().get("mix") or {}


def _music_presence_cfg() -> dict[str, Any]:
    raw = _mix_cfg().get("music_presence")
    return raw if isinstance(raw, dict) else {}


def _check_bed_presence_band(
    ctx: RunContext,
    *,
    assembly_path: Path,
    speech_stem: AudioSegment,
    segment_timing: dict[str, tuple[int, int]],
    contract: dict[str, Any],
    remux_cycle: int,
    overlays: list[dict[str, Any]] | None = None,
) -> str:
    """Write stem-aware A/B QC and return ``ok`` / ``remux_*`` / ``fail``."""
    del assembly_path, segment_timing
    from interview_mux.underbed_ab_qc import (
        analyze_underbed_ab_qc,
        underbed_eq_settings,
        underbed_qc_settings,
    )

    mix_cfg = _mix_cfg()
    settings = underbed_qc_settings(mix_cfg)
    if not settings["enabled"]:
        return "ok"
    eq = underbed_eq_settings(
        mix_cfg,
        depth_override_db=(
            float(contract["underbed_eq_depth_db"])
            if contract.get("underbed_eq_depth_db") is not None
            else None
        ),
    )
    report = analyze_underbed_ab_qc(
        speech_stem,
        list(overlays or []),
        mix_cfg=mix_cfg,
        eq_settings=eq,
    )
    report["remux_cycle"] = remux_cycle
    report["adjustments"] = {
        "bed_lift_db": float(contract.get("underbed_level_adjust_db") or 0.0),
        "carve_depth_db": float(eq["depth_db"]),
    }
    ctx.write_json("master/underbed_ab_qc.json", report)
    # Keep the established artifact path as a compact compatibility summary.
    legacy = {
        "version": 2,
        "ghost_windows": int(report["inaudible_windows"]),
        "drowning_windows": int(report["masking_windows"]),
        "windows_checked": int(report["windows_checked"]),
        "verdict": report["verdict"],
    }
    ctx.write_json("master/bed_presence_qc.json", legacy)

    verdict = str(report["verdict"])
    # S3: analyze + report only — no remux meta mutate / re-admit.
    # remux_* stays advisory (caller continues); fail_closed only for hard fail verdicts.
    if verdict in {"remux_masking", "remux_lift"}:
        ctx.log(
            f"mix: underbed {verdict} (no remux re-admit) — continue",
            level="warning",
            stage="mix",
            detail=report,
        )
        return verdict
    if verdict in {"fail", "fail_closed"} or (
        verdict not in {"ok", "pass"} and settings["fail_closed"]
    ):
        return "fail"
    return "ok"


def _bed_fade_ms(
    *,
    placement: str,
    cue: dict[str, Any],
    profile: dict[str, Any] | None,
) -> tuple[int, int, float]:
    """Return (fade_in_ms, fade_out_ms, curve) for under-segment beds.

    Explicit ``fade_in_ms`` / ``fade_out_ms`` on the cue always win. Otherwise
    ``crossfade_ms`` may only *lengthen* the organic speech-safe defaults —
    short placement-QA crossfades must not chop music tails into hard cuts.
    """
    presence = _music_presence_cfg()
    hints = placement_hints(profile)
    is_span = placement == "under_segment_span"
    default_in = int(
        presence.get("bed_fade_in_ms")
        or hints.get("bed_fade_in_ms")
        or (900 if is_span else 700)
    )
    default_out = int(
        presence.get("bed_span_fade_out_ms" if is_span else "bed_fade_out_ms")
        or hints.get("bed_fade_out_ms")
        or (3200 if is_span else 2200)
    )
    cue_xf = 0
    try:
        cue_xf = int(cue.get("crossfade_ms") or 0)
    except (TypeError, ValueError):
        cue_xf = 0
    if cue.get("fade_in_ms") is not None:
        try:
            fade_in = max(0, int(cue["fade_in_ms"]))
        except (TypeError, ValueError):
            fade_in = max(default_in, cue_xf)
    else:
        fade_in = max(default_in, cue_xf)
    if cue.get("fade_out_ms") is not None:
        try:
            fade_out = max(0, int(cue["fade_out_ms"]))
        except (TypeError, ValueError):
            fade_out = max(default_out, cue_xf)
    else:
        fade_out = max(default_out, cue_xf)
    curve = float(presence.get("bed_fade_curve") or 1.8)
    return fade_in, fade_out, curve


def _cold_open_bridge_budget_ms(ctx: RunContext) -> int:
    """Silence to reserve after preface VO for a speech-free theme_cold_open bridge."""
    presence = (_mix_cfg().get("music_presence") or {}) if isinstance(_mix_cfg(), dict) else {}
    air = int(presence.get("cold_open_air_ms") or 400)
    plan = load_sound_design_plan(ctx)
    assets = plan.get("assets") if isinstance(plan.get("assets"), list) else []
    dur_s = 0.0
    for a in assets:
        if isinstance(a, dict) and str(a.get("role") or "") == "theme_cold_open":
            try:
                dur_s = float(a.get("duration_seconds") or 0)
            except (TypeError, ValueError):
                dur_s = 0.0
            if dur_s > 0:
                break
    if dur_s <= 0:
        # Still reserve a short musical hinge when the asset list is incomplete.
        dur_s = 8.0
    return int(dur_s * 1000) + max(0, air)


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


def _speech_slice_start_ms(ctx: RunContext, start_ms: int, words: list[dict[str, Any]]) -> int:
    """Snap speech slice starts to word boundaries (mirrors end snap)."""
    if not bool(_mix_cfg().get("word_boundary_cuts", True)):
        return start_ms
    max_shift = int(_mix_cfg().get("word_boundary_max_shift_ms", 400))
    return snap_cut_to_word_boundary(start_ms, words, margin_ms=0, max_shift_ms=max_shift)


def _clamp_speech_slice_to_intentional(
    orig_start: int,
    orig_end: int,
    start: int,
    end: int,
    *,
    expand_tol_ms: int = 20,
) -> tuple[int, int]:
    """Keep word-boundary snap from expanding past intentional EDL/NLE bounds.

    Mix persists snapped source_* back into the live EDL; expanding past a
    producer cut (e.g. 97920→97970) reopens incomplete hanging tails.
    """
    if start < orig_start - expand_tol_ms:
        start = orig_start
    if end > orig_end + expand_tol_ms:
        end = orig_end
    if end < start:
        end = start
    return int(start), int(end)


def _append_mix_clip(
    base: AudioSegment,
    clip: AudioSegment,
    crossfade_ms: int,
) -> AudioSegment:
    adaptive = bool(_mix_cfg().get("adaptive_crossfade", True))
    return append_with_crossfade(base, clip, crossfade_ms, adaptive=adaptive)


def _level_match_vo(
    clip: AudioSegment,
    *,
    previous_native: AudioSegment | None = None,
    next_native: AudioSegment | None = None,
) -> AudioSegment:
    """Match synthetic speech to adjacent native speech only, with safe clamps."""
    if len(clip) <= 0:
        return clip
    raw = _mix_cfg().get("vo_adjacent_level_match")
    settings = raw if isinstance(raw, dict) else {}
    if not bool(settings.get("enabled", True)):
        return clip
    from interview_mux.speaker_level_match import apply_speaker_gain, measure_level_db

    window_ms = max(250, int(settings.get("reference_window_ms") or 4000))
    if previous_native is not None:
        previous_native = previous_native[max(0, len(previous_native) - window_ms) :]
    if next_native is not None:
        next_native = next_native[:window_ms]
    levels = [
        level
        for reference in (previous_native, next_native)
        if reference is not None
        for level in [measure_level_db(reference)]
        if level is not None
    ]
    target = sum(levels) / len(levels) if levels else -20.0
    current = measure_level_db(clip)
    if current is None:
        return clip
    max_gain = abs(float(settings.get("max_gain_db") or 8.0))
    gain = max(-max_gain, min(max_gain, target - current))
    return apply_speaker_gain(clip, gain)


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
    from interview_mux.music_listen_review import require_music_listen_for_mix
    from interview_mux.placement_qa import maybe_run_placement_qa
    from interview_mux.soundscape_policy import soundscape_enabled
    from interview_mux.soundscape_verify import run_soundscape_verify

    require_music_listen_for_mix(ctx)

    with logged_step("mix/placement_qa", ctx=ctx, stage="mix"):
        maybe_run_placement_qa(ctx)
        contract = mix_contract(ctx)
        # Intelligibility / presence remux hints via run_meta.
        try:
            if ctx.artifact_exists("run_meta.json"):
                meta = ctx.read_json("run_meta.json")
                if isinstance(meta, dict):
                    if meta.get("mix_intelligibility_remux_duck_db") is not None:
                        contract = {
                            **contract,
                            "duck_under_speech_db": float(
                                meta["mix_intelligibility_remux_duck_db"]
                            ),
                        }
                    if meta.get("mix_bed_presence_lift_db") is not None:
                        contract = {
                            **contract,
                            "bed_under_dialogue_db": float(
                                meta["mix_bed_presence_lift_db"]
                            ),
                        }
                    if meta.get("mix_underbed_carve_depth_db") is not None:
                        contract = {
                            **contract,
                            "underbed_eq_depth_db": float(
                                meta["mix_underbed_carve_depth_db"]
                            ),
                        }
                    if meta.get("mix_underbed_lift_db") is not None:
                        contract = {
                            **contract,
                            "underbed_level_adjust_db": float(
                                meta["mix_underbed_lift_db"]
                            ),
                        }
        except Exception:
            pass
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
        speech_join_crossfades = _flow1_speech_join_crossfades(ctx)
        words = _transcript_words(ctx)
        ctx.log("mix: loading EDL and ingest stem", level="info", stage="mix")
        edl = ctx.read_json("master/edl.json")
        if isinstance(edl, dict):
            from interview_mux.edl_source_contract import persist_sanitized_edl, sanitize_edl_source_paths

            # S2: sanitize ghost paths only — no listenability craft rewrite of live EDL.
            edl, ghosts = sanitize_edl_source_paths(ctx, edl)
            if ghosts:
                persist_sanitized_edl(ctx, edl)
        source = load_audio(ctx.read_path("ingest", "normalized.wav"))

    base = AudioSegment.silent(duration=0, frame_rate=DEFAULT_FRAME_RATE)
    segment_timing: dict[str, tuple[int, int]] = {}
    speech_count = 0
    vo_count = 0
    missing_vo: list[str] = []
    retried_vo: list[str] = []
    prev_speech_seg_id = ""
    live_vo_windows: list[tuple[int, int]] = []
    live_landmarks: dict[str, Any] = {
        "preface_end_ms": None,
        "first_question_start_ms": None,
        "first_speech_start_ms": None,
        "opening_music_window": None,
        "orientation_window": None,
        "orientation_bed_overlap_allowed": False,
        "vo_windows": live_vo_windows,
    }
    cold_bridge_ms = _cold_open_bridge_budget_ms(ctx)

    with logged_step("mix/build_base_timeline", ctx=ctx, stage="mix"):
        from interview_mux.speaker_level_match import (
            apply_speaker_gain,
            build_speaker_gains,
            gain_db_for_speaker,
            speaker_id_for_segment,
            speaker_level_match_cfg,
        )
        from interview_mux.music_lane import classify_vo_line

        speaker_gains = build_speaker_gains(ctx, source)
        if speaker_level_match_cfg().get("enabled") and speaker_gains:
            nonzero = {sid: g for sid, g in speaker_gains.items() if abs(g) >= 0.05}
            if nonzero:
                ctx.log(
                    f"mix: per-speaker level match applied to {len(nonzero)} speakers",
                    level="info",
                    stage="mix",
                    detail=nonzero,
                )

        clips = [c for c in (edl.get("clips") or []) if isinstance(c, dict)]
        last_vo_kind = ""
        previous_clip_kind = ""
        previous_native: AudioSegment | None = None

        def _next_native(start_index: int) -> AudioSegment | None:
            for future in clips[start_index + 1 :]:
                if str(future.get("type") or "") != "speech":
                    continue
                future_start = _speech_slice_start_ms(
                    ctx, int(future.get("source_start_ms") or 0), words
                )
                future_end = _speech_slice_end_ms(
                    ctx, int(future.get("source_end_ms") or future_start), words
                )
                if future_end <= future_start:
                    return None
                future_audio = source[future_start:future_end]
                future_sid = str(future.get("segment_id") or "")
                future_speaker = (
                    speaker_id_for_segment(ctx, future_sid) if future_sid else None
                )
                return apply_speaker_gain(
                    future_audio,
                    gain_db_for_speaker(speaker_gains, future_speaker),
                )
            return None

        junction_cfg = _mix_cfg().get("junction_crossfades")
        if not isinstance(junction_cfg, dict):
            junction_cfg = {}
        for idx, clip in enumerate(clips):
            ctype = str(clip.get("type") or "")
            t_before = len(base)
            if ctype == "speech":
                orig_start = int(clip.get("source_start_ms", 0))
                orig_end = int(clip.get("source_end_ms", orig_start))
                start = _speech_slice_start_ms(ctx, orig_start, words)
                end = _speech_slice_end_ms(ctx, orig_end, words)
                start, end = _clamp_speech_slice_to_intentional(
                    orig_start, orig_end, start, end
                )
                audio = source[max(0, start) : max(start, end)]
                seg_id = str(clip.get("segment_id") or "")
                spk = speaker_id_for_segment(ctx, seg_id) if seg_id else None
                audio = apply_speaker_gain(audio, gain_db_for_speaker(speaker_gains, spk))
                speech_count += 1
                join_key = (prev_speech_seg_id, seg_id) if prev_speech_seg_id and seg_id else None
                clip_crossfade = (
                    speech_join_crossfades[join_key]
                    if join_key and join_key in speech_join_crossfades
                    else crossfade_ms
                )
                if seg_id:
                    prev_speech_seg_id = seg_id
                window_ms = max(
                    250,
                    int(
                        ((_mix_cfg().get("vo_adjacent_level_match") or {}).get("reference_window_ms"))
                        or 4000
                    ),
                )
                previous_native = audio[max(0, len(audio) - window_ms) :]
            elif ctype == "vo_pickup":
                src_rel = clip.get("source_path")
                line_id = str(clip.get("line_id") or "")
                audio = None
                if src_rel:
                    vo_path = ctx.read_path(str(src_rel))
                    if vo_path.is_file():
                        audio = load_audio(vo_path)
                # S4: no last-chance synth — missing WAV is refuse, not heal.
                if audio is None:
                    audio = placeholder_from_clip(clip)
                    missing_vo.append(line_id or str(src_rel or "unknown"))
                    clip.pop("source_path", None)
                vo_count += 1
                clip_crossfade = crossfade_ms
                last_vo_kind = classify_vo_line(line_id)
            elif ctype == "transition":
                src_rel = clip.get("source_path")
                audio = None
                if src_rel:
                    tr_path = ctx.read_path(str(src_rel))
                    if tr_path.is_file():
                        audio = load_audio(tr_path)
                if audio is None and (src_rel or str(clip.get("text") or "").strip()):
                    # S4: no last-chance synth at mix.
                    if src_rel:
                        audio = placeholder_from_clip(clip)
                        missing_vo.append(f"transition:{src_rel}")
                        clip.pop("source_path", None)
                    else:
                        clip["timeline_start_ms"] = int(t_before)
                        clip["duration_ms"] = 0
                        clip["mix_overlap_ms"] = 0
                        continue
                elif audio is None:
                    # Text-less or silent transition marker — skip (zero duration).
                    clip["timeline_start_ms"] = int(t_before)
                    clip["duration_ms"] = 0
                    clip["mix_overlap_ms"] = 0
                    continue
                vo_count += 1
                clip_crossfade = crossfade_ms
                last_vo_kind = "other"
            elif ctype == "silence":
                from pydub import AudioSegment as _AS

                pad = max(0, int(clip.get("duration_ms") or 0))
                opening_music = (
                    str(clip.get("air_kind") or "") == "opening_music"
                    and bool(clip.get("preserve_planned_music"))
                    and not clip.get("omitted_theme_slot")
                )
                # Never expand opening_music air without an audible cold_open WAV.
                if opening_music and cold_bridge_ms > 0:
                    try:
                        from interview_mux.theme_slot_integrity import (
                            hollow_opening_music_finding,
                        )

                        if hollow_opening_music_finding(ctx) is None:
                            pad = max(pad, cold_bridge_ms)
                        else:
                            pad = 0
                    except Exception:
                        pad = max(pad, cold_bridge_ms)
                # After show-open preface, reserve air for a speech-free cold-open bridge
                # before the first question VO (hook → theme → question).
                if last_vo_kind == "preface" and cold_bridge_ms > 0:
                    nxt = clips[idx + 1] if idx + 1 < len(clips) else None
                    nxt_kind = (
                        classify_vo_line(str((nxt or {}).get("line_id") or ""))
                        if isinstance(nxt, dict) and str((nxt or {}).get("type") or "") == "vo_pickup"
                        else ""
                    )
                    if nxt_kind == "question":
                        pad = max(pad, cold_bridge_ms)
                if pad <= 0:
                    clip["timeline_start_ms"] = int(t_before)
                    clip["duration_ms"] = 0
                    clip["mix_overlap_ms"] = 0
                    continue
                audio = _AS.silent(duration=pad, frame_rate=getattr(base, "frame_rate", None) or 48000)
                clip_crossfade = 0
            else:
                clip["timeline_start_ms"] = int(t_before)
                clip["duration_ms"] = 0
                clip["mix_overlap_ms"] = 0
                continue
            if ctype in {"vo_pickup", "transition"}:
                audio = _level_match_vo(
                    audio,
                    previous_native=previous_native,
                    next_native=_next_native(idx),
                )
            typed_crossfade = junction_crossfade_ms(
                previous_clip_kind,
                ctype,
                config=junction_cfg,
                default_ms=clip_crossfade,
            )
            if not (
                ctype == "speech"
                and previous_clip_kind == "speech"
                and join_key
                and join_key in speech_join_crossfades
            ):
                clip_crossfade = typed_crossfade
            if len(base) == 0:
                base = audio
                overlap_ms = 0
            else:
                base = _append_mix_clip(base, audio, clip_crossfade)
                overlap_ms = max(0, t_before + len(audio) - len(base))
            previous_clip_kind = ctype
            t_start = t_before if t_before == 0 else max(0, t_before - int(overlap_ms or 0))
            t_end = len(base)
            clip["timeline_start_ms"] = int(t_start)
            clip["duration_ms"] = max(0, int(t_end) - int(t_start))
            clip["mix_overlap_ms"] = int(overlap_ms)
            if ctype == "speech":
                clip["source_start_ms"] = int(start)
                clip["source_end_ms"] = int(end)
            if ctype == "speech":
                seg_id = str(clip.get("segment_id") or "")
                if seg_id:
                    _update_segment_timing(segment_timing, seg_id, t_start, t_end)
                if live_landmarks.get("first_speech_start_ms") is None:
                    live_landmarks["first_speech_start_ms"] = t_start
            elif ctype == "vo_pickup":
                live_vo_windows.append((t_start, t_end))
                kind = classify_vo_line(str(clip.get("line_id") or ""))
                if kind == "preface":
                    pe = live_landmarks.get("preface_end_ms")
                    live_landmarks["preface_end_ms"] = t_end if pe is None else max(int(pe), t_end)
                    live_landmarks["orientation_window"] = (t_start, t_end)
                    live_landmarks["orientation_bed_overlap_allowed"] = bool(
                        clip.get("allow_music_bed_overlap")
                    )
                elif kind == "question" and live_landmarks.get("first_question_start_ms") is None:
                    live_landmarks["first_question_start_ms"] = t_start
            elif (
                ctype == "silence"
                and str(clip.get("air_kind") or "") == "opening_music"
            ):
                live_landmarks["opening_music_window"] = (t_start, t_end)

        if missing_vo:
            from interview_mux.loud_fail import raise_loud_failure

            # S4: refuse missing VO/transition WAV — pin synthesize, no mix heal.
            raise_loud_failure(
                ctx,
                "mix: missing VO WAV — resume vo_synthesize: "
                + ", ".join(sorted(set(missing_vo))[:8]),
                stage="mix",
                reason="missing_vo_wav",
                detail={
                    "missing_vo": sorted(set(missing_vo))[:12],
                    "resume": "vo_synthesize",
                },
            )
        if isinstance(edl, dict):
            edl["clips"] = clips
            edl["timeline_duration_ms"] = int(len(base))
            try:
                from interview_mux.air_order import write_live_edl

                write_live_edl(ctx, edl, source="mix_realized_times")
            except Exception as exc:
                ctx.log(
                    f"mix: failed to persist realized EDL times: {exc}",
                    level="warning",
                    stage="mix",
                )

        ctx.log(
            (
                f"mix: base timeline {len(base)} ms — "
                f"speech={speech_count}, vo={vo_count}, "
                f"segments={len(segment_timing)}, crossfade_ms={crossfade_ms}"
            ),
            level="info",
            stage="mix",
        )

    with logged_step("mix/apply_overlays", ctx=ctx, stage="mix"):
        landmarks = live_landmarks
        vo_excluded = list(landmarks.get("vo_windows") or [])
        overlays, overlay_stats = build_flow1_overlays(
            ctx,
            segment_timing=segment_timing,
            timeline_ms=len(base),
            contract=contract,
            speech_stem=base,
            excluded_windows=vo_excluded,
            vo_landmarks=landmarks,
        )
        mixed = base
        for cue in overlays:
            clip_audio = cue["audio"]
            if not isinstance(clip_audio, AudioSegment):
                continue
            pos = max(0, int(cue.get("position_ms", 0)))
            # pydub overlay truncates past len(mixed) — pad silence so outro /
            # cold-open overrun / preserve_full_duration cues remain audible.
            need = pos + len(clip_audio)
            if need > len(mixed):
                from pydub import AudioSegment as _ASPad

                pad_ms = need - len(mixed)
                mixed = mixed + _ASPad.silent(
                    duration=pad_ms,
                    frame_rate=mixed.frame_rate,
                )
            mixed = mixed.overlay(clip_audio, position=pos)

        post_overlay_timeline_ms = len(mixed)

        coverage_plan = load_sound_design_plan(ctx)
        coverage_assets = {
            str(row.get("asset_id") or ""): row
            for row in (coverage_plan.get("assets") or [])
            if isinstance(row, dict) and row.get("asset_id")
        }
        active_coverage_cues = [
            cue
            for cue in _flow_plan_cues(coverage_plan)
            if isinstance(cue, dict)
            and not cue.get("skip")
            and str(cue.get("asset_id") or "")
        ]
        # Drop cues anchored to segments that are not on the air timeline — they
        # cannot be realized and must not fail the mix as "missing" assets.
        placeable_coverage_cues: list[dict[str, Any]] = []
        for cue in active_coverage_cues:
            anchors = [
                str(cue.get("segment_id") or ""),
                str(cue.get("after_segment_id") or ""),
                str(cue.get("before_segment_id") or ""),
                *[str(x) for x in (cue.get("segment_ids") or []) if x],
            ]
            anchors = [a for a in anchors if a]
            if anchors and not any(a in segment_timing for a in anchors):
                continue
            placeable_coverage_cues.append(cue)
        intentionally_skipped_assets: set[str] = set()
        _, intentionally_skipped_assets = _filter_skipped_underscore_beds(
            placeable_coverage_cues,
            coverage_assets,
            underscore_policy=str(contract.get("underscore_policy") or ""),
        )
        planned_music_assets = {
            str(cue.get("asset_id") or "") for cue in placeable_coverage_cues
        } - intentionally_skipped_assets
        realized_music_assets = {
            str(cue.get("asset_id") or "")
            for cue in overlays
            if isinstance(cue, dict)
            and str(cue.get("asset_id") or "")
            and not cue.get("missing_asset")
        }
        # Realized requires audible bytes on disk (exec_11130: coverage lied).
        from interview_mux.theme_slot_integrity import theme_asset_audible

        realized_music_assets = {
            aid for aid in realized_music_assets if theme_asset_audible(ctx, aid)
        }
        missing_music_assets = sorted(planned_music_assets - realized_music_assets)
        # Lane exclusivity / stinger-cap may omit a generated stem from overlays.
        # Do not fail mix when the approved WAV exists on disk.
        sfx_dir = ctx.final_path("master", "sfx")
        assets_dir = ctx.final_path("sound_design", "assets")
        generated_ok: set[str] = set()
        for aid in missing_music_assets:
            for folder in (sfx_dir, assets_dir):
                wav = folder / f"{aid}.wav"
                try:
                    if wav.is_file() and wav.stat().st_size > 1000:
                        generated_ok.add(aid)
                        break
                except OSError:
                    continue
        if generated_ok:
            ctx.log(
                f"mix: generated but unplaced music assets (lane/cap): {sorted(generated_ok)}",
                level="warning",
                stage="mix",
            )
            missing_music_assets = [a for a in missing_music_assets if a not in generated_ok]
        realized_duration_rows = [
            {
                "asset_id": str(cue.get("asset_id") or ""),
                "music_role": cue.get("music_role"),
                "position_ms": int(cue.get("position_ms") or 0),
                "source_duration_ms": int(cue.get("source_duration_ms") or 0),
                "rendered_duration_ms": int(cue.get("rendered_duration_ms") or 0),
                "audible_end_ms": int(cue.get("position_ms") or 0)
                + int(cue.get("rendered_duration_ms") or 0),
                "preserve_full_duration": bool(cue.get("preserve_full_duration")),
            }
            for cue in overlays
            if isinstance(cue, dict) and str(cue.get("asset_id") or "")
        ]
        shortened_preserved_assets = sorted(
            {
                row["asset_id"]
                for row in realized_duration_rows
                if row["preserve_full_duration"]
                and (
                    row["rendered_duration_ms"] < row["source_duration_ms"]
                    or row["audible_end_ms"] > post_overlay_timeline_ms
                )
            }
        )
        ctx.write_json(
            "master/music_cue_coverage.json",
            {
                "version": 1,
                "planned_asset_ids": sorted(planned_music_assets),
                "realized_asset_ids": sorted(realized_music_assets),
                "missing_asset_ids": missing_music_assets,
                "shortened_preserved_asset_ids": shortened_preserved_assets,
                "realized_cues": realized_duration_rows,
                "intentionally_skipped_bed_asset_ids": sorted(
                    intentionally_skipped_assets
                ),
                "base_timeline_ms": len(base),
                "post_overlay_timeline_ms": post_overlay_timeline_ms,
                "preserved": not missing_music_assets
                and not shortened_preserved_assets,
            },
        )
        if missing_music_assets or shortened_preserved_assets:
            # HAU speech-first: beds deferred until MusicGen admit + remaster.
            speech_first = False
            try:
                from interview_mux.mix_junction_seat import beds_deferred_for_mix

                speech_first = bool(beds_deferred_for_mix(ctx))
            except Exception:
                speech_first = False
            if speech_first:
                ctx.log(
                    "mix: speech-first defer missing/shortened beds — "
                    + ", ".join(
                        [
                            *(f"missing:{x}" for x in missing_music_assets[:8]),
                            *(f"shortened:{x}" for x in shortened_preserved_assets[:8]),
                        ]
                    ),
                    level="warning",
                    stage="mix",
                )
            else:
                raise RuntimeError(
                    "mix: approved music assets missing or shortened: "
                    + ", ".join(
                        [
                            *(f"missing:{x}" for x in missing_music_assets),
                            *(f"shortened:{x}" for x in shortened_preserved_assets),
                        ]
                    )
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
        assembly.parent.mkdir(parents=True, exist_ok=True)
        mixed.export(str(assembly), format="wav")
        ctx.log(
            f"mix: assembly.wav ready ({len(mixed)} ms, VO + beds + stingers)",
            level="success",
            stage="mix",
            detail=str(assembly),
        )

    with logged_step("mix/post_mix_qc", ctx=ctx, stage="mix"):
        intel = maybe_check_mix_intelligibility(
            ctx,
            assembly_path=assembly,
            flow="podcast",
            stage="mix",
            speech_stem=base,
            segment_timing=segment_timing,
            contract=contract,
        )
        from interview_mux.master_qc import intelligibility_qc_config

        intel_cfg = intelligibility_qc_config()
        remux_on_fail = bool(intel_cfg.get("remux_on_fail", False))
        # S3: single render + refuse — no recursive remux re-admit.
        if intel is not None and not intel.ok and remux_on_fail:
            raise RuntimeError(
                "mix intelligibility QC failed: "
                + ", ".join(intel.flagged_segment_ids or intel.failures[:6] or ["unknown"])
            )
        # Ghost-bed presence: beds under speech must stay in audible band.
        presence = _check_bed_presence_band(
            ctx,
            assembly_path=assembly,
            speech_stem=base,
            segment_timing=segment_timing,
            contract=contract,
            remux_cycle=remux_cycle,
            overlays=overlays,
        )
        if presence.startswith("remux"):
            ctx.log(
                f"mix: bed presence advisory ({presence}) — no remux re-admit",
                level="warning",
                stage="mix",
            )
        elif presence == "fail":
            raise RuntimeError("mix bed presence QC failed (ghost or drowning beds)")
        if soundscape_enabled():
            report = run_soundscape_verify(ctx, remux_cycle=remux_cycle)
            if report.get("verdict") == "remediate":
                ctx.log(
                    "mix: soundscape remediate advisory — no remux re-admit",
                    level="warning",
                    stage="mix",
                )
            if report.get("verdict") == "fail_closed":
                raise RuntimeError(
                    "soundscape_verify fail_closed: " + "; ".join(report.get("failures") or [])
                )
        # overlay_stats["missing_assets"] is a count (int); completeness wants ids.
        # Honest limbo omits (operator/music_omitted.json) are not missing SFX.
        omitted_music: set[str] = set()
        try:
            if ctx.artifact_exists("operator/music_omitted.json"):
                doc = ctx.read_json("operator/music_omitted.json")
                for row in (doc.get("omitted") or []) if isinstance(doc, dict) else []:
                    if isinstance(row, dict) and row.get("asset_id"):
                        omitted_music.add(str(row["asset_id"]))
        except Exception:
            pass
        missing_sfx_ids = [
            str(o.get("asset_id") or "")
            for o in overlays
            if isinstance(o, dict)
            and o.get("missing_asset")
            and o.get("asset_id")
            and str(o.get("asset_id") or "") not in omitted_music
        ]
        enforce_mix_completeness(
            ctx,
            flow="podcast",
            stage="mix",
            missing_vo=missing_vo,
            missing_sfx=missing_sfx_ids,
            retried_vo=retried_vo,
        )
        from interview_mux.listenability_guards import (
            evaluate_listenability,
            write_listenability_contract,
        )

        edl_doc = ctx.read_json("master/edl.json") if ctx.artifact_exists("master/edl.json") else None
        listen_report = evaluate_listenability(ctx, edl=edl_doc if isinstance(edl_doc, dict) else None, stage="mix")
        write_listenability_contract(ctx, listen_report)
        try:
            from interview_mux.listen_quality import evaluate_listen_critic

            ordered = []
            if isinstance(edl_doc, dict):
                ordered = [str(s) for s in (edl_doc.get("ordered_segment_ids") or []) if s]
            if not ordered and ctx.artifact_exists("master/selection.json"):
                sel = ctx.read_json("master/selection.json")
                ordered = [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]
            health = (
                ctx.read_json("master/story_health.json")
                if ctx.artifact_exists("master/story_health.json")
                else None
            )
            hook_id = None
            by_id: dict = {}
            narr = None
            gap = None
            sdp = None
            if ctx.artifact_exists("understanding/episode_structure.json"):
                try:
                    es = ctx.read_json("understanding/episode_structure.json")
                    if isinstance(es, dict):
                        hook_id = es.get("hook_segment_id")
                except Exception:
                    pass
            if ctx.artifact_exists("segments/manifest.json"):
                man = ctx.read_json("segments/manifest.json")
                by_id = {
                    str(s["segment_id"]): s
                    for s in ((man or {}).get("segments") or [])
                    if isinstance(s, dict) and s.get("segment_id")
                }
            if ctx.artifact_exists("master/narrative_plan.json"):
                narr = ctx.read_json("master/narrative_plan.json")
            if ctx.artifact_exists("understanding/gap_report.json"):
                gap = ctx.read_json("understanding/gap_report.json")
            if ctx.artifact_exists("understanding/sound_design_plan.json"):
                sdp = ctx.read_json("understanding/sound_design_plan.json")
            critic = evaluate_listen_critic(
                ordered=ordered,
                edl=edl_doc if isinstance(edl_doc, dict) else None,
                story_health=health if isinstance(health, dict) else None,
                hook_segment_id=str(hook_id) if hook_id else None,
                segments_by_id=by_id or None,
                narrative_plan=narr if isinstance(narr, dict) else None,
                gap_report=gap if isinstance(gap, dict) else None,
                sound_design_plan=sdp if isinstance(sdp, dict) else None,
            )
            ctx.write_json("master/listen_critic.json", critic)
            if critic.get("g_listen_recommended"):
                # C14: do not re-arm G-Listen after refused_low_gain remutate.
                refuse_rearm = False
                try:
                    if ctx.artifact_exists("mastering/listen_delight_remutate.json"):
                        rem = ctx.read_json("mastering/listen_delight_remutate.json")
                        if isinstance(rem, dict) and str(rem.get("status") or "") == "refused_low_gain":
                            refuse_rearm = True
                except Exception:
                    refuse_rearm = False
                if not refuse_rearm:
                    def _glisten(m: dict) -> None:
                        if m.get("g_listen_skipped") or m.get("g_listen_cleared"):
                            return
                        m["g_listen_pending"] = True
                        m["g_listen_quality_score"] = critic.get("quality_score")

                    ctx.mutate_run_meta(_glisten)
                    ctx.log(
                        f"G-Listen recommended (score={critic.get('quality_score')}) — "
                        "optional operator listen before master_finalize",
                        level="warning",
                        stage="mix",
                    )
                    # Full-auto: clear after successful mix (incl. remaster remux).
                    # Partial keeps pending so finalize can block.
                    from interview_mux.gates import maybe_auto_clear_g_listen_for_full_auto

                    maybe_auto_clear_g_listen_for_full_auto(
                        ctx,
                        stage="mix",
                        reason="full_auto_after_successful_mix",
                    )
            if critic.get("verdict") == "warn":
                ctx.log(
                    f"listen_critic warn: {critic.get('warning_count')} issue(s)",
                    level="warning",
                    stage="mix",
                    detail=(critic.get("issues") or [])[:6],
                )
        except Exception as exc:
            ctx.log(f"listen_critic skipped: {exc}", level="warning", stage="mix")
        if listen_report.get("verdict") == "fail":
            from interview_mux.creative_delivery import creative_delivery_required
            from interview_mux.aspirational_quality import (
                apply_best_quality_candidate,
                family_attempts_exhausted,
                increment_family_attempt,
                is_aspirational_enabled,
                record_quality_advisories,
                register_quality_candidate,
            )

            msg = "listenability_contract: " + "; ".join(listen_report.get("failures") or [])
            aspirational = is_aspirational_enabled(ctx)
            try:
                from interview_mux.floor_progress import listenability_aspirational

                aspirational = aspirational or listenability_aspirational(ctx)
            except Exception:
                pass
            if aspirational:
                register_quality_candidate(ctx, family="listenability")
                increment_family_attempt(ctx, "listenability")
                if family_attempts_exhausted(ctx, "listenability"):
                    apply_best_quality_candidate(ctx, family="listenability")
                listen_report["verdict"] = "warning"
                listen_report["aspirational_fail"] = True
                listen_report["blocking"] = False
                write_listenability_contract(ctx, listen_report)
                record_quality_advisories(
                    ctx,
                    gate_id="listenability_contract",
                    failed_checks=list(listen_report.get("failures") or []),
                    detail={"stage": "mix"},
                    aspirational_proceeded=family_attempts_exhausted(ctx, "listenability"),
                )
                try:
                    from interview_mux.floor_progress import record_floor_advisory

                    record_floor_advisory(
                        ctx,
                        "listenability_contract",
                        {
                            "failures": list(listen_report.get("failures") or [])[:8],
                            "stage": "mix",
                        },
                        aspirational_proceeded=True,
                        mirror_quality=False,
                    )
                except Exception:
                    pass
                ctx.log(msg + " (aspirational advisory)", level="warning", stage="mix")
            elif listen_report.get("fail_closed") and creative_delivery_required():
                import os

                soft = os.environ.get("MUX_E2E_SOFT_LISTENABILITY", "").strip().lower() in {
                    "1",
                    "true",
                    "yes",
                }
                if not soft:
                    try:
                        meta = (
                            ctx.read_json("run_meta.json")
                            if ctx.artifact_exists("run_meta.json")
                            else {}
                        )
                        soft = bool(
                            isinstance(meta, dict)
                            and (
                                meta.get("e2e_soft_listenability")
                                or meta.get("e2e_soft_ship_listenability")
                            )
                        )
                    except Exception:
                        soft = False
                if soft:
                    listen_report["verdict"] = "warning"
                    listen_report["e2e_soft_ship"] = True
                    write_listenability_contract(ctx, listen_report)
                    ctx.log(msg + " (e2e soft-ship)", level="warning", stage="mix")
                else:
                    ctx.log(msg, level="error", stage="mix")
                    raise RuntimeError(msg)
            else:
                ctx.log(msg, level="warning", stage="mix")
    try:
        from interview_mux.write_staging import promote_staged_side_effects

        promote_staged_side_effects(ctx, ("master/assembly.wav",), stage_id="mix")
    except Exception as exc:
        ctx.log(f"mix: assembly promote skipped: {exc}", level="warning", stage="mix")
    try:
        from interview_mux.seam_autopsy import write_render_ledger

        write_render_ledger(ctx)
        from interview_mux.air_order import stamp_after_mix

        stamp_after_mix(ctx)
    except Exception as exc:
        ctx.log(f"render_ledger write skipped: {exc}", level="warning", stage="mix")
    # HX-2: write_live_edl / staging flush can leave assembly.wav older than
    # edl.json even when this render produced both — seat mtime before mark_done
    # so junction remaster does not inherit authority_denied:mark_done:hollow:mix.
    try:
        from interview_mux.air_order import (
            ensure_assembly_mtime_seats_edl,
            mix_outputs_seated,
        )

        ensure_assembly_mtime_seats_edl(ctx)
        if not mix_outputs_seated(ctx):
            ctx.log(
                "mix: outputs not fully seated (mtime+commitment) — refuse mark_done",
                level="warning",
                stage="mix",
            )
            from interview_mux.done_authority import require_seated_before_mix_mark

            require_seated_before_mix_mark(ctx)
    except RuntimeError:
        raise
    except Exception as exc:
        ctx.log(f"mix: assembly mtime seat skipped: {exc}", level="warning", stage="mix")
        from interview_mux.done_authority import require_seated_before_mix_mark

        # Fail closed: seating check crash must not hollow-stamp mix.
        require_seated_before_mix_mark(ctx)
    from interview_mux.done_authority import try_mark_done

    if not try_mark_done(ctx, "mix"):
        raise RuntimeError(
            "mix mark_done refused (AuthorityDenied / hollow) — "
            "assembly render is not seed-complete"
        )
    try:
        from interview_mux.mix_junction_seat import clear_remaster, close_preview_music_gate

        clear_remaster(ctx)
        close_preview_music_gate(ctx)
    except Exception:
        pass
    # Mode C: endless per-run timeline optimizer (defaults auto-start)
    try:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        if isinstance(meta, dict) and meta.get("timeline_optimizer_remastering"):
            # Clear remastering flag; do not nest another daemon start from sync remaster
            def _clear(m: dict) -> None:
                m["timeline_optimizer_remastering"] = False

            ctx.mutate_run_meta(_clear)
        else:
            from interview_mux.timeline_optimizer.config import optimizer_cfg
            from interview_mux.timeline_optimizer.daemon import (
                is_optimizer_running,
                start_optimizer_daemon,
            )

            ocfg = optimizer_cfg()
            if (
                ocfg.get("enabled")
                and ocfg.get("auto_start_after_mix")
                and not is_optimizer_running(ctx.run_id)
            ):
                res = start_optimizer_daemon(ctx)
                ctx.log(
                    f"timeline_optimizer daemon: {res}",
                    level="info",
                    stage="mix",
                )

                def _opt_meta(m: dict) -> None:
                    m["timeline_optimizer"] = {
                        "auto_started": True,
                        "mode": "endless_daemon",
                        "mutation_surface": "maximum",
                    }

                ctx.mutate_run_meta(_opt_meta)
    except Exception as exc:
        ctx.log(f"timeline_optimizer start skipped: {exc}", level="warning", stage="mix")
    return assembly


def mix_flow2(ctx: RunContext) -> Path:
    """Removed — Flow 2 highlight montage is no longer in the pipeline."""
    raise RuntimeError("Flow 2 removed")


def build_flow1_overlays(
    ctx: RunContext,
    *,
    segment_timing: dict[str, tuple[int, int]],
    timeline_ms: int,
    contract: dict[str, Any] | None = None,
    excluded_windows: list[tuple[int, int]] | None = None,
    speech_stem: AudioSegment | None = None,
    vo_landmarks: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Build mix overlays. Authority: SDP when plan has cues; legacy only when no SDP plan.

    Never invent legacy beds when SDP planned cues but assets are missing — use
    placeholders and report missing_assets truthfully (DEEP-MIX-01).
    """
    contract = contract or mix_contract(ctx)
    plan = load_sound_design_plan(ctx)
    sdp_cues = _flow_plan_cues(plan) if plan else []
    has_sdp_plan = bool(plan) and bool(sdp_cues)
    overlays = flow1_overlays_from_sdp(
        ctx,
        segment_timing=segment_timing,
        contract=contract,
        excluded_windows=excluded_windows or [],
        speech_stem=speech_stem,
        vo_landmarks=vo_landmarks,
    )
    stats = count_overlay_roles(overlays)
    missing = sum(1 for o in overlays if isinstance(o, dict) and o.get("missing_asset"))
    stats["missing_assets"] = int(missing)
    if overlays:
        stats["overlay_authority"] = "sdp_placeholders" if missing else "sdp_realized"
        return overlays, stats
    if has_sdp_plan:
        # SDP existed but realized empty (assets missing / all skipped) — no legacy invent.
        stats["overlay_authority"] = "none"
        return [], stats
    legacy = flow1_overlays_legacy(ctx, segment_timing=segment_timing, timeline_ms=timeline_ms)
    stats = count_overlay_roles(legacy)
    stats["missing_assets"] = sum(
        1 for o in legacy if isinstance(o, dict) and o.get("missing_asset")
    )
    stats["overlay_authority"] = "legacy_fallback" if legacy else "none"
    return legacy, stats


def _flow_plan_cues(plan: dict[str, Any]) -> list[Any]:
    flow_plans = plan.get("flow_plans") if isinstance(plan.get("flow_plans"), dict) else {}
    flow = flow_plans.get("podcast") if isinstance(flow_plans.get("podcast"), dict) else {}
    if not flow and isinstance(flow_plans.get("flow1"), dict):
        flow = flow_plans["flow1"]
    cues = flow.get("cues") if isinstance(flow.get("cues"), list) else []
    return cues


def _filter_skipped_underscore_beds(
    cues: list[dict[str, Any]],
    assets_by_id: dict[str, dict[str, Any]],
    *,
    underscore_policy: str,
) -> tuple[list[dict[str, Any]], set[str]]:
    """A skip-underscore contract removes beds, never bookends/punctuators."""
    if str(underscore_policy) != "skip":
        return list(cues), set()
    from interview_mux.music_lane import (
        LANE_BED,
        effective_cue_role,
        music_lane_for_role,
    )

    kept: list[dict[str, Any]] = []
    skipped_assets: set[str] = set()
    for cue in cues:
        asset_id = str(cue.get("asset_id") or "")
        lane = music_lane_for_role(
            effective_cue_role(cue, assets_by_id.get(asset_id, {}))
        )
        if lane == LANE_BED:
            if asset_id:
                skipped_assets.add(asset_id)
            continue
        kept.append(cue)
    return kept, skipped_assets


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
    speech_stem: AudioSegment | None = None,
    vo_landmarks: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    contract = contract or mix_contract(ctx)
    excluded = list(excluded_windows or [])
    skip_beds = contract.get("underscore_policy") == "skip"
    profile = load_profile(ctx)
    transcript = _load_transcript(ctx)
    segments_by_id = _segments_by_id(ctx)
    plan = load_sound_design_plan(ctx)
    if not plan:
        return []
    cues = _flow_plan_cues(plan)
    from interview_mux.placement_qa import apply_placement_adjustments
    from interview_mux.music_lane import (
        apply_music_lane_exclusivity,
        bind_cues_to_theme_assets,
        collapse_duplicate_music_cues,
        cold_open_position_ms,
        effective_cue_role,
        music_lane_for_role,
        vo_open_landmarks_from_edl,
        LANE_PUNCTUATOR,
    )

    cues = apply_placement_adjustments(ctx, [c for c in cues if isinstance(c, dict)])
    assets = plan.get("assets") if isinstance(plan.get("assets"), list) else []
    cues, bind_actions = bind_cues_to_theme_assets(cues, [a for a in assets if isinstance(a, dict)])
    assets_by_id = {
        str(a.get("asset_id")): a for a in assets if isinstance(a, dict) and a.get("asset_id")
    }
    if skip_beds:
        before_count = len(cues)
        cues, _skipped_assets = _filter_skipped_underscore_beds(
            cues,
            assets_by_id,
            underscore_policy="skip",
        )
        ctx.log(
            f"mix: underscore_skipped — removed {before_count - len(cues)} bed cue(s); "
            "preserving bookends and punctuators",
            level="info",
            stage="mix",
        )
    cues, collapse_actions = collapse_duplicate_music_cues(cues, assets_by_id)
    if bind_actions or collapse_actions:
        ctx.log(
            f"mix: music_lane bind={len(bind_actions)} collapse={len(collapse_actions)}",
            level="info",
            stage="mix",
        )
    landmarks = vo_landmarks
    if landmarks is None and ctx.artifact_exists("master/edl.json"):
        try:
            edl_doc = ctx.read_json("master/edl.json")
            landmarks = vo_open_landmarks_from_edl(edl_doc if isinstance(edl_doc, dict) else None)
        except (OSError, json.JSONDecodeError, TypeError):
            landmarks = {}
    landmarks = landmarks or {}
    if not excluded and landmarks.get("vo_windows"):
        excluded = list(landmarks["vo_windows"])
    out: list[dict[str, Any]] = []
    # The policy states a rate (0.4/min on exec_017); int() truncated it to 0,
    # so every planned stinger was dropped ("stinger cap reached (0/timeline)")
    # (ISSUES 165). Rate times real timeline minutes, at least one when the
    # rate allows any.
    stinger_rate = float(contract.get("stinger_max_per_minute", 4) or 0.0)
    timeline_minutes = max(
        1.0, max((end for _s, end in segment_timing.values()), default=60000) / 60000.0
    )
    max_stingers = int(stinger_rate * timeline_minutes) if stinger_rate > 0 else 0
    if stinger_rate > 0:
        max_stingers = max(1, max_stingers)
    stinger_count = 0
    duck_default = float(contract.get("duck_under_speech_db", 16.0))
    underbed_level_adjust_db = float(contract.get("underbed_level_adjust_db") or 0.0)
    sonic = load_sonic_context(ctx) or {}
    scenario = sonic.get("scenario") if isinstance(sonic.get("scenario"), dict) else {}
    atlas_bucket = str(scenario.get("atlas_bucket") or "")
    segment_flags = sonic.get("segment_flags") if isinstance(sonic.get("segment_flags"), dict) else {}
    overlap_high = {str(x) for x in (segment_flags.get("overlap_high") or [])}
    # Accents / overlapping bookends still sidechain. Underbeds use a constant
    # level plus EQ carve — a 12 dB speech-gate was pumping and burying them.
    _verb_skip_bed = {"silence_as_transition"}

    # Consecutive per-segment beds using the same motif are one musical scene,
    # not dozens of independently faded clips. Collapse them before rendering.
    ordered_timing_ids = list(segment_timing.keys())
    order_pos = {sid: i for i, sid in enumerate(ordered_timing_ids)}
    rendered_cues: list[dict[str, Any]] = []
    for raw_cue in cues:
        if not isinstance(raw_cue, dict):
            continue
        cue = dict(raw_cue)
        if str(cue.get("placement") or "") != "under_segment":
            rendered_cues.append(cue)
            continue
        sid = str(cue.get("segment_id") or "")
        if not sid:
            rendered_cues.append(cue)
            continue
        if rendered_cues:
            music_cfg = (merged_config().get("mastering") or {}).get("music_continuity") or {}
            prev = rendered_cues[-1]
            prev_ids = [str(x) for x in (prev.get("segment_ids") or []) if x]
            prev_sid = prev_ids[-1] if prev_ids else str(prev.get("segment_id") or "")
            contiguous = (
                bool(music_cfg.get("prefer_contiguous_beds", True))
                and str(prev.get("placement") or "") in {"under_segment", "under_segment_span"}
                and str(prev.get("asset_id") or "") == str(cue.get("asset_id") or "")
                and prev_sid in order_pos
                and sid in order_pos
                and order_pos[sid] == order_pos[prev_sid] + 1
            )
            if contiguous:
                scene_xf = int(music_cfg.get("scene_crossfade_ms") or 1800)
                merged = dict(prev)
                merged["placement"] = "under_segment_span"
                merged["segment_ids"] = [*(prev_ids or [prev_sid]), sid]
                merged["crossfade_ms"] = max(
                    scene_xf,
                    int(prev.get("crossfade_ms") or 0),
                    int(cue.get("crossfade_ms") or 0),
                )
                rendered_cues[-1] = merged
                continue
        rendered_cues.append(cue)

    for cue in rendered_cues:
        if not isinstance(cue, dict):
            continue
        asset_id = str(cue.get("asset_id") or "")
        asset = assets_by_id.get(asset_id, {})
        wav = resolve_asset_path(ctx, asset_id=asset_id, generated=plan.get("generated"))
        placement = str(cue.get("placement") or "")
        raw_level = cue.get("level_db")
        level_db = float(raw_level) if raw_level is not None else -25.0
        from interview_mux.creative_delivery import audibility_level_db
        from interview_mux.music_motif import THEME_BED_ROLES, THEME_PUNCTUATOR_ROLES, is_theme_role

        asset_role_early = effective_cue_role(cue, asset)
        if placement in {"under_segment", "under_segment_span"} or asset_role_early in THEME_BED_ROLES:
            level_db = audibility_level_db(role="bed", default=level_db)
        elif is_theme_role(asset_role_early) or asset_role_early in THEME_PUNCTUATOR_ROLES:
            # Role-aware hotter bookends / accents.
            level_db = audibility_level_db(
                role=asset_role_early or "stinger",
                default=max(level_db, -14.0 if asset_role_early in {"theme_cold_open", "theme_outro"} else -16.0),
            )
        elif placement == "under_segment":
            level_db = audibility_level_db(role="bed", default=level_db)
        else:
            level_db = audibility_level_db(role="stinger", default=level_db)
        from interview_mux.tbiy_mix import apply_pan_position, tbiy_level_adjustment_db

        level_db += tbiy_level_adjustment_db(ctx, cue, asset)
        if cue.get("skip") is True:
            continue

        if wav is None:
            from interview_mux.theme_slot_integrity import (
                is_speech_free_theme_role,
                refuse_silent_theme_overlay,
            )

            # HAU speech-first: omit missing theme beds; remaster after MusicGen.
            try:
                from interview_mux.mix_junction_seat import beds_deferred_for_mix

                if beds_deferred_for_mix(ctx) and is_speech_free_theme_role(
                    asset_role_early
                ):
                    ctx.log(
                        f"mix: speech-first skip missing theme {asset_id!r}",
                        level="info",
                        stage="mix",
                    )
                    continue
            except Exception:
                pass
            silent_err = refuse_silent_theme_overlay(
                role=asset_role_early,
                asset_id=asset_id,
                missing_asset=True,
            )
            if silent_err:
                raise RuntimeError(silent_err)
            base = placeholder_audio(asset, cue=cue)
            ctx.log(
                f"mix: missing asset {asset_id!r} — placeholder silence",
                level="warning",
                stage="mix",
            )
            missing_asset = True
        else:
            base = load_audio(wav)
            missing_asset = False
            from interview_mux.theme_slot_integrity import (
                is_speech_free_theme_role,
                refuse_silent_theme_overlay,
            )

            silent_err = refuse_silent_theme_overlay(
                role=asset_role_early,
                asset_id=asset_id,
                missing_asset=False,
                audio=base,
            )
            if silent_err:
                try:
                    from interview_mux.mix_junction_seat import beds_deferred_for_mix

                    if beds_deferred_for_mix(ctx) and is_speech_free_theme_role(
                        asset_role_early
                    ):
                        ctx.log(
                            f"mix: speech-first skip inaudible theme {asset_id!r}",
                            level="info",
                            stage="mix",
                        )
                        continue
                except Exception:
                    pass
                raise RuntimeError(silent_err)

        if placement in {"under_segment", "under_segment_span"}:
            span_ids = [str(x) for x in (cue.get("segment_ids") or []) if x]
            if not span_ids:
                span_ids = [str(cue.get("segment_id") or "")]
            timings = [segment_timing.get(sid) for sid in span_ids]
            timings = [t for t in timings if t]
            if not timings:
                continue
            seg_id = span_ids[0]
            if atlas_bucket == "panel" and seg_id in overlap_high:
                continue
            start_ms = int(timings[0][0])
            end_ms = int(timings[-1][1])
            orientation_window = landmarks.get("orientation_window")
            if (
                bool(landmarks.get("orientation_bed_overlap_allowed"))
                and isinstance(orientation_window, (list, tuple))
                and len(orientation_window) == 2
            ):
                orientation_end = int(orientation_window[1])
                body_start = min(
                    (
                        int(window[0])
                        for window in segment_timing.values()
                        if int(window[0]) >= orientation_end
                    ),
                    default=min(
                        (int(window[0]) for window in segment_timing.values()),
                        default=start_ms,
                    ),
                )
                if start_ms == body_start:
                    start_ms = min(start_ms, int(orientation_window[0]))
            dur = max(0, end_ms - start_ms)
            if dur <= 0:
                continue
            if bool((_mix_cfg()).get("adaptive_level_from_sap", True)):
                level_db = _adaptive_bed_level_db(ctx, default_level_db=level_db)
            level_db += underbed_level_adjust_db
            verb = str(cue.get("music_transition") or "").strip()
            if verb in _verb_skip_bed:
                continue
            fade_in, fade_out, fade_curve = _bed_fade_ms(
                placement=placement, cue=cue, profile=profile if isinstance(profile, dict) else None
            )
            # Keep a little body when the bed is short; still prefer long tails.
            fade_in = min(fade_in, max(40, dur // 3))
            fade_out = min(fade_out, max(80, (dur * 2) // 3))
            bed = loop_to_duration(base, dur)
            bed = apply_pan_position(bed, cue.get("pan_position"))
            from interview_mux.underbed_ab_qc import (
                apply_underbed_eq,
                underbed_eq_settings,
            )

            eq_settings = underbed_eq_settings(
                _mix_cfg(),
                depth_override_db=(
                    float(contract["underbed_eq_depth_db"])
                    if contract.get("underbed_eq_depth_db") is not None
                    else None
                ),
            )
            bed = apply_underbed_eq(bed, eq_settings)
            bed = bed.apply_gain(level_db)
            bed = organic_fade_in(bed, fade_in, curve=fade_curve)
            bed = organic_fade_out(bed, fade_out, curve=fade_curve)
            out.append(
                {
                    "audio": bed,
                    "position_ms": start_ms,
                    "role": "bed",
                    "music_role": "theme_underscore",
                    "asset_id": asset_id,
                    "cue_id": str(cue.get("cue_id") or ""),
                    "segment_ids": span_ids,
                    "level_db": level_db,
                    "duck_db": 0.0,
                    "underbed_eq": eq_settings,
                    "missing_asset": bool(missing_asset),
                }
            )
            continue

        asset_role = effective_cue_role(cue, asset)
        if _cue_uses_pause_alignment(cue, asset):
            if stinger_count >= max_stingers:
                ctx.log(
                    f"mix: stinger cap reached ({max_stingers}/timeline) — dropped {asset_id}",
                    level="warning",
                    stage="mix",
                )
                continue
            stinger_count += 1

        presence = _music_presence_cfg()
        fade_in = int(cue.get("crossfade_ms") or 80)
        fade_out = max(
            int(cue.get("crossfade_ms") or 0),
            int(presence.get("stinger_fade_out_ms") or 350),
        )
        if asset_role in {"theme_cold_open", "theme_outro"}:
            fade_in = max(fade_in, int(presence.get("cold_open_lead_in_fade_ms") or 900))
            fade_out = max(fade_out, int(presence.get("bookend_fade_out_ms") or 1800))
            base = enhance_speech_free_theme(base, role=asset_role)
        elif asset_role in {"theme_emphasis", "theme_chapter_resolve", "theme_transition"}:
            fade_out = max(fade_out, int(presence.get("accent_fade_out_ms") or 600))
            base = enhance_speech_free_theme(base, role=asset_role)
        # Short punctuators must keep a body — don't let long organic tails eat the hit.
        body_ms = max(1, len(base))
        fade_in = min(fade_in, max(20, body_ms // 5))
        fade_out = min(fade_out, max(40, body_ms // 3))
        cue_audio = organic_fade_in(base.apply_gain(level_db), fade_in)
        cue_audio = organic_fade_out(cue_audio, fade_out)
        cue_audio = apply_pan_position(cue_audio, cue.get("pan_position"))
        pos = flow1_cue_position(
            cue=cue,
            segment_timing=segment_timing,
            role=asset_role,
            vo_landmarks=landmarks,
            theme_duration_ms=len(cue_audio),
        )
        # Musical cold open: always prefer post-hook air gap placement.
        if asset_role == "theme_cold_open":
            air_ms = int(presence.get("cold_open_air_ms") or 400)
            opening_window = landmarks.get("opening_music_window")
            if (
                isinstance(opening_window, (list, tuple))
                and len(opening_window) == 2
                and int(opening_window[1]) > int(opening_window[0])
                and len(cue_audio)
                > int(opening_window[1]) - int(opening_window[0])
            ):
                ctx.log(
                    "mix: opening music exceeds protected air; preserving full "
                    "duration with speech ducking",
                    level="info",
                    stage="mix",
                    detail={
                        "asset_id": asset_id,
                        "music_duration_ms": len(cue_audio),
                        "protected_air_ms": int(opening_window[1])
                        - int(opening_window[0]),
                    },
                )
            pos = cold_open_position_ms(
                theme_duration_ms=len(cue_audio),
                landmarks=landmarks,
                segment_timing=segment_timing,
                air_ms=air_ms,
            )
            if speech_stem is not None and len(speech_stem) > 0:
                from interview_mux.sidechain_duck import duck_bed_with_sidechain

                speech_window = speech_stem[
                    max(0, int(pos)) : max(0, int(pos)) + len(cue_audio)
                ]
                cue_audio = duck_bed_with_sidechain(
                    cue_audio,
                    speech_window,
                    level_db=0.0,
                    duck_db=max(
                        MIN_DUCK_DB,
                        float(cue.get("duck_under_speech_db") or duck_default),
                    ),
                )
        if pos is None:
            pos = max(0, max((v[1] for v in segment_timing.values()), default=0) - 50)
        if asset_role != "theme_cold_open" and _cue_uses_pause_alignment(cue, asset):
            dur_s = float(asset.get("duration_seconds") or 0.4)
            musical_punct = asset_role in THEME_PUNCTUATOR_ROLES or is_theme_role(asset_role)
            legacy_sting = asset_role in ("chapter_stinger", "transition_stinger", "transition_whoosh")
            if musical_punct or legacy_sting:
                cue_audio = cue_audio[: int(max(dur_s, 4.0 if musical_punct else 0.4) * 1000)]
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
        # Accents over speech must sidechain-duck after final position is known.
        if (
            asset_role in {"theme_emphasis", "theme_chapter_resolve", "theme_transition"}
            and speech_stem is not None
            and len(speech_stem) > 0
            and pos is not None
        ):
            from interview_mux.sidechain_duck import duck_bed_with_sidechain

            speech_window = speech_stem[
                max(0, int(pos)) : max(0, int(pos)) + len(cue_audio)
            ]
            if len(speech_window) > 0 and float(speech_window.dBFS) > -48.0:
                cue_audio = duck_bed_with_sidechain(
                    cue_audio,
                    speech_window,
                    level_db=0.0,
                    duck_db=max(
                        MIN_DUCK_DB,
                        float(cue.get("duck_under_speech_db") or duck_default),
                    ),
                )
        lane = music_lane_for_role(asset_role)
        # Punctuators must not start inside VO pickups (bookends may use post-hook air).
        if lane == LANE_PUNCTUATOR and excluded:
            attack_ms = min(len(cue_audio), 500)
            if _overlaps_excluded(int(pos), attack_ms, excluded):
                continue
        if asset_role == "rhetorical_punctuator":
            role = "punctuator"
        elif asset_role in THEME_BED_ROLES:
            role = "bed"
        elif asset_role in {"theme_cold_open", "theme_outro"}:
            role = "theme"
        elif is_theme_role(asset_role):
            role = "theme_punctuator"
        else:
            role = "bridge" if placement == "before_segment" else "stinger"
        if asset_role in {"theme_cold_open", "theme_outro"} and missing_asset:
            from interview_mux.theme_slot_integrity import refuse_silent_theme_overlay

            try:
                from interview_mux.mix_junction_seat import beds_deferred_for_mix

                if beds_deferred_for_mix(ctx):
                    continue
            except Exception:
                pass
            err = refuse_silent_theme_overlay(
                role=asset_role, asset_id=asset_id, missing_asset=True
            )
            if err:
                raise RuntimeError(err)
        out.append(
            {
                "audio": cue_audio,
                "position_ms": pos,
                "role": role,
                "music_role": asset_role,
                "asset_id": asset_id,
                "source_duration_ms": body_ms,
                "rendered_duration_ms": len(cue_audio),
                "preserve_full_duration": asset_role
                in {"theme_cold_open", "theme_outro"}
                and not missing_asset,
                "missing_asset": bool(missing_asset),
            }
        )
        # Chapter-hinge breathe: dry micro-gap after resolve before speech resumes.
        if asset_role == "theme_chapter_resolve":
            breathe_ms = int(presence.get("chapter_resolve_breathe_ms") or 220)
            if breathe_ms > 0:
                out.append(
                    {
                        "audio": AudioSegment.silent(duration=breathe_ms, frame_rate=DEFAULT_FRAME_RATE),
                        "position_ms": int(pos) + len(cue_audio),
                        "role": "breathe",
                    }
                )

    realized = apply_music_lane_exclusivity(out)
    for overlay in realized:
        audio = overlay.get("audio") if isinstance(overlay, dict) else None
        if audio is None or not hasattr(audio, "__len__"):
            continue
        rendered_ms = len(audio)
        overlay["rendered_duration_ms"] = rendered_ms
        if overlay.get("preserve_full_duration") and rendered_ms < int(
            overlay.get("source_duration_ms") or rendered_ms
        ):
            raise RuntimeError(
                "mix: preserve_full_duration music cue was shortened: "
                + str(overlay.get("asset_id") or "unknown")
            )
    return realized


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
    out.append(
        {
            "audio": organic_fade_out(
                organic_fade_in(bed.apply_gain(-36.0), 400),
                900,
            ),
            "position_ms": 0,
            "role": "bed",
        }
    )
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
        sting = organic_fade_out(
            organic_fade_in(load_audio(path).apply_gain(-18.0), 60),
            350,
        )
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
    from interview_mux.music_lane import effective_cue_role

    if str(cue.get("trigger") or "") == "pause":
        return True
    role = effective_cue_role(cue, asset)
    if role == "theme_cold_open":
        return False
    return role in (
        "theme_emphasis",
        "theme_chapter_resolve",
        "theme_transition",
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


def flow1_cue_position(
    *,
    cue: dict,
    segment_timing: dict[str, tuple[int, int]],
    role: str | None = None,
    vo_landmarks: dict[str, Any] | None = None,
    theme_duration_ms: int | None = None,
) -> int | None:
    from interview_mux.music_lane import cold_open_position_ms, effective_cue_role

    placement = str(cue.get("placement") or "")
    resolved_role = str(role or effective_cue_role(cue) or "")
    # Cold open theme: post-hook air when landmarks exist; else timeline lead-in.
    if resolved_role == "theme_cold_open" or placement in {"cold_open", "show_open"}:
        if vo_landmarks and (
            vo_landmarks.get("preface_end_ms") is not None
            or vo_landmarks.get("first_question_start_ms") is not None
        ):
            return cold_open_position_ms(
                theme_duration_ms=int(theme_duration_ms or 8000),
                landmarks=vo_landmarks,
                segment_timing=segment_timing,
            )
        if segment_timing:
            first = min(v[0] for v in segment_timing.values())
            return max(0, first - 80)
        return 0
    # Chapter / hinge punctuators: prefer after_segment hinge, never spoken "Chapter N"
    if resolved_role in {"theme_chapter_resolve", "theme_transition", "rhetorical_punctuator"}:
        after = str(cue.get("after_segment_id") or cue.get("segment_id") or "")
        before = str(cue.get("before_segment_id") or "")
        if after and after in segment_timing:
            return segment_timing[after][1]
        if before and before in segment_timing:
            return segment_timing[before][0]
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
    """Removed — Flow 2 cue extraction is no longer in the pipeline."""
    raise RuntimeError("Flow 2 removed")


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


def enhance_speech_free_theme(segment: AudioSegment, *, role: str) -> AudioSegment:
    """Stereo width + gentle high shelf for cold open / outro / accents (beds stay mono)."""
    from interview_mux.music_motif import THEME_BED_ROLES, is_theme_role

    role_s = str(role or "")
    if role_s in THEME_BED_ROLES or role_s == "theme_underscore":
        return segment.set_channels(1)
    if not is_theme_role(role_s) and role_s not in {"theme_cold_open", "theme_outro", "theme_emphasis", "theme_chapter_resolve", "theme_transition"}:
        return segment
    cfg = _music_presence_cfg()
    width = float(cfg.get("speech_free_stereo_width") or 0.35)
    shelf_db = float(cfg.get("speech_free_high_shelf_db") or 1.5)
    # Mild presence EQ via high-pass residual blend (pydub-safe, no extra deps).
    bright = segment.high_pass_filter(int(cfg.get("speech_free_high_shelf_hz") or 6000)).apply_gain(shelf_db)
    mixed = segment.overlay(bright)
    # Pseudo-stereo: duplicate with slight delay/pan.
    if width > 0.01:
        delay_ms = max(8, int(18 * width))
        left = mixed
        right = AudioSegment.silent(duration=delay_ms, frame_rate=mixed.frame_rate) + mixed
        right = right[: len(left)]
        if len(right) < len(left):
            right = right + AudioSegment.silent(duration=len(left) - len(right), frame_rate=mixed.frame_rate)
        stereo = AudioSegment.from_mono_audiosegments(left, right)
        return stereo
    return mixed.set_channels(1)


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
    from interview_mux.creative_delivery import (
        _bed_level_band,
        audibility_level_db,
        creative_delivery_required,
    )

    default_level_db = audibility_level_db(role="bed", default=default_level_db)
    # Prefer the quiet end of the constant bed band under dense speech.
    lo, hi = _bed_level_band()
    if not creative_delivery_required():
        lo, hi = lo - 2.0, hi - 2.0
    profile = load_profile(ctx)
    if not isinstance(profile, dict):
        return default_level_db
    pacing = profile.get("pacing") if isinstance(profile.get("pacing"), dict) else {}
    speech_active_ratio = float(pacing.get("speech_active_ratio") or 0.0)
    if speech_active_ratio >= 0.75:
        return min(default_level_db, lo)
    if speech_active_ratio >= 0.6:
        return min(default_level_db, (lo + hi) / 2.0)
    return default_level_db


def _preview_cue_for_asset(ctx: RunContext, asset_id: str) -> tuple[int, float, str]:
    """Return (position_ms, level_db, role) for under-speech preview audition."""
    default = (30_000, -20.0, "")
    plan = load_sound_design_plan(ctx)
    if not plan:
        return default
    segments = _segments_by_id(ctx)
    flow_plans = plan.get("flow_plans") if isinstance(plan.get("flow_plans"), dict) else {}
    for flow_key in ("podcast", "flow1"):
        flow = flow_plans.get(flow_key) if isinstance(flow_plans.get(flow_key), dict) else {}
        cues = flow.get("cues") if isinstance(flow.get("cues"), list) else []
        for cue in cues:
            if not isinstance(cue, dict) or str(cue.get("asset_id") or "") != asset_id:
                continue
            if cue.get("skip") is True:
                continue
            raw_level = cue.get("level_db")
            level_db = float(raw_level) if raw_level is not None else -20.0
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
