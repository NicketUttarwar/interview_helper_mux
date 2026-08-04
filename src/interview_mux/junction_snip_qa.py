"""Mastering Junction Snips — deterministic edge QA + one final feel LLM.

Plan 2 (v2): every timeline junction is evaluated with transcript/energy signals
(zero per-edge OpenAI). A single ``junction_feel_audit`` LLM pass judges how the
assembled master feels. Remaster is bounded (≤2).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.audio_timeline import snap_cut_to_word_boundary
from interview_mux.config import merged_config
from interview_mux.gap_vo_prior_context import (
    ends_complete_thought,
    is_micro_segment,
    looks_like_impact_beat,
    prior_context_cfg,
)
from interview_mux.nle_state import load_nle, save_nle
from interview_mux.run_context import RunContext

QA_REL = "master/junction_snip_qa.json"
FEEL_REL = "master/junction_feel_audit.json"
STAGE_ID = "junction_snip_qa"
FEEL_STAGE_KEY = "junction_feel_audit"
FEEL_PROMPT = "mastering/junction-feel-audit.system.txt"

_BACKCHANNEL_RE = re.compile(
    r"^(okay|ok|yeah|yep|uh.?huh|mm+|mhm|right|sure|got it|i see)[.!?,]*$",
    re.IGNORECASE,
)

ALLOWED_FEEL_ACTIONS = frozenset(
    {
        "nudge_source_bounds",
        "insert_impact_hold",
        "clamp_air",
        "adjust_music_fade",
        "adjust_crossfade",
        "exclude_micro",
        "retarget_vo_anchor",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def junction_snip_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = (cfg or merged_config()).get("mastering") or {}
    block = raw.get("junction_snip_qa") if isinstance(raw.get("junction_snip_qa"), dict) else {}
    defaults: dict[str, Any] = {
        "mode": "advisory",  # off | advisory | authoritative
        "micro_nudge_ms": 2500,
        "phrase_extend_max_ms": 8000,
        "impact_hold_ms_min": 1200,
        "impact_hold_ms_max": 3500,
        "feel_audit_enabled": True,
        "max_remaster_rounds": 2,
        "apply_repairs": True,
        "music_soft_crossfade_ms": 180,
        "dead_air_clamp_ms": 2500,
        "pace_multipliers": {
            "sparse": 1.25,
            "fireside": 1.2,
            "balanced": 1.0,
            "dense": 0.85,
            "debate": 0.8,
        },
    }
    return {**defaults, **block}


def _pace_class(ctx: RunContext) -> str:
    if ctx.artifact_exists("understanding/source_acoustic_profile.json"):
        sap = ctx.read_json("understanding/source_acoustic_profile.json")
        if isinstance(sap, dict):
            for key in ("pace_class", "pacing_class", "delivery_pace"):
                val = str(sap.get(key) or "").strip().lower()
                if val:
                    return val
    sonic = (
        ctx.read_json("understanding/sonic_context.json")
        if ctx.artifact_exists("understanding/sonic_context.json")
        else {}
    )
    if isinstance(sonic, dict):
        scenario = sonic.get("scenario") if isinstance(sonic.get("scenario"), dict) else {}
        bucket = str(scenario.get("atlas_bucket") or "").lower()
        if bucket in {"fireside", "debate", "panel", "media_profile"}:
            return "fireside" if bucket == "fireside" else ("debate" if bucket in {"debate", "panel"} else "dense")
    return "balanced"


def _pace_mult(cfg: dict[str, Any], pace: str) -> float:
    table = cfg.get("pace_multipliers") if isinstance(cfg.get("pace_multipliers"), dict) else {}
    try:
        return float(table.get(pace) or table.get("balanced") or 1.0)
    except (TypeError, ValueError):
        return 1.0


def _segments_by_id(ctx: RunContext) -> dict[str, dict[str, Any]]:
    from interview_mux.nle_state import segments_by_id_with_nle

    return segments_by_id_with_nle(ctx)


def _transcript_words(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists("transcript/full.json"):
        return []
    full = ctx.read_json("transcript/full.json")
    words = full.get("words") or []
    return [w for w in words if isinstance(w, dict)] if isinstance(words, list) else []


def _text_in_window(words: list[dict[str, Any]], start_ms: int, end_ms: int) -> str:
    parts: list[str] = []
    for w in words:
        ws = int(w.get("start_ms") or 0)
        we = int(w.get("end_ms") or 0)
        if we < start_ms or ws > end_ms:
            continue
        t = str(w.get("text") or w.get("word") or "").strip()
        if t:
            parts.append(t)
    return " ".join(parts)


def _chapter_id_for(segment_id: str, selection: dict[str, Any]) -> str | None:
    for ch in selection.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        ids = [str(s) for s in (ch.get("segment_ids") or [])]
        if segment_id in ids:
            return str(ch.get("chapter_id") or ch.get("id") or ch.get("title") or "")
    return None


def _speaker_of(seg: dict[str, Any] | None) -> str:
    if not isinstance(seg, dict):
        return ""
    return str(seg.get("speaker_id") or seg.get("speaker") or "")


def _clip_end_text(seg: dict[str, Any] | None, words: list[dict[str, Any]], end_ms: int) -> str:
    if isinstance(seg, dict) and str(seg.get("text") or "").strip():
        text = str(seg.get("text") or "").strip()
        # Prefer last ~12 words of segment text for clause checks
        toks = text.split()
        return " ".join(toks[-12:]) if len(toks) > 12 else text
    return _text_in_window(words, max(0, end_ms - 4000), end_ms)


def _on_a_roll(
    *,
    seg: dict[str, Any],
    end_ms: int,
    words: list[dict[str, Any]],
    phrase_extend_max_ms: int,
) -> bool:
    speaker = _speaker_of(seg)
    if not speaker:
        return False
    # Look ahead on source continuum for same-speaker words with little pause
    ahead = [
        w
        for w in words
        if int(w.get("start_ms") or 0) >= end_ms - 40
        and int(w.get("start_ms") or 0) <= end_ms + phrase_extend_max_ms
        and str(w.get("speaker_id") or w.get("speaker") or speaker) == speaker
    ]
    if not ahead:
        # words may lack speaker_id — fall back to any words continuing quickly
        ahead = [
            w
            for w in words
            if end_ms <= int(w.get("start_ms") or 0) <= end_ms + min(1500, phrase_extend_max_ms)
        ]
    if not ahead:
        return False
    first_start = int(ahead[0].get("start_ms") or 0)
    gap = first_start - end_ms
    return gap < 450


def _find_phrase_end_ms(
    words: list[dict[str, Any]],
    from_ms: int,
    *,
    max_extend_ms: int,
    speaker: str = "",
) -> int | None:
    """Extend to the first word end that completes a thought within the window."""
    window = [
        w
        for w in words
        if from_ms < int(w.get("end_ms") or 0) <= from_ms + max_extend_ms
    ]
    if speaker:
        filtered = [
            w
            for w in window
            if not w.get("speaker_id") or str(w.get("speaker_id") or "") == speaker
        ]
        if filtered:
            window = filtered
    if not window:
        return None
    accumulated: list[str] = []
    for w in window:
        tok = str(w.get("text") or w.get("word") or "").strip()
        if tok:
            accumulated.append(tok)
        candidate = " ".join(accumulated)
        if ends_complete_thought(candidate) and candidate[-1:] in ".!?…":
            return int(w.get("end_ms") or 0)
        # Soft: stop at pause after content word
        if ends_complete_thought(candidate) and len(accumulated) >= 3:
            return int(w.get("end_ms") or 0)
    # Last complete word boundary in window if we gained content
    if accumulated and ends_complete_thought(" ".join(accumulated)):
        return int(window[-1].get("end_ms") or 0)
    return None


def _find_last_complete_phrase_end(
    words: list[dict[str, Any]],
    end_ms: int,
    *,
    max_lookback_ms: int,
) -> int | None:
    window = [
        w
        for w in words
        if end_ms - max_lookback_ms <= int(w.get("end_ms") or 0) <= end_ms
    ]
    if not window:
        return None
    # Walk backward for a terminal-punctuation word or soft-complete boundary
    for i in range(len(window) - 1, -1, -1):
        toks = [
            str(w.get("text") or w.get("word") or "").strip()
            for w in window[: i + 1]
            if str(w.get("text") or w.get("word") or "").strip()
        ]
        text = " ".join(toks)
        if not text:
            continue
        last = toks[-1]
        if last[-1:] in ".!?…" or ends_complete_thought(text):
            # Prefer true sentence end when available
            if last[-1:] in ".!?…" or i < len(window) - 1:
                return int(window[i].get("end_ms") or 0)
    return None


def _leading_trailing_silence(
    ctx: RunContext,
    start_ms: int,
    end_ms: int,
    *,
    search_ms: int,
) -> tuple[int | None, int | None]:
    """Return recommended start/end if leading/trailing silence valleys are better."""
    wav = None
    try:
        wav = ctx.read_path("ingest", "normalized.wav")
    except Exception:
        return None, None
    if not wav or not Path(wav).is_file():
        return None, None
    from interview_mux.audio_energy import find_silence_valley_ms, rms_at_ms

    new_start = None
    new_end = None
    try:
        # Leading silence: if head is quiet, snap start forward to valley near first energy
        head_rms = rms_at_ms(Path(wav), start_ms + 80)
        if head_rms is not None and head_rms < 0.01:
            valley = find_silence_valley_ms(Path(wav), start_ms, search_ms=min(search_ms, 800))
            # Prefer moving start later into content — search slightly ahead
            forward = find_silence_valley_ms(
                Path(wav), start_ms + min(400, search_ms // 2), search_ms=min(search_ms, 600)
            )
            if forward > start_ms:
                new_start = forward
            elif valley != start_ms:
                new_start = valley
        tail_rms = rms_at_ms(Path(wav), max(start_ms, end_ms - 80))
        if tail_rms is not None and tail_rms < 0.01:
            valley = find_silence_valley_ms(Path(wav), end_ms, search_ms=min(search_ms, 800))
            if valley < end_ms:
                new_end = valley
    except Exception:
        return None, None
    return new_start, new_end


def detect_junction_findings(
    ctx: RunContext,
    edl: dict[str, Any],
    *,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Deterministic detectors for every speech junction — no OpenAI."""
    conf = cfg or junction_snip_cfg()
    pace = _pace_class(ctx)
    mult = _pace_mult(conf, pace)
    micro_nudge = int(int(conf["micro_nudge_ms"]) * mult)
    phrase_max = int(int(conf["phrase_extend_max_ms"]) * mult)
    hold_min = int(int(conf["impact_hold_ms_min"]) * mult)
    hold_max = int(int(conf["impact_hold_ms_max"]) * mult)
    dead_air_clamp = int(int(conf["dead_air_clamp_ms"]) * mult)

    segs = _segments_by_id(ctx)
    words = _transcript_words(ctx)
    selection = (
        ctx.read_json("master/selection.json")
        if ctx.artifact_exists("master/selection.json")
        else {}
    )
    if not isinstance(selection, dict):
        selection = {}
    prior_cfg = prior_context_cfg()
    mix_cfg = merged_config().get("mix") or {}
    margin = int(mix_cfg.get("word_boundary_margin_ms", 50))
    max_shift = int(mix_cfg.get("word_boundary_max_shift_ms", 400))

    clips = [c for c in (edl.get("clips") or []) if isinstance(c, dict)]
    findings: list[dict[str, Any]] = []

    def add(
        kind: str,
        *,
        severity: str = "warn",
        segment_id: str | None = None,
        clip_index: int | None = None,
        action: str,
        detail: dict[str, Any] | None = None,
        evidence: str = "",
    ) -> None:
        findings.append(
            {
                "kind": kind,
                "severity": severity,
                "segment_id": segment_id,
                "clip_index": clip_index,
                "action": action,
                "detail": detail or {},
                "evidence": evidence,
            }
        )

    for i, clip in enumerate(clips):
        ctype = str(clip.get("type") or "")
        if ctype == "speech":
            sid = str(clip.get("segment_id") or "")
            seg = segs.get(sid) or {}
            src_start = int(clip.get("source_start_ms") or 0)
            src_end = int(clip.get("source_end_ms") or src_start)
            # Word-boundary mid-word risk
            snapped_start = snap_cut_to_word_boundary(
                src_start, words, margin_ms=0, max_shift_ms=max_shift
            )
            snapped_end = snap_cut_to_word_boundary(
                src_end, words, margin_ms=margin, max_shift_ms=max_shift
            )
            if abs(snapped_start - src_start) >= 25:
                add(
                    "mid_word_start",
                    segment_id=sid,
                    clip_index=i,
                    action="nudge_source_bounds",
                    detail={"edge": "start", "recommended_ms": snapped_start},
                    evidence=f"start {src_start} → word snap {snapped_start}",
                )
            if abs(snapped_end - src_end) >= 25:
                add(
                    "mid_word_end",
                    segment_id=sid,
                    clip_index=i,
                    action="nudge_source_bounds",
                    detail={"edge": "end", "recommended_ms": snapped_end},
                    evidence=f"end {src_end} → word snap {snapped_end}",
                )

            lead, trail = _leading_trailing_silence(
                ctx, src_start, src_end, search_ms=micro_nudge
            )
            if lead is not None and lead > src_start + 40:
                add(
                    "leading_silence",
                    segment_id=sid,
                    clip_index=i,
                    action="nudge_source_bounds",
                    detail={"edge": "start", "recommended_ms": lead},
                    evidence=f"leading silence valley → {lead}",
                )
            if trail is not None and trail < src_end - 40:
                add(
                    "trailing_silence",
                    segment_id=sid,
                    clip_index=i,
                    action="nudge_source_bounds",
                    detail={"edge": "end", "recommended_ms": trail},
                    evidence=f"trailing silence valley → {trail}",
                )

            end_text = _clip_end_text(seg if isinstance(seg, dict) else None, words, src_end)
            incomplete = bool(end_text) and not ends_complete_thought(end_text)
            on_roll = incomplete and _on_a_roll(
                seg=seg if isinstance(seg, dict) else {},
                end_ms=src_end,
                words=words,
                phrase_extend_max_ms=phrase_max,
            )
            ch = _chapter_id_for(sid, selection)
            next_sid = None
            for j in range(i + 1, len(clips)):
                if str(clips[j].get("type") or "") == "speech":
                    next_sid = str(clips[j].get("segment_id") or "")
                    break
            next_ch = _chapter_id_for(next_sid, selection) if next_sid else None
            chapter_bleed = bool(incomplete and ch and next_ch and ch != next_ch)

            if on_roll and not chapter_bleed:
                extended = _find_phrase_end_ms(
                    words,
                    src_end,
                    max_extend_ms=phrase_max,
                    speaker=_speaker_of(seg if isinstance(seg, dict) else None),
                )
                add(
                    "on_a_roll",
                    severity="critical",
                    segment_id=sid,
                    clip_index=i,
                    action="extend_later",
                    detail={
                        "recommended_ms": extended,
                        "end_text": end_text[-80:],
                    },
                    evidence=f"incomplete end {end_text[-40:]!r}; same-speaker continuum",
                )
            elif incomplete and chapter_bleed:
                earlier = _find_last_complete_phrase_end(
                    words, src_end, max_lookback_ms=phrase_max
                )
                add(
                    "chapter_bleed_incomplete",
                    severity="critical",
                    segment_id=sid,
                    clip_index=i,
                    action="cut_earlier",
                    detail={"recommended_ms": earlier, "end_text": end_text[-80:]},
                    evidence=f"incomplete at chapter hinge: {end_text[-40:]!r}",
                )
            elif incomplete:
                extended = _find_phrase_end_ms(
                    words,
                    src_end,
                    max_extend_ms=phrase_max,
                    speaker=_speaker_of(seg if isinstance(seg, dict) else None),
                )
                earlier = _find_last_complete_phrase_end(
                    words, src_end, max_lookback_ms=min(phrase_max, 5000)
                )
                if extended:
                    add(
                        "incomplete_clause",
                        severity="critical",
                        segment_id=sid,
                        clip_index=i,
                        action="extend_later",
                        detail={"recommended_ms": extended, "end_text": end_text[-80:]},
                        evidence=f"incomplete clause: {end_text[-40:]!r}",
                    )
                elif earlier and earlier < src_end - 80:
                    add(
                        "incomplete_clause",
                        severity="critical",
                        segment_id=sid,
                        clip_index=i,
                        action="cut_earlier",
                        detail={"recommended_ms": earlier, "end_text": end_text[-80:]},
                        evidence=f"incomplete clause cut earlier: {end_text[-40:]!r}",
                    )

            # Impact hold: impactful speech followed soon by VO without hold
            if looks_like_impact_beat(seg if isinstance(seg, dict) else None, cfg=prior_cfg):
                has_hold = False
                next_vo = False
                for j in range(i + 1, min(i + 6, len(clips))):
                    nj = clips[j]
                    nt = str(nj.get("type") or "")
                    if nt == "silence" and str(nj.get("air_kind") or "") == "impact_hold":
                        has_hold = True
                        break
                    if nt == "vo_pickup":
                        next_vo = True
                        break
                    if nt == "speech":
                        break
                if next_vo and not has_hold:
                    hold_ms = max(hold_min, min(hold_max, int(2000 * mult)))
                    add(
                        "missing_impact_hold",
                        segment_id=sid,
                        clip_index=i,
                        action="insert_impact_hold",
                        detail={"hold_ms": hold_ms},
                        evidence="impact native close → VO without music/speech-free hold",
                    )

            # VO → micro
            if is_micro_segment(seg if isinstance(seg, dict) else None, cfg=prior_cfg) or (
                _BACKCHANNEL_RE.match(str((seg or {}).get("text") or "").strip())
            ):
                prev_vo = False
                for j in range(i - 1, max(-1, i - 5), -1):
                    pt = str(clips[j].get("type") or "")
                    if pt == "vo_pickup":
                        prev_vo = True
                        break
                    if pt == "speech":
                        break
                if prev_vo:
                    add(
                        "vo_micro",
                        severity="critical",
                        segment_id=sid,
                        clip_index=i,
                        action="exclude_micro",
                        detail={},
                        evidence=f"micro/backchannel after VO: {(seg or {}).get('text', '')!r}",
                    )

        elif ctype == "silence":
            air = str(clip.get("air_kind") or "")
            dur = int(clip.get("duration_ms") or 0)
            if air != "impact_hold" and dur > dead_air_clamp:
                add(
                    "dead_air_stack",
                    clip_index=i,
                    action="clamp_air",
                    detail={"recommended_ms": dead_air_clamp, "current_ms": dur},
                    evidence=f"silence {air or 'pad'} {dur}ms > clamp {dead_air_clamp}",
                )

    # Music transition faults from SDP cues (hard cuts / missing soft fades)
    findings.extend(_detect_music_transition_findings(ctx, conf))

    return findings


def _detect_music_transition_findings(
    ctx: RunContext, conf: dict[str, Any]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        return out
    plan = ctx.read_json("understanding/sound_design_plan.json")
    if not isinstance(plan, dict):
        return out
    soft_xf = int(conf.get("music_soft_crossfade_ms") or 180)
    cues: list[dict[str, Any]] = []
    flow = (plan.get("flow_plans") or {}).get("podcast") or {}
    if isinstance(flow, dict):
        raw = flow.get("cues") or []
        if isinstance(raw, list):
            cues = [c for c in raw if isinstance(c, dict)]
    if not cues and isinstance(plan.get("cues"), list):
        cues = [c for c in plan["cues"] if isinstance(c, dict)]
    for cue in cues:
        aid = str(cue.get("asset_id") or "")
        if not aid:
            continue
        placement = str(cue.get("placement") or "")
        xf = cue.get("crossfade_ms")
        role = str(cue.get("role") or "")
        # Abrupt beds / bookends into speech
        if placement in {"under_segment", "after_segment", "before_segment"} or role.startswith(
            "theme_"
        ):
            if xf is None or int(xf) < 80:
                out.append(
                    {
                        "kind": "music_hard_transition",
                        "severity": "warn",
                        "segment_id": cue.get("segment_id"),
                        "clip_index": None,
                        "action": "adjust_music_fade",
                        "detail": {
                            "asset_id": aid,
                            "suggested_crossfade_ms": soft_xf,
                            "placement": placement,
                        },
                        "evidence": f"music cue {aid} missing/soft crossfade ({xf})",
                    }
                )
    return out


def _recompute_timeline(clips: list[dict[str, Any]]) -> int:
    t = 0
    for clip in clips:
        if not isinstance(clip, dict):
            continue
        clip["timeline_start_ms"] = t
        dur = max(0, int(clip.get("duration_ms") or 0))
        if str(clip.get("type") or "") == "speech":
            ss = int(clip.get("source_start_ms") or 0)
            se = int(clip.get("source_end_ms") or ss)
            dur = max(0, se - ss)
            clip["duration_ms"] = dur
        t += dur
    return t


def apply_junction_repairs(
    ctx: RunContext,
    edl: dict[str, Any],
    findings: list[dict[str, Any]],
    *,
    cfg: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    """Apply deterministic repairs to EDL + NLE + placement adjustments.

    Returns (edl, applied_rows, needs_remaster).
    """
    conf = cfg or junction_snip_cfg()
    if not findings:
        return edl, [], False
    if not bool(conf.get("apply_repairs", True)):
        return edl, [], False

    clips = [dict(c) for c in (edl.get("clips") or []) if isinstance(c, dict)]
    nle = load_nle(ctx)
    overrides = dict(nle.get("segment_overrides") or {})
    applied: list[dict[str, Any]] = []
    music_adjs: list[dict[str, Any]] = []
    excluded: set[str] = set()
    changed = False

    # Process excludes first
    for f in findings:
        if f.get("action") != "exclude_micro":
            continue
        sid = str(f.get("segment_id") or "")
        if not sid or sid in excluded:
            continue
        ov = dict(overrides.get(sid) or {})
        ov["excluded"] = True
        ov["exclude_reason"] = "junction_snip_qa:vo_micro"
        overrides[sid] = ov
        excluded.add(sid)
        # Remove speech clip from EDL
        clips = [
            c
            for c in clips
            if not (
                str(c.get("type") or "") == "speech" and str(c.get("segment_id") or "") == sid
            )
        ]
        applied.append({**f, "status": "applied"})
        changed = True

    # Bound nudges / extend / cut
    for f in findings:
        action = str(f.get("action") or "")
        sid = str(f.get("segment_id") or "")
        if action not in {"nudge_source_bounds", "extend_later", "cut_earlier"}:
            continue
        if not sid or sid in excluded:
            continue
        detail = f.get("detail") if isinstance(f.get("detail"), dict) else {}
        recommended = detail.get("recommended_ms")
        if recommended is None:
            applied.append({**f, "status": "skipped_no_recommendation"})
            continue
        rec = int(recommended)
        edge = str(detail.get("edge") or ("end" if action != "nudge_source_bounds" else "end"))
        if action == "nudge_source_bounds":
            edge = str(detail.get("edge") or "end")
        else:
            edge = "end"

        for c in clips:
            if str(c.get("type") or "") != "speech" or str(c.get("segment_id") or "") != sid:
                continue
            ss = int(c.get("source_start_ms") or 0)
            se = int(c.get("source_end_ms") or ss)
            phrase_max = int(conf.get("phrase_extend_max_ms") or 8000)
            if edge == "start":
                # Allow small retreat for continuum; don't cross end
                new_ss = max(0, min(rec, se - 300))
                if abs(new_ss - ss) < 20:
                    continue
                c["source_start_ms"] = new_ss
                ov = dict(overrides.get(sid) or {})
                ov["start_ms"] = new_ss
                if "end_ms" not in ov:
                    ov["end_ms"] = se
                overrides[sid] = ov
            else:
                # Allow extend beyond prior end up to phrase_max from original
                new_se = max(ss + 300, rec)
                # Cap wild extends
                if new_se > se + phrase_max:
                    new_se = se + phrase_max
                if new_se < se - phrase_max:
                    new_se = max(ss + 300, se - phrase_max)
                if abs(new_se - se) < 20:
                    continue
                c["source_end_ms"] = new_se
                ov = dict(overrides.get(sid) or {})
                if "start_ms" not in ov:
                    ov["start_ms"] = ss
                ov["end_ms"] = new_se
                overrides[sid] = ov
            applied.append({**f, "status": "applied", "applied_ms": rec})
            changed = True
            break

    # Impact holds — insert after speech clip before next VO
    for f in findings:
        if f.get("action") != "insert_impact_hold":
            continue
        idx = f.get("clip_index")
        if idx is None:
            continue
        # Find current index by segment after prior mutations
        sid = str(f.get("segment_id") or "")
        insert_at = None
        for i, c in enumerate(clips):
            if str(c.get("type") or "") == "speech" and str(c.get("segment_id") or "") == sid:
                insert_at = i + 1
                break
        if insert_at is None:
            continue
        # Skip if hold already present
        if insert_at < len(clips):
            nxt = clips[insert_at]
            if str(nxt.get("type") or "") == "silence" and str(nxt.get("air_kind") or "") == "impact_hold":
                applied.append({**f, "status": "already_present"})
                continue
        detail = f.get("detail") if isinstance(f.get("detail"), dict) else {}
        hold_ms = int(detail.get("hold_ms") or conf.get("impact_hold_ms_min") or 1200)
        hold_ms = max(
            int(conf.get("impact_hold_ms_min") or 1200),
            min(int(conf.get("impact_hold_ms_max") or 3500), hold_ms),
        )
        clips.insert(
            insert_at,
            {
                "type": "silence",
                "air_kind": "impact_hold",
                "timeline_start_ms": 0,
                "duration_ms": hold_ms,
            },
        )
        applied.append({**f, "status": "applied", "hold_ms": hold_ms})
        changed = True

    # Clamp dead air
    for f in findings:
        if f.get("action") != "clamp_air":
            continue
        idx = f.get("clip_index")
        if idx is None or idx >= len(clips):
            continue
        # Re-find silence by scanning (indices may have shifted from holds)
        # Use original index best-effort on silence clips still over clamp
        detail = f.get("detail") if isinstance(f.get("detail"), dict) else {}
        rec = int(detail.get("recommended_ms") or conf.get("dead_air_clamp_ms") or 2500)
        for c in clips:
            if str(c.get("type") or "") != "silence":
                continue
            if str(c.get("air_kind") or "") == "impact_hold":
                continue
            dur = int(c.get("duration_ms") or 0)
            if dur > rec:
                c["duration_ms"] = rec
                changed = True
                applied.append({**f, "status": "applied", "clamped_to_ms": rec})
                break

    # Music fades → placement adjustments
    for f in findings:
        if f.get("action") != "adjust_music_fade":
            continue
        detail = f.get("detail") if isinstance(f.get("detail"), dict) else {}
        aid = str(detail.get("asset_id") or "")
        if not aid:
            continue
        xf = int(detail.get("suggested_crossfade_ms") or conf.get("music_soft_crossfade_ms") or 180)
        music_adjs.append(
            {
                "asset_id": aid,
                "action": "adjust_crossfade",
                "suggested_crossfade_ms": xf,
                "reason": "junction_snip_qa:music_hard_transition",
                "provenance": {
                    "rule_id": "junction_snip_qa",
                    "source_artifact": QA_REL,
                    "detail": str(f.get("evidence") or ""),
                },
                "adaptive_level_source": "default",
            }
        )
        applied.append({**f, "status": "applied", "suggested_crossfade_ms": xf})
        changed = True

    if music_adjs:
        _merge_placement_adjustments(ctx, music_adjs)

    if overrides != (nle.get("segment_overrides") or {}):
        nle = dict(nle)
        nle["segment_overrides"] = overrides
        # Mark junction provenance without forcing structural cascade
        nle["junction_snip_qa"] = {"updated_at": _now(), "override_count": len(overrides)}
        save_nle(ctx, nle)
        changed = True

    timeline = _recompute_timeline(clips)
    new_edl = dict(edl)
    new_edl["clips"] = clips
    new_edl["timeline_duration_ms"] = timeline
    new_edl["silence_clip_count"] = sum(1 for c in clips if str(c.get("type") or "") == "silence")
    # Drop excluded from ordered list if present
    if excluded:
        ordered = [s for s in (new_edl.get("ordered_segment_ids") or []) if str(s) not in excluded]
        new_edl["ordered_segment_ids"] = ordered
        from interview_mux.order_hash import stamp_order_hash

        new_edl = stamp_order_hash(new_edl)
        _exclude_from_selection(ctx, excluded)

    if changed:
        ctx.write_json("master/edl.json", new_edl)

    return new_edl, applied, changed


def _exclude_from_selection(ctx: RunContext, excluded: set[str]) -> None:
    if not excluded or not ctx.artifact_exists("master/selection.json"):
        return
    sel = ctx.read_json("master/selection.json")
    if not isinstance(sel, dict):
        return
    from interview_mux.order_hash import stamp_order_hash

    ordered = [s for s in (sel.get("ordered_segment_ids") or []) if str(s) not in excluded]
    sel = dict(sel)
    sel["ordered_segment_ids"] = ordered
    excl_list = list(sel.get("excluded_segment_ids") or [])
    existing = {
        (e if isinstance(e, str) else str((e or {}).get("segment_id") or ""))
        for e in excl_list
    }
    for sid in excluded:
        if sid in existing:
            continue
        excl_list.append({"segment_id": sid, "reason": "junction_snip_qa:vo_micro"})
    sel["excluded_segment_ids"] = excl_list
    ctx.write_json("master/selection.json", stamp_order_hash(sel))


def _merge_placement_adjustments(ctx: RunContext, rows: list[dict[str, Any]]) -> None:
    from interview_mux.placement_qa import OUTPUT_PATH, load_placement_adjustments

    doc = load_placement_adjustments(ctx)
    existing = [r for r in (doc.get("adjustments") or []) if isinstance(r, dict)]
    by_asset = {str(r.get("asset_id")): r for r in existing if r.get("asset_id")}
    for row in rows:
        aid = str(row.get("asset_id") or "")
        if not aid:
            continue
        prev = by_asset.get(aid, {})
        by_asset[aid] = {**prev, **row}
    out = {"version": int(doc.get("version") or 1), "adjustments": list(by_asset.values())}
    ctx.write_json(OUTPUT_PATH, out)


def remaster_mix_only(ctx: RunContext) -> None:
    """Rebuild mix from current EDL (and placement adjustments) without wiping EDL."""
    from interview_mux.assembly_ledger import write_assembly_ledger
    from interview_mux.stages import assembly

    marker = ctx.final_path(".stage_done", "mix")
    if marker.is_file():
        try:
            marker.unlink()
        except OSError:
            pass
    try:
        write_assembly_ledger(ctx)
    except Exception as exc:
        ctx.log(f"junction_snip_qa: ledger refresh skipped: {exc}", level="warning", stage=STAGE_ID)
    assembly.run_mix(ctx)


def build_feel_audit_context(
    ctx: RunContext,
    snip_report: dict[str, Any],
) -> dict[str, Any]:
    """Bounded context for the single feel-audit LLM call."""
    edl = ctx.read_json("master/edl.json") if ctx.artifact_exists("master/edl.json") else {}
    clips = [c for c in (edl.get("clips") or []) if isinstance(c, dict)] if isinstance(edl, dict) else []
    seams: list[dict[str, Any]] = []
    words = _transcript_words(ctx)
    segs = _segments_by_id(ctx)
    for i, clip in enumerate(clips[:80]):
        ctype = str(clip.get("type") or "")
        row: dict[str, Any] = {
            "i": i,
            "type": ctype,
            "timeline_start_ms": clip.get("timeline_start_ms"),
            "duration_ms": clip.get("duration_ms"),
        }
        if ctype == "speech":
            sid = str(clip.get("segment_id") or "")
            row["segment_id"] = sid
            seg = segs.get(sid) or {}
            text = str(seg.get("text") or "")[:160]
            row["text_head"] = text[:80]
            row["text_tail"] = text[-80:] if len(text) > 80 else text
            row["source_start_ms"] = clip.get("source_start_ms")
            row["source_end_ms"] = clip.get("source_end_ms")
            end_ms = int(clip.get("source_end_ms") or 0)
            row["end_window"] = _text_in_window(words, max(0, end_ms - 2500), end_ms)[-120:]
        elif ctype == "silence":
            row["air_kind"] = clip.get("air_kind")
        elif ctype == "vo_pickup":
            row["line_id"] = clip.get("line_id")
            row["targets_segment_id"] = clip.get("targets_segment_id")
        seams.append(row)

    residuals = [
        f
        for f in (snip_report.get("findings") or [])
        if isinstance(f, dict) and f.get("status") not in {"applied", "already_present"}
    ][:40]
    applied = [a for a in (snip_report.get("applied") or []) if isinstance(a, dict)][:40]
    return {
        "version": 1,
        "seam_sample": seams,
        "deterministic_applied": applied,
        "deterministic_residuals": residuals,
        "timeline_duration_ms": edl.get("timeline_duration_ms") if isinstance(edl, dict) else None,
        "allowed_actions": sorted(ALLOWED_FEEL_ACTIONS),
        "llm_budget": "single_call_only",
    }


def run_junction_feel_audit(
    ctx: RunContext,
    snip_report: dict[str, Any],
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One LLM call judging final master feel. Fail-open on errors."""
    conf = cfg or junction_snip_cfg()
    if not bool(conf.get("feel_audit_enabled", True)):
        audit = {
            "version": 1,
            "skipped": True,
            "reason": "feel_audit_disabled",
            "directives": [],
            "findings": [],
            "llm_calls": 0,
            "generated_at": _now(),
        }
        ctx.write_json(FEEL_REL, audit)
        return audit

    packet = build_feel_audit_context(ctx, snip_report)
    directives: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    verdict = "pass"
    llm_calls = 0
    error: str | None = None
    try:
        from interview_mux.stages.llm_runner import run_prompt_envelope

        user_content = json.dumps(packet, indent=2, ensure_ascii=False)
        envelope = run_prompt_envelope(
            FEEL_STAGE_KEY,
            FEEL_PROMPT,
            user_content,
            ctx=ctx,
            explicit_tier="standard",
            record_stage_key=STAGE_ID,
        )
        llm_calls = 1
        raw = envelope.get("parsed") if isinstance(envelope, dict) else None
        if not isinstance(raw, dict):
            # Some envelopes nest under artifacts / content
            raw = envelope.get("artifacts") if isinstance(envelope, dict) else None
            if isinstance(raw, dict) and "junction_feel_audit" in raw:
                raw = raw["junction_feel_audit"]
            elif isinstance(envelope, dict) and "verdict" in envelope:
                raw = envelope
        if isinstance(raw, dict):
            verdict = str(raw.get("verdict") or "pass")
            for d in raw.get("directives") or []:
                if not isinstance(d, dict):
                    continue
                action = str(d.get("action") or "")
                if action not in ALLOWED_FEEL_ACTIONS:
                    continue
                directives.append(d)
            findings = [f for f in (raw.get("findings") or []) if isinstance(f, dict)]
        else:
            # Try parse content string
            content = ""
            if isinstance(envelope, dict):
                content = str(envelope.get("content") or envelope.get("text") or "")
            if content.strip().startswith("{"):
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict):
                        verdict = str(parsed.get("verdict") or "pass")
                        for d in parsed.get("directives") or []:
                            if isinstance(d, dict) and str(d.get("action") or "") in ALLOWED_FEEL_ACTIONS:
                                directives.append(d)
                        findings = [f for f in (parsed.get("findings") or []) if isinstance(f, dict)]
                except json.JSONDecodeError:
                    error = "feel_audit_unparseable"
    except Exception as exc:
        error = str(exc)[:240]
        ctx.log(f"junction_feel_audit failed open: {exc}", level="warning", stage=STAGE_ID)

    audit = {
        "version": 1,
        "verdict": verdict,
        "findings": findings,
        "directives": directives,
        "llm_calls": llm_calls,
        "error": error,
        "remaster_round": 0,
        "generated_at": _now(),
    }
    ctx.write_json(FEEL_REL, audit)
    return audit


def apply_feel_directives(
    ctx: RunContext,
    audit: dict[str, Any],
    *,
    cfg: dict[str, Any] | None = None,
) -> bool:
    """Map feel-audit directives onto the same repair machinery. Returns needs_remaster."""
    conf = cfg or junction_snip_cfg()
    directives = [d for d in (audit.get("directives") or []) if isinstance(d, dict)]
    if not directives:
        return False
    edl = ctx.read_json("master/edl.json") if ctx.artifact_exists("master/edl.json") else None
    if not isinstance(edl, dict):
        return False
    findings: list[dict[str, Any]] = []
    for d in directives:
        action = str(d.get("action") or "")
        if action not in ALLOWED_FEEL_ACTIONS:
            continue
        detail = dict(d.get("detail") or {}) if isinstance(d.get("detail"), dict) else {}
        if action == "adjust_crossfade":
            action = "adjust_music_fade"
            if "suggested_crossfade_ms" not in detail:
                detail["suggested_crossfade_ms"] = int(conf.get("music_soft_crossfade_ms") or 180)
        findings.append(
            {
                "kind": f"feel_{action}",
                "severity": str(d.get("severity") or "warn"),
                "segment_id": d.get("segment_id"),
                "clip_index": d.get("clip_index"),
                "action": action if action != "retarget_vo_anchor" else "exclude_micro",
                "detail": detail,
                "evidence": str(d.get("evidence") or "feel_audit"),
            }
        )
    if not findings:
        return False
    _edl2, applied, changed = apply_junction_repairs(ctx, edl, findings, cfg=conf)
    audit = dict(audit)
    audit["applied_directives"] = applied
    audit["remaster_round"] = 1 if changed else 0
    ctx.write_json(FEEL_REL, audit)
    return changed


def run_junction_snip_qa(ctx: RunContext) -> None:
    """Delivery stage: deterministic junction QA → remaster → one feel audit → optional remaster."""
    conf = junction_snip_cfg()
    mode = str(conf.get("mode") or "advisory").lower()
    if mode == "off":
        report = {
            "version": 1,
            "mode": "off",
            "skipped": True,
            "findings": [],
            "applied": [],
            "remaster_rounds": 0,
            "llm_calls": 0,
            "generated_at": _now(),
        }
        ctx.write_json(QA_REL, report)
        return

    if not ctx.artifact_exists("master/edl.json"):
        ctx.log("junction_snip_qa: no master/edl.json — skip", level="warning", stage=STAGE_ID)
        ctx.write_json(
            QA_REL,
            {
                "version": 1,
                "mode": mode,
                "skipped": True,
                "reason": "missing_edl",
                "findings": [],
                "applied": [],
                "remaster_rounds": 0,
                "llm_calls": 0,
                "generated_at": _now(),
            },
        )
        return

    edl = ctx.read_json("master/edl.json")
    if not isinstance(edl, dict):
        raise ValueError("master/edl.json is not an object")

    findings = detect_junction_findings(ctx, edl, cfg=conf)
    remaster_rounds = 0
    applied: list[dict[str, Any]] = []

    edl2, applied, needs = apply_junction_repairs(ctx, edl, findings, cfg=conf)
    max_rounds = min(2, int(conf.get("max_remaster_rounds") or 2))
    if needs and remaster_rounds < max_rounds:
        try:
            remaster_mix_only(ctx)
            remaster_rounds += 1
        except Exception as exc:
            ctx.log(f"junction_snip_qa remaster failed open: {exc}", level="warning", stage=STAGE_ID)

    report = {
        "version": 1,
        "mode": mode,
        "pace_class": _pace_class(ctx),
        "findings": findings,
        "applied": applied,
        "remaster_rounds": remaster_rounds,
        "llm_calls": 0,
        "advisory": mode != "authoritative",
        "blocking": False,
        "generated_at": _now(),
    }
    ctx.write_json(QA_REL, report)

    audit = run_junction_feel_audit(ctx, report, cfg=conf)
    report["llm_calls"] = int(audit.get("llm_calls") or 0)
    ctx.write_json(QA_REL, report)

    if report["llm_calls"] > 2:
        # Hard invariant: O(1) LLM budget
        ctx.log(
            f"junction_snip_qa: unexpected llm_calls={report['llm_calls']}",
            level="warning",
            stage=STAGE_ID,
        )

    if remaster_rounds < max_rounds and apply_feel_directives(ctx, audit, cfg=conf):
        try:
            remaster_mix_only(ctx)
            remaster_rounds += 1
            report["remaster_rounds"] = remaster_rounds
            ctx.write_json(QA_REL, report)
        except Exception as exc:
            ctx.log(f"junction_feel remaster failed open: {exc}", level="warning", stage=STAGE_ID)

    # Surface in run_meta without blocking
    meta: dict[str, Any]
    if ctx.artifact_exists("run_meta.json"):
        doc = ctx.read_json("run_meta.json")
        meta = doc if isinstance(doc, dict) else {}
    else:
        meta = {}
    qc = meta.get("qc_summaries") if isinstance(meta.get("qc_summaries"), dict) else {}
    qc["junction_snip_qa"] = {
        "advisory": True,
        "blocking": False,
        "findings": len(findings),
        "applied": len(applied),
        "remaster_rounds": remaster_rounds,
        "llm_calls": report["llm_calls"],
        "feel_verdict": audit.get("verdict"),
    }
    meta["qc_summaries"] = qc
    ctx.write_json("run_meta.json", meta)

    if mode == "authoritative":
        critical_left = [
            f
            for f in findings
            if f.get("severity") == "critical"
            and not any(
                a.get("kind") == f.get("kind")
                and a.get("segment_id") == f.get("segment_id")
                and a.get("status") == "applied"
                for a in applied
            )
        ]
        if critical_left:
            ctx.log(
                f"junction_snip_qa authoritative residuals: {len(critical_left)} "
                "(advisory surface — does not block master_finalize)",
                level="warning",
                stage=STAGE_ID,
            )
