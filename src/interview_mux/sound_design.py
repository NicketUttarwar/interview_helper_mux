"""Mix engine — full-master assembly with VO, beds, stingers, ducking (BUILD-065)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from pydub import AudioSegment

from interview_mux.acoustic_profile import load_profile, mix_contract, placement_hints
from interview_mux.audio_timeline import append_with_crossfade, snap_cut_to_word_boundary
from interview_mux.config import merged_config
from interview_mux.master_qc import maybe_check_mix_intelligibility
from interview_mux.mix_completeness import enforce_mix_completeness
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.sonic_context import load_sonic_context

DEFAULT_FRAME_RATE = 48_000
MIN_DUCK_DB = 18.0


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
        speech_join_crossfades = _flow1_speech_join_crossfades(ctx)
        words = _transcript_words(ctx)
        ctx.log("mix: loading EDL and ingest stem", level="info", stage="mix")
        edl = ctx.read_json("master/edl.json")
        source = load_audio(ctx.read_path("ingest", "normalized.wav"))

    base = AudioSegment.silent(duration=0, frame_rate=DEFAULT_FRAME_RATE)
    segment_timing: dict[str, tuple[int, int]] = {}
    speech_count = 0
    vo_count = 0
    missing_vo: list[str] = []
    prev_speech_seg_id = ""

    with logged_step("mix/build_base_timeline", ctx=ctx, stage="mix"):
        from interview_mux.speaker_level_match import (
            apply_speaker_gain,
            build_speaker_gains,
            gain_db_for_speaker,
            speaker_id_for_segment,
            speaker_level_match_cfg,
        )

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

        for clip in edl.get("clips") or []:
            ctype = str(clip.get("type") or "")
            if ctype == "speech":
                start = int(clip.get("source_start_ms", 0))
                end = _speech_slice_end_ms(ctx, int(clip.get("source_end_ms", start)), words)
                audio = source[max(0, start) : max(start, end)]
                seg_id = str(clip.get("segment_id") or "")
                spk = speaker_id_for_segment(ctx, seg_id) if seg_id else None
                audio = apply_speaker_gain(audio, gain_db_for_speaker(speaker_gains, spk))
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
            elif ctype == "transition":
                src_rel = clip.get("source_path")
                if src_rel:
                    tr_path = ctx.read_path(str(src_rel))
                    if tr_path.is_file():
                        audio = load_audio(tr_path)
                    else:
                        audio = placeholder_from_clip(clip)
                        missing_vo.append(f"transition:{src_rel}")
                else:
                    # Text-less or silent transition marker — skip (zero duration).
                    continue
                vo_count += 1
                clip_crossfade = crossfade_ms
            elif ctype == "silence":
                from pydub import AudioSegment as _AS

                pad = max(0, int(clip.get("duration_ms") or 0))
                if pad <= 0:
                    continue
                audio = _AS.silent(duration=pad, frame_rate=getattr(base, "frame_rate", None) or 48000)
                clip_crossfade = 0
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
                f"speech={speech_count}, vo={vo_count}, "
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
            speech_stem=base,
        )
        mixed = base
        for cue in overlays:
            clip_audio = cue["audio"]
            if not isinstance(clip_audio, AudioSegment):
                continue
            pos = max(0, int(cue.get("position_ms", 0)))
            mixed = mixed.overlay(clip_audio, position=pos)

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
                def _glisten(m: dict) -> None:
                    m["g_listen_pending"] = True
                    m["g_listen_quality_score"] = critic.get("quality_score")

                ctx.mutate_run_meta(_glisten)
                ctx.log(
                    f"G-Listen recommended (score={critic.get('quality_score')}) — "
                    "optional operator listen before master_finalize",
                    level="warning",
                    stage="mix",
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

            msg = "listenability_contract: " + "; ".join(listen_report.get("failures") or [])
            if listen_report.get("fail_closed") and creative_delivery_required():
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
    ctx.mark_done("mix")
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
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    contract = contract or mix_contract(ctx)
    overlays = flow1_overlays_from_sdp(
        ctx,
        segment_timing=segment_timing,
        contract=contract,
        excluded_windows=excluded_windows or [],
        speech_stem=speech_stem,
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
    speech_stem: AudioSegment | None = None,
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
    # Soft map episode_structure music_transition verbs → duck / level nudge
    _verb_duck = {
        "under_speech": duck_default,
        "into_speech": max(duck_default, 18.0),
        "around_vo": max(duck_default, 20.0),
        "silence_as_transition": 99.0,
        "resolve_swell": max(8.0, duck_default - 4.0),
        "tension_hold": duck_default + 2.0,
    }

    for cue in cues:
        if not isinstance(cue, dict):
            continue
        asset_id = str(cue.get("asset_id") or "")
        asset = assets_by_id.get(asset_id, {})
        wav = resolve_asset_path(ctx, asset_id=asset_id, generated=plan.get("generated"))
        placement = str(cue.get("placement") or "")
        level_db = float(cue.get("level_db", -28.0))
        from interview_mux.creative_delivery import audibility_level_db
        from interview_mux.music_motif import THEME_BED_ROLES, THEME_PUNCTUATOR_ROLES, is_theme_role

        asset_role_early = str(asset.get("role") or cue.get("role") or "")
        if placement == "under_segment" or asset_role_early in THEME_BED_ROLES:
            level_db = audibility_level_db(role="bed", default=level_db)
        elif is_theme_role(asset_role_early) or asset_role_early in THEME_PUNCTUATOR_ROLES:
            # Cold open / resolve / emphasis slightly hotter than beds.
            if asset_role_early in {"theme_cold_open", "theme_chapter_resolve", "theme_outro"}:
                level_db = audibility_level_db(role="stinger", default=max(level_db, -14.0))
            else:
                level_db = audibility_level_db(role="stinger", default=level_db)
        elif placement == "under_segment":
            level_db = audibility_level_db(role="bed", default=level_db)
        else:
            level_db = audibility_level_db(role="stinger", default=level_db)
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
            verb = str(cue.get("music_transition") or "").strip()
            duck_for_cue = float(_verb_duck.get(verb, duck_default))
            if verb == "silence_as_transition":
                continue
            duck_db = max(MIN_DUCK_DB, tbiy_duck_db(ctx, cue, duck_for_cue))
            fade_in = int(cue.get("crossfade_ms") or 120)
            fade_out = int(cue.get("crossfade_ms") or 150)
            bed = loop_to_duration(base, dur)
            bed = apply_pan_position(bed, cue.get("pan_position"))
            speech_window = None
            if speech_stem is not None and len(speech_stem) > 0:
                speech_window = speech_stem[max(0, start_ms) : max(start_ms, end_ms)]
            from interview_mux.sidechain_duck import duck_bed_with_sidechain

            bed = duck_bed_with_sidechain(
                bed,
                speech_window,
                level_db=level_db,
                duck_db=duck_db,
            )
            bed = bed.fade_in(fade_in).fade_out(fade_out)
            out.append({"audio": bed, "position_ms": start_ms, "role": "bed"})
            continue

        asset_role = str(asset.get("role") or cue.get("role") or "")
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
        # Musical cold open: lead-in before first speech when no anchor resolved.
        if asset_role == "theme_cold_open" and (pos is None or pos < 80):
            pos = 0
        if pos is None:
            pos = max(0, max((v[1] for v in segment_timing.values()), default=0) - 50)
        if _cue_uses_pause_alignment(cue, asset):
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
        if excluded and _overlaps_excluded(int(pos), len(cue_audio), excluded):
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
    role = str(asset.get("role") or cue.get("role") or "")
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


def flow1_cue_position(*, cue: dict, segment_timing: dict[str, tuple[int, int]]) -> int | None:
    placement = str(cue.get("placement") or "")
    role = str(cue.get("role") or "")
    # Cold open theme always leads the timeline when placement is ambiguous
    if role == "theme_cold_open" or placement in {"cold_open", "show_open"}:
        if segment_timing:
            first = min(v[0] for v in segment_timing.values())
            return max(0, first - 80)
        return 0
    # Chapter / hinge punctuators: prefer after_segment hinge, never spoken "Chapter N"
    if role in {"theme_chapter_resolve", "theme_transition", "rhetorical_punctuator"}:
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
    from interview_mux.creative_delivery import audibility_level_db, creative_delivery_required

    default_level_db = audibility_level_db(role="bed", default=default_level_db)
    if creative_delivery_required():
        return default_level_db
    profile = load_profile(ctx)
    if not isinstance(profile, dict):
        return default_level_db
    pacing = profile.get("pacing") if isinstance(profile.get("pacing"), dict) else {}
    speech_active_ratio = float(pacing.get("speech_active_ratio") or 0.0)
    if speech_active_ratio >= 0.75:
        return min(default_level_db, -30.0)
    if speech_active_ratio >= 0.6:
        return min(default_level_db, -28.0)
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
