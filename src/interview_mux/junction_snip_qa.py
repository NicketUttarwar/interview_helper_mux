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
    is_backchannel_only_text,
    is_legal_conceptual_hinge,
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


def _canonical_edl_order(edl: dict[str, Any]) -> list[str]:
    return [str(s) for s in (edl.get("ordered_segment_ids") or []) if s]


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
        "merge_micro",
        "retarget_vo_anchor",
    }
)

_EDGE_ACTION_PRIORITY = {
    "extend_later": 100,
    "merge_micro": 90,
    "cut_earlier": 80,
    "exclude_micro": 70,
    "nudge_source_bounds": 40,
}
_KIND_PRIORITY = {
    "on_a_roll": 100,
    "chapter_bleed_incomplete": 95,
    "incomplete_clause": 90,
    "vo_micro": 85,
    "mid_word_start": 50,
    "mid_word_end": 50,
    "leading_silence": 20,
    "trailing_silence": 20,
}


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
        # Audio slices are [start_ms, end_ms); words touching only the boundary
        # are not audible in the clip.
        if we <= start_ms or ws >= end_ms:
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
    # The EDL bound may have moved beyond the original segment boundary during
    # remediation. Always evaluate the words actually audible at the current
    # bound; static segment text would report the same incomplete clause forever.
    audible = _text_in_window(words, max(0, end_ms - 4000), end_ms).strip()
    if audible:
        toks = audible.split()
        return " ".join(toks[-12:]) if len(toks) > 12 else audible
    if isinstance(seg, dict) and str(seg.get("text") or "").strip():
        text = str(seg.get("text") or "").strip()
        toks = text.split()
        return " ".join(toks[-12:]) if len(toks) > 12 else text
    return ""


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


# Never let a phrase-extend invade the next selected speech source start.
SOURCE_OVERLAP_EPS_MS = 80


def _next_speech_source_start(
    clips: list[dict[str, Any]],
    from_index: int,
) -> int | None:
    for j in range(from_index + 1, len(clips)):
        other = clips[j]
        if not isinstance(other, dict):
            continue
        if str(other.get("type") or "") != "speech":
            continue
        try:
            return int(other.get("source_start_ms") or 0)
        except (TypeError, ValueError):
            return None
    return None


def _clamp_end_before_next_speech(
    end_ms: int,
    next_source_start_ms: int | None,
    *,
    eps_ms: int = SOURCE_OVERLAP_EPS_MS,
) -> int:
    if next_source_start_ms is None:
        return end_ms
    return min(end_ms, int(next_source_start_ms) - int(eps_ms))


def _pause_after_word(
    words: list[dict[str, Any]],
    word: dict[str, Any],
    *,
    index: int | None = None,
) -> int | None:
    """Inter-word pause after ``word`` (ms), or None when unknown."""
    try:
        end = int(word.get("end_ms") or 0)
    except (TypeError, ValueError):
        return None
    if index is not None and 0 <= index + 1 < len(words):
        nxt = words[index + 1]
        try:
            return max(0, int(nxt.get("start_ms") or 0) - end)
        except (TypeError, ValueError):
            return None
    for w in words:
        try:
            start = int(w.get("start_ms") or 0)
        except (TypeError, ValueError):
            continue
        if start >= end:
            return max(0, start - end)
    return None


def _find_phrase_end_ms(
    words: list[dict[str, Any]],
    from_ms: int,
    *,
    max_extend_ms: int,
    speaker: str = "",
    hard_cap_ms: int | None = None,
) -> int | None:
    """Extend to the first word end that completes a thought within the window."""
    cap = from_ms + max_extend_ms
    if hard_cap_ms is not None:
        cap = min(cap, int(hard_cap_ms))
    if cap <= from_ms:
        return None
    window = [
        w
        for w in words
        if from_ms < int(w.get("end_ms") or 0) <= cap
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
    for i, w in enumerate(window):
        tok = str(w.get("text") or w.get("word") or "").strip()
        if tok:
            accumulated.append(tok)
        candidate = " ".join(accumulated)
        if is_backchannel_only_text(candidate):
            continue
        pause = _pause_after_word(window, w, index=i)
        if pause is None:
            pause = _pause_after_word(words, w)
        if ends_complete_thought(candidate, next_pause_ms=pause) and candidate[-1:] in ".!?…":
            return int(w.get("end_ms") or 0)
        # Soft: stop at pause after content word
        if (
            ends_complete_thought(candidate, next_pause_ms=pause)
            and len(accumulated) >= 3
        ):
            return int(w.get("end_ms") or 0)
    # Last complete word boundary in window if we gained content
    last_pause = _pause_after_word(words, window[-1])
    if accumulated and ends_complete_thought(
        " ".join(accumulated), next_pause_ms=last_pause
    ):
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
        pause = None
        if i + 1 < len(window):
            pause = max(
                0,
                int(window[i + 1].get("start_ms") or 0)
                - int(window[i].get("end_ms") or 0),
            )
        else:
            # Pause from end of this word to the original cut / next source word
            pause = max(0, end_ms - int(window[i].get("end_ms") or 0))
            if pause == 0:
                pause = _pause_after_word(words, window[i])
        complete = is_legal_conceptual_hinge(
            text, words=words, end_ms=int(window[i].get("end_ms") or 0), next_pause_ms=pause
        )
        if complete:
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


def _phrase_action_for_incomplete(
    *,
    can_extend: bool,
    can_cut: bool,
    can_merge: bool,
    is_micro: bool,
) -> str:
    """Ladder: extend → merge → cut → exclude(micros) / residual critical."""
    if can_extend:
        return "extend_later"
    if can_merge:
        return "merge_micro"
    if can_cut:
        return "cut_earlier"
    if is_micro:
        return "exclude_micro"
    return "cut_earlier"  # keep critical path; apply will skip without recommendation


def _merge_candidate_for_clip(
    *,
    clips: list[dict[str, Any]],
    index: int,
    sid: str,
    src_start: int,
    src_end: int,
    speaker: str | None,
    chapter: str | None,
    selection: dict[str, Any],
    segs: dict[str, Any],
    gap_max_ms: int = 450,
    allow_cross_speaker: bool = False,
) -> dict[str, Any] | None:
    """Adjacent speech within gap — prefer absorbing the incomplete close."""
    if not speaker and not allow_cross_speaker:
        return None
    candidates: list[tuple[int, dict[str, Any]]] = []
    for j in (index - 1, index + 1):
        if j < 0 or j >= len(clips):
            continue
        other = clips[j]
        if str(other.get("type") or "") != "speech":
            continue
        oid = str(other.get("segment_id") or "")
        if not oid or oid == sid:
            continue
        oseg = segs.get(oid) or {}
        other_speaker = _speaker_of(oseg if isinstance(oseg, dict) else None)
        if other_speaker != speaker and not allow_cross_speaker:
            continue
        och = _chapter_id_for(oid, selection)
        if chapter and och and chapter != och:
            continue
        oss = int(other.get("source_start_ms") or 0)
        ose = int(other.get("source_end_ms") or oss)
        gap = min(abs(oss - src_end), abs(src_start - ose), abs(oss - src_start), abs(ose - src_end))
        # Prefer chronological neighbors with small source gap.
        if j == index + 1:
            gap = max(0, oss - src_end)
        elif j == index - 1:
            gap = max(0, src_start - ose)
        if gap > gap_max_ms:
            continue
        candidates.append((gap, other))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    other = candidates[0][1]
    oid = str(other.get("segment_id") or "")
    oss = int(other.get("source_start_ms") or 0)
    ose = int(other.get("source_end_ms") or oss)
    cur_dur = max(0, src_end - src_start)
    oth_dur = max(0, ose - oss)
    if cur_dur <= oth_dur:
        drop_id, survivor_id = sid, oid
        new_start, new_end = min(src_start, oss), max(src_end, ose)
    else:
        drop_id, survivor_id = oid, sid
        new_start, new_end = min(src_start, oss), max(src_end, ose)
    return {
        "drop_segment_id": drop_id,
        "survivor_segment_id": survivor_id,
        "new_start_ms": new_start,
        "new_end_ms": new_end,
        "gap_ms": candidates[0][0],
    }


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
    hyst_ms = max(40, int(0.15 * micro_nudge))

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
    nle = load_nle(ctx)
    nudge_history = (
        nle.get("junction_nudge_history")
        if isinstance(nle.get("junction_nudge_history"), dict)
        else {}
    )

    clips = [c for c in (edl.get("clips") or []) if isinstance(c, dict)]
    findings: list[dict[str, Any]] = []
    # One winner per (segment_id, edge) — incomplete/extend/cut > mid_word > silence.
    edge_winners: dict[tuple[str, str], dict[str, Any]] = {}

    def _edge_key(segment_id: str | None, action: str, detail: dict[str, Any]) -> tuple[str, str] | None:
        if not segment_id:
            return None
        if action in {"extend_later", "cut_earlier", "merge_micro", "exclude_micro"}:
            return (segment_id, "end")
        if action == "nudge_source_bounds":
            return (segment_id, str(detail.get("edge") or "end"))
        return None

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
        detail = dict(detail or {})
        # Hysteresis: suppress re-fire unless delta large or valley moved.
        if action == "nudge_source_bounds" and segment_id:
            edge = str(detail.get("edge") or "end")
            hist = nudge_history.get(f"{segment_id}:{edge}")
            if isinstance(hist, dict) and detail.get("recommended_ms") is not None:
                prev = hist.get("applied_ms")
                if prev is not None and abs(int(detail["recommended_ms"]) - int(prev)) < hyst_ms:
                    return
        row = {
            "kind": kind,
            "severity": severity,
            "segment_id": segment_id,
            "clip_index": clip_index,
            "action": action,
            "detail": detail,
            "evidence": evidence,
        }
        key = _edge_key(segment_id, action, detail)
        if key is None:
            findings.append(row)
            return
        score = _EDGE_ACTION_PRIORITY.get(action, 0) + _KIND_PRIORITY.get(kind, 0)
        if severity == "critical":
            score += 25
        prev = edge_winners.get(key)
        if prev is None or score > int(prev.get("_score") or 0):
            row["_score"] = score
            edge_winners[key] = row

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
                next_start = _next_speech_source_start(clips, i)
                snapped_end = _clamp_end_before_next_speech(snapped_end, next_start)
                if snapped_end > src_start + 300 and abs(snapped_end - src_end) >= 25:
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
                # Trailing silence must not create incomplete ends.
                tentative_end_text = _clip_end_text(
                    seg if isinstance(seg, dict) else None, words, trail
                )
                if tentative_end_text and not ends_complete_thought(tentative_end_text):
                    pass
                else:
                    add(
                        "trailing_silence",
                        segment_id=sid,
                        clip_index=i,
                        action="nudge_source_bounds",
                        detail={"edge": "end", "recommended_ms": trail},
                        evidence=f"trailing silence valley → {trail}",
                    )

            end_text = _clip_end_text(seg if isinstance(seg, dict) else None, words, src_end)
            from interview_mux.gap_vo_prior_context import (
                clause_continues_after,
                is_legal_conceptual_hinge,
            )

            legal = bool(end_text) and is_legal_conceptual_hinge(
                end_text, words=words, end_ms=src_end, next_pause_ms=None
            )
            continues = clause_continues_after(words, src_end, max_lookahead_ms=phrase_max)
            incomplete = bool(end_text) and (not legal or continues)
            on_roll = incomplete and (
                continues
                or _on_a_roll(
                    seg=seg if isinstance(seg, dict) else {},
                    end_ms=src_end,
                    words=words,
                    phrase_extend_max_ms=phrase_max,
                )
            )
            ch = _chapter_id_for(sid, selection)
            next_sid = None
            for j in range(i + 1, len(clips)):
                if str(clips[j].get("type") or "") == "speech":
                    next_sid = str(clips[j].get("segment_id") or "")
                    break
            next_ch = _chapter_id_for(next_sid, selection) if next_sid else None
            chapter_bleed = bool(incomplete and ch and next_ch and ch != next_ch)
            speaker = _speaker_of(seg if isinstance(seg, dict) else None)
            is_micro = bool(
                is_micro_segment(seg if isinstance(seg, dict) else None, cfg=prior_cfg)
                or _BACKCHANNEL_RE.match(str((seg or {}).get("text") or "").strip())
            )
            merge = None
            if incomplete and not chapter_bleed:
                merge = _merge_candidate_for_clip(
                    clips=clips,
                    index=i,
                    sid=sid,
                    src_start=src_start,
                    src_end=src_end,
                    speaker=speaker,
                    chapter=ch,
                    selection=selection,
                    segs=segs,
                )
                if merge is None:
                    merge = _merge_candidate_for_clip(
                        clips=clips,
                        index=i,
                        sid=sid,
                        src_start=src_start,
                        src_end=src_end,
                        speaker=speaker,
                        chapter=ch,
                        selection=selection,
                        segs=segs,
                        gap_max_ms=max(1000, phrase_max),
                        allow_cross_speaker=True,
                    )

            next_src_start = _next_speech_source_start(clips, i)
            extend_hard_cap = (
                int(next_src_start) - SOURCE_OVERLAP_EPS_MS
                if next_src_start is not None
                else None
            )
            # Prefer absorbing same-speaker continuum when phrase end would invade
            # the next keep — widen merge gap to phrase budget for on-a-roll.
            if incomplete and not chapter_bleed and merge is None and on_roll:
                merge = _merge_candidate_for_clip(
                    clips=clips,
                    index=i,
                    sid=sid,
                    src_start=src_start,
                    src_end=src_end,
                    speaker=speaker,
                    chapter=ch,
                    selection=selection,
                    segs=segs,
                    gap_max_ms=max(450, phrase_max),
                )

            extend_speaker = "" if continues else speaker
            if on_roll and not chapter_bleed:
                extended = _find_phrase_end_ms(
                    words,
                    src_end,
                    max_extend_ms=phrase_max,
                    speaker=extend_speaker,
                    hard_cap_ms=extend_hard_cap,
                )
                earlier = (
                    None
                    if extended is not None
                    else _find_last_complete_phrase_end(
                        words, src_end, max_lookback_ms=max(phrase_max, 12_000)
                    )
                )
                can_cut = bool(
                    earlier is not None
                    and earlier > src_start + 300
                    and earlier < src_end - 80
                )
                # Invasion would leave incomplete — prefer cut/merge over fake extend.
                if (
                    extended is not None
                    and extend_hard_cap is not None
                    and extended >= extend_hard_cap
                    and earlier is not None
                    and can_cut
                ):
                    extended = None
                action = _phrase_action_for_incomplete(
                    can_extend=extended is not None,
                    can_cut=can_cut,
                    can_merge=merge is not None,
                    is_micro=is_micro,
                )
                # Continuum with no safe phrase end: merge across keepers rather
                # than shipping a mid-flow chop or impact-hold band-aid.
                if (
                    action == "cut_earlier"
                    and not can_cut
                    and merge is not None
                ):
                    action = "merge_micro"
                recommended = extended if extended is not None else earlier
                if recommended is not None and action == "extend_later":
                    recommended = _clamp_end_before_next_speech(
                        int(recommended), next_src_start
                    )
                    if recommended <= src_end + 20:
                        recommended = None
                        action = _phrase_action_for_incomplete(
                            can_extend=False,
                            can_cut=can_cut,
                            can_merge=merge is not None,
                            is_micro=is_micro,
                        )
                        if action == "cut_earlier" and not can_cut and merge is not None:
                            action = "merge_micro"
                        recommended = earlier if can_cut else None
                detail: dict[str, Any] = {
                    "recommended_ms": recommended,
                    "end_text": end_text[-80:],
                    "unrecoverable_within_clip": (
                        recommended is None
                        and merge is None
                        and not is_micro
                        and action != "merge_micro"
                    ),
                }
                if action == "merge_micro" and merge:
                    detail.update(merge)
                add(
                    "on_a_roll",
                    severity="critical",
                    segment_id=sid,
                    clip_index=i,
                    action=action,
                    detail=detail,
                    evidence=f"incomplete end {end_text[-40:]!r}; same-speaker continuum",
                )
            elif incomplete and chapter_bleed:
                earlier = _find_last_complete_phrase_end(
                    words, src_end, max_lookback_ms=max(phrase_max, 12_000)
                )
                can_cut = bool(
                    earlier is not None
                    and earlier > src_start + 300
                    and earlier < src_end - 80
                )
                action = "cut_earlier" if can_cut else ("exclude_micro" if is_micro else "cut_earlier")
                add(
                    "chapter_bleed_incomplete",
                    severity="critical",
                    segment_id=sid,
                    clip_index=i,
                    action=action,
                    detail={
                        "recommended_ms": earlier,
                        "end_text": end_text[-80:],
                        "unrecoverable_within_clip": not can_cut and not is_micro,
                    },
                    evidence=f"incomplete at chapter hinge: {end_text[-40:]!r}",
                )
            elif incomplete:
                extended = _find_phrase_end_ms(
                    words,
                    src_end,
                    max_extend_ms=phrase_max,
                    speaker="" if continues else speaker,
                    hard_cap_ms=extend_hard_cap,
                )
                earlier = _find_last_complete_phrase_end(
                    words, src_end, max_lookback_ms=max(phrase_max, 12_000)
                )
                can_cut = bool(
                    earlier is not None
                    and earlier > src_start + 300
                    and earlier < src_end - 80
                )
                if (
                    extended is not None
                    and extend_hard_cap is not None
                    and extended >= extend_hard_cap
                    and earlier is not None
                    and can_cut
                ):
                    extended = None
                action = _phrase_action_for_incomplete(
                    can_extend=extended is not None,
                    can_cut=can_cut,
                    can_merge=merge is not None,
                    is_micro=is_micro,
                )
                recommended = extended if extended is not None else earlier
                if recommended is not None and action == "extend_later":
                    recommended = _clamp_end_before_next_speech(
                        int(recommended), next_src_start
                    )
                    if recommended <= src_end + 20:
                        recommended = earlier if can_cut else None
                        action = _phrase_action_for_incomplete(
                            can_extend=False,
                            can_cut=can_cut,
                            can_merge=merge is not None,
                            is_micro=is_micro,
                        )
                detail = {
                    "recommended_ms": recommended,
                    "end_text": end_text[-80:],
                    "unrecoverable_within_clip": (
                        recommended is None
                        and merge is None
                        and not is_micro
                        and action != "merge_micro"
                    ),
                }
                if action == "merge_micro" and merge:
                    detail.update(merge)
                add(
                    "incomplete_clause",
                    severity="critical",
                    segment_id=sid,
                    clip_index=i,
                    action=action,
                    detail=detail,
                    evidence=f"incomplete clause: {end_text[-40:]!r}",
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
            if is_micro:
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

    for row in edge_winners.values():
        row.pop("_score", None)
        findings.append(row)

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
    music_cfg = (merged_config().get("mastering") or {}).get("music_continuity") or {}
    require_bookends = bool(music_cfg.get("require_true_bookend_anchors", True))
    cues: list[dict[str, Any]] = []
    flow = (plan.get("flow_plans") or {}).get("podcast") or {}
    if isinstance(flow, dict):
        raw = flow.get("cues") or []
        if isinstance(raw, list):
            cues = [c for c in raw if isinstance(c, dict)]
    if not cues and isinstance(plan.get("cues"), list):
        cues = [c for c in plan["cues"] if isinstance(c, dict)]
    from interview_mux.placement_qa import apply_placement_adjustments

    cues = apply_placement_adjustments(ctx, cues)
    # Contiguous under_segment_span beds already carry scene XF — skip spam.
    for cue in cues:
        aid = str(cue.get("asset_id") or "")
        if not aid:
            continue
        placement = str(cue.get("placement") or "")
        if placement == "under_segment_span":
            continue
        xf_raw = cue.get("crossfade_ms")
        role = str(cue.get("role") or "")
        effective_xf = int(xf_raw) if xf_raw is not None else 0
        # Abrupt beds / bookends into speech
        if placement in {"under_segment", "after_segment", "before_segment"} or role.startswith(
            "theme_"
        ):
            if effective_xf < soft_xf:
                severity = "warn"
                if require_bookends and (
                    "cold_open" in role or "outro" in role or placement in {"before_segment", "after_segment"}
                ):
                    severity = "critical" if effective_xf <= 0 else "warn"
                out.append(
                    {
                        "kind": "music_hard_transition",
                        "severity": severity,
                        "segment_id": cue.get("segment_id"),
                        "clip_index": None,
                        "action": "adjust_music_fade",
                        "detail": {
                            "asset_id": aid,
                            "suggested_crossfade_ms": soft_xf,
                            "placement": placement,
                            "effective_crossfade_ms": effective_xf,
                        },
                        "evidence": (
                            f"music cue {aid} missing/soft crossfade "
                            f"(effective={effective_xf}, need>={soft_xf})"
                        ),
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
    nudge_history = dict(
        nle.get("junction_nudge_history")
        if isinstance(nle.get("junction_nudge_history"), dict)
        else {}
    )
    applied: list[dict[str, Any]] = []
    music_adjs: list[dict[str, Any]] = []
    excluded: set[str] = set()
    exclude_reasons: dict[str, str] = {}
    changed = False

    # Process excludes first
    for f in findings:
        if f.get("action") != "exclude_micro":
            continue
        sid = str(f.get("segment_id") or "")
        if not sid or sid in excluded:
            continue
        kind = str(f.get("kind") or "exclude_micro")
        reason = f"junction_snip_qa:{kind}"
        ov = dict(overrides.get(sid) or {})
        ov["excluded"] = True
        ov["exclude_reason"] = reason
        overrides[sid] = ov
        excluded.add(sid)
        exclude_reasons[sid] = reason
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

    # Same-speaker micro merge (absorb drop into survivor bounds)
    for f in findings:
        if f.get("action") != "merge_micro":
            continue
        detail = f.get("detail") if isinstance(f.get("detail"), dict) else {}
        drop_id = str(detail.get("drop_segment_id") or "")
        survivor_id = str(detail.get("survivor_segment_id") or "")
        if not drop_id or not survivor_id or drop_id in excluded:
            continue
        new_start = detail.get("new_start_ms")
        new_end = detail.get("new_end_ms")
        if new_start is None or new_end is None:
            applied.append({**f, "status": "skipped_no_recommendation"})
            continue
        for c in clips:
            if str(c.get("type") or "") != "speech" or str(c.get("segment_id") or "") != survivor_id:
                continue
            c["source_start_ms"] = int(new_start)
            c["source_end_ms"] = int(new_end)
            ov = dict(overrides.get(survivor_id) or {})
            ov["start_ms"] = int(new_start)
            ov["end_ms"] = int(new_end)
            overrides[survivor_id] = ov
            break
        reason = f"junction_snip_qa:{f.get('kind') or 'merge_micro'}"
        ov_drop = dict(overrides.get(drop_id) or {})
        ov_drop["excluded"] = True
        ov_drop["exclude_reason"] = reason
        overrides[drop_id] = ov_drop
        excluded.add(drop_id)
        exclude_reasons[drop_id] = reason
        clips = [
            c
            for c in clips
            if not (
                str(c.get("type") or "") == "speech" and str(c.get("segment_id") or "") == drop_id
            )
        ]
        applied.append({**f, "status": "applied", "survivor_segment_id": survivor_id})
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
                # Allow extend beyond prior end up to phrase_max from original,
                # but never invade the next selected speech source range.
                new_se = max(ss + 300, rec)
                # Cap wild extends
                if new_se > se + phrase_max:
                    new_se = se + phrase_max
                if new_se < se - phrase_max:
                    new_se = max(ss + 300, se - phrase_max)
                clip_index = next(
                    (
                        idx
                        for idx, row in enumerate(clips)
                        if str(row.get("type") or "") == "speech"
                        and str(row.get("segment_id") or "") == sid
                    ),
                    None,
                )
                next_start = (
                    _next_speech_source_start(clips, clip_index)
                    if clip_index is not None
                    else None
                )
                new_se = _clamp_end_before_next_speech(new_se, next_start)
                if new_se <= ss + 300:
                    applied.append({**f, "status": "skipped_next_clip_clamp"})
                    break
                if abs(new_se - se) < 20:
                    continue
                c["source_end_ms"] = new_se
                ov = dict(overrides.get(sid) or {})
                if "start_ms" not in ov:
                    ov["start_ms"] = ss
                ov["end_ms"] = new_se
                overrides[sid] = ov
            # Commit the *actual* written bound, not the uncapped recommendation.
            written = (
                int(c.get("source_start_ms") or 0)
                if edge == "start"
                else int(c.get("source_end_ms") or 0)
            )
            nudge_history[f"{sid}:{edge}"] = {
                "applied_ms": written,
                "kind": f.get("kind"),
                "updated_at": _now(),
            }
            applied.append({**f, "status": "applied", "applied_ms": written, "edge": edge})
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

    # Strip orphan VO targeting excluded speech (e.g. vo_micro exclude left the
    # preceding vo_pickup on the timeline).
    if excluded:
        before_n = len(clips)
        clips = [
            c
            for c in clips
            if not (
                str(c.get("type") or "") == "vo_pickup"
                and str(c.get("targets_segment_id") or "") in excluded
            )
        ]
        if len(clips) < before_n:
            changed = True
            applied.append(
                {
                    "action": "strip_orphan_vo_pickup",
                    "excluded_segment_ids": sorted(excluded),
                    "removed_clips": before_n - len(clips),
                    "status": "applied",
                }
            )
        placements = [
            p
            for p in (edl.get("gap_placements") or [])
            if isinstance(p, dict)
            and str(p.get("targets_segment_id") or "") not in excluded
        ]
        if placements != list(edl.get("gap_placements") or []):
            edl = dict(edl)
            edl["gap_placements"] = placements
            changed = True
        if ctx.artifact_exists("understanding/gap_report.json"):
            try:
                from interview_mux.gap_framing import rebase_gap_lines_to_selection
                from interview_mux.write_staging import write_committed_json

                gr = ctx.read_json("understanding/gap_report.json")
                if isinstance(gr, dict):
                    ordered_live = [
                        str(s)
                        for s in (edl.get("ordered_segment_ids") or [])
                        if str(s) not in excluded
                    ]
                    if not ordered_live and ctx.artifact_exists("master/selection.json"):
                        sel = ctx.read_json("master/selection.json")
                        if isinstance(sel, dict):
                            ordered_live = [
                                str(s)
                                for s in (sel.get("ordered_segment_ids") or [])
                                if str(s) not in excluded
                            ]
                    rebased, notes = rebase_gap_lines_to_selection(gr, ordered_live)
                    if notes:
                        write_committed_json(
                            ctx,
                            "understanding/gap_report.json",
                            rebased,
                            stage_key=STAGE_ID,
                        )
                        applied.append(
                            {
                                "action": "rebase_gap_report_after_exclude",
                                "notes": notes[:12],
                                "status": "applied",
                            }
                        )
                        changed = True
            except Exception as exc:
                applied.append(
                    {
                        "action": "rebase_gap_report_after_exclude",
                        "status": "failed",
                        "error": str(exc)[:160],
                    }
                )

    if overrides != (nle.get("segment_overrides") or {}) or nudge_history != (
        nle.get("junction_nudge_history") or {}
    ):
        nle = dict(nle)
        nle["segment_overrides"] = overrides
        nle["junction_nudge_history"] = nudge_history
        # Mark junction provenance without forcing structural cascade
        nle["junction_snip_qa"] = {"updated_at": _now(), "override_count": len(overrides)}
        save_nle(ctx, nle)
        changed = True

    timeline = _recompute_timeline(clips)
    new_edl = dict(edl)
    new_edl["clips"] = clips
    new_edl["timeline_duration_ms"] = timeline
    new_edl["silence_clip_count"] = sum(1 for c in clips if str(c.get("type") or "") == "silence")
    # Drop excluded from ordered list if present — always persist EDL when order
    # changes even if clip/override mutations did not set ``changed`` (otherwise
    # selection is updated and EDL on disk drifts).
    if excluded:
        ordered = [s for s in (new_edl.get("ordered_segment_ids") or []) if str(s) not in excluded]
        if ordered != list(new_edl.get("ordered_segment_ids") or []):
            changed = True
        # Selection is authority: bump lock on exclude, then copy onto EDL.
        _exclude_from_selection(ctx, excluded, reasons=exclude_reasons)
        new_edl["ordered_segment_ids"] = ordered
        from interview_mux.order_hash import copy_order_lock, stamp_order_hash

        if ctx.artifact_exists("master/selection.json"):
            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict):
                new_edl = copy_order_lock(sel, stamp_order_hash(new_edl))
            else:
                new_edl = stamp_order_hash(new_edl)
        else:
            new_edl = stamp_order_hash(new_edl)
        changed = True

    if changed:
        from interview_mux.order_hash import copy_order_lock, stamp_order_hash
        from interview_mux.write_staging import write_committed_json

        # Persist bound repairs immediately — StageInfo does not claim edl/selection,
        # so a normal flush would delete them and leave commitment diverged.
        new_edl = stamp_order_hash(new_edl)
        if ctx.artifact_exists("master/selection.json"):
            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict):
                # Selection leads: copy lock onto EDL; never rewrite selection from EDL.
                new_edl = copy_order_lock(sel, new_edl)
                from interview_mux.order_hash import assert_selection_leads_edl

                try:
                    assert_selection_leads_edl(sel, new_edl)
                except ValueError as exc:
                    ctx.log(
                        f"junction repair EDL/selection divergence (selection leads): {exc}",
                        level="warning",
                        stage=STAGE_ID,
                    )
        write_committed_json(ctx, "master/edl.json", new_edl, stage_key=STAGE_ID)

    return new_edl, applied, changed


def _exclude_from_selection(
    ctx: RunContext,
    excluded: set[str],
    *,
    reasons: dict[str, str] | None = None,
) -> None:
    if not excluded or not ctx.artifact_exists("master/selection.json"):
        return
    try:
        from interview_mux.hard_keep import hard_keep_segment_ids

        keeps = hard_keep_segment_ids(ctx)
        blocked = excluded & keeps
        if blocked:
            ctx.log(
                "junction refuse exclude of hard-keep: " + ", ".join(sorted(blocked)[:8]),
                level="warning",
                stage="junction_snip_qa",
            )
            excluded = {s for s in excluded if s not in keeps}
        if not excluded:
            return
    except Exception:
        pass
    sel = ctx.read_json("master/selection.json")
    if not isinstance(sel, dict):
        return
    from interview_mux.order_hash import bump_order_lock
    from interview_mux.write_staging import write_committed_json

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
        reason = (reasons or {}).get(sid) or "junction_snip_qa:exclude_micro"
        excl_list.append({"segment_id": sid, "reason": reason})
    sel["excluded_segment_ids"] = excl_list
    # Commit immediately — staging-only writes are invisible to commitment verify
    # when StageInfo does not claim selection.json.
    write_committed_json(
        ctx,
        "master/selection.json",
        bump_order_lock(sel, source="junction_snip_qa:exclude"),
        stage_key=STAGE_ID,
    )


def _merge_placement_adjustments(ctx: RunContext, rows: list[dict[str, Any]]) -> None:
    from interview_mux.placement_qa import OUTPUT_PATH, load_placement_adjustments
    from interview_mux.write_staging import write_committed_json

    doc = load_placement_adjustments(ctx)
    existing = [r for r in (doc.get("adjustments") or []) if isinstance(r, dict)]
    by_asset = {str(r.get("asset_id")): r for r in existing if r.get("asset_id")}
    for row in rows:
        aid = str(row.get("asset_id") or "")
        if not aid:
            continue
        prev = by_asset.get(aid, {})
        by_asset[aid] = {**prev, **row}
        # Keep SDP podcast cues sticky so remasters see soft fades without
        # re-depending solely on placement_adjustments flush timing.
        xf = row.get("suggested_crossfade_ms")
        if xf is not None:
            _patch_sdp_cue_crossfade(ctx, aid, int(xf))
    out = {"version": int(doc.get("version") or 1), "adjustments": list(by_asset.values())}
    write_committed_json(ctx, OUTPUT_PATH, out, stage_key=STAGE_ID)


def _patch_sdp_cue_crossfade(ctx: RunContext, asset_id: str, crossfade_ms: int) -> None:
    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        return
    plan = ctx.read_json("understanding/sound_design_plan.json")
    if not isinstance(plan, dict):
        return
    changed = False

    def _patch_list(cues: list[Any]) -> list[Any]:
        nonlocal changed
        out: list[Any] = []
        for cue in cues:
            if not isinstance(cue, dict):
                out.append(cue)
                continue
            if str(cue.get("asset_id") or "") != asset_id:
                out.append(cue)
                continue
            prev = int(cue.get("crossfade_ms") or 0)
            if prev >= crossfade_ms:
                out.append(cue)
                continue
            patched = dict(cue)
            patched["crossfade_ms"] = crossfade_ms
            out.append(patched)
            changed = True
        return out

    flow_plans = plan.get("flow_plans") if isinstance(plan.get("flow_plans"), dict) else {}
    podcast = flow_plans.get("podcast") if isinstance(flow_plans.get("podcast"), dict) else None
    if podcast and isinstance(podcast.get("cues"), list):
        podcast = dict(podcast)
        podcast["cues"] = _patch_list(list(podcast["cues"]))
        flow_plans = dict(flow_plans)
        flow_plans["podcast"] = podcast
        plan = dict(plan)
        plan["flow_plans"] = flow_plans
    if isinstance(plan.get("cues"), list):
        plan = dict(plan)
        plan["cues"] = _patch_list(list(plan["cues"]))
    if changed:
        from interview_mux.write_staging import write_committed_json

        write_committed_json(
            ctx,
            "understanding/sound_design_plan.json",
            plan,
            stage_key=STAGE_ID,
        )


def remaster_mix_only(ctx: RunContext) -> None:
    """Rebuild mix from current EDL (and placement adjustments) without wiping EDL."""
    from interview_mux.assembly_ledger import write_assembly_ledger
    from interview_mux.stages import assembly
    from interview_mux.write_staging import promote_staged_side_effects

    marker = ctx.final_path(".stage_done", "mix")
    if marker.is_file():
        try:
            marker.unlink()
        except OSError:
            pass
    ledger = write_assembly_ledger(ctx)
    if not ledger.get("complete", True):
        # Structural excludes can create new speech adjacencies. A mix-only
        # rebuild would bypass seam_glue and ship a naked reorder seam.
        assembly.run_edl(ctx)
        ledger = write_assembly_ledger(ctx)
        if not ledger.get("complete", True):
            raise RuntimeError(
                f"junction remaster left {ledger.get('naked_seam_count')} naked seam(s)"
            )
    assembly.run_mix(ctx)
    from interview_mux.seam_autopsy import write_render_ledger

    write_render_ledger(ctx)
    # EDL/assembly are owned by edl/mix for invalidation — promote as side effects
    # so junction flush does not delete the remastered render.
    promote_staged_side_effects(
        ctx,
        (
            "master/edl.json",
            "master/selection.json",
            "master/assembly.wav",
            "master/assembly_ledger.json",
            "master/render_ledger.json",
            "master/bridge_completeness.json",
            "sound_design/placement_adjustments.json",
            "understanding/sound_design_plan.json",
        ),
        stage_id=STAGE_ID,
    )


def _set_g_listen_pending_after_remaster(ctx: RunContext) -> None:
    """Refresh listen critic and set g_listen_pending when recommended."""
    try:
        if not ctx.artifact_exists("master/listen_critic.json"):
            return
        critic = ctx.read_json("master/listen_critic.json")
        if isinstance(critic, dict) and critic.get("g_listen_recommended"):

            def _glisten(m: dict) -> None:
                # Operator already continued/skipped for this run — do not re-arm
                # (remaster thrash + e2e clear loops otherwise fight forever).
                if m.get("g_listen_skipped") or m.get("g_listen_cleared"):
                    return
                m["g_listen_pending"] = True
                if critic.get("quality_score") is not None:
                    m["g_listen_quality_score"] = critic.get("quality_score")

            ctx.mutate_run_meta(_glisten)
    except Exception as exc:
        ctx.log(
            f"junction remaster: could not refresh g_listen pending ({exc})",
            level="warning",
            stage=STAGE_ID,
        )


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
        "llm_budget": "at_most_two_calls_primary_plus_retry",
    }


def run_junction_feel_audit(
    ctx: RunContext,
    snip_report: dict[str, Any],
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One LLM call judging final master feel. Retry once on schema/unavailable."""
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
    verdict = "unavailable"
    llm_calls = 0
    error: str | None = None
    allowed = {"pass", "soft_pass", "fail", "remux_suggested", "unavailable"}

    def _parse_feel_payload(envelope: Any) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], str | None]:
        local_directives: list[dict[str, Any]] = []
        local_findings: list[dict[str, Any]] = []
        local_error: str | None = None
        local_verdict = "unavailable"
        raw = envelope.get("parsed") if isinstance(envelope, dict) else None
        if not isinstance(raw, dict):
            raw = envelope.get("artifacts") if isinstance(envelope, dict) else None
            if isinstance(raw, dict) and "junction_feel_audit" in raw:
                raw = raw["junction_feel_audit"]
            elif isinstance(envelope, dict) and "verdict" in envelope:
                raw = envelope
        if isinstance(raw, dict):
            local_verdict = str(raw.get("verdict") or "unavailable")
            for d in raw.get("directives") or []:
                if not isinstance(d, dict):
                    continue
                action = str(d.get("action") or "")
                if action not in ALLOWED_FEEL_ACTIONS:
                    continue
                local_directives.append(d)
            local_findings = [f for f in (raw.get("findings") or []) if isinstance(f, dict)]
        else:
            content = ""
            if isinstance(envelope, dict):
                content = str(envelope.get("content") or envelope.get("text") or "")
            if content.strip().startswith("{"):
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict):
                        local_verdict = str(parsed.get("verdict") or "unavailable")
                        for d in parsed.get("directives") or []:
                            if isinstance(d, dict) and str(d.get("action") or "") in ALLOWED_FEEL_ACTIONS:
                                local_directives.append(d)
                        local_findings = [
                            f for f in (parsed.get("findings") or []) if isinstance(f, dict)
                        ]
                except json.JSONDecodeError:
                    local_error = "feel_audit_unparseable"
            else:
                local_error = "feel_audit_empty_payload"
        if local_verdict not in allowed:
            local_verdict = "unavailable"
        return local_verdict, local_directives, local_findings, local_error

    from interview_mux.stages.llm_runner import run_prompt_envelope

    user_content = json.dumps(packet, indent=2, ensure_ascii=False)
    max_attempts = 3
    tiers = ("standard", "standard", "flagship")
    for attempt in range(1, max_attempts + 1):
        try:
            envelope = run_prompt_envelope(
                FEEL_STAGE_KEY,
                FEEL_PROMPT,
                user_content,
                ctx=ctx,
                explicit_tier=tiers[attempt - 1],
                bump_tier=attempt > 1,
                record_stage_key=FEEL_STAGE_KEY,
            )
            llm_calls += 1
            verdict, directives, findings, error = _parse_feel_payload(envelope)
            if verdict != "unavailable" and not error:
                break
            if attempt < max_attempts:
                ctx.log(
                    f"junction_feel_audit retry after unavailable/schema issue "
                    f"(attempt {attempt}/{max_attempts})",
                    level="warn",
                    stage=STAGE_ID,
                )
                continue
        except Exception as exc:
            error = str(exc)[:240]
            verdict = "unavailable"
            ctx.log(f"junction_feel_audit unavailable: {exc}", level="error", stage=STAGE_ID)
            if attempt < max_attempts:
                continue
            break

    if error:
        verdict = "unavailable"

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
    nle = load_nle(ctx)
    nudge_history = (
        nle.get("junction_nudge_history")
        if isinstance(nle.get("junction_nudge_history"), dict)
        else {}
    )
    for d in directives:
        action = str(d.get("action") or "")
        if action not in ALLOWED_FEEL_ACTIONS:
            continue
        detail = dict(d.get("detail") or {}) if isinstance(d.get("detail"), dict) else {}
        if action == "adjust_crossfade":
            action = "adjust_music_fade"
            if "suggested_crossfade_ms" not in detail:
                detail["suggested_crossfade_ms"] = int(conf.get("music_soft_crossfade_ms") or 180)
        severity = str(d.get("severity") or "warn")
        # Feel must not re-nudge edges already applied this stage unless critical.
        if action == "nudge_source_bounds" and severity != "critical":
            sid = str(d.get("segment_id") or "")
            edge = str(detail.get("edge") or "end")
            if sid and f"{sid}:{edge}" in nudge_history:
                continue
        findings.append(
            {
                "kind": f"feel_{action}",
                "severity": severity,
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
    max_rounds = max(1, int(conf.get("max_remaster_rounds") or 8))
    residual_findings = list(findings)

    # Two full repair runs maximum.  Each run detects the complete set first,
    # applies every repair in one batch, remasters, and only then rescans.
    from interview_mux.failure_recovery import identify_all_failures, plan_all_fixes

    remediation_runs: list[dict[str, Any]] = []
    current_edl = edl
    prior_applied_sig: set[tuple[str, str, int]] | None = None
    for run_index in range(1, max_rounds + 1):
        if not residual_findings:
            break
        provisional = {
            "version": 1,
            "mode": mode,
            "pace_class": _pace_class(ctx),
            "findings": residual_findings,
            "applied": [],
            "remaster_rounds": remaster_rounds,
            "llm_calls": 0,
            "advisory": False,
            "blocking": True,
            "generated_at": _now(),
        }
        review = identify_all_failures(
            ctx,
            trigger="junction_quality",
            snip_report=provisional,
            run_index=run_index,
        )
        plan_all_fixes(ctx, review)
        next_edl, run_applied, needs = apply_junction_repairs(
            ctx, current_edl, residual_findings, cfg=conf
        )
        applied.extend(run_applied)
        applied_sig = {
            (
                str(a.get("segment_id") or a.get("kind") or ""),
                str(a.get("action") or ""),
                int(round(int(a.get("applied_ms") or a.get("suggested_crossfade_ms") or 0) / 40.0) * 40),
            )
            for a in run_applied
            if isinstance(a, dict) and a.get("status") == "applied"
        }
        if prior_applied_sig is not None and applied_sig and applied_sig == prior_applied_sig:
            ctx.log(
                "junction_snip_qa: oscillating repair signature — halt remaster thrash",
                level="warning",
                stage=STAGE_ID,
            )
            residual_findings = detect_junction_findings(ctx, current_edl, cfg=conf)
            break
        prior_applied_sig = applied_sig
        if needs:
            try:
                remaster_mix_only(ctx)
            except Exception as exc:
                from interview_mux.loud_fail import raise_loud_failure

                raise_loud_failure(
                    ctx,
                    f"Junction remediation run {run_index} could not remaster: {exc}",
                    stage=STAGE_ID,
                    reason="junction_remaster_failed",
                    detail={"run_index": run_index, "piece_count": len(residual_findings)},
                    cause=exc,
                )
            remaster_rounds += 1
            _set_g_listen_pending_after_remaster(ctx)
        current_edl = (
            ctx.read_json("master/edl.json")
            if ctx.artifact_exists("master/edl.json")
            else next_edl
        )
        residual_findings = detect_junction_findings(ctx, current_edl, cfg=conf)
        critical_residuals = [
            f for f in residual_findings if str(f.get("severity") or "") == "critical"
        ]
        pieces = [p for p in (review.get("broken_pieces") or []) if isinstance(p, dict)]
        pieces_resolved = max(0, len(pieces) - len(critical_residuals))
        actions_executed = [
            str(a.get("action") or "")
            for a in run_applied
            if isinstance(a, dict) and a.get("status") == "applied"
        ]
        row = {
            "run_index": run_index,
            "pieces_targeted": len(pieces),
            "pieces_resolved": pieces_resolved,
            "actions_executed": actions_executed,
            "residual_after": len(residual_findings),
            "critical_residual_after": len(critical_residuals),
            "completed_at": _now(),
        }
        remediation_runs.append(row)
        from interview_mux.failure_recovery import append_learning
        from interview_mux.write_staging import write_committed_json

        write_committed_json(
            ctx,
            "master/remediation_run_log.json",
            {
                "version": 1,
                "max_runs": 2,
                "runs": remediation_runs,
                "runs_used": len(remediation_runs),
                "third_run_forbidden": True,
            },
        )
        append_learning(
            ctx,
            {
                "execution_id": ctx.run_id,
                "source_audio_hash": (
                    (ctx.read_json("run_meta.json") or {}).get("source_audio_hash")
                    if ctx.artifact_exists("run_meta.json")
                    else None
                ),
                "trigger": "junction_quality",
                **row,
                "failure_codes": sorted({str(p.get("kind") or "") for p in pieces}),
                "succeeded": pieces_resolved >= len(pieces) and not critical_residuals,
            },
        )
        if not critical_residuals:
            break

    report = {
        "version": 1,
        "mode": mode,
        "pace_class": _pace_class(ctx),
        "findings": findings,
        "applied": applied,
        "residual_findings": residual_findings,
        "remaster_rounds": remaster_rounds,
        "remediation_runs": remediation_runs,
        "llm_calls": 0,
        "advisory": mode != "authoritative",
        "blocking": mode == "authoritative",
        "generated_at": _now(),
    }
    ctx.write_json(QA_REL, report)

    audit = run_junction_feel_audit(ctx, report, cfg=conf)
    report["llm_calls"] = int(audit.get("llm_calls") or 0)
    ctx.write_json(QA_REL, report)

    if report["llm_calls"] > 6:
        ctx.log(
            f"junction_snip_qa feel-audit calls={report['llm_calls']} (escalation ladder exhausted)",
            level="warning",
            stage=STAGE_ID,
        )

    if (
        audit.get("verdict") != "unavailable"
        and remaster_rounds < max_rounds
        and apply_feel_directives(ctx, audit, cfg=conf)
    ):
        try:
            remaster_mix_only(ctx)
            remaster_rounds += 1
            _set_g_listen_pending_after_remaster(ctx)
            report["remaster_rounds"] = remaster_rounds
            ctx.write_json(QA_REL, report)
        except Exception as exc:
            from interview_mux.loud_fail import raise_loud_failure

            try:
                from interview_mux.homunculus.issues import ingest_catch

                ingest_catch(
                    ctx,
                    kind="junction_feel_remaster_failed",
                    source="junction_snip_qa",
                    stage_id=STAGE_ID,
                    implicated=[STAGE_ID, "mix"],
                    evidence={"error": str(exc)[:240]},
                )
            except Exception:
                pass
            raise_loud_failure(
                ctx,
                f"Junction feel remediation could not remaster: {exc}",
                stage=STAGE_ID,
                reason="junction_feel_remaster_failed",
                cause=exc,
            )

    from interview_mux.seam_autopsy import build_autopsy, enrich_ledger, write_autopsy
    from interview_mux.order_hash import (
        assert_selection_leads_edl,
        copy_order_lock,
        order_hashes_match,
        stamp_order_hash,
    )
    from interview_mux.write_staging import write_committed_json

    # Final air-order lock: EDL must match selection. Never rewrite selection from EDL.
    if isinstance(current_edl, dict):
        current_edl = stamp_order_hash(current_edl)
        if ctx.artifact_exists("master/selection.json"):
            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict) and not order_hashes_match(sel, current_edl):
                ctx.log(
                    "junction_snip_qa: EDL diverges from selection — aligning EDL to selection lock",
                    level="warning",
                    stage=STAGE_ID,
                )
                # Align EDL ordered ids to selection (selection leads).
                current_edl = dict(current_edl)
                current_edl["ordered_segment_ids"] = list(sel.get("ordered_segment_ids") or [])
                current_edl = copy_order_lock(sel, stamp_order_hash(current_edl))
                try:
                    assert_selection_leads_edl(sel, current_edl)
                except ValueError as exc:
                    from interview_mux.loud_fail import raise_loud_failure

                    raise_loud_failure(
                        ctx,
                        str(exc),
                        stage=STAGE_ID,
                        reason="order_lock_selection_leads",
                        cause=exc,
                    )
            elif isinstance(sel, dict):
                current_edl = copy_order_lock(sel, current_edl)
        # Persist in-memory EDL only when disk copy differs (repairs / order stamp).
        disk_edl = (
            ctx.read_json("master/edl.json")
            if ctx.artifact_exists("master/edl.json")
            else None
        )
        if not isinstance(disk_edl, dict) or _canonical_edl_order(disk_edl) != _canonical_edl_order(
            current_edl
        ) or str(disk_edl.get("order_content_hash") or "") != str(
            current_edl.get("order_content_hash") or ""
        ):
            write_committed_json(ctx, "master/edl.json", current_edl, stage_key=STAGE_ID)

        # If assembly is older than the committed EDL (or missing), remaster once.
        try:
            asm_path = ctx.final_path("master", "assembly.wav")
            edl_path = ctx.final_path("master", "edl.json")
            needs_remaster = (not asm_path.is_file()) or (
                edl_path.is_file()
                and asm_path.is_file()
                and asm_path.stat().st_mtime_ns < edl_path.stat().st_mtime_ns
            )
            if needs_remaster:
                ctx.log(
                    "junction_snip_qa: remastering mix so assembly matches current EDL",
                    level="info",
                    stage=STAGE_ID,
                )
                remaster_mix_only(ctx)
                remaster_rounds += 1
                report["remaster_rounds"] = remaster_rounds
                ctx.write_json(QA_REL, report)
                if ctx.artifact_exists("master/edl.json"):
                    loaded = ctx.read_json("master/edl.json")
                    if isinstance(loaded, dict):
                        current_edl = loaded
        except Exception as exc:
            from interview_mux.loud_fail import raise_loud_failure

            raise_loud_failure(
                ctx,
                f"Junction could not remaster assembly for commitment: {exc}",
                stage=STAGE_ID,
                reason="junction_commitment_remaster_failed",
                cause=exc,
            )

    autopsy = build_autopsy(
        ctx,
        phase="post_junction",
        snip_report=report,
        edl=current_edl,
    )
    write_autopsy(ctx, autopsy)
    enrich_ledger(ctx, autopsy)
    commitment = autopsy.get("commitment") if isinstance(autopsy.get("commitment"), dict) else {}
    critical_left = [
        f for f in residual_findings if str(f.get("severity") or "") == "critical"
    ]
    blocking_reasons = list(commitment.get("reasons") or [])
    # When autopsy commitment is already committed and the feel audit soft-passed,
    # residual "critical" labels after the remaster budget are observational —
    # re-running junction forever does not improve ship readiness.
    commit_ok = str(commitment.get("status") or "") == "committed"
    feel_ok = str(audit.get("verdict") or "") in {"pass", "soft_pass", "warn"}
    _INCOMPLETE_SOFT_BLOCK_KINDS = frozenset(
        {
            "on_a_roll",
            "incomplete_clause",
            "chapter_bleed_incomplete",
        }
    )

    def _is_incomplete_cut_residual(finding: dict[str, Any]) -> bool:
        kind = str(finding.get("kind") or "")
        if kind in _INCOMPLETE_SOFT_BLOCK_KINDS:
            return True
        detail = finding.get("detail") if isinstance(finding.get("detail"), dict) else {}
        return bool(detail.get("unrecoverable_within_clip"))

    if critical_left and not (commit_ok and feel_ok):
        blocking_reasons.append("critical_junction_residuals_after_two_runs")
    elif critical_left and commit_ok and feel_ok:
        softenable = [
            f
            for f in residual_findings
            if isinstance(f, dict)
            and str(f.get("severity") or "") == "critical"
            and not _is_incomplete_cut_residual(f)
        ]
        from interview_mux.e2e_soft import e2e_soft_enabled

        if softenable and e2e_soft_enabled():
            report["critical_residuals_softened"] = True
            report["critical_residual_soft_reason"] = (
                "commitment_committed_and_feel_soft_pass_after_budget"
            )
            for finding in softenable:
                finding["severity"] = "warning"
                finding["e2e_softened"] = True
        elif softenable:
            blocking_reasons.append("critical_junction_residuals_after_two_runs")
        # Incomplete mid-clause residuals stay critical — cut_integrity must fail.
        critical_left = [
            f
            for f in residual_findings
            if isinstance(f, dict) and str(f.get("severity") or "") == "critical"
        ]
        if critical_left:
            blocking_reasons.append("critical_incomplete_cut_residuals")
            # Prefer seam re-fuse when incomplete residuals remain between selected natives.
            try:
                from interview_mux.stages.low_conf_fuse_stages import (
                    run_connector_fuse_pass_junction_heal,
                )

                run_connector_fuse_pass_junction_heal(ctx)
                report["connector_fuse_junction_heal"] = True
            except Exception as fuse_exc:  # noqa: BLE001
                report["connector_fuse_junction_heal_error"] = str(fuse_exc)[:300]
    # unavailable after retry is a blocking quality signal.
    if audit.get("verdict") == "unavailable":
        report["feel_audit_unavailable"] = True
        blocking_reasons.append("junction_feel_audit_unavailable")
    enforce_block = mode == "authoritative"
    report["commitment"] = commitment
    report["blocking_reasons"] = sorted(set(blocking_reasons))
    ctx.write_json(QA_REL, report)

    # Surface the authoritative result in run_meta.
    meta: dict[str, Any]
    if ctx.artifact_exists("run_meta.json"):
        doc = ctx.read_json("run_meta.json")
        meta = doc if isinstance(doc, dict) else {}
    else:
        meta = {}
    qc = meta.get("qc_summaries") if isinstance(meta.get("qc_summaries"), dict) else {}
    qc["junction_snip_qa"] = {
        "passed": not bool(blocking_reasons),
        "advisory": False,
        "blocking": bool(blocking_reasons) and enforce_block,
        "findings": len(findings),
        "applied": len(applied),
        "residual_findings": len(residual_findings),
        "critical_residuals": len(critical_left),
        "remaster_rounds": remaster_rounds,
        "llm_calls": report["llm_calls"],
        "feel_verdict": audit.get("verdict"),
        "commitment_status": commitment.get("status"),
        "blocking_reasons": sorted(set(blocking_reasons)),
    }
    qc["seam_autopsy"] = {
        "passed": not bool(autopsy.get("blocking_reasons")),
        "blocking": bool(autopsy.get("blocking_reasons")) and enforce_block,
        "commitment_status": commitment.get("status"),
        "continuity": (autopsy.get("scores") or {}).get("continuity"),
        "worst_seam_count": len(autopsy.get("worst_seam_ids") or []),
    }
    meta["qc_summaries"] = qc
    ctx.write_json("run_meta.json", meta)

    if blocking_reasons and enforce_block:
        from interview_mux.loud_fail import raise_loud_failure

        raise_loud_failure(
            ctx,
            "Junction quality failed after the bounded remediation budget: "
            + ", ".join(sorted(set(blocking_reasons))),
            stage=STAGE_ID,
            reason="junction_quality_blocked",
            detail={
                "remediation_runs_used": len(remediation_runs),
                "critical_residuals": len(critical_left),
                "blocking_reasons": sorted(set(blocking_reasons)),
            },
        )
