"""Deterministic boundary enrichment for fine-grained segmentation."""

from __future__ import annotations

import re
from typing import Any

from interview_mux.config import merged_config
from interview_mux.segment_timeline_standard import segmentation_cfg


def _seg_cfg(cfg: dict[str, Any] | None) -> dict[str, Any]:
    if cfg is None:
        return segmentation_cfg()
    if isinstance(cfg.get("analysis"), dict):
        return segmentation_cfg(cfg)
    return {**segmentation_cfg(), **cfg}


def _words_from_transcript(transcript: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(transcript, dict):
        return []
    words = transcript.get("words") or []
    return [w for w in words if isinstance(w, dict) and w.get("start_ms") is not None and w.get("end_ms") is not None]


def _speaker_roles(speakers_doc: dict[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(speakers_doc, dict):
        return out
    for sp in speakers_doc.get("speakers") or []:
        if not isinstance(sp, dict):
            continue
        sid = str(sp.get("speaker_id") or sp.get("id") or "")
        if sid:
            out[sid] = str(sp.get("role") or "unknown")
    return out


def majority_speaker_for_span(
    words: list[dict[str, Any]], start_ms: int, end_ms: int
) -> str | None:
    """Speaker with the most overlapping talk-time in [start_ms, end_ms], not the first word."""
    counts: dict[str, int] = {}
    for word in words:
        try:
            w0 = int(float(word.get("start_ms") or 0))
            w1 = int(float(word.get("end_ms") or w0))
        except (TypeError, ValueError):
            continue
        if w1 < start_ms or w0 > end_ms:
            continue
        sid = str(word.get("speaker_id") or word.get("speaker") or "").strip()
        if not sid:
            continue
        counts[sid] = counts.get(sid, 0) + max(1, w1 - w0)
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]


def stamp_span_speakers(
    rows: list[dict[str, Any]],
    transcript: dict[str, Any] | None,
    speakers_doc: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Set speaker_id (and speaker_role when known) from word-level majority duration."""
    words = _words_from_transcript(transcript)
    roles = _speaker_roles(speakers_doc)
    if not words:
        return [dict(r) if isinstance(r, dict) else r for r in rows]
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            out.append(row)
            continue
        r = dict(row)
        if r.get("start_ms") is None or r.get("end_ms") is None:
            out.append(r)
            continue
        sid = majority_speaker_for_span(words, int(r["start_ms"]), int(r["end_ms"]))
        if sid:
            r["speaker_id"] = sid
            if sid in roles:
                r["speaker_role"] = roles[sid]
        out.append(r)
    return out


def restamp_run_span_speakers(ctx: Any) -> dict[str, int]:
    """Rewrite boundary/manifest speaker_id from word majority; keep 0.1.0 stable.

    Persist under ALLOW stage_keys — never inherit ``missing_framing`` /
    other non-owners (exec_13159 AuthorityDenied on boundaries.json).
    """
    from interview_mux.artifact_ownership import write_permitted

    transcript = (
        ctx.read_json("transcript/full.json")
        if ctx.artifact_exists("transcript/full.json")
        else None
    )
    speakers_doc = (
        ctx.read_json("understanding/speakers.json")
        if ctx.artifact_exists("understanding/speakers.json")
        else None
    )
    roles = _speaker_roles(speakers_doc)
    changed = {"boundaries": 0, "manifest": 0}

    def _persist(rel: str, payload: dict[str, Any], *, candidates: list[str]) -> bool:
        for stage_key in candidates:
            ok, _reason = write_permitted(ctx, rel, stage_key)
            if not ok:
                continue
            if rel == "segments/boundaries.json":
                from interview_mux.shared_path_commit import commit_boundaries_doc

                commit_boundaries_doc(
                    ctx,
                    payload,
                    stage_key=stage_key,
                    claim_producer=True,
                    skip_handoff=True,
                )
            elif rel == "understanding/content_brief.json":
                from interview_mux.shared_path_commit import commit_content_brief_doc

                commit_content_brief_doc(
                    ctx,
                    payload,
                    stage_key=stage_key,
                    claim_producer=True,
                    skip_handoff=True,
                )
            else:
                ctx.write_json(rel, payload, skip_handoff=True, stage_key=stage_key)
            return True
        return False

    if ctx.artifact_exists("segments/boundaries.json"):
        doc = ctx.read_json("segments/boundaries.json")
        rows = [r for r in (doc.get("boundaries") or []) if isinstance(r, dict)] if isinstance(doc, dict) else []
        stamped = stamp_span_speakers(rows, transcript, speakers_doc)
        n = sum(
            1
            for a, b in zip(rows, stamped)
            if str(a.get("speaker_id") or "") != str(b.get("speaker_id") or "")
        )
        if n:
            out = dict(doc)
            out["boundaries"] = stamped
            meta = out.get("_meta") if isinstance(out.get("_meta"), dict) else {}
            contract = meta.get("segment_contract") if isinstance(meta, dict) else {}
            publisher = ""
            if isinstance(contract, dict):
                publisher = str(contract.get("publisher_stage") or "").strip()
            candidates = [
                s
                for s in (
                    publisher,
                    "chapter_close_hitch",
                    "boundary_detection",
                    "edl_overlap_repair",
                )
                if s
            ]
            if _persist("segments/boundaries.json", out, candidates=candidates):
                changed["boundaries"] = n
    if ctx.artifact_exists("segments/manifest.json"):
        doc = ctx.read_json("segments/manifest.json")
        rows = [r for r in (doc.get("segments") or []) if isinstance(r, dict)] if isinstance(doc, dict) else []
        stamped = stamp_span_speakers(rows, transcript, speakers_doc)
        n = 0
        for row in stamped:
            sid = str(row.get("speaker_id") or "")
            role = roles.get(sid)
            if role:
                if str(row.get("speaker_role") or "") != role:
                    n += 1
                row["speaker_role"] = role
                typ = str(row.get("type") or "")
                if role == "interviewee" and typ == "interviewer_question":
                    row["type"] = "interviewee_answer"
                    n += 1
                elif role == "interviewer" and typ == "interviewee_answer":
                    row["type"] = "interviewer_question"
                    n += 1
            orig = next((r for r in rows if r.get("segment_id") == row.get("segment_id")), None)
            if orig and str(orig.get("speaker_id") or "") != sid:
                n += 1
        if n:
            out = dict(doc)
            out["segments"] = stamped
            if _persist(
                "segments/manifest.json",
                out,
                candidates=[
                    "segment_classification",
                    "edl_overlap_repair",
                    "connector_fuse_pass",
                ],
            ):
                changed["manifest"] = n
    if any(changed.values()) and hasattr(ctx, "log"):
        ctx.log(
            f"restamped span speakers boundaries={changed['boundaries']} "
            f"manifest={changed['manifest']}",
            level="info",
            stage="segment_classification",
        )
    return changed


def _words_in_span(words: list[dict[str, Any]], start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    return [
        w
        for w in words
        if int(w.get("start_ms", 0)) >= start_ms - 20
        and int(w.get("end_ms", 0)) <= end_ms + 20
    ]


def _word_count(span: list[dict[str, Any]]) -> int:
    return sum(1 for w in span if str(w.get("text") or "").strip())


_ACK_TOKENS = frozenset(
    {
        "okay",
        "ok",
        "yeah",
        "yep",
        "yes",
        "right",
        "sure",
        "exactly",
        "mm",
        "mhm",
        "mmhmm",
        "uhhuh",
    }
)


def _ack_token(text: str) -> bool:
    bare = re.findall(r"[A-Za-z0-9']+", text or "")
    return bool(bare) and all(tok.lower() in _ACK_TOKENS for tok in bare)


def _split_points_from_backchannels(
    words: list[dict[str, Any]],
    *,
    start_ms: int,
    end_ms: int,
    roles: dict[str, str],
    backchannel_max_words: int,
) -> list[int]:
    del roles
    span_words = _words_in_span(words, start_ms, end_ms)
    if len(span_words) < 2:
        return []

    splits: list[int] = []
    i = 0
    while i < len(span_words):
        w = span_words[i]
        if not _ack_token(str(w.get("text") or "")):
            i += 1
            continue
        turn_start = i
        while i < len(span_words) and _ack_token(str(span_words[i].get("text") or "")):
            i += 1
        turn_words = span_words[turn_start:i]
        if _word_count(turn_words) <= backchannel_max_words:
            split_start = int(turn_words[0]["start_ms"])
            split_end = int(turn_words[-1]["end_ms"])
            from interview_mux.diarization_suspicion import island_is_absorbable_micro

            if island_is_absorbable_micro(words, turn_words):
                continue
            if start_ms + 500 < split_start < end_ms - 500:
                splits.append(split_start)
            if start_ms + 500 < split_end < end_ms - 500:
                splits.append(split_end)
    return sorted(set(splits))


def _split_row_at_points(
    row: dict[str, Any],
    split_points: list[int],
    *,
    reason: str,
) -> list[dict[str, Any]]:
    start = int(row["start_ms"])
    end = int(row["end_ms"])
    speaker_id = row.get("speaker_id")
    points = sorted(p for p in split_points if start + 500 < p < end - 500)
    if not points:
        return [dict(row)]

    out: list[dict[str, Any]] = []
    cursor = start
    for point in points:
        out.append(
            {
                "start_ms": cursor,
                "end_ms": point,
                "speaker_id": speaker_id,
                "proposed_split_reason": reason,
            }
        )
        cursor = point
    out.append(
        {
            "start_ms": cursor,
            "end_ms": end,
            "speaker_id": speaker_id,
            "proposed_split_reason": reason,
        }
    )
    return out


def split_backchannel_turns(
    rows: list[dict[str, Any]],
    transcript: dict[str, Any] | None,
    speakers_doc: dict[str, Any] | None,
    *,
    cfg: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sc = _seg_cfg(cfg)
    if not sc.get("split_backchannels", True):
        return rows, []
    words = _words_from_transcript(transcript)
    roles = _speaker_roles(speakers_doc)
    max_words = int(sc.get("backchannel_max_words") or 8)
    min_ms = int(sc.get("min_segment_duration_ms") or 4000)

    applied: list[dict[str, Any]] = []
    result: list[dict[str, Any]] = []
    for row in rows:
        if row.get("start_ms") is None or row.get("end_ms") is None:
            result.append(dict(row))
            continue
        start = int(row["start_ms"])
        end = int(row["end_ms"])
        if end - start < min_ms * 2:
            result.append(dict(row))
            continue
        splits = _split_points_from_backchannels(
            words,
            start_ms=start,
            end_ms=end,
            roles=roles,
            backchannel_max_words=max_words,
        )
        if not splits:
            result.append(dict(row))
            continue
        pieces = _split_row_at_points(row, splits, reason="backchannel")
        applied.append({"action": "split_backchannel", "segment_id": row.get("segment_id"), "splits": len(pieces) - 1})
        result.extend(pieces)
    return result, applied


def _best_complete_thought_split(
    words: list[dict[str, Any]],
    *,
    start_ms: int,
    end_ms: int,
    pause_split_ms: int,
    target_ms: int | None = None,
    min_ms: int = 4000,
) -> int | None:
    """Split at a concept change near ``target_ms`` (never a raw midpoint)."""
    from interview_mux.gap_vo_prior_context import (
        concept_boundary_rank,
        is_legal_conceptual_hinge,
        word_density_per_sec,
    )

    del pause_split_ms
    span_words = _words_in_span(words, start_ms, end_ms)
    if len(span_words) < 2:
        return None
    best: tuple[float, int] | None = None
    for i in range(len(span_words) - 1):
        prev = span_words[i]
        nxt = span_words[i + 1]
        gap = int(nxt["start_ms"]) - int(prev["end_ms"])
        split_at = int(nxt["start_ms"])
        if split_at <= start_ms + min_ms or split_at >= end_ms - min_ms:
            continue
        toks = [
            str(w.get("text") or "").strip()
            for w in span_words[: i + 1]
            if str(w.get("text") or "").strip()
        ]
        text = " ".join(toks)
        if not text:
            continue
        end_ms_word = int(prev["end_ms"])
        if not is_legal_conceptual_hinge(
            text, words=span_words, end_ms=end_ms_word, next_pause_ms=gap
        ):
            continue
        before = word_density_per_sec(span_words, end_ms_word - 1)
        after = word_density_per_sec(span_words, split_at)
        score = concept_boundary_rank(gap_ms=gap, density_before=before, density_after=after)
        if target_ms is not None:
            score -= abs(split_at - target_ms) / 100_000.0
        if best is None or score > best[0]:
            best = (score, split_at)
    return best[1] if best else None


def _all_complete_thought_split_points(
    words: list[dict[str, Any]],
    *,
    start_ms: int,
    end_ms: int,
    pause_split_ms: int,
    min_ms: int,
) -> list[int]:
    """Every concept change in-span (not midpoints, pauses, or finished sentences)."""
    from interview_mux.gap_vo_prior_context import is_legal_conceptual_hinge

    del pause_split_ms
    span_words = _words_in_span(words, start_ms, end_ms)
    if len(span_words) < 2:
        return []
    points: list[int] = []
    for i in range(len(span_words) - 1):
        prev = span_words[i]
        nxt = span_words[i + 1]
        gap = int(nxt["start_ms"]) - int(prev["end_ms"])
        split_at = int(nxt["start_ms"])
        if split_at <= start_ms + min_ms or split_at >= end_ms - min_ms:
            continue
        toks = [
            str(w.get("text") or "").strip()
            for w in span_words[: i + 1]
            if str(w.get("text") or "").strip()
        ]
        text = " ".join(toks)
        if not text:
            continue
        if not is_legal_conceptual_hinge(
            text, words=span_words, end_ms=int(prev["end_ms"]), next_pause_ms=gap
        ):
            continue
        points.append(split_at)
    return points


def split_complete_thought_hinges(
    rows: list[dict[str, Any]],
    transcript: dict[str, Any] | None,
    *,
    cfg: dict[str, Any] | None = None,
    topic_split_times: list[int] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split each row at every legal complete-thought hinge, plus topic snaps."""
    sc = _seg_cfg(cfg)
    min_ms = int(sc.get("min_segment_duration_ms") or 4000)
    pause_ms = int(
        ((merged_config().get("analysis") or {}).get("prompt_thresholds") or {}).get(
            "pause_split_ms"
        )
        or 1000
    )
    words = _words_from_transcript(transcript)
    if not words:
        return [dict(r) for r in rows], []
    topic_times = sorted(int(t) for t in (topic_split_times or []) if t is not None)

    applied: list[dict[str, Any]] = []
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("start_ms") is None or row.get("end_ms") is None:
            result.append(dict(row) if isinstance(row, dict) else row)
            continue
        start = int(row["start_ms"])
        end = int(row["end_ms"])
        points = _all_complete_thought_split_points(
            words,
            start_ms=start,
            end_ms=end,
            pause_split_ms=pause_ms,
            min_ms=min_ms,
        )
        for target in topic_times:
            if not (start + min_ms < target < end - min_ms):
                continue
            if any(abs(p - target) < 250 for p in points):
                continue
            snapped = _best_complete_thought_split(
                words,
                start_ms=start,
                end_ms=end,
                pause_split_ms=pause_ms,
                target_ms=target,
                min_ms=min_ms,
            )
            if snapped is not None and snapped not in points:
                points.append(snapped)
        points = sorted(set(points))
        filtered: list[int] = []
        cursor = start
        for point in points:
            if point - cursor >= min_ms and end - point >= min_ms:
                filtered.append(point)
                cursor = point
        if not filtered:
            result.append(dict(row))
            continue
        pieces = _split_row_at_points(row, filtered, reason="complete_thought")
        if len(pieces) > 1:
            applied.append(
                {
                    "action": "split_complete_thought",
                    "splits": len(pieces) - 1,
                    "segment_id": row.get("segment_id"),
                }
            )
        result.extend(pieces)
    return result, applied


def enforce_max_segment_duration(
    rows: list[dict[str, Any]],
    transcript: dict[str, Any] | None,
    *,
    cfg: dict[str, Any] | None = None,
    topic_split_times: list[int] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Length never places a cut.

    A span stays whole until the words change concept. The duration cap does not
    split it, does not cut on a breath or a word near the middle, and does not
    mark it unairable.
    """
    del transcript, cfg, topic_split_times
    kept = [dict(r) for r in rows if isinstance(r, dict)]
    return kept, []


def topic_split_times_from_brief(
    content_brief: dict[str, Any] | None,
    manifest: dict[str, Any] | None,
) -> list[int]:
    """Collect boundary times where reanchored topics change segment mapping."""
    if not isinstance(content_brief, dict) or not isinstance(manifest, dict):
        return []
    by_id = {
        str(s.get("segment_id")): s
        for s in (manifest.get("segments") or [])
        if isinstance(s, dict) and s.get("segment_id")
    }
    times: list[int] = []
    for topic in content_brief.get("topics") or []:
        if not isinstance(topic, dict):
            continue
        seg_ids = topic.get("segment_ids") or []
        if not isinstance(seg_ids, list) or len(seg_ids) < 2:
            continue
        ordered = sorted(str(s) for s in seg_ids)
        for sid in ordered[1:]:
            row = by_id.get(sid)
            if row and row.get("start_ms") is not None:
                times.append(int(row["start_ms"]))
    return sorted(set(times))


def detect_overloaded_segment_ids(
    boundaries_doc: dict[str, Any],
    *,
    content_brief: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
    cfg: dict[str, Any] | None = None,
) -> set[str]:
    sc = _seg_cfg(cfg)
    max_ms = sc.get("max_segment_duration_ms")
    max_ms = int(max_ms) if max_ms is not None else None
    overloaded: set[str] = set()

    topic_counts: dict[str, int] = {}
    if isinstance(content_brief, dict):
        for topic in content_brief.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            for sid in topic.get("segment_ids") or []:
                s = str(sid)
                topic_counts[s] = topic_counts.get(s, 0) + 1

    tag_counts: dict[str, set[str]] = {}
    if isinstance(manifest, dict):
        for seg in manifest.get("segments") or []:
            if not isinstance(seg, dict) or not seg.get("segment_id"):
                continue
            sid = str(seg["segment_id"])
            tags = {str(t) for t in (seg.get("topic_tags") or []) if t}
            if len(tags) > 1:
                tag_counts[sid] = tags

    for row in boundaries_doc.get("boundaries") or []:
        if not isinstance(row, dict) or not row.get("segment_id"):
            continue
        sid = str(row["segment_id"])
        if topic_counts.get(sid, 0) > 1:
            overloaded.add(sid)
        if sid in tag_counts:
            overloaded.add(sid)
        if max_ms and row.get("start_ms") is not None and row.get("end_ms") is not None:
            if int(row["end_ms"]) - int(row["start_ms"]) > max_ms:
                overloaded.add(sid)
    return overloaded


def enrich_boundary_rows(
    rows: list[dict[str, Any]],
    *,
    transcript: dict[str, Any] | None = None,
    speakers_doc: dict[str, Any] | None = None,
    content_brief: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
    cfg: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply deterministic fine-grain splits before timeline normalization."""
    applied: list[dict[str, Any]] = []
    current = [dict(r) for r in rows if isinstance(r, dict)]

    bc_rows, bc_actions = split_backchannel_turns(current, transcript, speakers_doc, cfg=cfg)
    applied.extend(bc_actions)
    current = bc_rows

    topic_times = topic_split_times_from_brief(content_brief, manifest)
    hinge_rows, hinge_actions = split_complete_thought_hinges(
        current,
        transcript,
        cfg=cfg,
        topic_split_times=topic_times,
    )
    applied.extend(hinge_actions)
    current = hinge_rows

    dur_rows, dur_actions = enforce_max_segment_duration(
        current,
        transcript,
        cfg=cfg,
        topic_split_times=topic_times,
    )
    applied.extend(dur_actions)
    stamped = stamp_span_speakers(dur_rows, transcript, speakers_doc)
    return stamped, applied
