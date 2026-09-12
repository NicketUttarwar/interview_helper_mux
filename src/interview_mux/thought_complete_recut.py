"""Surgical thought-complete recuts for hanging native ends.

When a kept clip ends mid-thought, do **not** absorb the next whole segment
(``merge_micro``). Walk following same-speaker transcript, pick a complete-thought
cut (LLM batched O(1), deterministic fallback), extend the hanging clip only to
that cut, and recut leftover following speech so it stays independent.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from interview_mux.audio_timeline import snap_cut_to_word_boundary
from interview_mux.gap_vo_prior_context import (
    DEFAULT_PAUSE_SPLIT_MS,
    ends_complete_thought,
    ends_hanging_setup,
    is_backchannel_only_text,
    is_legal_conceptual_hinge,
    opens_with_backchannel_completion,
    opens_with_clause_continuer,
)
from interview_mux.run_context import RunContext

STAGE_KEY = "junction_thought_complete"
PROMPT_REL = "mastering/junction-thought-complete.system.txt"
ARTIFACT_REL = "master/junction_thought_complete.json"
ACTION = "thought_complete_recut"

_MAX_LLM_ATTEMPTS = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _word_text(w: dict[str, Any]) -> str:
    return str(w.get("text") or w.get("word") or "").strip()


def _slim_word(w: dict[str, Any]) -> dict[str, Any]:
    return {
        "text": _word_text(w),
        "start_ms": int(w.get("start_ms") or 0),
        "end_ms": int(w.get("end_ms") or 0),
    }


def _words_in_window(
    words: list[dict[str, Any]], start_ms: int, end_ms: int
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for w in words:
        if not isinstance(w, dict):
            continue
        ws = int(w.get("start_ms") or 0)
        we = int(w.get("end_ms") or 0)
        if we <= start_ms or ws >= end_ms:
            continue
        if _word_text(w):
            out.append(w)
    return out


def _pause_after(words: list[dict[str, Any]], index: int) -> int | None:
    if index < 0 or index >= len(words) - 1:
        return None
    return max(
        0,
        int(words[index + 1].get("start_ms") or 0)
        - int(words[index].get("end_ms") or 0),
    )


def following_speech_clips(
    clips: list[dict[str, Any]],
    index: int,
    *,
    speaker: str,
    segs: dict[str, Any],
    max_segments: int,
    horizon_ms: int,
) -> list[dict[str, Any]]:
    """Timeline-following same-speaker speech clips inside the horizon."""
    from interview_mux.junction_snip_qa import _speaker_of

    out: list[dict[str, Any]] = []
    hanging = clips[index]
    hang_end = int(hanging.get("source_end_ms") or hanging.get("source_start_ms") or 0)
    for j in range(index + 1, len(clips)):
        other = clips[j]
        if str(other.get("type") or "") != "speech":
            continue
        oid = str(other.get("segment_id") or "")
        if not oid:
            continue
        oseg = segs.get(oid) if isinstance(segs.get(oid), dict) else {}
        other_speaker = _speaker_of(oseg if isinstance(oseg, dict) else None)
        if speaker and other_speaker and other_speaker != speaker:
            continue
        oss = int(other.get("source_start_ms") or 0)
        if oss >= horizon_ms:
            break
        if oss + 40 < hang_end:
            continue
        out.append(other)
        if len(out) >= max_segments:
            break
    return out


def build_lookahead_chain(
    *,
    clips: list[dict[str, Any]],
    index: int,
    words: list[dict[str, Any]],
    speaker: str,
    segs: dict[str, Any],
    max_segments: int,
    max_ms: int,
) -> list[dict[str, Any]]:
    hanging = clips[index]
    src_end = int(hanging.get("source_end_ms") or hanging.get("source_start_ms") or 0)
    horizon = src_end + max(500, max_ms)
    following = following_speech_clips(
        clips,
        index,
        speaker=speaker,
        segs=segs,
        max_segments=max_segments,
        horizon_ms=horizon,
    )
    chain: list[dict[str, Any]] = []
    cursor = src_end
    for other in following:
        oss = int(other.get("source_start_ms") or 0)
        ose = int(other.get("source_end_ms") or oss)
        if oss > cursor + 40:
            gap_words = _words_in_window(words, cursor, oss)
            if gap_words:
                chain.append(
                    {
                        "kind": "gap",
                        "segment_id": None,
                        "start_ms": cursor,
                        "end_ms": oss,
                        "words": [_slim_word(w) for w in gap_words],
                        "text": " ".join(_word_text(w) for w in gap_words),
                    }
                )
        clip_words = _words_in_window(words, oss, ose)
        chain.append(
            {
                "kind": "speech",
                "segment_id": str(other.get("segment_id") or ""),
                "start_ms": oss,
                "end_ms": ose,
                "words": [_slim_word(w) for w in clip_words],
                "text": " ".join(_word_text(w) for w in clip_words),
            }
        )
        cursor = max(cursor, ose)
    if not following:
        gap_words = _words_in_window(words, src_end, horizon)
        if gap_words:
            chain.append(
                {
                    "kind": "gap",
                    "segment_id": None,
                    "start_ms": src_end,
                    "end_ms": int(gap_words[-1].get("end_ms") or src_end),
                    "words": [_slim_word(w) for w in gap_words],
                    "text": " ".join(_word_text(w) for w in gap_words),
                }
            )
    return chain


def lookahead_available(
    *,
    clips: list[dict[str, Any]],
    index: int,
    words: list[dict[str, Any]],
    speaker: str,
    segs: dict[str, Any],
    max_segments: int,
    max_ms: int,
) -> bool:
    hanging = clips[index]
    src_end = int(hanging.get("source_end_ms") or hanging.get("source_start_ms") or 0)
    if _words_in_window(words, src_end, src_end + max(500, max_ms)):
        return True
    return bool(
        following_speech_clips(
            clips,
            index,
            speaker=speaker,
            segs=segs,
            max_segments=max_segments,
            horizon_ms=src_end + max(500, max_ms),
        )
    )


def _next_opens_new_beat(text: str) -> bool:
    """True when following speech starts a new native beat, not the hanging clause."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    if opens_with_backchannel_completion(stripped):
        return True
    first = stripped.lower().strip(".,!?;:\"'")
    return first in {"anyway", "meanwhile", "however", "okay", "ok", "alright", "well"}


def complete_thought_candidates(
    words: list[dict[str, Any]],
    from_ms: int,
    *,
    horizon_ms: int,
    speaker: str = "",
) -> list[int]:
    """Word-end times after ``from_ms`` that finish the hanging clause.

    Stops before a *second* non-backchannel complete idea so we never swallow
    the next native section whole. A following backchannel / new-beat opener
    ("okay", "so", "then") is a legal cut even without ``.!?``.
    """
    window = [
        w
        for w in words
        if from_ms < int(w.get("end_ms") or 0) <= horizon_ms and _word_text(w)
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
        return []
    candidates: list[int] = []
    accumulated: list[str] = []
    seen_real_complete = False
    for i, w in enumerate(window):
        tok = _word_text(w)
        accumulated.append(tok)
        candidate = " ".join(accumulated)
        pause = _pause_after(window, i)
        end_ms = int(w.get("end_ms") or 0)
        rest = " ".join(
            _word_text(window[j]) for j in range(i + 1, min(i + 5, len(window)))
        )
        complete = ends_complete_thought(candidate, next_pause_ms=pause)
        if not complete:
            # Trailing commas / subordinate tails still count as done when the
            # next native beat is a backchannel or discourse opener ("okay").
            if rest and _next_opens_new_beat(rest):
                complete = True
            elif not ends_hanging_setup(candidate) and is_legal_conceptual_hinge(
                candidate,
                words=window,
                end_ms=end_ms,
                next_pause_ms=pause,
            ):
                complete = True
        if not complete:
            continue
        if is_backchannel_only_text(candidate):
            # Skip filler closes when a real completion can still follow.
            if i == len(window) - 1:
                candidates.append(end_ms)
            continue
        if seen_real_complete:
            break
        candidates.append(end_ms)
        seen_real_complete = True
    return candidates


def remainder_open_ms(
    words: list[dict[str, Any]],
    keep_end_ms: int,
    *,
    horizon_ms: int,
    speaker: str = "",
) -> int | None:
    """First legal leftover open after the complete-thought cut, or None to drop."""
    window = [
        w
        for w in words
        if keep_end_ms <= int(w.get("start_ms") or 0) <= horizon_ms and _word_text(w)
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
    leftover = " ".join(_word_text(w) for w in window)
    if is_backchannel_only_text(leftover):
        return None
    # Skip continuer-only prefix ("and" / "but") so the leftover opens legally.
    start_i = 0
    while start_i < len(window) and opens_with_clause_continuer(_word_text(window[start_i])):
        start_i += 1
    if start_i >= len(window):
        return None
    slice_words = window[start_i:]
    text = " ".join(_word_text(w) for w in slice_words)
    if is_backchannel_only_text(text):
        return None
    pause = None
    if len(slice_words) >= 2:
        pause = max(
            0,
            int(slice_words[1].get("start_ms") or 0) - int(slice_words[0].get("end_ms") or 0),
        )
    hinge = is_legal_conceptual_hinge(
        _word_text(slice_words[0]),
        next_pause_ms=pause if pause is not None else DEFAULT_PAUSE_SPLIT_MS,
    )
    if not hinge and opens_with_clause_continuer(text):
        return None
    return int(slice_words[0].get("start_ms") or 0)


def propose_deterministic_cut(
    *,
    hanging_end_ms: int,
    words: list[dict[str, Any]],
    speaker: str,
    horizon_ms: int,
) -> dict[str, Any] | None:
    candidates = complete_thought_candidates(
        words, hanging_end_ms, horizon_ms=horizon_ms, speaker=speaker
    )
    if not candidates:
        return None
    keep_end = candidates[0]
    remainder = remainder_open_ms(
        words, keep_end, horizon_ms=horizon_ms, speaker=speaker
    )
    return {
        "keep_end_ms": keep_end,
        "remainder_start_ms": remainder,
        "legal_cut_ms": candidates,
        "source": "deterministic_transcript",
    }


def _snap_keep_end(
    keep_end_ms: int,
    candidates: list[int],
    words: list[dict[str, Any]],
) -> int | None:
    if not candidates:
        return None
    if keep_end_ms in candidates:
        return keep_end_ms
    snapped = snap_cut_to_word_boundary(
        keep_end_ms, words, margin_ms=40, max_shift_ms=400
    )
    if snapped in candidates:
        return snapped
    nearest = min(candidates, key=lambda ms: abs(ms - keep_end_ms))
    if abs(nearest - keep_end_ms) <= 800:
        return nearest
    return candidates[0]


def _horizon_ms(hanging_end: int, chain: list[dict[str, Any]], max_ms: int) -> int:
    last = hanging_end + max(500, max_ms)
    for row in chain:
        last = max(last, int(row.get("end_ms") or last))
    return last


def build_case_packet(
    *,
    case_id: str,
    hanging_id: str,
    hanging_start_ms: int,
    hanging_end_ms: int,
    hanging_end_text: str,
    speaker: str,
    chain: list[dict[str, Any]],
    words: list[dict[str, Any]],
    max_ms: int,
) -> dict[str, Any]:
    horizon = _horizon_ms(hanging_end_ms, chain, max_ms)
    det = propose_deterministic_cut(
        hanging_end_ms=hanging_end_ms,
        words=words,
        speaker=speaker,
        horizon_ms=horizon,
    )
    lookahead_words: list[dict[str, Any]] = []
    for row in chain:
        lookahead_words.extend(row.get("words") or [])
    return {
        "case_id": case_id,
        "hanging_segment_id": hanging_id,
        "speaker_id": speaker,
        "hanging_end_text": hanging_end_text,
        "hanging_source_start_ms": hanging_start_ms,
        "hanging_source_end_ms": hanging_end_ms,
        "lookahead": chain,
        "words": lookahead_words,
        "legal_cut_ms": list((det or {}).get("legal_cut_ms") or []),
        "deterministic_proposal": det,
    }


def _parse_llm_cuts(envelope: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(envelope, dict):
        return []
    artifacts = envelope.get("artifacts")
    payload = artifacts if isinstance(artifacts, dict) else envelope
    for key in ("junction_thought_complete", "content"):
        nested = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(nested, dict):
            payload = nested
            break
    if isinstance(payload, dict) and isinstance(payload.get("content"), str):
        try:
            parsed = json.loads(payload["content"])
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            pass
    rows = payload.get("cuts") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict) and r.get("case_id")]


def run_junction_thought_complete(
    ctx: RunContext,
    cases: list[dict[str, Any]],
    *,
    cfg: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], int]:
    """One batched LLM call (max 2 attempts). Returns (artifact, llm_calls)."""
    del cfg
    empty = {
        "version": 1,
        "generated_at": _now(),
        "cuts": [],
        "llm_calls": 0,
        "source": "skipped",
    }
    if not cases:
        return empty, 0
    packet = {
        "task": (
            "Pick complete-thought cut points for hanging native clips. "
            "Do not absorb whole following sections."
        ),
        "excerpts": [str(c.get("hanging_end_text") or "") for c in cases],
        "words": [w for c in cases for w in (c.get("words") or [])][:80],
        "cases": cases,
    }
    user_content = json.dumps(packet, indent=2, ensure_ascii=False)
    from interview_mux.stages.llm_runner import run_prompt_envelope

    llm_calls = 0
    cuts: list[dict[str, Any]] = []
    error: str | None = None
    for attempt in range(1, _MAX_LLM_ATTEMPTS + 1):
        try:
            envelope = run_prompt_envelope(
                STAGE_KEY,
                PROMPT_REL,
                user_content,
                ctx=ctx,
                include_preamble=False,
                task_kind="primary",
                explicit_tier="standard" if attempt == 1 else "flagship",
                bump_tier=attempt > 1,
                record_stage_key=STAGE_KEY,
            )
            llm_calls += 1
            cuts = _parse_llm_cuts(envelope if isinstance(envelope, dict) else None)
            if cuts:
                error = None
                break
            error = "empty_cuts"
        except Exception as exc:  # noqa: BLE001
            error = str(exc)[:240]
            ctx.log(
                f"junction_thought_complete LLM unavailable (attempt {attempt}): {exc}",
                level="warning",
                stage=STAGE_KEY,
            )
    artifact = {
        "version": 1,
        "generated_at": _now(),
        "cuts": cuts,
        "llm_calls": llm_calls,
        "source": "llm" if cuts else "deterministic_fallback",
        "error": error,
    }
    ctx.write_json(ARTIFACT_REL, artifact)
    return artifact, llm_calls


def enrich_thought_complete_findings(
    ctx: RunContext,
    edl: dict[str, Any],
    findings: list[dict[str, Any]],
    *,
    cfg: dict[str, Any] | None = None,
    allow_llm: bool = True,
) -> tuple[list[dict[str, Any]], int]:
    """Fill keep_end / remainder on thought_complete_recut findings. O(1) LLM."""
    from interview_mux.junction_snip_qa import (
        _clip_end_text,
        _segments_by_id,
        _speaker_of,
        _transcript_words,
        junction_snip_cfg,
    )

    conf = cfg or junction_snip_cfg()
    if not bool(conf.get("thought_complete_llm_enabled", True)) and not findings:
        return findings, 0
    clips = [c for c in (edl.get("clips") or []) if isinstance(c, dict)]
    words = _transcript_words(ctx)
    segs = _segments_by_id(ctx)
    max_segments = max(1, int(conf.get("thought_complete_max_segments") or 4))
    max_ms = max(500, int(conf.get("thought_complete_max_ms") or conf.get("phrase_extend_max_ms") or 24000))

    pending: list[tuple[dict[str, Any], dict[str, Any]]] = []
    packets: list[dict[str, Any]] = []
    for f in findings:
        if str(f.get("action") or "") != ACTION:
            continue
        sid = str(f.get("segment_id") or "")
        idx = f.get("clip_index")
        if idx is None:
            idx = next(
                (
                    i
                    for i, c in enumerate(clips)
                    if str(c.get("type") or "") == "speech"
                    and str(c.get("segment_id") or "") == sid
                ),
                None,
            )
        if idx is None or not sid:
            continue
        clip = clips[int(idx)]
        hang_start = int(clip.get("source_start_ms") or 0)
        hang_end = int(clip.get("source_end_ms") or hang_start)
        speaker = _speaker_of(segs.get(sid) if isinstance(segs.get(sid), dict) else None)
        chain = build_lookahead_chain(
            clips=clips,
            index=int(idx),
            words=words,
            speaker=speaker,
            segs=segs,
            max_segments=max_segments,
            max_ms=max_ms,
        )
        packet = build_case_packet(
            case_id=sid,
            hanging_id=sid,
            hanging_start_ms=hang_start,
            hanging_end_ms=hang_end,
            hanging_end_text=str(
                (f.get("detail") or {}).get("end_text")
                or _clip_end_text(segs.get(sid), words, hang_end)
            ),
            speaker=speaker,
            chain=chain,
            words=words,
            max_ms=max_ms,
        )
        packets.append(packet)
        pending.append((f, packet))

    llm_calls = 0
    by_id: dict[str, dict[str, Any]] = {}
    llm_on = bool(allow_llm) and bool(conf.get("thought_complete_llm_enabled", True))
    if packets and llm_on:
        artifact, llm_calls = run_junction_thought_complete(ctx, packets, cfg=conf)
        for row in artifact.get("cuts") or []:
            if isinstance(row, dict) and row.get("case_id"):
                by_id[str(row["case_id"])] = row
    elif packets:
        ctx.write_json(
            ARTIFACT_REL,
            {
                "version": 1,
                "generated_at": _now(),
                "cuts": [],
                "llm_calls": 0,
                "source": "llm_disabled",
            },
        )

    for f, packet in pending:
        sid = str(packet.get("case_id") or "")
        det = packet.get("deterministic_proposal") if isinstance(packet.get("deterministic_proposal"), dict) else None
        llm_row = by_id.get(sid)
        hang_end = int(packet.get("hanging_source_end_ms") or 0)
        horizon = hang_end + max_ms
        for row in packet.get("lookahead") or []:
            if isinstance(row, dict):
                horizon = max(horizon, int(row.get("end_ms") or horizon))
        candidates = [int(x) for x in (packet.get("legal_cut_ms") or []) if x is not None]
        keep_end: int | None = None
        remainder: int | None = None
        source = "deterministic_transcript"
        if llm_row and llm_row.get("keep_end_ms") is not None:
            keep_end = _snap_keep_end(int(llm_row["keep_end_ms"]), candidates, words)
            source = "llm"
            rem_raw = llm_row.get("remainder_start_ms")
            if rem_raw is not None and keep_end is not None:
                remainder = int(rem_raw)
                if remainder < keep_end:
                    remainder = remainder_open_ms(
                        words, keep_end, horizon_ms=horizon, speaker=str(packet.get("speaker_id") or "")
                    )
        if keep_end is None and det:
            keep_end = int(det["keep_end_ms"])
            remainder = det.get("remainder_start_ms")
            source = "deterministic_transcript"
        detail = dict(f.get("detail") or {})
        if keep_end is None:
            detail["unrecoverable_within_clip"] = True
            f["detail"] = detail
            continue
        if remainder is None and source == "deterministic_transcript" and det:
            remainder = det.get("remainder_start_ms")
        elif remainder is None:
            remainder = remainder_open_ms(
                words, keep_end, horizon_ms=horizon, speaker=str(packet.get("speaker_id") or "")
            )
        consumed: list[str] = []
        for row in packet.get("lookahead") or []:
            if not isinstance(row, dict) or row.get("kind") != "speech":
                continue
            oid = str(row.get("segment_id") or "")
            oss = int(row.get("start_ms") or 0)
            ose = int(row.get("end_ms") or oss)
            if not oid:
                continue
            if ose <= keep_end:
                consumed.append(oid)
            elif oss < keep_end < ose:
                consumed.append(oid)
        detail.update(
            {
                "keep_end_ms": keep_end,
                "remainder_start_ms": remainder,
                "consumed_segment_ids": consumed,
                "legal_cut_ms": candidates,
                "cut_source": source,
                "unrecoverable_within_clip": False,
            }
        )
        if llm_row and llm_row.get("rationale"):
            detail["rationale"] = str(llm_row.get("rationale") or "")
        f["detail"] = detail
        f["action"] = ACTION
    return findings, llm_calls


def apply_thought_complete_to_clips(
    clips: list[dict[str, Any]],
    finding: dict[str, Any],
    *,
    overrides: dict[str, Any],
    excluded: set[str],
    exclude_reasons: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    """Mutate EDL clips for one thought_complete_recut finding."""
    detail = finding.get("detail") if isinstance(finding.get("detail"), dict) else {}
    sid = str(finding.get("segment_id") or "")
    keep_end = detail.get("keep_end_ms")
    if not sid or keep_end is None:
        return clips, overrides, False
    keep_end = int(keep_end)
    remainder = detail.get("remainder_start_ms")
    remainder_ms = int(remainder) if remainder is not None else None
    if remainder_ms is not None and remainder_ms < keep_end:
        remainder_ms = keep_end
    reason = f"junction_snip_qa:{finding.get('kind') or ACTION}"
    hanging: dict[str, Any] | None = None
    hang_index = -1
    for i, c in enumerate(clips):
        if str(c.get("type") or "") == "speech" and str(c.get("segment_id") or "") == sid:
            hanging = c
            hang_index = i
            break
    if hanging is None:
        return clips, overrides, False
    hang_start = int(hanging.get("source_start_ms") or 0)
    prior_end = int(hanging.get("source_end_ms") or hang_start)
    if keep_end <= hang_start + 300:
        return clips, overrides, False
    hanging["source_end_ms"] = keep_end
    hanging["duration_ms"] = keep_end - hang_start
    ov = dict(overrides.get(sid) or {})
    ov["start_ms"] = hang_start
    ov["end_ms"] = keep_end
    overrides[sid] = ov

    drop: set[str] = set()
    remainder_shifted = False
    for j in range(hang_index + 1, len(clips)):
        other = clips[j]
        if str(other.get("type") or "") != "speech":
            continue
        oid = str(other.get("segment_id") or "")
        if not oid or oid == sid:
            continue
        oss = int(other.get("source_start_ms") or 0)
        ose = int(other.get("source_end_ms") or oss)
        if ose <= keep_end:
            drop.add(oid)
            continue
        if oss < keep_end < ose:
            new_start = remainder_ms if remainder_ms is not None else keep_end
            if new_start < keep_end:
                new_start = keep_end
            if new_start >= ose - 300:
                drop.add(oid)
            else:
                if abs(new_start - oss) >= 20:
                    other["source_start_ms"] = new_start
                    other["duration_ms"] = ose - new_start
                    o_ov = dict(overrides.get(oid) or {})
                    o_ov["start_ms"] = new_start
                    o_ov["end_ms"] = ose
                    overrides[oid] = o_ov
                    remainder_shifted = True
            continue
        if remainder_ms is not None and oss <= remainder_ms < ose:
            if abs(remainder_ms - oss) >= 20:
                other["source_start_ms"] = remainder_ms
                other["duration_ms"] = ose - remainder_ms
                o_ov = dict(overrides.get(oid) or {})
                o_ov["start_ms"] = remainder_ms
                o_ov["end_ms"] = ose
                overrides[oid] = o_ov
                remainder_shifted = True
        break

    for oid in drop:
        excluded.add(oid)
        exclude_reasons[oid] = reason
        o_ov = dict(overrides.get(oid) or {})
        o_ov["excluded"] = True
        o_ov["exclude_reason"] = reason
        overrides[oid] = o_ov
    if drop:
        clips = [
            c
            for c in clips
            if not (
                str(c.get("type") or "") == "speech"
                and str(c.get("segment_id") or "") in drop
            )
        ]
    # No-op keep_end (== current end) with no neighbor mutation is not a heal.
    material = bool(drop) or remainder_shifted or abs(keep_end - prior_end) >= 20
    return clips, overrides, material
