"""Deterministic artifact repairs for ITR."""

from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from typing import Any

from interview_mux.classification_obligation import (
    build_obligation,
    segment_text_excerpt,
    segment_type_hints,
)
from interview_mux.config import merged_config
from interview_mux.issue_severity_rules import ClassifiedIssue
from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS, validate_artifact_write
from interview_mux.segment_timeline import sort_segments_by_start_ms, segment_timeline_cfg


def _parse_stringified_exclude_row(raw: str) -> tuple[str, str] | None:
    """Recover {segment_id, reason} when an exclude row was stringified."""
    text = str(raw or "").strip()
    if not text or text[0] not in "{[":
        return None
    payload: Any = None
    try:
        import json

        payload = json.loads(text)
    except Exception:
        try:
            import ast

            payload = ast.literal_eval(text)
        except Exception:
            return None
    if isinstance(payload, list) and payload:
        payload = payload[0]
    if not isinstance(payload, dict):
        return None
    sid = str(payload.get("segment_id") or payload.get("id") or "").strip()
    if not sid:
        return None
    reason = str(payload.get("reason") or "").strip()
    return sid, reason

VALID_FLAGS = frozenset(
    {"starts_mid_thought", "references_prior_missing", "heavy_crosstalk"}
)
def _text_jaccard(a: str, b: str) -> float:
    """Token-set Jaccard similarity for near-duplicate segment text."""
    ta = {t for t in a.lower().split() if t}
    tb = {t for t in b.lower().split() if t}
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


VALID_SEGMENT_TYPES = frozenset(
    {
        "interviewee_answer",
        "interviewer_question",
        "interviewer_reaction",
        "setup",
        "aside",
        "coda",
    }
)

_MANIFEST_SEGMENT_ID_RE = re.compile(r"^seg_\d+[a-z]*$", re.IGNORECASE)


def is_manifest_segment_id(value: str) -> bool:
    """True when ``value`` matches canonical manifest segment_id format."""
    return bool(_MANIFEST_SEGMENT_ID_RE.match(str(value).strip()))


def _normalize_topic_label(name: str) -> str:
    return (
        str(name or "")
        .lower()
        .strip()
        .replace("&", "and")
        .replace(":", " ")
        .replace("-", " ")
    )


def _topic_name_matches_tag(name: str, tag: str) -> bool:
    norm_name = _normalize_topic_label(name).replace(" ", "_")
    norm_tag = str(tag or "").lower().strip().replace(" ", "_")
    if not norm_name or not norm_tag:
        return False
    if norm_tag in norm_name or norm_name in norm_tag:
        return True
    name_tokens = {t for t in re.split(r"[_\s]+", norm_name) if len(t) > 3}
    tag_tokens = {t for t in re.split(r"[_\s]+", norm_tag) if len(t) > 3}
    return bool(name_tokens & tag_tokens)


def _sanitize_topic_segment_ids(seg_ids: list[Any], manifest_ids: set[str]) -> list[str]:
    if manifest_ids:
        return [str(s) for s in seg_ids if str(s) in manifest_ids]
    return [str(s) for s in seg_ids if is_manifest_segment_id(str(s))]


def _speakers_by_id(ctx: Any) -> dict[str, str]:
    if not ctx.artifact_exists("understanding/speakers.json"):
        return {}
    doc = ctx.read_json("understanding/speakers.json")
    out: dict[str, str] = {}
    for sp in (doc.get("speakers") or []) if isinstance(doc, dict) else []:
        if isinstance(sp, dict) and sp.get("speaker_id"):
            sid = str(sp["speaker_id"])
            out[sid] = str(sp.get("role") or sp.get("speaker_role") or "unknown")
    return out


def _infer_segment_type(row: dict[str, Any], speakers: dict[str, str]) -> str:
    spk = str(row.get("speaker_id") or "")
    role = str(row.get("speaker_role") or speakers.get(spk, "unknown"))
    text = str(row.get("text") or "")
    if role == "interviewer" or role in ("moderator", "co_host"):
        if "?" in text[:200]:
            return "interviewer_question"
        return "interviewer_reaction"
    if "?" in text[:120] and text.index("?") < 80:
        return "interviewer_question"
    return "interviewee_answer"


def _append_repair_meta(artifacts: dict[str, Any], entry: dict[str, Any]) -> None:
    meta = artifacts.setdefault("_meta", {})
    repairs = meta.setdefault("repairs", [])
    entry = dict(entry)
    entry.setdefault("at", datetime.now(timezone.utc).isoformat())
    repairs.append(entry)


def repair_manifest_segments(
    ctx: Any,
    manifest: dict[str, Any],
    *,
    issues: list[ClassifiedIssue] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return (patched_manifest, applied_repairs)."""
    out = copy.deepcopy(manifest)
    applied: list[dict[str, Any]] = []
    speakers = _speakers_by_id(ctx)
    segs = out.get("segments")
    if not isinstance(segs, list):
        return out, applied

    # Normalize null/missing arrays and roles on each row
    for i, row in enumerate(segs):
        if not isinstance(row, dict):
            continue
        if row.get("topic_tags") is None or "topic_tags" not in row:
            row["topic_tags"] = []
            applied.append({"action": "default_value", "path": f"segments[{i}].topic_tags", "value": []})
        if row.get("flags") is None:
            row["flags"] = []
            applied.append({"action": "default_value", "path": f"segments[{i}].flags", "value": []})
        elif isinstance(row.get("flags"), list):
            cleaned = [f for f in row["flags"] if f in VALID_FLAGS]
            if cleaned != row["flags"]:
                row["flags"] = cleaned
                applied.append({"action": "drop_invalid_flags", "path": f"segments[{i}].flags"})
        spk = str(row.get("speaker_id") or "")
        if row.get("speaker_role") in (None, "unknown") and spk in speakers and speakers[spk] != "unknown":
            row["speaker_role"] = speakers[spk]
            applied.append(
                {"action": "infer_enum", "path": f"segments[{i}].speaker_role", "value": speakers[spk]}
            )
        # Hydrate-from-boundaries stubs (and sparse LLM rows) may omit required type.
        if not row.get("type") or str(row.get("type")) not in VALID_SEGMENT_TYPES:
            role = str(row.get("speaker_role") or speakers.get(spk) or "unknown").lower()
            if role in {"interviewer", "host", "moderator", "co_host", "frame"}:
                inferred = "interviewer_question"
            elif role in {"interviewee", "guest", "panelist", "subject", "content"}:
                inferred = "interviewee_answer"
            else:
                inferred = "interviewee_answer"
            row["type"] = inferred
            applied.append({"action": "default_value", "path": f"segments[{i}].type", "value": inferred})
        if not row.get("speaker_id"):
            row["speaker_id"] = "spk_unknown"
            applied.append({"action": "default_value", "path": f"segments[{i}].speaker_id", "value": "spk_unknown"})
        if not row.get("speaker_role") or str(row.get("speaker_role")) not in {"interviewer", "interviewee", "unknown"}:
            row["speaker_role"] = "unknown"
            applied.append({"action": "default_value", "path": f"segments[{i}].speaker_role", "value": "unknown"})

    # Drop zero-length segments
    kept: list[dict[str, Any]] = []
    for row in segs:
        if not isinstance(row, dict):
            continue
        start = row.get("start_ms")
        end = row.get("end_ms")
        if start is not None and end is not None and int(end) <= int(start):
            applied.append({"action": "drop_row", "segment_id": row.get("segment_id"), "reason": "zero_length"})
            continue
        kept.append(row)
    out["segments"] = kept
    segs = kept

    # Overlap / duplicate span: drop near-duplicate text
    by_span: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in segs:
        if not isinstance(row, dict):
            continue
        key = (int(row.get("start_ms", 0)), int(row.get("end_ms", 0)))
        by_span.setdefault(key, []).append(row)

    drop_ids: set[str] = set()
    for (_start, _end), group in by_span.items():
        if len(group) < 2:
            continue
        # Keep row with more specific type diversity; prefer interviewer types when text differs slightly
        texts = [str(r.get("text") or "") for r in group]
        if all(_text_jaccard(texts[0], t) > 0.95 for t in texts[1:]):
            # Drop duplicates after first
            for dup in group[1:]:
                sid = str(dup.get("segment_id") or "")
                if sid:
                    drop_ids.add(sid)
                    applied.append(
                        {
                            "action": "drop_row",
                            "segment_id": sid,
                            "reason": "duplicate_span_same_text",
                        }
                    )

    if drop_ids:
        out["segments"] = [r for r in out["segments"] if str(r.get("segment_id")) not in drop_ids]
        segs = out["segments"]

    # Trim overlapping timeline (non-identical spans)
    cfg = segment_timeline_cfg()
    allow_overlap = int(cfg.get("allow_overlap_ms", 0))
    sorted_rows = sort_segments_by_start_ms([r for r in segs if isinstance(r, dict)])
    prev_end: int | None = None
    for row in sorted_rows:
        if row.get("start_ms") is None or row.get("end_ms") is None:
            continue
        start = int(row["start_ms"])
        end = int(row["end_ms"])
        if prev_end is not None and start < prev_end - allow_overlap:
            new_start = prev_end
            if new_start < end:
                row["start_ms"] = new_start
                applied.append(
                    {
                        "action": "trim_overlap",
                        "segment_id": row.get("segment_id"),
                        "start_ms": new_start,
                    }
                )
            else:
                sid = str(row.get("segment_id") or "")
                if sid:
                    drop_ids.add(sid)
                    applied.append({"action": "drop_row", "segment_id": sid, "reason": "overlap_trim_zero"})
        prev_end = max(prev_end or 0, int(row.get("end_ms", end)))

    if drop_ids:
        out["segments"] = [r for r in out["segments"] if str(r.get("segment_id")) not in drop_ids]

    # Infer segment types when all same — skip monologue / content-dominant sources.
    types = [str(r.get("type")) for r in out["segments"] if isinstance(r, dict) and r.get("type")]
    if types and types.count("interviewee_answer") == len(types) and len(types) >= 2:
        from interview_mux.classification_obligation import allows_all_interviewee_answer

        if not allows_all_interviewee_answer(ctx).allowed:
            for row in out["segments"]:
                if not isinstance(row, dict):
                    continue
                inferred = _infer_segment_type(row, speakers)
                if inferred != row.get("type"):
                    old = row.get("type")
                    row["type"] = inferred
                    applied.append(
                        {
                            "action": "infer_segment_type",
                            "segment_id": row.get("segment_id"),
                            "from": old,
                            "to": inferred,
                        }
                    )

    # Fabricate missing segments from boundaries
    from interview_mux.segment_timeline_standard import segmentation_cfg

    if segmentation_cfg().get("fabricate_missing_segments", True) and ctx.artifact_exists("segments/boundaries.json"):
        boundaries = ctx.read_json("segments/boundaries.json")
        speakers_doc = ctx.read_json("understanding/speakers.json") if ctx.artifact_exists("understanding/speakers.json") else None
        obligation = build_obligation(ctx, boundaries, speakers_doc)
        required = set(obligation.get("required_segment_ids") or [])
        present = {
            str(r.get("segment_id"))
            for r in out.get("segments") or []
            if isinstance(r, dict) and r.get("segment_id")
        }
        missing = sorted(required - present)
        boundary_rows = {
            str(b["segment_id"]): b
            for b in (boundaries.get("boundaries") or [])
            if isinstance(b, dict) and b.get("segment_id")
        }
        for seg_id in missing:
            brow = boundary_rows.get(seg_id, {"segment_id": seg_id})
            start_ms = int(brow.get("start_ms", 0))
            end_ms = int(brow.get("end_ms", 0))
            text = segment_text_excerpt(ctx, start_ms, end_ms) if end_ms > start_ms else ""
            spk = str(brow.get("speaker_id") or "spk_0")
            role = speakers.get(spk, "unknown")
            hints = segment_type_hints(brow, speakers)
            seg_type = _infer_segment_type(
                {"speaker_id": spk, "speaker_role": role, "text": text},
                speakers,
            )
            if hints.get("has_question_mark") and role == "interviewer":
                seg_type = "interviewer_question"
            new_row = {
                "segment_id": seg_id,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "speaker_id": spk,
                "speaker_role": role if role != "unknown" else "interviewee",
                "type": seg_type,
                "text": text or f"(segment {seg_id})",
                "topic_tags": [],
                "flags": [],
            }
            out.setdefault("segments", []).append(new_row)
            applied.append({"action": "fabricate_segment", "segment_id": seg_id})

    if cfg.get("sort_on_write", True):
        out["segments"] = sort_segments_by_start_ms(out.get("segments") or [])

    for entry in applied:
        _append_repair_meta(out, entry)
    return out, applied


def _speaker_at_ms(ctx: Any, start_ms: int) -> str | None:
    if not ctx.artifact_exists("transcript/full.json"):
        return None
    try:
        words = ctx.read_json("transcript/full.json").get("words") or []
    except Exception:
        return None
    best: str | None = None
    for word in words:
        if not isinstance(word, dict):
            continue
        spk = word.get("speaker_id")
        if not spk:
            continue
        w_start = word.get("start_ms")
        w_end = word.get("end_ms")
        if w_start is None:
            continue
        if int(w_start) <= start_ms and (w_end is None or int(w_end) >= start_ms):
            return str(spk)
        if int(w_start) >= start_ms and best is None:
            return str(spk)
        if int(w_start) <= start_ms:
            best = str(spk)
    return best


def repair_boundaries(ctx: Any, doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from interview_mux.boundary_collate import normalize_boundary_timeline

    out = copy.deepcopy(doc)
    applied: list[dict[str, Any]] = []
    if out.get("warnings") is None:
        out["warnings"] = []
        applied.append({"action": "default_value", "path": "warnings", "value": []})
    rows = out.get("boundaries")
    if not isinstance(rows, list):
        return out, applied

    speakers_doc = ctx.read_json("understanding/speakers.json") if ctx.artifact_exists("understanding/speakers.json") else {}
    default_spk = ""
    for sp in (speakers_doc.get("speakers") or []) if isinstance(speakers_doc, dict) else []:
        if isinstance(sp, dict) and sp.get("speaker_id"):
            default_spk = str(sp["speaker_id"])
            break

    hydrated: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        normalized = dict(row)
        if not normalized.get("speaker_id"):
            inferred = None
            if normalized.get("start_ms") is not None:
                inferred = _speaker_at_ms(ctx, int(normalized["start_ms"]))
            spk = inferred or default_spk
            if spk:
                normalized["speaker_id"] = spk
                applied.append(
                    {
                        "action": "default_value",
                        "path": "speaker_id",
                        "value": spk,
                        "segment_id": normalized.get("segment_id"),
                    }
                )
        if not str(normalized.get("proposed_split_reason") or "").strip():
            normalized["proposed_split_reason"] = "topic_shift"
            applied.append(
                {
                    "action": "default_value",
                    "path": "proposed_split_reason",
                    "value": "topic_shift",
                    "segment_id": normalized.get("segment_id"),
                }
            )
        hydrated.append(normalized)

    transcript = ctx.read_json("transcript/full.json") if ctx.artifact_exists("transcript/full.json") else None
    content_brief = ctx.read_json("understanding/content_brief.json") if ctx.artifact_exists("understanding/content_brief.json") else None
    manifest = ctx.read_json("segments/manifest.json") if ctx.artifact_exists("segments/manifest.json") else None
    from interview_mux.boundary_enrich import enrich_boundary_rows

    enriched, enrich_actions = enrich_boundary_rows(
        hydrated,
        transcript=transcript if isinstance(transcript, dict) else None,
        speakers_doc=speakers_doc if isinstance(speakers_doc, dict) else None,
        content_brief=content_brief if isinstance(content_brief, dict) else None,
        manifest=manifest if isinstance(manifest, dict) else None,
    )
    applied.extend(enrich_actions)

    normalized_rows, timeline_actions = normalize_boundary_timeline(enriched)
    applied.extend(timeline_actions)
    out["boundaries"] = normalized_rows
    for entry in applied:
        _append_repair_meta(out, entry)
    return out, applied


def _speaker_turns_from_transcript(ctx: Any) -> dict[str, list[str]]:
    turns: dict[str, list[str]] = {}
    if not ctx.artifact_exists("transcript/full.json"):
        return turns
    words = ctx.read_json("transcript/full.json").get("words") or []
    cur = None
    buf: list[str] = []

    def flush() -> None:
        if cur is None or not buf:
            return
        turns.setdefault(cur, []).append(" ".join(buf))

    for w in words:
        if not isinstance(w, dict):
            continue
        tok = str(w.get("text") or w.get("word") or "").strip()
        if not tok:
            continue
        sid = str(w.get("speaker_id") or w.get("speaker") or "") or "unk"
        if sid != cur:
            flush()
            buf = []
            cur = sid
        buf.append(tok)
    flush()
    return turns


_INTERVIEWER_SCORE_CUES = (
    "thanks for joining",
    "thank you for joining",
    "welcome to",
    "we're going to talk",
    "we are going to talk",
    "tell me",
    "can you",
    "let's talk",
    "i want to remind",
    "stay up on the latest",
)
_FILLER_QUESTION_RE = re.compile(
    r"^(okay|ok|right|yeah|yep|you know|so|yes)\s*[?.!,]*$",
    re.I,
)


def _interviewer_score(ctx: Any, speaker_id: str) -> float:
    turns = _speaker_turns_from_transcript(ctx).get(speaker_id) or []
    if not turns:
        return 0.0
    score = 0.0
    for text in turns:
        lower = text.lower()
        if any(cue in lower for cue in _INTERVIEWER_SCORE_CUES):
            score += 3.0
        if _FILLER_QUESTION_RE.match(text.strip()):
            continue
        if "?" in text and len(text) >= 48:
            score += 1.5
        elif "?" in text and len(text) >= 20:
            score += 0.4
    return score


def _infer_speaker_role(ctx: Any, speaker_id: str) -> str:
    """Heuristic role from host cues / substantial questions, not filler 'okay?'."""
    try:
        turns_by = _speaker_turns_from_transcript(ctx)
        if turns_by:
            scores = {sid: _interviewer_score(ctx, sid) for sid in turns_by}
            if speaker_id in scores and len(scores) >= 2:
                winner = max(scores.items(), key=lambda kv: kv[1])[0]
                return "interviewer" if speaker_id == winner else "interviewee"
            if _interviewer_score(ctx, speaker_id) >= 3.0:
                return "interviewer"
            return "interviewee"
        if ctx.artifact_exists("transcript/normalized.json"):
            doc = ctx.read_json("transcript/normalized.json")
            turns = doc.get("turns") or doc.get("segments") or []
            q_count = 0
            total = 0
            for turn in turns:
                if not isinstance(turn, dict):
                    continue
                spk = str(turn.get("speaker_id") or turn.get("speaker") or "")
                if spk and spk != speaker_id:
                    continue
                text = str(turn.get("text") or "")
                total += 1
                if "?" in text[:120] and not _FILLER_QUESTION_RE.match(text.strip()):
                    q_count += 1
            if total and q_count / total > 0.35:
                return "interviewer"
    except Exception:
        pass
    return "interviewee"


def repair_speakers(ctx: Any, doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    out = copy.deepcopy(doc)
    applied: list[dict[str, Any]] = []
    rows = out.get("speakers")
    if not isinstance(rows, list):
        return out, applied
    stats_by_id: dict[str, dict[str, Any]] = {}
    try:
        if ctx.artifact_exists("transcript/full.json"):
            from interview_mux.source_topology import _speaker_talk_stats

            transcript = ctx.read_json("transcript/full.json")
            stats = _speaker_talk_stats(transcript, out)
            stats_by_id = {
                str(s["speaker_id"]): s for s in stats if s.get("speaker_id")
            }
    except Exception:
        stats_by_id = {}
    all_unknown = all(
        isinstance(r, dict) and str(r.get("role") or r.get("speaker_role") or "unknown") == "unknown"
        for r in rows
    ) or False
    low_confidence = bool(rows) and all(
        isinstance(r, dict) and float(r.get("confidence") or 0) <= 0.55
        for r in rows
    )
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        sid = str(row.get("speaker_id") or row.get("id") or "")
        talk = stats_by_id.get(sid) or {}
        if row.get("avg_turn_length_ms") is None and talk:
            row["avg_turn_length_ms"] = round(float(talk.get("avg_turn_ms", 0)), 1)
            applied.append(
                {
                    "action": "default_value",
                    "path": f"speakers[{i}].avg_turn_length_ms",
                    "value": row["avg_turn_length_ms"],
                }
            )
        if row.get("label") is None and row.get("display_name"):
            row["label"] = row["display_name"]
            applied.append({"action": "default_value", "path": f"speakers[{i}].label"})
        if row.get("confidence") is None:
            row["confidence"] = 0.5
            applied.append({"action": "default_value", "path": f"speakers[{i}].confidence", "value": 0.5})
        role = str(row.get("role") or row.get("speaker_role") or "unknown")
        if role == "moderator":
            row["role"] = "interviewer"
            role = "interviewer"
            applied.append({"action": "normalize_moderator_to_interviewer", "speaker_id": sid})
        if role == "unknown" or all_unknown or low_confidence:
            inferred = _infer_speaker_role(ctx, sid)
            if inferred != role or role == "unknown" or all_unknown:
                row["role"] = inferred
                applied.append(
                    {
                        "action": "infer_speaker_role",
                        "speaker_id": sid,
                        "value": inferred,
                        "reason": "low_confidence" if low_confidence and not all_unknown else "unknown",
                    }
                )
    # Tie-break: among dual unknowns resolved to same role, prefer question-dense as interviewer.
    roles_now = [
        str(r.get("role") or "unknown")
        for r in rows
        if isinstance(r, dict)
    ]
    if roles_now.count("interviewer") >= 2 and len(rows) == 2:
        scored = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("speaker_id") or row.get("id") or "")
            scored.append((sid, _interviewer_score(ctx, sid)))
        scored.sort(key=lambda kv: kv[1], reverse=True)
        winner = scored[0][0] if scored else None
        if winner:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                sid = str(row.get("speaker_id") or row.get("id") or "")
                new_role = "interviewer" if sid == winner else "interviewee"
                if str(row.get("role") or "") != new_role:
                    row["role"] = new_role
                    applied.append(
                        {
                            "action": "disambiguate_dual_interviewer",
                            "speaker_id": sid,
                            "value": new_role,
                            "score": dict(scored).get(sid),
                        }
                    )
    if roles_now.count("interviewer") == 0 and len(rows) >= 2:
        best_id = None
        best_score = -1.0
        for row in rows:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("speaker_id") or row.get("id") or "")
            # Re-score via question heuristic only.
            if _infer_speaker_role(ctx, sid) == "interviewer":
                best_id = sid
                break
            talk = stats_by_id.get(sid) or {}
            # Least talk often = interviewer in duo interviews.
            talk_ms = float(talk.get("talk_ms") or talk.get("total_ms") or 1e18)
            score = 1.0 / max(1.0, talk_ms)
            if score > best_score:
                best_score = score
                best_id = sid
        if best_id:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                sid = str(row.get("speaker_id") or row.get("id") or "")
                if sid == best_id:
                    row["role"] = "interviewer"
                    applied.append({"action": "tiebreak_interviewer", "speaker_id": sid})
                elif str(row.get("role") or "") == "interviewer":
                    row["role"] = "interviewee"
    # Harden: dominant talker with low question density is never interviewer.
    for row in rows:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("speaker_id") or row.get("id") or "")
        role = str(row.get("role") or row.get("speaker_role") or "")
        if role != "interviewer":
            continue
        talk = stats_by_id.get(sid) or {}
        talk_ms = float(talk.get("talk_ms") or talk.get("total_ms") or 0)
        others = [
            float((stats_by_id.get(str(r.get("speaker_id") or r.get("id") or "")) or {}).get("talk_ms") or 0)
            for r in rows
            if isinstance(r, dict) and str(r.get("speaker_id") or r.get("id") or "") != sid
        ]
        other_max = max(others) if others else 0.0
        inferred = _infer_speaker_role(ctx, sid)
        if inferred == "interviewee" and talk_ms > 0 and talk_ms >= other_max * 1.35:
            row["role"] = "interviewee"
            applied.append(
                {
                    "action": "demote_dominant_talker_from_interviewer",
                    "speaker_id": sid,
                    "talk_ms": talk_ms,
                }
            )
    # Ensure at least one interviewer remains when possible.
    roles_final = [str(r.get("role") or "") for r in rows if isinstance(r, dict)]
    if roles_final.count("interviewer") == 0 and len(rows) >= 2:
        best_id = None
        best_q = -1.0
        for row in rows:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("speaker_id") or row.get("id") or "")
            if _infer_speaker_role(ctx, sid) == "interviewer":
                best_id = sid
                break
            talk = stats_by_id.get(sid) or {}
            talk_ms = float(talk.get("talk_ms") or talk.get("total_ms") or 1e18)
            score = 1.0 / max(1.0, talk_ms)
            if score > best_q:
                best_q = score
                best_id = sid
        if best_id:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                sid = str(row.get("speaker_id") or row.get("id") or "")
                if sid == best_id:
                    row["role"] = "interviewer"
                    applied.append({"action": "restore_interviewer_after_demote", "speaker_id": sid})
    for entry in applied:
        _append_repair_meta(out, entry)
    return out, applied


def realign_manifest_roles_from_speakers(ctx: Any) -> list[dict[str, Any]]:
    """Rewrite segment speaker_role/type from understanding/speakers.json.

    Classification copies LLM speaker_roles. When those roles were a 0.5-confidence
    coin-flip, interviewer_question rows contain guest lectures and missing_framing
    refuses coverage. Realign types to the repaired role map without a full re-LLM.
    """
    if not ctx.artifact_exists("understanding/speakers.json") or not ctx.artifact_exists(
        "segments/manifest.json"
    ):
        return []
    speakers = ctx.read_json("understanding/speakers.json")
    role_by: dict[str, str] = {}
    for row in speakers.get("speakers") or []:
        if isinstance(row, dict) and row.get("speaker_id") and row.get("role"):
            role_by[str(row["speaker_id"])] = str(row["role"])
    if not role_by:
        return []
    man = ctx.read_json("segments/manifest.json")
    applied: list[dict[str, Any]] = []
    for seg in man.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        sid = str(seg.get("speaker_id") or "")
        role = role_by.get(sid)
        if not role:
            continue
        prev_role = str(seg.get("speaker_role") or "")
        prev_type = str(seg.get("type") or "")
        if prev_role != role:
            seg["speaker_role"] = role
            applied.append(
                {
                    "action": "realign_speaker_role",
                    "segment_id": seg.get("segment_id"),
                    "from": prev_role,
                    "to": role,
                }
            )
        if role == "interviewee" and prev_type in {"interviewer_question", "interviewer_reaction"}:
            seg["type"] = "interviewee_answer"
            applied.append(
                {
                    "action": "realign_segment_type",
                    "segment_id": seg.get("segment_id"),
                    "from": prev_type,
                    "to": "interviewee_answer",
                }
            )
        elif role == "interviewer" and prev_type == "interviewee_answer":
            seg["type"] = "interviewer_question"
            applied.append(
                {
                    "action": "realign_segment_type",
                    "segment_id": seg.get("segment_id"),
                    "from": prev_type,
                    "to": "interviewer_question",
                }
            )
    if not applied:
        return []
    from interview_mux.artifact_lifecycle import restamp_committed_artifact

    restamp_committed_artifact(
        ctx,
        "segments/manifest.json",
        producer_stage="segment_classification",
        doc=man,
    )
    return applied


def _manifest_ids_and_tags(ctx: Any) -> tuple[set[str], dict[str, list[str]]]:
    manifest_ids: set[str] = set()
    tag_to_segments: dict[str, list[str]] = {}
    if not ctx.artifact_exists("segments/manifest.json"):
        return manifest_ids, tag_to_segments
    manifest = ctx.read_json("segments/manifest.json")
    for row in (manifest.get("segments") or []) if isinstance(manifest, dict) else []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("segment_id") or "")
        if sid:
            manifest_ids.add(sid)
        for tag in row.get("topic_tags") or []:
            tag_to_segments.setdefault(str(tag), []).append(sid)
    manifest_ids |= _live_split_child_ids(ctx)
    return manifest_ids, tag_to_segments


def _live_split_child_ids(ctx: Any) -> set[str]:
    """NLE/CTA recut children that ranking/shape must treat as real candidates."""
    ids: set[str] = set()
    try:
        from interview_mux.nle_state import load_nle

        overrides = (load_nle(ctx).get("segment_overrides") or {})
        for sid, ov in overrides.items():
            if not isinstance(ov, dict):
                continue
            if ov.get("parent_id") and ov.get("start_ms") is not None:
                ids.add(str(sid))
            for child in ov.get("split_into") or []:
                if child:
                    ids.add(str(child))
    except Exception:
        pass
    try:
        from interview_mux.media_ip_cta import admitted_story_segment_ids

        ids |= admitted_story_segment_ids(ctx)
    except Exception:
        pass
    return {s for s in ids if s}


def repair_content_brief(ctx: Any, doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    out = copy.deepcopy(doc)
    applied: list[dict[str, Any]] = []
    manifest_ids, tag_to_segments = _manifest_ids_and_tags(ctx)

    claims = out.get("key_claims")
    if isinstance(claims, list):
        kept_claims = []
        for i, claim in enumerate(claims):
            if not isinstance(claim, dict):
                applied.append({"action": "drop_row", "path": f"key_claims[{i}]"})
                continue
            evidence = (
                claim.get("evidence")
                or claim.get("evidence_anchors")
                or claim.get("segment_ids")
                or claim.get("evidence_segment_ids")
                or claim.get("approx_time_range")
            )
            if not evidence and str(claim.get("claim") or claim.get("text") or "").strip():
                applied.append({"action": "drop_row", "path": f"key_claims[{i}]", "reason": "no_evidence"})
                continue
            for field in ("segment_ids", "evidence_segment_ids"):
                vals = claim.get(field)
                if isinstance(vals, list):
                    cleaned = _sanitize_topic_segment_ids(vals, manifest_ids)
                    if cleaned != vals:
                        claim[field] = cleaned
                        applied.append({"action": "drop_orphan_ref", "path": f"key_claims[{i}].{field}"})
            kept_claims.append(claim)
        out["key_claims"] = kept_claims

    if not str(out.get("thesis") or "").strip() and out.get("topics"):
        topics = out.get("topics") or []
        if isinstance(topics, list) and topics and isinstance(topics[0], dict):
            summary = str(topics[0].get("summary") or topics[0].get("name") or "").strip()
            if summary:
                out["thesis"] = summary[:240]
                applied.append({"action": "default_value", "path": "thesis", "source": "topic_summary"})

    generic_names = frozenset({"theme", "topic", "general", "misc", "other"})
    kept_topics: list[dict[str, Any]] = []
    pending_chrono: list[tuple[int, dict[str, Any]]] = []
    for i, topic in enumerate(out.get("topics") or []):
        if not isinstance(topic, dict):
            continue
        name = str(topic.get("name") or "").lower().strip()
        if name in generic_names and not topic.get("segment_ids") and not topic.get("evidence"):
            applied.append({"action": "drop_row", "path": f"topics[{i}]", "reason": "generic_theme"})
            continue
        seg_ids = topic.get("segment_ids")
        if isinstance(seg_ids, list):
            cleaned = _sanitize_topic_segment_ids(seg_ids, manifest_ids)
            if cleaned != seg_ids:
                topic["segment_ids"] = cleaned
                applied.append({"action": "drop_orphan_ref", "path": f"topics[{i}].segment_ids"})
        if not topic.get("segment_ids"):
            matched: list[str] = []
            for tag, sids in tag_to_segments.items():
                if _topic_name_matches_tag(name, tag):
                    matched.extend(sids)
            if matched:
                topic["segment_ids"] = sorted(set(matched))
                applied.append({"action": "map_topic_segments", "path": f"topics[{i}].segment_ids"})
        # Claim / evidence segment refs are a second host anchor when topic_tags are empty.
        if not (topic.get("segment_ids") or []) and manifest_ids:
            claim_hits: list[str] = []
            for claim in out.get("key_claims") or []:
                if not isinstance(claim, dict):
                    continue
                for field in ("segment_ids", "evidence_segment_ids"):
                    vals = claim.get(field)
                    if isinstance(vals, list):
                        claim_hits.extend(_sanitize_topic_segment_ids(vals, manifest_ids))
            if claim_hits:
                topic["segment_ids"] = sorted(set(claim_hits))[:12]
                applied.append(
                    {"action": "map_topic_segments_from_claims", "path": f"topics[{i}].segment_ids"}
                )
        # Reanchor completeness requires segment_ids once a segment manifest exists.
        # content_context runs before boundary/classification — keep unanchored topics then.
        if not (topic.get("segment_ids") or []):
            if manifest_ids:
                # Defer drop: chronological backfill below prefers keeping named topics.
                pending_chrono.append((i, topic))
                continue
        kept_topics.append(topic)
    if pending_chrono and manifest_ids:
        ordered = sorted(manifest_ids)
        n = len(pending_chrono)
        chunk = max(1, len(ordered) // n)
        for j, (i, topic) in enumerate(pending_chrono):
            start = j * chunk
            end = len(ordered) if j == n - 1 else min(len(ordered), start + chunk)
            if start >= len(ordered):
                start = max(0, len(ordered) - chunk)
                end = len(ordered)
            topic["segment_ids"] = ordered[start:end] or ordered[:1]
            applied.append(
                {
                    "action": "map_topic_segments_chrono",
                    "path": f"topics[{i}].segment_ids",
                    "count": len(topic["segment_ids"]),
                }
            )
            kept_topics.append(topic)
        pending_chrono = []
    elif pending_chrono and not manifest_ids:
        kept_topics.extend(t for _, t in pending_chrono)
        pending_chrono = []
    # Last resort: never leave topics=[] when a thesis + manifest exist — one covering topic.
    if not kept_topics and manifest_ids and str(out.get("thesis") or "").strip():
        covering = {
            "name": "Episode themes",
            "summary": str(out.get("thesis") or "").strip()[:400],
            "segment_ids": sorted(manifest_ids)[:48],
        }
        kept_topics.append(covering)
        applied.append(
            {
                "action": "synthesize_covering_topic",
                "path": "topics[0]",
                "count": len(covering["segment_ids"]),
            }
        )
    out["topics"] = kept_topics
    rel_applied = _ensure_topic_relationships(out)
    applied.extend(rel_applied)

    for entry in applied:
        _append_repair_meta(out, entry)
    return out, applied


def _ensure_topic_relationships(brief: dict[str, Any]) -> list[dict[str, Any]]:
    """Host-synthesize a sequential topic graph when the LLM omitted relationships.

    Reanchor completeness requires a non-empty ``topic_relationships`` list. Null-ack
    of that field otherwise marks the brief incomplete after the stage is already
    ``.stage_done``, and fill-gaps then rewinds to ``content_context`` forever.
    """
    existing = brief.get("topic_relationships")
    if isinstance(existing, list) and existing:
        return []
    topics = [t for t in (brief.get("topics") or []) if isinstance(t, dict)]
    names = [str(t.get("name") or "").strip() for t in topics]
    names = [n for n in names if n]
    if not names:
        return []
    rows: list[dict[str, Any]] = []
    if len(names) == 1:
        segs = topics[0].get("segment_ids") if topics else []
        evidence = [str(s) for s in segs[:4]] if isinstance(segs, list) else []
        rows.append(
            {
                "from_topic": names[0],
                "to_topic": names[0],
                "relation": "returns_to",
                "description": f"{names[0]} is the through-line of this interview.",
                "evidence_segment_ids": evidence,
            }
        )
    else:
        for earlier, later, t_a, t_b in zip(names, names[1:], topics, topics[1:]):
            segs_a = t_a.get("segment_ids") if isinstance(t_a.get("segment_ids"), list) else []
            segs_b = t_b.get("segment_ids") if isinstance(t_b.get("segment_ids"), list) else []
            evidence = list(dict.fromkeys([str(s) for s in [*segs_a[-2:], *segs_b[:2]] if s]))
            rows.append(
                {
                    "from_topic": earlier,
                    "to_topic": later,
                    "relation": "prerequisite",
                    "description": f"{earlier} sets up {later} in the interview arc.",
                    "evidence_segment_ids": evidence,
                }
            )
    brief["topic_relationships"] = rows
    return [{"action": "synthesize_topic_relationships", "path": "topic_relationships", "count": len(rows)}]


def sync_content_brief_topic_segment_ids(
    ctx: Any,
    *,
    overlay_stage: str | None = None,
) -> list[dict[str, Any]]:
    """
    Align content_brief topic segment_ids with manifest topic_tags and persist to disk.

    Uses staged manifest when ``overlay_stage`` has pending writes (write-approval path).
    """
    if not ctx.artifact_exists("understanding/content_brief.json"):
        return []
    from interview_mux.artifact_cross_validate import cross_validate_pending_overlay

    with cross_validate_pending_overlay(ctx, overlay_stage):
        brief = ctx.read_json("understanding/content_brief.json")
    if not isinstance(brief, dict):
        return []
    with cross_validate_pending_overlay(ctx, overlay_stage):
        repaired, applied = repair_content_brief(ctx, brief)
    if not applied:
        return []
    from interview_mux.artifact_lifecycle import restamp_committed_artifact

    restamp_committed_artifact(
        ctx,
        "understanding/content_brief.json",
        producer_stage="content_brief_reanchor",
        doc=repaired if isinstance(repaired, dict) else None,
    )
    return applied


def repair_gap_evaluations(ctx: Any, doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    out = copy.deepcopy(doc)
    applied: list[dict[str, Any]] = []
    manifest_ids: set[str] = set()
    if ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")
        manifest_ids = {
            str(s.get("segment_id"))
            for s in (manifest.get("segments") or [])
            if isinstance(s, dict) and s.get("segment_id")
        }
    evals = out.get("evaluations")
    if isinstance(evals, list) and manifest_ids:
        kept = []
        for row in evals:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("segment_id") or "")
            if sid and sid not in manifest_ids:
                applied.append({"action": "drop_orphan_ref", "segment_id": sid})
                continue
            kept.append(row)
        out["evaluations"] = kept
        # When missing_framing already burned its coverage CAP, fabricate/promote
        # as keep-eligible seals — not unscored batch_fill thrash (exec_13159
        # seg_061–064 stuck on fabricate_evaluation after coverage_passes=2).
        coverage_passes = 0
        try:
            coverage_passes = int((out.get("_meta") or {}).get("coverage_passes") or 0)
        except Exception:
            coverage_passes = 0
        from interview_mux.stages.gaps import (
            MISSING_FRAMING_COVERAGE_CAP,
            _gap_eval_is_unscored_fill,
        )

        seal_fabricate = coverage_passes >= int(MISSING_FRAMING_COVERAGE_CAP)
        # Promote already-fabricated rows once coverage CAP is burned.
        if seal_fabricate:
            promoted: list[dict[str, Any]] = []
            for row in kept:
                if not isinstance(row, dict):
                    promoted.append(row)
                    continue
                if _gap_eval_is_unscored_fill(row):
                    sealed = dict(row)
                    meta = dict(sealed.get("_meta") or {})
                    meta["filled_by"] = "coverage_exhausted_accept"
                    meta["producer"] = "coverage_exhausted_accept"
                    meta["reason"] = "coverage_cap_seal"
                    sealed["_meta"] = meta
                    promoted.append(sealed)
                    applied.append(
                        {
                            "action": "coverage_cap_seal_existing",
                            "segment_id": sealed.get("segment_id"),
                        }
                    )
                else:
                    promoted.append(row)
            kept = promoted
            out["evaluations"] = kept
        # Add missing evaluation rows
        present = {str(r.get("segment_id")) for r in kept if isinstance(r, dict)}
        for sid in sorted(manifest_ids - present):
            if seal_fabricate:
                kept.append(
                    {
                        **{
                            "segment_id": sid,
                            "self_explanatory": True,
                            "gap_type": "ok_with_light_bridge",
                            "secondary_gap_type": None,
                            "severity": "low",
                            "listener_confusion": "",
                            "recommended_framing": "none",
                            "candidate_for_summary": False,
                            "supports_ranking_exclude": False,
                            "duplicate_claim_cluster": "",
                            "ready": True,
                        },
                        "_meta": {
                            "filled_by": "coverage_exhausted_accept",
                            "producer": "coverage_exhausted_accept",
                            "reason": "coverage_cap_seal",
                        },
                    }
                )
                applied.append(
                    {"action": "coverage_cap_seal_fabricate", "segment_id": sid}
                )
            else:
                kept.append(
                    {
                        "segment_id": sid,
                        "self_explanatory": True,
                        "gap_type": "ok_with_light_bridge",
                        "secondary_gap_type": None,
                        "severity": "low",
                        "listener_confusion": "",
                        "recommended_framing": "none",
                        "candidate_for_summary": False,
                        "supports_ranking_exclude": False,
                        "duplicate_claim_cluster": "",
                        "ready": True,
                        "_meta": {
                            "filled_by": "repair_gap_evaluations",
                            "reason": "fabricate_evaluation",
                        },
                    }
                )
                applied.append({"action": "fabricate_evaluation", "segment_id": sid})
        out["evaluations"] = kept
    # LLM often returns a sparse score set; default remaining stubs so completeness
    # gates can pass without endless re-volleys on large manifests.
    if isinstance(out.get("evaluations"), list):
        for i, row in enumerate(out["evaluations"]):
            if not isinstance(row, dict):
                continue
            producer = str((row.get("_meta") or {}).get("producer") or "")
            if producer == "gap_fill_skip":
                continue
            # Explicit envelope nulls (key present, value null) — coerce for disk.
            if row.get("listener_confusion") is None:
                row["listener_confusion"] = ""
                applied.append(
                    {
                        "action": "null_to_empty_string",
                        "path": f"evaluations[{i}].listener_confusion",
                    }
                )
            elif not isinstance(row.get("listener_confusion"), str):
                row["listener_confusion"] = str(row.get("listener_confusion") or "")
            if "recommended_framing" in row and row.get("recommended_framing") is None:
                row["recommended_framing"] = "none"
                applied.append(
                    {
                        "action": "default_value",
                        "path": f"evaluations[{i}].recommended_framing",
                        "value": "none",
                    }
                )
            if "duplicate_claim_cluster" in row and row.get("duplicate_claim_cluster") is None:
                row["duplicate_claim_cluster"] = ""
                applied.append(
                    {
                        "action": "null_to_empty_string",
                        "path": f"evaluations[{i}].duplicate_claim_cluster",
                    }
                )
            for bk in (
                "self_explanatory",
                "candidate_for_summary",
                "supports_ranking_exclude",
                "ready",
            ):
                if bk in row and row.get(bk) is None:
                    row[bk] = False if bk != "self_explanatory" else True
                    applied.append(
                        {"action": "coerce_bool", "path": f"evaluations[{i}].{bk}"}
                    )
                elif bk in row and not isinstance(row.get(bk), bool):
                    row[bk] = bool(row.get(bk))
            if row.get("severity") and row.get("gap_type"):
                continue
            tagged = False
            if not row.get("severity"):
                row["severity"] = "low"
                applied.append({"action": "default_value", "path": f"evaluations[{i}].severity", "value": "low"})
                tagged = True
            if not row.get("gap_type"):
                row["gap_type"] = "ok_with_light_bridge"
                applied.append(
                    {
                        "action": "default_value",
                        "path": f"evaluations[{i}].gap_type",
                        "value": "ok_with_light_bridge",
                    }
                )
                tagged = True
            if "self_explanatory" not in row:
                row["self_explanatory"] = True
            if "listener_confusion" not in row:
                row["listener_confusion"] = ""
            if tagged:
                meta = dict(row.get("_meta") or {})
                meta["filled_by"] = "repair_gap_evaluations"
                meta.setdefault("reason", "default_value")
                row["_meta"] = meta
    for entry in applied:
        _append_repair_meta(out, entry)
    return out, applied


def _readmit_cta_story_children(
    ctx: Any,
    ordered: list[str],
    applied: list[dict[str, Any]],
    *,
    banned_ids: set[str] | None = None,
) -> list[str]:
    """Put CTA-sanitized story remainders back on the air-order candidate list.

    Honors ``artifact_sanitize.selection.max_cta_readmit`` (default 0 = no-op).
    Never re-admits ids in ``banned_ids`` (sanitize drops / exclusions).
    """
    try:
        from interview_mux.artifact_sanitize.config import sanitize_selection_cfg

        max_readmit = int(sanitize_selection_cfg().get("max_cta_readmit") or 0)
    except Exception:
        max_readmit = 0
    if max_readmit <= 0:
        applied.append({"action": "skip_cta_readmit", "reason": "max_cta_readmit=0"})
        return ordered
    try:
        from interview_mux.media_ip_cta import admitted_story_segment_ids, never_touch_segment_ids

        story = [s for s in admitted_story_segment_ids(ctx) if s not in never_touch_segment_ids(ctx)]
    except Exception:
        return ordered
    if not story:
        return ordered
    ban = {str(s) for s in (banned_ids or set()) if s}
    have = set(ordered)
    missing = [s for s in story if s not in have and s not in ban]
    if not missing:
        return ordered
    if len(missing) > max_readmit:
        applied.append(
            {
                "action": "cap_cta_readmit",
                "max": max_readmit,
                "requested": len(missing),
            }
        )
        missing = missing[:max_readmit]
    try:
        from interview_mux.nle_state import segments_by_id_with_nle

        by_id = segments_by_id_with_nle(ctx)
    except Exception:
        by_id = {}
    out = list(ordered)
    for sid in missing:
        try:
            start = int((by_id.get(sid) or {}).get("start_ms") or 0)
        except (TypeError, ValueError):
            start = 0
        idx = len(out)
        for i, other in enumerate(out):
            try:
                other_start = int((by_id.get(other) or {}).get("start_ms") or 0)
            except (TypeError, ValueError):
                other_start = 0
            if start < other_start:
                idx = i
                break
        out.insert(idx, sid)
        have.add(sid)
    applied.append({"action": "readmit_cta_story_children", "segment_ids": missing[:24]})
    return out


def _selection_excluded_id_set(doc: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for row in doc.get("excluded_segment_ids") or []:
        if isinstance(row, dict):
            sid = str(row.get("segment_id") or "")
        else:
            sid = str(row or "")
        if sid:
            out.add(sid)
    return out


def _normalize_master_selection_only(
    ctx: Any, doc: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Schema/orphan/dedupe/never-touch normalize — no CTA readmit or leftovers growth."""
    out = copy.deepcopy(doc)
    applied: list[dict[str, Any]] = []
    manifest_ids, _ = _manifest_ids_and_tags(ctx)
    ordered = out.get("ordered_segment_ids")
    if isinstance(ordered, list):
        seen: set[str] = set()
        deduped: list[str] = []
        for sid in ordered:
            s = str(sid)
            if manifest_ids and s not in manifest_ids:
                applied.append({"action": "drop_orphan_ref", "segment_id": s})
                continue
            if s in seen:
                applied.append({"action": "dedupe", "segment_id": s})
                continue
            seen.add(s)
            deduped.append(s)
        try:
            from interview_mux.media_ip_cta import never_touch_segment_ids

            banned = never_touch_segment_ids(ctx)
        except Exception:
            banned = set()
        if banned:
            cta_drop = [s for s in deduped if s in banned]
            if cta_drop:
                deduped = [s for s in deduped if s not in banned]
                applied.append({"action": "drop_never_touch_cta", "ids": cta_drop[:24]})
        out["ordered_segment_ids"] = deduped
    # Always reconcile/prune air↔exclude contradictions — normalize-only must still
    # clear lint (`exclude_rationales[x] contradicts ordered_segment_ids`). Ranking
    # writes with a fresh sanitize stamp use amplify=False and previously skipped this
    # (exec_11630: finale_tail_leftover rationales left on readmitted air ids).
    before_rat = (
        dict(out.get("exclude_rationales"))
        if isinstance(out.get("exclude_rationales"), dict)
        else {}
    )
    before_ord = list(out.get("ordered_segment_ids") or [])
    before_excl = list(out.get("excluded_segment_ids") or [])
    out = reconcile_ordered_vs_excluded(out)
    if (
        list(out.get("ordered_segment_ids") or []) != before_ord
        or list(out.get("excluded_segment_ids") or []) != before_excl
        or (
            dict(out.get("exclude_rationales"))
            if isinstance(out.get("exclude_rationales"), dict)
            else {}
        )
        != before_rat
    ):
        applied.append({"action": "reconcile_ordered_vs_excluded"})
        if (
            dict(out.get("exclude_rationales"))
            if isinstance(out.get("exclude_rationales"), dict)
            else {}
        ) != before_rat:
            applied.append({"action": "prune_stale_exclude_rationales"})
    from interview_mux.order_hash import bump_order_lock

    out = bump_order_lock(out, source="artifact_repairs.normalize_selection")
    applied.append({"action": "normalize_selection_only"})
    return out, applied


def repair_master_selection(
    ctx: Any,
    doc: dict[str, Any],
    *,
    amplify: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not amplify:
        return _normalize_master_selection_only(ctx, doc)
    out = copy.deepcopy(doc)
    applied: list[dict[str, Any]] = []
    before_n = len([s for s in (out.get("ordered_segment_ids") or []) if s])
    excluded_ban = _selection_excluded_id_set(out)
    manifest_ids, _ = _manifest_ids_and_tags(ctx)
    ordered = out.get("ordered_segment_ids")
    if isinstance(ordered, list):
        seen: set[str] = set()
        deduped: list[str] = []
        for sid in ordered:
            s = str(sid)
            if manifest_ids and s not in manifest_ids:
                applied.append({"action": "drop_orphan_ref", "segment_id": s})
                continue
            if s in seen:
                applied.append({"action": "dedupe", "segment_id": s})
                continue
            seen.add(s)
            deduped.append(s)
        ordered_now = _readmit_cta_story_children(
            ctx, deduped, applied, banned_ids=excluded_ban
        )
        try:
            from interview_mux.media_ip_cta import never_touch_segment_ids

            banned = never_touch_segment_ids(ctx)
        except Exception:
            banned = set()
        if banned:
            cta_drop = [s for s in ordered_now if s in banned]
            if cta_drop:
                ordered_now = [s for s in ordered_now if s not in banned]
                applied.append({"action": "drop_never_touch_cta", "ids": cta_drop[:24]})
        out["ordered_segment_ids"] = ordered_now
        # Drop blank / unusable answer segments (blank-safe for later chapter repairs).
        # Use the post-readmit list so CTA story children are not wiped here.
        # Never empty the entire air order — fixture/short manifests must not
        # collapse selection to [] (schema + one-writer refuse).
        # Never drop hard-keeps as blank — lattice restore then fails with
        # hard_keep_missing_from_order (exec_13198 seg_028 "Okay.").
        try:
            from interview_mux.hard_keep import hard_keep_segment_ids

            hard_keeps = {str(s) for s in (hard_keep_segment_ids(ctx) or []) if s}
        except Exception:
            hard_keeps = set()
        blank_drop = [
            s
            for s in ordered_now
            if _segment_is_blank_or_unusable(ctx, s) and s not in hard_keeps
        ]
        if blank_drop:
            kept = [s for s in ordered_now if s not in set(blank_drop)]
            if kept:
                out["ordered_segment_ids"] = kept
                excl = list(out.get("excluded_segment_ids") or [])
                have = {str(r.get("segment_id") if isinstance(r, dict) else r) for r in excl}
                for sid in blank_drop:
                    if sid not in have:
                        excl.append({"segment_id": sid, "reason": "blank_or_unusable_answer_audio"})
                        have.add(sid)
                out["excluded_segment_ids"] = excl
                applied.append({"action": "drop_blank_segments", "ids": blank_drop})
            else:
                applied.append(
                    {
                        "action": "keep_blank_segments_refuse_empty_order",
                        "ids": blank_drop[:24],
                    }
                )
    excluded = out.get("excluded_segment_ids")
    if isinstance(excluded, list):
        # Schema requires {segment_id, reason} objects; LLMs often emit bare id strings.
        rationales = out.get("exclude_rationales") if isinstance(out.get("exclude_rationales"), dict) else {}
        rationales = dict(rationales)
        normalized: list[dict[str, Any]] = []
        seen_ex: set[str] = set()
        for row in excluded:
            if isinstance(row, str):
                sid = row.strip()
                reason = str(rationales.get(sid) or "excluded_from_master")
                if sid[:1] in "{[":
                    parsed = _parse_stringified_exclude_row(sid)
                    if parsed:
                        sid = parsed[0]
                        reason = parsed[1] or reason
            elif isinstance(row, dict):
                sid = str(row.get("segment_id") or row.get("id") or "").strip()
                reason = str(row.get("reason") or rationales.get(sid) or "excluded_from_master")
            else:
                continue
            if not sid or sid in seen_ex:
                continue
            if manifest_ids and sid not in manifest_ids:
                applied.append({"action": "drop_orphan_ref", "segment_id": sid})
                continue
            seen_ex.add(sid)
            normalized.append({"segment_id": sid, "reason": reason})
            rationales.setdefault(sid, reason)
        if normalized != excluded:
            applied.append({"action": "normalize_excluded_segment_ids", "count": len(normalized)})
        try:
            from interview_mux.artifact_sanitize.config import sanitize_selection_cfg
            from interview_mux.media_ip_cta import admitted_story_segment_ids

            story = admitted_story_segment_ids(ctx)
            max_readmit = int(sanitize_selection_cfg().get("max_cta_readmit") or 0)
        except Exception:
            story = set()
            max_readmit = 0
        # When CTA readmit is disabled, keep sanitize/exclusion drops authoritative.
        if story and max_readmit > 0:
            on_air = {str(s) for s in (out.get("ordered_segment_ids") or []) if s}
            protect = story & on_air
            before_n = len(normalized)
            normalized = [
                row
                for row in normalized
                if str(row.get("segment_id") or "") not in protect
            ]
            if len(normalized) != before_n:
                applied.append(
                    {"action": "keep_cta_story_children", "count": before_n - len(normalized)}
                )
            for sid in protect:
                rationales.pop(sid, None)
        elif story and max_readmit <= 0:
            applied.append(
                {
                    "action": "skip_keep_cta_story_children",
                    "reason": "max_cta_readmit=0",
                    "excluded_story": len(story & excluded_ban),
                }
            )
        out["excluded_segment_ids"] = normalized
        if normalized:
            out["exclude_rationales"] = rationales
            applied.append({"action": "sync_exclude_rationales", "count": len(rationales)})
    elif out.get("excluded_segment_ids") and out.get("exclude_rationales") is None:
        out["exclude_rationales"] = {}
        applied.append({"action": "default_value", "path": "exclude_rationales"})
    if manifest_ids:
        ordered_set = {str(s) for s in (out.get("ordered_segment_ids") or []) if s}
        excl = list(out.get("excluded_segment_ids") or [])
        have = {
            str(r.get("segment_id") if isinstance(r, dict) else r)
            for r in excl
            if r is not None
        }
        missing = [s for s in manifest_ids if s not in ordered_set and s not in have]
        if missing:
            for sid in missing:
                excl.append({"segment_id": sid, "reason": "not_selected"})
            out["excluded_segment_ids"] = excl
            applied.append(
                {"action": "fill_unlisted_manifest_exclusions", "count": len(missing)}
            )
    try:
        from interview_mux.selection_order_repair import repair_selection_order

        plan = None
        if ctx.artifact_exists("master/narrative_plan.json"):
            loaded = ctx.read_json("master/narrative_plan.json")
            plan = loaded if isinstance(loaded, dict) else None
        starts: dict[str, int] = {}
        for rel in ("segments/boundaries.json", "segments/segments.json"):
            if not ctx.artifact_exists(rel):
                continue
            boundaries_doc = ctx.read_json(rel)
            rows = []
            if isinstance(boundaries_doc, dict):
                rows = list(
                    boundaries_doc.get("boundaries") or boundaries_doc.get("segments") or []
                )
            for row in rows:
                if not isinstance(row, dict) or not row.get("segment_id"):
                    continue
                try:
                    starts[str(row["segment_id"])] = int(row.get("start_ms") or 0)
                except (TypeError, ValueError):
                    continue
        ban_grow = _selection_excluded_id_set(out) | excluded_ban
        out, order_notes = repair_selection_order(
            out,
            plan,
            source_start_ms=starts or None,
            banned_readmit_ids=ban_grow,
            protect_final_ids=_closing_ids_safe(ctx, out),
        )
        applied.extend(order_notes)
    except Exception:
        pass
    # Selection is the air-order authority.  Narrative chapters may describe a
    # wider candidate pool, but they must never force excluded material back
    # into the episode (exec_1131 expanded a tight pack by 161 segments here).
    ordered = out.get("ordered_segment_ids")
    if isinstance(ordered, list) and ctx.artifact_exists("master/narrative_plan.json"):
        plan = ctx.read_json("master/narrative_plan.json")
        required: list[str] = []
        for ch in (plan.get("chapters") or []) if isinstance(plan, dict) else []:
            if not isinstance(ch, dict):
                continue
            for sid in ch.get("segment_ids") or []:
                s = str(sid)
                if s and s not in required and not _segment_is_blank_or_unusable(ctx, s):
                    required.append(s)
        if required:
            ordered_set = {str(s) for s in ordered}
            missing = [s for s in required if s not in ordered_set]
            if missing:
                applied.append(
                    {
                        "action": "intersect_narrative_chapters_with_selection",
                        "count": len(missing),
                        "ids": missing[:24],
                        "reason": "selection_exclusions_are_authoritative",
                    }
                )
    # Normalize chapter membership *to* the selected order without mutating that
    # order or dumping unassigned leftovers into a chapter.  Narrative repair
    # may annotate; it may not reverse ranking/creative-pack decisions.
    ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    chapters = out.get("chapters")
    if isinstance(chapters, list) and ordered:
        order_set = set(ordered)
        pos = {sid: idx for idx, sid in enumerate(ordered)}
        assigned: set[str] = set()
        new_chapters: list[dict[str, Any]] = []
        changed = False
        for ch in chapters:
            if not isinstance(ch, dict):
                continue
            raw_ids = [str(s) for s in (ch.get("segment_ids") or []) if s]
            ids = [s for s in raw_ids if s in order_set and s not in assigned]
            ids.sort(key=lambda sid: pos.get(sid, 10**9))
            if ids != raw_ids:
                changed = True
            for sid in ids:
                assigned.add(sid)
            row = dict(ch)
            row["segment_ids"] = ids
            new_chapters.append(row)
        leftovers = [sid for sid in ordered if sid not in assigned]
        if leftovers:
            from interview_mux.selection_order_repair import fill_chapter_list_membership_gaps

            filled_chapters, filled_ids = fill_chapter_list_membership_gaps(new_chapters, ordered)
            if filled_ids:
                new_chapters = filled_chapters
                changed = True
                applied.append(
                    {
                        "action": "fill_chapter_membership_gaps",
                        "count": len(filled_ids),
                        "ids": filled_ids[:12],
                    }
                )
            else:
                applied.append(
                    {
                        "action": "preserve_unassigned_selected_segments",
                        "count": len(leftovers),
                        "ids": leftovers[:12],
                        "reason": "do_not_mutate_selection_order_or_chapter_membership",
                    }
                )
        # Drop empty chapter shells — narrative_qc treats them as hard errors and
        # edl_narrative_audit LLMs then demand re-including excluded early acts.
        nonempty = [ch for ch in new_chapters if ch.get("segment_ids")]
        if len(nonempty) != len(new_chapters):
            changed = True
            applied.append(
                {
                    "action": "drop_empty_selection_chapters",
                    "removed": len(new_chapters) - len(nonempty),
                }
            )
            new_chapters = nonempty
        # Merge duplicate chapter titles (audit: max 8 + no split-title reuse).
        merged_by_title: list[dict[str, Any]] = []
        title_index: dict[str, int] = {}
        for ch in new_chapters:
            title = str(ch.get("title") or ch.get("chapter_title") or "").strip()
            key = title.casefold() if title else f"__anon_{len(merged_by_title)}"
            ids = [str(s) for s in (ch.get("segment_ids") or []) if s]
            if key in title_index and title:
                idx = title_index[key]
                prev = merged_by_title[idx]
                prev_ids = [str(s) for s in (prev.get("segment_ids") or []) if s]
                combined = list(dict.fromkeys([*prev_ids, *ids]))
                combined.sort(key=lambda sid: pos.get(sid, 10**9))
                prev["segment_ids"] = combined
                changed = True
                applied.append(
                    {
                        "action": "merge_duplicate_chapter_titles",
                        "title": title,
                        "count": len(combined),
                    }
                )
            else:
                title_index[key] = len(merged_by_title)
                merged_by_title.append(dict(ch))
        new_chapters = merged_by_title
        # Clamp to delivery_brief chapter_budget.max (default 8).
        max_chapters = 8
        try:
            if ctx.artifact_exists("understanding/delivery_brief.json"):
                brief = ctx.read_json("understanding/delivery_brief.json")
                budget = (brief or {}).get("chapter_budget") if isinstance(brief, dict) else {}
                if isinstance(budget, dict) and budget.get("max") is not None:
                    max_chapters = max(1, int(budget["max"]))
        except Exception:
            pass
        while len(new_chapters) > max_chapters:
            # Merge the adjacent pair with fewest combined segments (preserve arc ends).
            best_i = 0
            best_cost = 10**9
            for i in range(len(new_chapters) - 1):
                a = new_chapters[i].get("segment_ids") or []
                b = new_chapters[i + 1].get("segment_ids") or []
                cost = len(a) + len(b)
                # Prefer interior merges over collapsing cold-open/finale.
                if i == 0 or i + 1 == len(new_chapters) - 1:
                    cost += 3
                if cost < best_cost:
                    best_cost = cost
                    best_i = i
            left = dict(new_chapters[best_i])
            right = new_chapters[best_i + 1]
            left_ids = [str(s) for s in (left.get("segment_ids") or []) if s]
            right_ids = [str(s) for s in (right.get("segment_ids") or []) if s]
            combined = list(dict.fromkeys([*left_ids, *right_ids]))
            combined.sort(key=lambda sid: pos.get(sid, 10**9))
            left["segment_ids"] = combined
            if not str(left.get("title") or "").strip():
                left["title"] = str(right.get("title") or right.get("chapter_title") or "")
            new_chapters = [
                *new_chapters[:best_i],
                left,
                *new_chapters[best_i + 2 :],
            ]
            changed = True
            applied.append(
                {
                    "action": "clamp_chapters_to_budget",
                    "max": max_chapters,
                    "remaining": len(new_chapters),
                }
            )
        if changed:
            out["chapters"] = new_chapters
            applied.append(
                {
                    "action": "intersect_selection_chapters",
                    "count": len(new_chapters),
                }
            )
        # Keep narrative_plan chapter membership in sync with selection authority.
        try:
            align_notes = align_narrative_plan_to_selection(ctx, ordered_ids=ordered)
            applied.extend(align_notes)
        except Exception:
            pass
    media_cta = out.get("media_ip_cta")
    if isinstance(media_cta, list):
        normalized_cta: list[dict[str, Any]] = []
        for row in media_cta:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            cuts = item.get("cut_ms")
            if cuts is None:
                item.pop("cut_ms", None)
                applied.append({"action": "drop_null", "path": "media_ip_cta.cut_ms"})
            elif isinstance(cuts, (int, float)):
                item["cut_ms"] = [int(cuts)]
                applied.append({"action": "coerce_cut_ms_array", "path": "media_ip_cta.cut_ms"})
            elif isinstance(cuts, list):
                item["cut_ms"] = [int(x) for x in cuts if isinstance(x, (int, float))]
            else:
                item.pop("cut_ms", None)
                applied.append({"action": "drop_invalid", "path": "media_ip_cta.cut_ms"})
            normalized_cta.append(item)
        out["media_ip_cta"] = normalized_cta
    reconciled = reconcile_ordered_vs_excluded(out)
    if (
        reconciled.get("ordered_segment_ids") != out.get("ordered_segment_ids")
        or reconciled.get("excluded_segment_ids") != out.get("excluded_segment_ids")
        or reconciled.get("exclude_rationales") != out.get("exclude_rationales")
    ):
        applied.append({"action": "reconcile_ordered_vs_excluded"})
        if reconciled.get("exclude_rationales") != out.get("exclude_rationales"):
            applied.append({"action": "prune_stale_exclude_rationales"})
    out = reconciled
    _sort_selection_chapters_with_backward_jumps(ctx, out, applied)
    # Growth budget: amplifying repair must not balloon membership past sanitize/ranking.
    try:
        from interview_mux.artifact_sanitize.config import sanitize_selection_cfg

        growth_pct = float(sanitize_selection_cfg().get("max_order_growth_pct") or 15.0)
    except Exception:
        growth_pct = 15.0
    after_ids = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    # Also drop any excluded / banned ids that snuck back onto air.
    ban_final = excluded_ban | _selection_excluded_id_set(out)
    if ban_final:
        filtered = [s for s in after_ids if s not in ban_final]
        if len(filtered) != len(after_ids):
            dropped = [s for s in after_ids if s in ban_final]
            applied.append(
                {
                    "action": "drop_banned_readmit",
                    "count": len(dropped),
                    "ids": dropped[:24],
                }
            )
            after_ids = filtered
            out["ordered_segment_ids"] = after_ids
    if before_n > 0 and growth_pct >= 0:
        cap = max(before_n, int(before_n * (1.0 + (growth_pct / 100.0))))
        if len(after_ids) > cap:
            # Prefer keeping the prefix of current order (already topo-shaped).
            kept = after_ids[:cap]
            applied.append(
                {
                    "action": "clamp_order_growth",
                    "before": before_n,
                    "after": len(after_ids),
                    "cap": cap,
                    "growth_pct": growth_pct,
                }
            )
            out["ordered_segment_ids"] = kept
            after_ids = kept
    from interview_mux.order_hash import bump_order_lock

    stamped = bump_order_lock(out, source="artifact_repairs.repair_selection")
    if stamped.get("order_content_hash") != out.get("order_content_hash") or stamped.get(
        "order_lock"
    ) != out.get("order_lock"):
        applied.append(
            {
                "action": "stamp_order_content_hash",
                "order_content_hash": stamped.get("order_content_hash"),
                "order_lock_revision": (stamped.get("order_lock") or {}).get("revision"),
            }
        )
    out = stamped
    for entry in applied:
        _append_repair_meta(out, entry)
    return out, applied


def _segment_start_ms_map(ctx: Any) -> dict[str, int]:
    starts: dict[str, int] = {}
    if not ctx.artifact_exists("segments/manifest.json"):
        return starts
    manifest = ctx.read_json("segments/manifest.json")
    for row in (manifest.get("segments") or []) if isinstance(manifest, dict) else []:
        if not isinstance(row, dict) or not row.get("segment_id"):
            continue
        sid = str(row["segment_id"])
        try:
            starts[sid] = int(row.get("start_ms") or 0)
        except (TypeError, ValueError):
            starts[sid] = 0
    return starts


def _start_ms_for(sid: str, starts: dict[str, int]) -> int:
    if sid in starts:
        return starts[sid]
    stem = _parent_stem_segment_id(sid)
    return starts.get(stem, 0)


def _sort_selection_chapters_with_backward_jumps(
    ctx: Any,
    out: dict[str, Any],
    applied: list[dict[str, Any]],
) -> None:
    """Restore source time inside a chapter that currently airs a backward jump.

    Ranking sometimes parks a late fragment (e.g. seg_062) at the front of the
    closing chapter, then jumps back into earlier regulatory talk. Sort that
    contiguous chapter span by start_ms so the selected order stays coherent.
    """
    ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    chapters = out.get("chapters")
    if not ordered or not isinstance(chapters, list):
        return
    starts = _segment_start_ms_map(ctx)
    if not starts:
        return
    pos = {sid: idx for idx, sid in enumerate(ordered)}
    changed = False
    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        ids = [str(s) for s in (ch.get("segment_ids") or []) if s in pos]
        if len(ids) < 2:
            continue
        times = [_start_ms_for(sid, starts) for sid in ids]
        if not any(times[i] + 5000 < times[i - 1] for i in range(1, len(times))):
            continue
        idxs = [pos[sid] for sid in ids]
        lo, hi = min(idxs), max(idxs)
        span = ordered[lo : hi + 1]
        if set(span) != set(ids):
            continue
        ranked = sorted(
            ids,
            key=lambda sid: (_start_ms_for(sid, starts), pos[sid]),
        )
        if ranked == ids:
            continue
        ordered[lo : hi + 1] = ranked
        ch["segment_ids"] = ranked
        pos = {sid: idx for idx, sid in enumerate(ordered)}
        changed = True
        applied.append(
            {
                "action": "sort_chapter_air_order_by_source_time",
                "title": str(ch.get("title") or "")[:80],
                "ids": ranked[:12],
            }
        )
    if changed:
        out["ordered_segment_ids"] = ordered


def align_narrative_plan_to_selection(
    ctx: Any,
    *,
    ordered_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Rewrite narrative_plan chapters/constraints onto the selected air order.

    Selection is authoritative. Empty early-act chapter shells after a tight
    creative pack must be dropped — never used to force leftovers back in.
    """
    applied: list[dict[str, Any]] = []
    if not ctx.artifact_exists("master/narrative_plan.json"):
        return applied
    if ordered_ids is None:
        if not ctx.artifact_exists("master/selection.json"):
            return applied
        sel = ctx.read_json("master/selection.json")
        ordered_ids = [str(s) for s in (sel.get("ordered_segment_ids") or []) if s] if isinstance(sel, dict) else []
    order_set = {str(s) for s in (ordered_ids or []) if s}
    if not order_set:
        return applied
    plan = ctx.read_json("master/narrative_plan.json")
    if not isinstance(plan, dict):
        return applied
    out = copy.deepcopy(plan)
    chapters = out.get("chapters")
    if isinstance(chapters, list):
        kept: list[dict[str, Any]] = []
        dropped = 0
        for ch in chapters:
            if not isinstance(ch, dict):
                continue
            ids = [str(s) for s in (ch.get("segment_ids") or []) if str(s) in order_set]
            if not ids:
                dropped += 1
                continue
            row = dict(ch)
            row["segment_ids"] = ids
            open_id = str(row.get("suggested_open_segment_id") or "")
            if open_id and open_id not in order_set:
                row["suggested_open_segment_id"] = ids[0]
            kept.append(row)
        from interview_mux.selection_order_repair import fill_chapter_list_membership_gaps

        filled_chapters, filled_ids = fill_chapter_list_membership_gaps(
            kept, [str(s) for s in (ordered_ids or []) if s]
        )
        if filled_ids:
            kept = filled_chapters
            applied.append(
                {
                    "action": "fill_narrative_chapter_membership_gaps",
                    "ids": filled_ids[:12],
                }
            )
        if dropped or kept != chapters or filled_ids:
            out["chapters"] = kept
            applied.append(
                {
                    "action": "align_narrative_chapters_to_selection",
                    "kept": len(kept),
                    "dropped_empty": dropped,
                }
            )
    constraints = out.get("ordering_constraints")
    if isinstance(constraints, list):
        kept_c: list[Any] = []
        dropped_c = 0
        for row in constraints:
            if not isinstance(row, dict):
                continue
            before = str(
                row.get("before_segment_id")
                or row.get("before")
                or row.get("setup_segment_id")
                or ""
            )
            after = str(
                row.get("after_segment_id")
                or row.get("after")
                or row.get("payoff_segment_id")
                or ""
            )
            if (before and before not in order_set) or (after and after not in order_set):
                dropped_c += 1
                continue
            # Drop constraints that contradict selection air order (selection wins).
            if before and after and before in order_set and after in order_set:
                positions = {sid: i for i, sid in enumerate(ordered_ids or [])}
                if positions.get(before, -1) >= positions.get(after, 10**9):
                    dropped_c += 1
                    continue
            kept_c.append(row)
        if dropped_c:
            out["ordering_constraints"] = kept_c
            applied.append(
                {
                    "action": "drop_narrative_constraints_outside_selection",
                    "count": dropped_c,
                }
            )
    if applied:
        # Mix/junction freeze correctly denies edl_narrative_audit:narrative_metadata_align.
        # Do not attempt persist — soft-skip so order_reconcile / SDP invent do not
        # raise authority_denied and rewind (exec_13177 i15).
        mix_locked = False
        try:
            from interview_mux.artifact_ownership import current_epoch

            mix_locked = str(current_epoch(ctx) or "") in {
                "mix_seated",
                "junction_committed",
            }
        except Exception:
            mix_locked = False
        if not mix_locked:
            try:
                mix_locked = bool(ctx.artifact_exists("master/assembly.wav"))
            except Exception:
                mix_locked = False
        if mix_locked:
            applied.append(
                {
                    "action": "narrative_align_skipped_mix_seated",
                    "reason": "narrative_metadata_align forbidden under mix/junction seat",
                }
            )
            return applied
        try:
            from interview_mux.write_staging import write_committed_json

            write_committed_json(
                ctx,
                "master/narrative_plan.json",
                out,
                stage_key="edl_narrative_audit",
                mutation_class="narrative_metadata_align",
            )
        except Exception:
            ctx.write_json(
                "master/narrative_plan.json",
                out,
                stage_key="edl_narrative_audit",
                mutation_class="narrative_metadata_align",
            )
    return applied


def _drop_redundant_remapped_seeds(
    out: dict[str, Any], *, applied: list[dict[str, Any]]
) -> None:
    """Drop vo_seed_* / vo_density_* rows that remapped onto a target already covered by real VO."""
    lines = out.get("interviewer_lines")
    if not isinstance(lines, list):
        return
    covered_by_real: set[str] = set()
    for ln in lines:
        if not isinstance(ln, dict):
            continue
        lid = str(ln.get("line_id") or "")
        if lid.startswith("vo_seed_") or lid.startswith("vo_density_"):
            continue
        tgt = str(ln.get("targets_segment_id") or ln.get("segment_id") or "")
        if tgt:
            covered_by_real.add(tgt)
    kept: list[dict[str, Any]] = []
    dropped = 0
    for ln in lines:
        if not isinstance(ln, dict):
            continue
        lid = str(ln.get("line_id") or "")
        tgt = str(ln.get("targets_segment_id") or "")
        is_seed = lid.startswith("vo_seed_") or lid.startswith("vo_density_")
        if is_seed and tgt and tgt in covered_by_real:
            orig = ""
            if lid.startswith("vo_seed_"):
                orig = lid[len("vo_seed_") :]
            elif lid.startswith("vo_density_"):
                orig = lid[len("vo_density_") :]
            if orig and orig != tgt:
                dropped += 1
                applied.append(
                    {
                        "action": "drop_redundant_remapped_seed",
                        "line_id": lid,
                        "targets": tgt,
                    }
                )
                continue
            if orig == tgt:
                dropped += 1
                applied.append(
                    {
                        "action": "drop_seed_target_already_covered",
                        "line_id": lid,
                        "targets": tgt,
                    }
                )
                continue
        kept.append(ln)
    if dropped:
        out["interviewer_lines"] = kept


def _dedupe_interviewer_lines(
    out: dict[str, Any], *, applied: list[dict[str, Any]]
) -> None:
    """Keep first occurrence of each line_id / identical target+text (heal loops must not stack)."""
    lines = out.get("interviewer_lines")
    if not isinstance(lines, list):
        return
    seen: set[str] = set()
    seen_text: set[tuple[str, str, str]] = set()
    kept: list[dict[str, Any]] = []
    dropped = 0
    for row in lines:
        if not isinstance(row, dict):
            continue
        lid = str(row.get("line_id") or "").strip()
        if lid and lid in seen:
            dropped += 1
            continue
        tgt = str(row.get("targets_segment_id") or "").strip()
        placement = str(row.get("placement") or "before").strip() or "before"
        text_norm = " ".join(str(row.get("text") or "").strip().lower().split())
        tkey = (text_norm, tgt, placement)
        if text_norm and tgt and tkey in seen_text:
            dropped += 1
            continue
        if lid:
            seen.add(lid)
        if text_norm and tgt:
            seen_text.add(tkey)
        kept.append(row)
    if dropped:
        out["interviewer_lines"] = kept
        applied.append({"action": "dedupe_line_ids", "dropped": dropped})


def _seed_missing_high_gap_interviewer_lines(
    ctx: Any,
    out: dict[str, Any],
    *,
    manifest_ids: set[str],
    applied: list[dict[str, Any]],
) -> None:
    """Peeled (S7): persist/repair must not seed high-gap lines.

    HG-5 playbook / ``fill_uncovered_high_gaps`` owns seed.
    """
    raise RuntimeError(
        "artifact_repairs:_seed_missing_high_gap_interviewer_lines peeled — "
        "HG-5 playbook / fill_uncovered_high_gaps owns high-gap seed"
    )


def _segment_is_blank_or_unusable(ctx: Any, seg_id: str) -> bool:
    if not ctx.artifact_exists("segments/manifest.json"):
        return False
    try:
        from interview_mux.media_ip_cta import admitted_story_segment_ids, never_touch_segment_ids

        admitted = str(seg_id) in admitted_story_segment_ids(ctx) and str(
            seg_id
        ) not in never_touch_segment_ids(ctx)
    except Exception:
        admitted = False
    man = ctx.read_json("segments/manifest.json")
    for row in (man.get("segments") or []) if isinstance(man, dict) else []:
        if not isinstance(row, dict):
            continue
        if str(row.get("segment_id") or "") != seg_id:
            continue
        text = str(row.get("text") or "").strip()
        dur = max(0, int(row.get("end_ms") or 0) - int(row.get("start_ms") or 0))
        # Empty / near-silent always unusable (even admitted story kids).
        if not text or dur < 400:
            return True
        meta = row.get("_meta") if isinstance(row.get("_meta"), dict) else {}
        story_keep_ok = bool(meta.get("story_keep_ok"))
        # Listen-complete CTA story prefixes may stay short on air.
        if admitted and story_keep_ok:
            return False
        # Incomplete micro-fragments are blank even if admitted without stamp
        # (exec_11630 seg_003a/003j blank-on-air contradiction).
        words = [w for w in text.replace("…", " ").split() if w.strip(".,;:!?\"'")]
        if len(words) <= 8 and dur < 8000:
            return True
        return False
    return False


def _same_speaker_source_contiguous_rows(
    prev: dict[str, Any] | None,
    curr: dict[str, Any] | None,
    *,
    gap_ms: int = 2500,
) -> bool:
    if not isinstance(prev, dict) or not isinstance(curr, dict):
        return False
    prev_spk = str(prev.get("speaker_id") or "").strip()
    curr_spk = str(curr.get("speaker_id") or "").strip()
    if not prev_spk or prev_spk != curr_spk:
        return False
    try:
        prev_end = int(prev.get("end_ms") or prev.get("source_end_ms") or 0)
        curr_start = int(curr.get("start_ms") or curr.get("source_start_ms") or 0)
    except (TypeError, ValueError):
        return False
    return -gap_ms <= (curr_start - prev_end) <= gap_ms


def _enforce_min_vo_insert_ratio(ctx: Any, out: dict[str, Any], *, applied: list[dict[str, Any]]) -> None:
    """Hard floor: ceil(selected_speech * min_vo_insert_ratio) host VO lines."""
    import math

    from interview_mux.config import merged_config

    gf = ((merged_config().get("analysis") or {}).get("gap_framing") or {})
    ratio = float(gf.get("min_vo_insert_ratio") or 0.0)
    if ratio <= 0:
        return
    ordered: list[str] = []
    if ctx.artifact_exists("master/selection.json"):
        try:
            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict):
                ordered = [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]
        except Exception:
            ordered = []
    if not ordered and ctx.artifact_exists("segments/manifest.json"):
        try:
            man = ctx.read_json("segments/manifest.json")
            ordered = [
                str(r.get("segment_id"))
                for r in ((man or {}).get("segments") or [])
                if isinstance(r, dict) and r.get("segment_id")
            ]
        except Exception:
            ordered = []
    if not ordered:
        return
    floor = max(1, int(math.ceil(len(ordered) * ratio)))
    lines = out.get("interviewer_lines")
    if not isinstance(lines, list):
        lines = []
        out["interviewer_lines"] = lines
    covered = {
        str(ln.get("targets_segment_id") or ln.get("segment_id") or "")
        for ln in lines
        if isinstance(ln, dict) and not ln.get("skipped_optional")
    }
    if len([ln for ln in lines if isinstance(ln, dict) and not ln.get("skipped_optional")]) >= floor:
        return
    chapter_ends: set[str] = set()
    if ctx.artifact_exists("master/narrative_plan.json"):
        try:
            plan = ctx.read_json("master/narrative_plan.json")
            for ch in ((plan or {}).get("chapters") or []):
                if isinstance(ch, dict):
                    segs = [str(s) for s in (ch.get("segment_ids") or [])]
                    if segs:
                        chapter_ends.add(segs[-1])
        except Exception:
            pass
    # Speaker-role changes (true conversational seams) — never mid-monologue breaks.
    role_hinges: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    try:
        man = ctx.read_json("segments/manifest.json") if ctx.artifact_exists("segments/manifest.json") else {}
        by_id = {
            str(r.get("segment_id")): r
            for r in ((man or {}).get("segments") or [])
            if isinstance(r, dict) and r.get("segment_id")
        }
        prev_spk = ""
        for sid in ordered:
            row = by_id.get(sid) or {}
            spk = str(row.get("speaker_id") or "")
            if prev_spk and spk and spk != prev_spk and sid not in covered:
                role_hinges.append(sid)
            prev_spk = spk or prev_spk
    except Exception:
        role_hinges = []
    stride = max(1, len(ordered) // max(1, floor))
    priority = list(dict.fromkeys(role_hinges + [s for s in ordered if s in chapter_ends] + ordered))
    from interview_mux.gap_vo_prior_context import (
        apply_prior_context_to_density_seed,
        courtesy_seed_text,
    )

    pred: dict[str, str] = {}
    for i in range(1, len(ordered)):
        pred[ordered[i]] = ordered[i - 1]

    seed_i = 0
    variety_cats = (
        ["framing_question"] * 4
        + ["story_bridge"] * 3
        + ["segment_summary"] * 2
        + ["episode_preface"]
    )
    for i, sid in enumerate(priority):
        if len([ln for ln in lines if isinstance(ln, dict) and not ln.get("skipped_optional")]) >= floor:
            break
        if sid in covered:
            continue
        prior_sid = pred.get(sid) or ""
        if (
            prior_sid
            and sid not in chapter_ends
            and sid not in role_hinges
            and _same_speaker_source_contiguous_rows(by_id.get(prior_sid), by_id.get(sid))
        ):
            continue
        # Always take speaker-change / chapter seeds; otherwise stride-sample.
        if sid not in role_hinges and sid not in chapter_ends:
            try:
                oi = ordered.index(sid)
            except ValueError:
                continue
            if oi % stride != 0:
                continue
        if sid in chapter_ends:
            cat = "episode_preface"
        elif sid in role_hinges:
            cat = "framing_question"
        else:
            cat = variety_cats[seed_i % len(variety_cats)]
            seed_i += 1
        text = courtesy_seed_text(None, category=cat, target_segment_id=sid)
        final_sid, final_text, _prior, prov = apply_prior_context_to_density_seed(
            ctx, target_segment_id=sid, category=cat, text=text
        )
        if final_sid in covered and final_sid != sid:
            # Relocated onto an already-covered substantive target — skip duplicate.
            covered.add(sid)
            continue
        covered.add(sid)
        covered.add(final_sid)
        line = {
            "line_id": f"vo_density_{final_sid}",
            "gap_type": "missing_followup",
            "line_category": cat,
            "text": final_text,
            "targets_segment_id": final_sid,
            "placement": "before",
            "delivery": "synthesize",
            "rationale": f"Density floor seed (min_vo_insert_ratio={ratio})",
            "supports_segment_ids": [final_sid],
            "replaces_source_segments": [],
            "estimated_duration_sec": 5,
            "severity": "medium",
            "suggested_tone": "neutral",
            "density_forced": True,
        }
        if prov.get("prior_segment_id"):
            line["prior_segment_id"] = prov.get("prior_segment_id")
        if prov.get("prior_impact_beat") is not None:
            line["prior_impact_beat"] = bool(prov.get("prior_impact_beat"))
        if prov.get("prior_complete_thought") is not None:
            line["prior_complete_thought"] = bool(prov.get("prior_complete_thought"))
        if final_sid != sid:
            line["rationale"] = (
                f"Density floor seed (min_vo_insert_ratio={ratio}; "
                f"relocated from micro {sid} → {final_sid})"
            )
            applied.append(
                {
                    "action": "seed_vo_density_floor_relocated",
                    "from_segment_id": sid,
                    "segment_id": final_sid,
                    "category": cat,
                    "prior_impact_beat": bool(line.get("prior_impact_beat")),
                }
            )
        else:
            applied.append(
                {
                    "action": "seed_vo_density_floor",
                    "segment_id": final_sid,
                    "category": cat,
                    "prior_impact_beat": bool(line.get("prior_impact_beat")),
                }
            )
        lines.append(line)

def _rewrite_editorial_qc_vo_lines(
    ctx: Any,
    out: dict[str, Any],
    *,
    applied: list[dict[str, Any]],
) -> None:
    """Replace gap-eval QC prose in spoken VO with courteous interviewer copy."""
    from interview_mux.gap_framing import GAP_TYPE_TO_CATEGORY, infer_line_category
    from interview_mux.gap_vo_prior_context import (
        apply_prior_context_to_density_seed,
        courtesy_seed_text,
    )
    from interview_mux.spoken_meta_lint import is_editorial_qc_prose

    lines = out.get("interviewer_lines")
    if not isinstance(lines, list):
        return
    rewritten: list[dict[str, Any]] = []
    for row in lines:
        if not isinstance(row, dict):
            continue
        line = dict(row)
        text = str(line.get("text") or "").strip()
        if not text or not is_editorial_qc_prose(text):
            rewritten.append(line)
            continue
        category = str(line.get("line_category") or "").strip() or infer_line_category(line)
        if not category:
            gap_type = str(line.get("gap_type") or "")
            category = GAP_TYPE_TO_CATEGORY.get(gap_type, "framing_question")
        target = str(line.get("targets_segment_id") or line.get("segment_id") or "").strip()
        new_text = courtesy_seed_text(None, category=category, target_segment_id=target or None)
        if target:
            try:
                target, new_text, _prior, prov = apply_prior_context_to_density_seed(
                    ctx,
                    target_segment_id=target,
                    category=category,
                    text=new_text,
                )
                if isinstance(prov, dict):
                    for key in (
                        "prior_segment_id",
                        "prior_impact_beat",
                        "prior_complete_thought",
                        "density_forced",
                    ):
                        if key in prov:
                            line[key] = prov[key]
            except Exception:
                pass
        if is_editorial_qc_prose(new_text):
            new_text = courtesy_seed_text(None, category=category, target_segment_id=target or None)
        line["text"] = new_text
        if target:
            line["targets_segment_id"] = target
        applied.append(
            {
                "action": "rewrite_editorial_qc_vo",
                "line_id": line.get("line_id"),
            }
        )
        rewritten.append(line)
    out["interviewer_lines"] = rewritten


def repair_gap_report(
    ctx: Any,
    doc: dict[str, Any],
    *,
    resolve_high_gap_seats: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    out = copy.deepcopy(doc)
    applied: list[dict[str, Any]] = []
    manifest_ids, _ = _manifest_ids_and_tags(ctx)
    lines = out.get("interviewer_lines")
    if isinstance(lines, list):
        cleaned: list[dict[str, Any]] = []
        for row in lines:
            if not isinstance(row, dict):
                continue
            fixed = dict(row)
            for key in (
                "act_context",
                "trim_hint_ms",
                "skipped_optional",
                "blocking",
                "severity",
                "suggested_tone",
                "rationale",
                "voice_speaker_id",
            ):
                if fixed.get(key) is None:
                    fixed.pop(key, None)
                    applied.append({"action": "drop_null", "path": key})
            # Schema boolean fields — LLM often emits JSON null; coerce rather than drop so
            # provenance keys remain present for downstream courtesy / density audits.
            for bool_key in ("prior_impact_beat", "prior_complete_thought", "density_forced"):
                if bool_key in fixed:
                    fixed[bool_key] = bool(fixed.get(bool_key))
                    applied.append({"action": "coerce_bool", "path": bool_key})
            if "prior_segment_id" in fixed and fixed.get("prior_segment_id") is not None:
                fixed["prior_segment_id"] = str(fixed.get("prior_segment_id") or "") or None
            extracted = fixed.get("extracted_from")
            if isinstance(extracted, dict):
                cleaned_ex = {
                    k: v
                    for k, v in extracted.items()
                    if v is not None and str(v).strip() != ""
                }
                if cleaned_ex:
                    fixed["extracted_from"] = cleaned_ex
                else:
                    fixed.pop("extracted_from", None)
                    applied.append({"action": "drop_null", "path": "extracted_from"})
            elif extracted is None and "extracted_from" in fixed:
                fixed.pop("extracted_from", None)
                applied.append({"action": "drop_null", "path": "extracted_from"})
            guard = fixed.get("spoken_copy_guard")
            if "spoken_copy_guard" in fixed and guard is None:
                fixed.pop("spoken_copy_guard", None)
                applied.append({"action": "drop_null", "path": "spoken_copy_guard"})
            elif isinstance(guard, dict):
                cleaned_g: dict[str, Any] = {}
                changed = False
                for gkey, gval in guard.items():
                    if gval is None:
                        changed = True
                        if gkey == "action":
                            cleaned_g[gkey] = "omit"
                        elif gkey in {"script_hash", "context_hash"}:
                            cleaned_g[gkey] = ""
                        continue
                    cleaned_g[gkey] = gval
                if changed:
                    if cleaned_g:
                        fixed["spoken_copy_guard"] = cleaned_g
                    else:
                        fixed.pop("spoken_copy_guard", None)
                    applied.append(
                        {
                            "action": "coalesce_spoken_copy_guard_nulls",
                            "line_id": fixed.get("line_id"),
                        }
                    )
            # Schema requires arrays; LLMs often emit null for unused lists.
            for arr_key in (
                "replaces_source_segments",
                "supports_segment_ids",
                "nugget_ids",
                "recovery_of_talking_point_ids",
            ):
                if arr_key in fixed and fixed.get(arr_key) is None:
                    fixed[arr_key] = []
                    applied.append({"action": "null_to_empty_array", "path": arr_key})
                elif arr_key in fixed and not isinstance(fixed.get(arr_key), list):
                    fixed[arr_key] = []
                    applied.append({"action": "coerce_array", "path": arr_key})
            # Envelope nulls on string taxonomy leaves — coerce via existing vocabulary.
            if "line_category" in fixed and (
                fixed.get("line_category") is None
                or not str(fixed.get("line_category") or "").strip()
            ):
                from interview_mux.gap_framing import infer_line_category

                fixed["line_category"] = infer_line_category(fixed)
                applied.append({"action": "default_line_category", "path": "line_category"})
            if "origin" in fixed and fixed.get("origin") is None:
                fixed["origin"] = ""
                applied.append({"action": "null_to_empty_string", "path": "origin"})
            elif "origin" in fixed and not isinstance(fixed.get("origin"), str):
                fixed["origin"] = str(fixed.get("origin") or "")
            # Pre-flush courtesy lint requires conversation-partner rationale when
            # text is present (exec_13177: high_gap_vo seeds omitted rationale →
            # commit_barrier_halt masked as pending_only).
            text_s = str(fixed.get("text") or "").strip()
            if text_s and not str(fixed.get("rationale") or "").strip():
                confusion = ""
                extracted = fixed.get("extracted_from")
                if isinstance(extracted, dict):
                    confusion = str(
                        extracted.get("listener_confusion") or ""
                    ).strip()
                rationale = "Auto-repaired interviewer line — conversation-partner value."
                if confusion:
                    rationale = f"{rationale} Mission: {confusion[:160]}"
                elif str(fixed.get("line_id") or "").startswith("vo_seed_"):
                    rationale = (
                        "Auto-seeded for high-severity gap missing an interviewer line."
                    )
                fixed["rationale"] = rationale
                applied.append(
                    {
                        "action": "default_rationale",
                        "line_id": fixed.get("line_id"),
                    }
                )
            if not str(fixed.get("gap_type") or "").strip():
                origin = str(fixed.get("origin") or "")
                fixed["gap_type"] = "nugget_layup" if origin == "nugget_layup" else "missing_setup"
                applied.append({"action": "default_gap_type", "path": "gap_type"})
            cleaned.append(fixed)
        lines = cleaned
        out["interviewer_lines"] = cleaned
    # opening_orientation: envelope nulls on string/bool leaves refuse disk write.
    oo = out.get("opening_orientation")
    if isinstance(oo, dict):
        oo_fixed = dict(oo)
        oo_changed = False
        for sk in ("sequence", "target_segment_id", "omit_reason"):
            if sk in oo_fixed and oo_fixed.get(sk) is None:
                oo_fixed[sk] = ""
                oo_changed = True
                applied.append({"action": "null_to_empty_string", "path": f"opening_orientation.{sk}"})
            elif sk in oo_fixed and not isinstance(oo_fixed.get(sk), str):
                oo_fixed[sk] = str(oo_fixed.get(sk) or "")
                oo_changed = True
        for bk in ("required", "omitted"):
            if bk in oo_fixed and oo_fixed.get(bk) is None:
                oo_fixed[bk] = False
                oo_changed = True
                applied.append({"action": "coerce_bool", "path": f"opening_orientation.{bk}"})
            elif bk in oo_fixed and not isinstance(oo_fixed.get(bk), bool):
                oo_fixed[bk] = bool(oo_fixed.get(bk))
                oo_changed = True
        if oo_changed:
            out["opening_orientation"] = oo_fixed
    # exec_13181: non-orientation tier-D waive must not leave orientation omitted.
    try:
        from interview_mux.opening_orientation import (
            repair_false_orientation_omit_from_non_orient_waive,
        )

        out, false_omit_notes = repair_false_orientation_omit_from_non_orient_waive(out)
        applied.extend(false_omit_notes)
        lines = out.get("interviewer_lines") or lines
    except Exception:
        pass
    if isinstance(lines, list) and manifest_ids:
        kept = []
        for row in lines:
            if not isinstance(row, dict):
                continue
            tgt = str(row.get("targets_segment_id") or row.get("segment_id") or "")
            if tgt and tgt not in manifest_ids:
                applied.append({"action": "drop_orphan_ref", "segment_id": tgt})
                continue
            if not row.get("line_id"):
                row["line_id"] = f"line_{len(kept) + 1}"
                applied.append({"action": "default_value", "path": "line_id"})
            kept.append(row)
        out["interviewer_lines"] = kept
    _dedupe_interviewer_lines(out, applied=applied)
    _drop_redundant_remapped_seeds(out, applied=applied)
    _rewrite_editorial_qc_vo_lines(ctx, out, applied=applied)
    # S7: do not seed/fill high gaps in compose repair — HG-5 playbook owns seed.
    # Still clear orphan layup authority stamps so repair does not greenwash.
    if bool(out.get("nugget_layup_authority")):
        plan_on_disk = False
        try:
            from interview_mux.nugget_layup import PLAN_REL

            plan_on_disk = bool(ctx.artifact_exists(PLAN_REL))
        except Exception:
            plan_on_disk = False
        if not plan_on_disk:
            out["nugget_layup_authority"] = False
            applied.append(
                {
                    "action": "clear_orphan_nugget_layup_authority",
                    "reason": "stamp_without_plan",
                }
            )
    _drop_redundant_remapped_seeds(out, applied=applied)
    _dedupe_interviewer_lines(out, applied=applied)
    # Trim over-budget line text so post-commit word-limit lint can pass.
    try:
        from interview_mux.gap_framing import infer_line_category, word_limit_for_category

        trimmed_lines: list[dict[str, Any]] = []
        for row in list(out.get("interviewer_lines") or []):
            if not isinstance(row, dict):
                continue
            line = dict(row)
            text = str(line.get("text") or "").strip()
            if text:
                cat = infer_line_category(line)
                limit = max(1, int(word_limit_for_category(cat)))
                words = text.split()
                if len(words) > limit:
                    from interview_mux.spoken_copy_guard import shorten_spoken_text

                    line["text"] = shorten_spoken_text(text, limit)
                    applied.append(
                        {
                            "action": "trim_line_word_limit",
                            "line_id": line.get("line_id"),
                            "category": cat,
                            "from": len(words),
                            "to": limit,
                        }
                    )
            trimmed_lines.append(line)
        out["interviewer_lines"] = trimmed_lines
    except Exception:
        pass
    try:
        from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

        skip_density = gap_fill_was_skipped(ctx)
    except Exception:
        skip_density = False
    if not skip_density:
        _enforce_min_vo_insert_ratio(ctx, out, applied=applied)
    # Stamp prior-native provenance + rewrite leftover interruptive openers after impact.
    try:
        from interview_mux.gap_vo_prior_context import (
            build_prior_native_context,
            cold_open_layup_ok,
            courtesy_seed_text,
            has_forward_cue,
            is_interruptive_opener,
            last_sentence_restates_target,
            load_ordered_and_segments,
            prior_context_cfg,
            repair_last_sentence_layup,
            stamp_lines_prior_provenance,
            write_gap_vo_context_audit,
        )

        stamped = stamp_lines_prior_provenance(ctx, list(out.get("interviewer_lines") or []))
        ordered, by_id, chapters = load_ordered_and_segments(ctx)
        settings = prior_context_cfg()
        from interview_mux.opening_orientation import is_episode_orientation
        from interview_mux.air_script import seated_vo_line_ids
        from interview_mux.mastering_plan_loader import load_plan_raw
        from interview_mux.vo_contract import ensure_gap_line_on_air, mark_gap_line_not_on_air

        _plan = load_plan_raw(ctx) if ctx.artifact_exists("mastering/mastering_plan.json") else {}
        _seated_ids = seated_vo_line_ids(_plan)
        try:
            from interview_mux.air_script import omitted_vo_line_ids as _omitted_vo_line_ids

            _omitted_ids = _omitted_vo_line_ids(_plan)
        except Exception:
            _omitted_ids = set()

        fixed_lines: list[dict[str, Any]] = []
        for row in stamped:
            if not isinstance(row, dict):
                continue
            line = dict(row)
            # Episode orientation is selection-independent setup copy — never
            # collapse it into a courtesy seam hinge after impact beats.
            # Still heal a missing forward cue so post-commit lint does not loop.
            if is_episode_orientation(line):
                text_now = str(line.get("text") or "").strip()
                try:
                    from interview_mux.spoken_meta_lint import (
                        rewrite_speaker_role_labels,
                        spoken_structure_hits,
                    )

                    if text_now and "spoken_speaker_role_label" in spoken_structure_hits(
                        text_now
                    ):
                        healed = rewrite_speaker_role_labels(text_now)
                        if healed and healed != text_now:
                            line["text"] = healed
                            text_now = healed
                            applied.append(
                                {
                                    "action": "preface_speaker_role_rewrite",
                                    "line_id": line.get("line_id"),
                                }
                            )
                except Exception:
                    pass
                text_now = str(line.get("text") or "").strip()
                tid_now = str(line.get("targets_segment_id") or "").strip()
                cat = str(line.get("line_category") or "episode_preface")
                target_row = by_id.get(tid_now) or {}
                target_text = str(
                    target_row.get("text") or target_row.get("text_excerpt") or ""
                )
                # F3: missing forward cue OR cued-but-restating first native
                # (cold_open_layup_ok overlap) — both need repair_last_sentence_layup.
                # Prior path only healed missing cues then continue'd, so restatement
                # blocked pre-flush (exec_13181 vo_preface_seg_004).
                needs_preface_layup = bool(text_now) and (
                    not has_forward_cue(text_now)
                    or not cold_open_layup_ok(
                        line, target_text=target_text, ordered_ids=ordered
                    )
                )
                if needs_preface_layup:
                    prior = build_prior_native_context(
                        target_segment_id=tid_now,
                        ordered_ids=ordered,
                        segments_by_id=by_id,
                        chapters=chapters,
                        cfg=settings,
                    )
                    from interview_mux.gap_framing import word_limit_for_category as _wlim

                    missing_cue = not has_forward_cue(text_now)
                    line["text"] = repair_last_sentence_layup(
                        text_now,
                        prior=prior,
                        category=cat,
                        target_text=target_text,
                        target_segment_id=tid_now or None,
                        max_words=max(1, int(_wlim(cat))),
                    )
                    applied.append(
                        {
                            "action": (
                                "preface_forward_cue_heal"
                                if missing_cue
                                else "preface_cold_open_layup_heal"
                            ),
                            "line_id": line.get("line_id"),
                            "targets_segment_id": tid_now,
                        }
                    )
                fixed_lines.append(line)
                continue
            # Authoritative layups own their recovery copy — courtesy rewrites
            # were replacing plan text with canned hinges and failing EDL.
            is_authoritative_layup = (
                bool(out.get("nugget_layup_authority"))
                and str(line.get("origin") or "") == "nugget_layup"
            )
            if (
                not is_authoritative_layup
                and line.get("prior_impact_beat")
                and is_interruptive_opener(str(line.get("text") or ""))
            ):
                cat = str(line.get("line_category") or "framing_question")
                prior = build_prior_native_context(
                    target_segment_id=str(line.get("targets_segment_id") or ""),
                    ordered_ids=ordered,
                    segments_by_id=by_id,
                    chapters=chapters,
                    cfg=settings,
                )
                line["text"] = courtesy_seed_text(
                    prior, category=cat, target_segment_id=str(line.get("targets_segment_id") or "") or None
                )
                applied.append(
                    {
                        "action": "rewrite_interruptive_after_impact",
                        "line_id": line.get("line_id"),
                        "prior_segment_id": line.get("prior_segment_id"),
                    }
                )
            text_now = str(line.get("text") or "").strip()
            try:
                from interview_mux.spoken_meta_lint import (
                    rewrite_speaker_role_labels,
                    spoken_structure_hits,
                )

                if text_now and "spoken_speaker_role_label" in spoken_structure_hits(
                    text_now
                ):
                    healed = rewrite_speaker_role_labels(text_now)
                    if healed and healed != text_now:
                        line["text"] = healed
                        text_now = healed
                        applied.append(
                            {
                                "action": "speaker_role_rewrite",
                                "line_id": line.get("line_id"),
                            }
                        )
            except Exception:
                pass
            tid_now = str(line.get("targets_segment_id") or "").strip()
            target_row = by_id.get(tid_now) or {}
            target_text = str(target_row.get("text") or target_row.get("text_excerpt") or "")
            overlap_dirty = last_sentence_restates_target(text_now, target_text)
            needs_layup = (not is_authoritative_layup) and text_now and (
                not has_forward_cue(text_now)
                or not cold_open_layup_ok(line, target_text=target_text, ordered_ids=ordered)
            )
            if needs_layup or overlap_dirty:
                cat = str(line.get("line_category") or "framing_question")
                prior = build_prior_native_context(
                    target_segment_id=tid_now,
                    ordered_ids=ordered,
                    segments_by_id=by_id,
                    chapters=chapters,
                    cfg=settings,
                )
                from interview_mux.gap_framing import word_limit_for_category as _wlim

                line["text"] = repair_last_sentence_layup(
                    text_now,
                    prior=prior,
                    target_text=target_text,
                    category=cat,
                    target_segment_id=tid_now or None,
                    max_words=max(1, int(_wlim(cat))),
                )
                applied.append(
                    {
                        "action": "repair_last_sentence_overlap"
                        if overlap_dirty
                        else "repair_last_sentence_layup",
                        "line_id": line.get("line_id"),
                        "targets_segment_id": tid_now,
                    }
                )
            if last_sentence_restates_target(str(line.get("text") or ""), target_text):
                lid_now = str(line.get("line_id") or "").strip()
                # Air-contract omit wins — never revive an omitted seat via overlap heal.
                if lid_now and lid_now in _omitted_ids and lid_now not in _seated_ids:
                    line = mark_gap_line_not_on_air(
                        line,
                        reason_code="air_script_omit_sync",
                        ctx=ctx,
                        gap_report=out if isinstance(out, dict) else None,
                    )
                    applied.append(
                        {
                            "action": "overlap_keep_omitted",
                            "line_id": line.get("line_id"),
                            "targets_segment_id": tid_now,
                        }
                    )
                elif lid_now and lid_now in _seated_ids:
                    line = ensure_gap_line_on_air(line)
                    applied.append(
                        {
                            "action": "overlap_keep_seated",
                            "line_id": line.get("line_id"),
                            "targets_segment_id": tid_now,
                        }
                    )
                else:
                    line = mark_gap_line_not_on_air(
                        line,
                        reason_code="last_sentence_overlap",
                        ctx=ctx,
                        gap_report=out if isinstance(out, dict) else None,
                    )
                    applied.append(
                        {
                            "action": "skip_last_sentence_overlap",
                            "line_id": line.get("line_id"),
                            "targets_segment_id": tid_now,
                        }
                    )
            fixed_lines.append(line)
        # Final coerce after stamp/rewrite — never leave JSON null on boolean schema fields.
        coerced: list[dict[str, Any]] = []
        for row in fixed_lines:
            if not isinstance(row, dict):
                continue
            line = dict(row)
            for bool_key in ("prior_impact_beat", "prior_complete_thought", "density_forced"):
                if bool_key in line:
                    line[bool_key] = bool(line.get(bool_key))
            extracted = line.get("extracted_from")
            if isinstance(extracted, dict):
                cleaned_ex = {
                    k: v
                    for k, v in extracted.items()
                    if v is not None and str(v).strip() != ""
                }
                if cleaned_ex:
                    line["extracted_from"] = cleaned_ex
                else:
                    line.pop("extracted_from", None)
            elif extracted is None and "extracted_from" in line:
                line.pop("extracted_from", None)
            coerced.append(line)
        # Final word-budget after layup — trim-then-cue used to re-bloom past max
        # (exec_13159 vo_context_seg_009: 20→22 post-commit).
        try:
            from interview_mux.gap_framing import (
                infer_line_category,
                word_limit_for_category,
            )
            from interview_mux.spoken_copy_guard import shorten_spoken_text

            rebudgeted: list[dict[str, Any]] = []
            for row in coerced:
                if not isinstance(row, dict):
                    continue
                line = dict(row)
                text = str(line.get("text") or "").strip()
                if text:
                    cat = infer_line_category(line)
                    limit = max(1, int(word_limit_for_category(cat)))
                    words = re.findall(r"\S+", text)
                    if len(words) > limit:
                        if has_forward_cue(text):
                            line["text"] = repair_last_sentence_layup(
                                text,
                                category=cat,
                                max_words=limit,
                            )
                        else:
                            line["text"] = shorten_spoken_text(text, limit)
                        applied.append(
                            {
                                "action": "rebudget_after_layup",
                                "line_id": line.get("line_id"),
                                "category": cat,
                                "from": len(words),
                                "to": limit,
                            }
                        )
                rebudgeted.append(line)
            coerced = rebudgeted
        except Exception:
            pass
        out["interviewer_lines"] = coerced
        write_gap_vo_context_audit(ctx, coerced)
    except Exception:
        pass
    from interview_mux.gates import g1_vo_was_skipped_optional, vo_gap_line_effectively_optional
    from interview_mux.v2.config import v2_g1_optional

    # Cascade-skip only when a real G1 skip was applied (non-empty line ids or
    # at least one line already marked). Never trust a stale empty-skip meta alone.
    skip_applied_ids: set[str] = set()
    if ctx.artifact_exists("run_meta.json"):
        meta = ctx.read_json("run_meta.json")
        if isinstance(meta, dict):
            raw_ids = meta.get("g1_skip_applied_line_ids")
            if isinstance(raw_ids, list):
                skip_applied_ids = {str(x) for x in raw_ids if x}
    already_skipped = False
    if isinstance(lines, list):
        already_skipped = any(
            isinstance(row, dict) and row.get("skipped_optional") for row in lines
        )
    real_skip = bool(skip_applied_ids) or already_skipped
    if v2_g1_optional() and g1_vo_was_skipped_optional(ctx) and real_skip:
        lines = out.get("interviewer_lines")
        if isinstance(lines, list):
            for row in lines:
                if not isinstance(row, dict):
                    continue
                delivery = str(row.get("delivery") or "").lower()
                if delivery not in {"record", "synthesize"}:
                    continue
                if vo_gap_line_effectively_optional(ctx, row):
                    if not row.get("skipped_optional"):
                        row["skipped_optional"] = True
                        row["blocking"] = False
                        applied.append(
                            {
                                "action": "mark_skipped_optional",
                                "line_id": row.get("line_id"),
                            }
                        )
    # Final listener-facing guard after every deterministic repair/rewrite.
    from interview_mux.opening_orientation import is_episode_orientation
    from interview_mux.spoken_copy_guard import enrich_evidence_from_run, guard_spoken_copy

    by_id: dict[str, dict[str, Any]] = {}
    if ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")
        by_id = {
            str(row.get("segment_id")): row
            for row in ((manifest or {}).get("segments") or [])
            if isinstance(row, dict) and row.get("segment_id")
        }
    grounding_context = (
        ctx.read_json("understanding/content_brief.json")
        if ctx.artifact_exists("understanding/content_brief.json")
        else None
    )
    guarded_lines: list[dict[str, Any]] = []
    seen_texts: list[str] = []
    for row in out.get("interviewer_lines") or []:
        if not isinstance(row, dict):
            continue
        if row.get("skipped_optional"):
            guarded_lines.append(row)
            continue
        required = is_episode_orientation(row) or bool(row.get("required"))
        lid = str(row.get("line_id") or "")
        origin = str(row.get("origin") or "")
        if (
            lid.startswith("vo_fill_")
            or lid.startswith("vo_seed_")
            or origin in {"high_gap_vo_fill", "nugget_layup"}
            or str(row.get("severity") or "").lower() == "high"
        ):
            required = True
            row["required"] = True
        # Episode-preface copy describes the whole conversation, not a local
        # source-timeline join. Applying negative-gap chronology rules here
        # misclassifies phrases such as "next-chapter goals" and replaces the
        # orientation with a generic seam hinge.
        source_gap = None if required else row.get("source_gap_ms")
        if source_gap is None and not required:
            target = str(row.get("targets_segment_id") or "")
            prior_id = str(row.get("prior_segment_id") or "")
            prior_row = by_id.get(prior_id) or {}
            target_row = by_id.get(target) or {}
            if prior_row and target_row:
                try:
                    source_gap = int(target_row.get("start_ms") or 0) - int(
                        prior_row.get("end_ms") or 0
                    )
                except (TypeError, ValueError):
                    source_gap = None
        target = str(row.get("targets_segment_id") or "")
        prior_id = str(row.get("prior_segment_id") or "")
        prior_row = by_id.get(prior_id) or {}
        target_row = by_id.get(target) or {}
        evidence = {
            "line_id": row.get("line_id"),
            "line_category": row.get("line_category"),
            "target_excerpt": target_row.get("text"),
            "after_topic": target_row.get("topic"),
            "before_excerpt": row.get("before_excerpt") or prior_row.get("text"),
            "source_gap_ms": source_gap,
            "grounding_context": grounding_context,
            "strict_grounding": bool(grounding_context or target_row or prior_row),
        }
        evidence = enrich_evidence_from_run(ctx, evidence)
        orientation_purpose = (
            f"gap_repair[episode_preface:{lid}]"
            if is_episode_orientation(row)
            else f"gap_repair[{row.get('line_id') or target}]"
        )
        decision = guard_spoken_copy(
            str(row.get("text") or ""),
            evidence=evidence,
            required=required,
            purpose=orientation_purpose,
            seen_texts=seen_texts,
        )
        orig_text = str(row.get("text") or "").strip()
        new_text = str(decision.get("text") or "").strip()
        from interview_mux.spoken_meta_lint import is_hard_structure_violation

        hard_structure = any(
            is_hard_structure_violation(str(violation).split(":", 1)[0])
            for violation in (decision.get("violations") or [])
        )
        # Never replace a substantive episode orientation with a guard hinge,
        # but never keep metadata / structure / repeated-sentence violations.
        if (
            is_episode_orientation(row)
            and len(orig_text.split()) >= 6
            and decision.get("action") in {"fallback", "omit", "block"}
            and not hard_structure
        ):
            fixed = dict(row)
            guarded_lines.append(fixed)
            seen_texts.append(orig_text)
            applied.append(
                {
                    "action": "keep_orientation_despite_spoken_fallback",
                    "line_id": row.get("line_id"),
                    "violations": decision.get("violations"),
                    "guard_action": decision.get("action"),
                }
            )
            continue
        if (
            required
            and len(orig_text.split()) >= 6
            and len(new_text.split()) < 6
            and not hard_structure
        ):
            fixed = dict(row)
            guarded_lines.append(fixed)
            seen_texts.append(orig_text)
            applied.append(
                {
                    "action": "keep_orientation_despite_spoken_fallback",
                    "line_id": row.get("line_id"),
                    "violations": decision.get("violations"),
                    "guard_action": decision.get("action"),
                }
            )
            continue
        # Same for authoritative layups — fallback hinges destroy coverage QC.
        if (
            bool(out.get("nugget_layup_authority"))
            and str(row.get("origin") or "") == "nugget_layup"
            and orig_text
            and not hard_structure
            and (
                decision.get("action") in {"omit", "fallback"}
                or (
                    new_text
                    and new_text.lower() in {
                        "what changed after that?",
                        "what happened next?",
                        "what was at stake?",
                    }
                )
            )
        ):
            fixed = dict(row)
            guarded_lines.append(fixed)
            seen_texts.append(orig_text)
            applied.append(
                {
                    "action": "keep_layup_despite_spoken_fallback",
                    "line_id": row.get("line_id"),
                    "violations": decision.get("violations"),
                    "guard_action": decision.get("action"),
                }
            )
            continue
        if decision["action"] == "block":
            # Authoritative layups that still cannot speak cleanly must be
            # omitted rather than hard-stopping publish/recompose forever.
            if (
                bool(out.get("nugget_layup_authority"))
                and str(row.get("origin") or "") == "nugget_layup"
            ):
                applied.append(
                    {
                        "action": "omit_unspeakable_layup",
                        "line_id": row.get("line_id"),
                        "violations": decision["violations"],
                    }
                )
                continue
            lid_block = str(row.get("line_id") or "")
            # Empty / unspeakable deterministic seeds: omit + demote at repair end
            # instead of loud-fail thrash (exec_13157).
            if lid_block.startswith("vo_seed_") or not str(row.get("text") or "").strip():
                text_block = str(row.get("text") or "").strip()
                if lid_block.startswith(("vo_seed_", "vo_fill_")) and text_block:
                    fixed = dict(row)
                    guarded_lines.append(fixed)
                    seen_texts.append(text_block)
                    applied.append(
                        {
                            "action": "keep_high_gap_seed_despite_spoken_block",
                            "line_id": lid_block,
                            "violations": decision.get("violations"),
                        }
                    )
                    continue
                applied.append(
                    {
                        "action": "omit_unsafe_optional_vo",
                        "line_id": row.get("line_id"),
                        "violations": decision["violations"],
                    }
                )
                continue
            # Required non-layup: never ValueError thrash (exec_11630 #13).
            # Loud-fail pins compose/layup — never soft EDL.
            from interview_mux.loud_fail import raise_loud_failure

            pin_stage = (
                "nugget_layup_compose"
                if bool(out.get("nugget_layup_authority"))
                else "gap_framing_compose"
            )
            raise_loud_failure(
                ctx,
                f"required gap VO blocked by spoken_copy_guard "
                f"({row.get('line_id') or target}): "
                + ", ".join(decision["violations"]),
                stage=pin_stage,
                reason="spoken_copy_unhealable",
                detail={
                    "line_id": row.get("line_id"),
                    "violations": decision.get("violations"),
                    "guard_action": "block",
                },
            )
        if decision["action"] == "omit":
            if required:
                lid_omit = str(row.get("line_id") or "")
                text_omit = str(row.get("text") or "").strip()
                # Empty deterministic seeds may omit; non-empty seeds/fills must keep
                # (R1 cover-all-highs) — never drop a seeded high-gap line.
                if not text_omit and (
                    lid_omit.startswith("vo_seed_") or lid_omit.startswith("vo_fill_")
                ):
                    applied.append(
                        {
                            "action": "omit_unsafe_optional_vo",
                            "line_id": row.get("line_id"),
                            "violations": decision["violations"],
                        }
                    )
                    continue
                if lid_omit.startswith(("vo_seed_", "vo_fill_")) and text_omit:
                    fixed = dict(row)
                    guarded_lines.append(fixed)
                    seen_texts.append(text_omit)
                    applied.append(
                        {
                            "action": "keep_high_gap_seed_despite_spoken_omit",
                            "line_id": lid_omit,
                            "violations": decision.get("violations"),
                        }
                    )
                    continue
                if not text_omit:
                    applied.append(
                        {
                            "action": "omit_unsafe_optional_vo",
                            "line_id": row.get("line_id"),
                            "violations": decision["violations"],
                        }
                    )
                    continue
                from interview_mux.loud_fail import raise_loud_failure

                raise_loud_failure(
                    ctx,
                    f"required high-gap VO omitted after rewrite ({row.get('line_id')})",
                    stage="gap_framing_compose",
                    reason="high_gap_uncovered",
                    detail={"violations": decision.get("violations")},
                )
            # R8: heal forward cue / keep framing setup lines instead of silent omit.
            cat = str(row.get("line_category") or "").lower()
            keep_framing = (
                "preface" in cat
                or "cold_open" in cat
                or "context_setup" in cat
                or "story_bridge" in cat
                or is_episode_orientation(row)
                or str(row.get("line_id") or "").startswith(("vo_seed_", "vo_fill_"))
            )
            if keep_framing and str(row.get("text") or "").strip():
                try:
                    from interview_mux.gap_vo_prior_context import (
                        has_forward_cue,
                        repair_last_sentence_layup,
                    )
                    from interview_mux.gap_framing import word_limit_for_category

                    text_now = str(row.get("text") or "").strip()
                    if not has_forward_cue(text_now):
                        text_now = repair_last_sentence_layup(
                            text_now,
                            category=cat or "story_bridge",
                            max_words=max(1, int(word_limit_for_category(cat or "story_bridge"))),
                        )
                    fixed = dict(row)
                    fixed["text"] = text_now
                    guarded_lines.append(fixed)
                    seen_texts.append(text_now)
                    applied.append(
                        {
                            "action": "keep_framing_despite_spoken_omit",
                            "line_id": row.get("line_id"),
                            "violations": decision.get("violations"),
                        }
                    )
                    continue
                except Exception:
                    pass
            applied.append(
                {
                    "action": "omit_unsafe_optional_vo",
                    "line_id": row.get("line_id"),
                    "violations": decision["violations"],
                }
            )
            continue
        fixed = dict(row)
        fixed["text"] = decision["text"]
        fixed["spoken_copy_guard"] = {
            "action": decision["action"],
            "script_hash": decision["script_hash"],
            "context_hash": decision["context_hash"],
        }
        guarded_lines.append(fixed)
        seen_texts.append(str(decision["text"]))
    out["interviewer_lines"] = guarded_lines
    # Re-inject authoritative layups after spoken-copy omit — restore must be last
    # so a later guard cannot wipe recovery copy again.
    try:
        from interview_mux.nugget_layup import restore_layup_lines

        out, restored = restore_layup_lines(ctx, out)
        applied.extend(restored)
    except Exception:
        pass
    # Air-contract omit wins over EDL courtesy / spoken-copy rewrites. Without
    # this restamp, omitted_line_ids lose skip flags and required layups demand
    # WAVs → vo_synthesize thrash under soft freeze (exec_11165).
    try:
        from interview_mux.air_script import omitted_vo_line_ids, seated_vo_line_ids
        from interview_mux.mastering_plan_loader import load_plan_raw
        from interview_mux.vo_contract import mark_gap_line_not_on_air

        plan = (
            load_plan_raw(ctx)
            if ctx.artifact_exists("mastering/mastering_plan.json")
            else {}
        )
        omitted = omitted_vo_line_ids(plan)
        seated = seated_vo_line_ids(plan)
        lines = out.get("interviewer_lines")
        if isinstance(lines, list) and omitted:
            restamped: list[Any] = []
            for row in lines:
                if not isinstance(row, dict):
                    restamped.append(row)
                    continue
                lid = str(row.get("line_id") or "").strip()
                if (
                    lid
                    and lid in omitted
                    and lid not in seated
                    and not (
                        row.get("skipped_optional") and row.get("air_script_omit")
                    )
                ):
                    # Never restamp omit onto required / episode orientation —
                    # stale seats after false tier-D meta flip (exec_13181).
                    try:
                        from interview_mux.opening_orientation import (
                            is_episode_orientation,
                            orientation_omitted,
                        )

                        if is_episode_orientation(row) and not orientation_omitted(out):
                            restamped.append(row)
                            applied.append(
                                {
                                    "action": "skip_restamp_required_orientation",
                                    "line_id": lid,
                                }
                            )
                            continue
                    except Exception:
                        pass
                    # Don't restamp soft omit when it would drop hosted floor
                    # below need (exec_13181 context_seg_004 oscillation).
                    try:
                        from interview_mux.gap_fill_eligibility import (
                            hosted_framing_requires_synthetic_vo,
                            min_synthetic_vo_lines,
                        )
                        from interview_mux.vo_contract import omit_wins_skip_reason

                        if (
                            ctx is not None
                            and hosted_framing_requires_synthetic_vo(ctx)
                            and not omit_wins_skip_reason(row, gap_report=out)
                        ):
                            need = min_synthetic_vo_lines(ctx)
                            active_now = sum(
                                1
                                for ln in (out.get("interviewer_lines") or [])
                                if isinstance(ln, dict)
                                and str(ln.get("delivery") or "").lower()
                                == "synthesize"
                                and str(ln.get("text") or "").strip()
                                and not ln.get("skipped_optional")
                                and not ln.get("air_script_omit")
                            )
                            if active_now < need:
                                restamped.append(row)
                                applied.append(
                                    {
                                        "action": "skip_restamp_hosted_floor",
                                        "line_id": lid,
                                    }
                                )
                                continue
                    except Exception:
                        pass
                    row = mark_gap_line_not_on_air(
                        row,
                        reason_code="air_script_omit_sync",
                        ctx=ctx,
                        gap_report=out,
                        peer_lines=list(out.get("interviewer_lines") or []),
                    )
                    applied.append(
                        {"action": "restamp_air_contract_omit", "line_id": lid}
                    )
                restamped.append(row)
            out["interviewer_lines"] = restamped
    except Exception:
        pass
    # Spoken-copy omit can drop seed/fill lines after compose already resolved.
    # Reconcile the authoritative on-air seats after all repair omissions.
    try:
        from interview_mux.high_gap_vo import resolve_seats

        resolution = (
            resolve_seats(ctx, intent="repair", gap_report=out)
            if resolve_high_gap_seats
            else None
        )
        if resolution is not None and resolution.demoted:
            applied.append(
                {
                    "action": "demote_uncovered_high_after_repair",
                    "demoted": resolution.demoted,
                }
            )
    except Exception:
        pass
    for entry in applied:
        _append_repair_meta(out, entry)
    return out, applied


_COVERAGE_STOPWORDS = frozenset(
    {
        "about",
        "after",
        "because",
        "being",
        "from",
        "have",
        "into",
        "that",
        "their",
        "there",
        "these",
        "this",
        "those",
        "through",
        "using",
        "when",
        "which",
        "while",
        "with",
        "would",
        "could",
        "should",
        "mohan",
        "says",
        "said",
        "also",
        "than",
        "then",
        "them",
        "they",
        "were",
        "what",
        "your",
    }
)


def _coverage_tokens(text: str) -> set[str]:
    raw = re.findall(r"[a-z][a-z0-9']{3,}|[0-9]+(?:\.[0-9]+)?", str(text or "").lower())
    return {t for t in raw if t not in _COVERAGE_STOPWORDS}


def _alias_topic_to_brief(topic: str, brief_names: list[str]) -> str:
    src = _coverage_tokens(topic)
    if not src or not brief_names:
        return ""
    best = ""
    best_score = 0.0
    for name in brief_names:
        dst = _coverage_tokens(name)
        if not dst:
            continue
        score = len(src & dst) / max(1, len(src | dst))
        if score > best_score:
            best_score = score
            best = name
    return best if best_score >= 0.35 else ""


def _parent_stem_segment_id(sid: str) -> str:
    match = re.match(r"^(seg_\d+)[a-z]+$", str(sid or ""), re.I)
    return match.group(1) if match else ""


def _selected_air_texts(ctx: Any, sel_ids: list[str]) -> dict[str, str]:
    by_id: dict[str, dict[str, Any]] = {}
    if ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")
        for row in (manifest.get("segments") or []) if isinstance(manifest, dict) else []:
            if isinstance(row, dict) and row.get("segment_id"):
                by_id[str(row["segment_id"])] = row
    texts: dict[str, str] = {}
    for sid in sel_ids:
        row = by_id.get(sid) or {}
        text = str(row.get("text") or "").strip()
        if not text:
            parent = str(row.get("parent_id") or "") or _parent_stem_segment_id(sid)
            if parent and parent in by_id:
                text = str(by_id[parent].get("text") or "").strip()
        if not text:
            start = int(row.get("start_ms") or 0)
            end = int(row.get("end_ms") or 0)
            if end > start:
                text = str(segment_text_excerpt(ctx, start, end, max_chars=1200) or "").strip()
        texts[sid] = text
    return texts


def _best_matching_segments(
    query: str,
    texts: dict[str, str],
    *,
    min_hits: int = 2,
    cap: int = 4,
) -> list[str]:
    qtoks = _coverage_tokens(query)
    if not qtoks:
        return []
    scored: list[tuple[int, str]] = []
    for sid, text in texts.items():
        blob = str(text or "").lower()
        if not blob:
            continue
        hits = sum(1 for token in qtoks if token in blob)
        if hits >= min_hits:
            scored.append((hits, sid))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [sid for _, sid in scored[:cap]]


def _bind_coverage_to_selected_air(
    ctx: Any,
    out: dict[str, Any],
    applied: list[dict[str, Any]],
) -> None:
    """Map empty coverage rows onto selected-air transcripts.

    Talking-points coverage often ships with empty segment_ids (cuts lack
    talking_point_id) while the selected order still contains the cited
    evidence. Bind those rows instead of leaving coverage_score at 0.
    """
    if not ctx.artifact_exists("master/selection.json"):
        return
    sel = ctx.read_json("master/selection.json")
    sel_ids = (
        [str(x) for x in ((sel or {}).get("ordered_segment_ids") or []) if x]
        if isinstance(sel, dict)
        else []
    )
    if not sel_ids:
        return
    texts = _selected_air_texts(ctx, sel_ids)
    if not any(texts.values()):
        return
    sel_set = set(sel_ids)
    bound = 0

    def _mark_row(row: dict[str, Any], query: str, *, min_hits: int) -> bool:
        existing = [str(s) for s in (row.get("segment_ids") or []) if str(s) in sel_set]
        if existing:
            changed = existing != list(row.get("segment_ids") or []) or not row.get("covered")
            row["segment_ids"] = existing
            row["covered"] = True
            return changed
        hits = _best_matching_segments(query, texts, min_hits=min_hits)
        if not hits:
            return False
        row["segment_ids"] = hits
        row["covered"] = True
        return True

    for row in out.get("claim_mappings") or []:
        if not isinstance(row, dict):
            continue
        query = str(row.get("claim") or row.get("text") or "")
        if query and _mark_row(row, query, min_hits=2):
            bound += 1

    brief_names: list[str] = []
    if ctx.artifact_exists("understanding/content_brief.json"):
        brief = ctx.read_json("understanding/content_brief.json")
        for topic in (brief.get("topics") or []) if isinstance(brief, dict) else []:
            if isinstance(topic, dict) and topic.get("name"):
                name = str(topic["name"]).strip()
                if name and name not in brief_names:
                    brief_names.append(name)

    topic_rows = out.get("topic_mappings")
    if not isinstance(topic_rows, list):
        topic_rows = []
        out["topic_mappings"] = topic_rows
    by_topic = {
        str(row.get("topic") or row.get("name") or "").strip().lower(): row
        for row in topic_rows
        if isinstance(row, dict)
    }
    for name in brief_names:
        key = name.lower()
        row = by_topic.get(key)
        if row is None:
            row = {"topic": name, "segment_ids": [], "covered": False}
            topic_rows.append(row)
            by_topic[key] = row
        if _mark_row(row, name, min_hits=1):
            bound += 1

    if not bound:
        return
    applied.append({"action": "bind_coverage_to_selection", "count": bound})
    covered_topics = {
        str(row.get("topic") or "").strip().lower()
        for row in topic_rows
        if isinstance(row, dict) and row.get("covered") and (row.get("segment_ids") or [])
    }
    missing = out.get("missing_coverage")
    if isinstance(missing, list) and covered_topics:
        kept_missing: list[Any] = []
        for row in missing:
            if not isinstance(row, dict):
                kept_missing.append(row)
                continue
            label = str(row.get("topic") or row.get("item") or "").strip().lower()
            aliased = _alias_topic_to_brief(label, brief_names).lower() if label else ""
            if label in covered_topics or aliased in covered_topics:
                continue
            kept_missing.append(row)
        if len(kept_missing) != len(missing):
            out["missing_coverage"] = kept_missing
            applied.append(
                {
                    "action": "drop_missing_coverage_now_bound",
                    "count": len(missing) - len(kept_missing),
                }
            )
    mapped = {
        str(s)
        for key in ("topic_mappings", "claim_mappings")
        for row in (out.get(key) or [])
        if isinstance(row, dict)
        for s in (row.get("segment_ids") or [])
        if s
    }
    if mapped:
        out["orphan_segment_ids"] = [
            sid for sid in (out.get("orphan_segment_ids") or []) if str(sid) not in mapped
        ]
    covered_n = sum(
        1
        for row in topic_rows
        if isinstance(row, dict) and row.get("covered") and (row.get("segment_ids") or [])
    )
    if topic_rows:
        out["coverage_score"] = round(covered_n / max(1, len(topic_rows)), 4)


def repair_coverage_audit(ctx: Any, doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    out = copy.deepcopy(doc)
    applied: list[dict[str, Any]] = []
    manifest_ids, _ = _manifest_ids_and_tags(ctx)
    brief_names: list[str] = []
    brief_topics: set[str] = set()
    if ctx.artifact_exists("understanding/content_brief.json"):
        brief = ctx.read_json("understanding/content_brief.json")
        for t in (brief.get("topics") or []) if isinstance(brief, dict) else []:
            if isinstance(t, dict) and t.get("name"):
                name = str(t["name"]).strip()
                if name and name not in brief_names:
                    brief_names.append(name)
                brief_topics.add(name.lower())
    all_mapped: set[str] = set()
    for key in ("topic_mappings", "claim_mappings"):
        rows = out.get(key)
        if not isinstance(rows, list):
            continue
        kept_rows: list[dict[str, Any]] = []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            if key == "topic_mappings":
                topic = str(row.get("topic") or row.get("name") or "").lower()
                if brief_topics and topic and topic not in brief_topics:
                    aliased = _alias_topic_to_brief(topic, brief_names)
                    if aliased:
                        row["topic"] = aliased
                        applied.append(
                            {
                                "action": "alias_topic_mapping_to_brief",
                                "from": topic,
                                "to": aliased,
                            }
                        )
                    else:
                        applied.append({"action": "drop_orphan_ref", "topic": topic})
                        continue
            seg_ids = row.get("segment_ids")
            if isinstance(seg_ids, list) and manifest_ids:
                cleaned = _sanitize_topic_segment_ids(seg_ids, manifest_ids)
                if cleaned != seg_ids:
                    row["segment_ids"] = cleaned
                    applied.append({"action": "drop_orphan_ref", "path": f"{key}[{i}].segment_ids"})
                all_mapped.update(cleaned)
            elif isinstance(seg_ids, list):
                all_mapped.update(str(s) for s in seg_ids if s)
            kept_rows.append(row)
        out[key] = kept_rows
    if manifest_ids:
        orphans = sorted(manifest_ids - all_mapped)
        if orphans:
            out["orphan_segment_ids"] = orphans
            applied.append({"action": "compute_orphan_segment_ids", "count": len(orphans)})
        elif out.get("orphan_segment_ids"):
            out["orphan_segment_ids"] = []
            applied.append({"action": "clear_orphan_segment_ids"})
    missing = out.get("missing_coverage")
    if isinstance(missing, list):
        kept = []
        for row in missing:
            if not isinstance(row, dict):
                continue
            topic = str(row.get("topic") or row.get("name") or "").lower()
            if brief_topics and topic and topic not in brief_topics:
                applied.append({"action": "drop_orphan_ref", "topic": topic})
                continue
            kept.append(row)
        out["missing_coverage"] = kept
    # Narrative QC requires every brief topic either mapped with segment_ids or
    # documented in missing_coverage. LLMs often leave 1–2 topics uncovered.
    if brief_topics:
        mapped_with_segs: set[str] = set()
        for row in out.get("topic_mappings") or []:
            if not isinstance(row, dict):
                continue
            topic = str(row.get("topic") or row.get("name") or "").strip().lower()
            segs = row.get("segment_ids") or []
            if topic and isinstance(segs, list) and any(str(s).strip() for s in segs):
                mapped_with_segs.add(topic)
        missing_rows = out.get("missing_coverage")
        if not isinstance(missing_rows, list):
            missing_rows = []
            out["missing_coverage"] = missing_rows
        documented = {
            str(row.get("topic") or row.get("name") or "").strip().lower()
            for row in missing_rows
            if isinstance(row, dict)
        }
        brief_names: list[str] = []
        if ctx.artifact_exists("understanding/content_brief.json"):
            brief = ctx.read_json("understanding/content_brief.json")
            for t in (brief.get("topics") or []) if isinstance(brief, dict) else []:
                if isinstance(t, dict) and t.get("name"):
                    brief_names.append(str(t["name"]))
        for name in brief_names:
            key = name.lower()
            if key in mapped_with_segs or key in documented:
                continue
            missing_rows.append(
                {
                    "item": name,
                    "suggestion": (
                        "Documented as uncovered for narrative_qc; "
                        "prefer remapping in a later coverage refine if airtime allows."
                    ),
                    "topic": name,
                    "reason": "auto_documented_uncovered_brief_topic",
                    "severity": "low",
                }
            )
            documented.add(key)
            applied.append({"action": "seed_missing_coverage_from_brief_topic", "topic": name[:80]})
    # Ensure every content_brief claim has a claim_mappings row (narrative_qc exact-match).
    if ctx.artifact_exists("understanding/content_brief.json"):
        brief = ctx.read_json("understanding/content_brief.json")
        claim_rows = out.get("claim_mappings")
        if not isinstance(claim_rows, list):
            claim_rows = []
            out["claim_mappings"] = claim_rows
        mapped = {
            str(r.get("claim") or "").strip().casefold()
            for r in claim_rows
            if isinstance(r, dict) and r.get("claim")
        }
        brief_claims = []
        if isinstance(brief, dict):
            brief_claims.extend(brief.get("key_claims") or [])
            brief_claims.extend(brief.get("claims") or [])
        for claim in brief_claims:
            if not isinstance(claim, dict):
                continue
            text = str(claim.get("claim") or claim.get("text") or "").strip()
            if not text or text.casefold() in mapped:
                continue
            segs = claim.get("evidence_segment_ids") or claim.get("segment_ids") or []
            if not isinstance(segs, list):
                segs = []
            segs = [str(s) for s in segs if s]
            if manifest_ids:
                segs = [s for s in segs if s in manifest_ids]
            claim_rows.append(
                {
                    "claim": text,
                    "segment_ids": segs,
                    "covered": bool(segs),
                }
            )
            mapped.add(text.casefold())
            applied.append({"action": "seed_claim_mapping_from_brief", "claim": text[:80]})
    # Narrative QC: open coherence missing_callback topics must appear as
    # missing_coverage.item (or mapped with segment_ids). Generic
    # "coherence:{id}" rows do not match the topic-name check.
    try:
        from interview_mux.coherence.paths import COHERENCE_REPORT_PATH
        from interview_mux.narrative_qc import (
            _documented_excludes,
            _norm_name,
            _topic_mapping_index,
        )

        if ctx.artifact_exists(COHERENCE_REPORT_PATH):
            report = ctx.read_json(COHERENCE_REPORT_PATH)
            if (report.get("gate") or {}).get("activated"):
                missing_rows = out.get("missing_coverage")
                if not isinstance(missing_rows, list):
                    missing_rows = []
                    out["missing_coverage"] = missing_rows
                documented = _documented_excludes(missing_rows)
                by_topic = _topic_mapping_index(out.get("topic_mappings") or [])
                for risk in report.get("risks") or []:
                    if not isinstance(risk, dict):
                        continue
                    if risk.get("kind") != "missing_callback" or risk.get("status") == "resolved":
                        continue
                    topic = str(
                        (risk.get("evidence") or {}).get("topic") or risk.get("theme_id") or ""
                    ).strip()
                    if not topic:
                        continue
                    norm = _norm_name(topic)
                    mapping = by_topic.get(norm)
                    if mapping and (mapping.get("segment_ids") or []):
                        continue
                    if norm in documented:
                        continue
                    missing_rows.append(
                        {
                            "item": topic,
                            "topic": topic,
                            "suggestion": (
                                "Coherence missing_callback documented for narrative_qc."
                            ),
                            "reason": "coherence_missing_callback",
                            "severity": "low",
                        }
                    )
                    documented.add(norm)
                    applied.append(
                        {
                            "action": "seed_missing_coverage_from_coherence_callback",
                            "topic": topic[:80],
                        }
                    )
    except Exception:
        pass
    # Post-commit lint requires non-empty missing_coverage when coherence risks are open.
    if not out.get("missing_coverage"):
        try:
            from interview_mux.coherence import coherence_active
            from interview_mux.coherence.duration_gate import coherence_activated
            from interview_mux.coherence.paths import COHERENCE_REPORT_PATH

            if (
                coherence_active()
                and coherence_activated(ctx)
                and ctx.artifact_exists(COHERENCE_REPORT_PATH)
            ):
                report = ctx.read_json(COHERENCE_REPORT_PATH)
                open_risks = [
                    r
                    for r in (report.get("risks") or [])
                    if isinstance(r, dict) and r.get("status", "open") == "open"
                ]
                if open_risks:
                    seeded: list[dict[str, Any]] = []
                    for risk in open_risks[:12]:
                        kind = str(risk.get("kind") or "coherence_risk")
                        rid = str(risk.get("risk_id") or kind)
                        seeded.append(
                            {
                                "item": f"coherence:{rid}",
                                "suggestion": (
                                    f"Address open {kind} risk {rid} "
                                    f"(see understanding/coherence_report.json)."
                                ),
                            }
                        )
                    out["missing_coverage"] = seeded
                    applied.append(
                        {
                            "action": "seed_missing_coverage_from_coherence",
                            "count": len(seeded),
                        }
                    )
        except Exception:
            pass
    _bind_coverage_to_selected_air(ctx, out, applied)
    if out.get("coverage_score") is None and out.get("topics_covered") is not None:
        out["coverage_score"] = float(out.get("topics_covered") or 0)
        applied.append({"action": "default_value", "path": "coverage_score"})
    for entry in applied:
        _append_repair_meta(out, entry)
    return out, applied


def _content_brief_topic_segment_map(ctx: Any) -> list[tuple[str, list[str]]]:
    """Topic labels from content_brief with their segment_ids (manifest order preserved later)."""
    if not ctx.artifact_exists("understanding/content_brief.json"):
        return []
    brief = ctx.read_json("understanding/content_brief.json")
    rows: list[tuple[str, list[str]]] = []
    for topic in (brief.get("topics") or []) if isinstance(brief, dict) else []:
        if not isinstance(topic, dict):
            continue
        name = str(topic.get("name") or "").strip()
        seg_ids = topic.get("segment_ids") or []
        if name and isinstance(seg_ids, list) and seg_ids:
            rows.append((name, [str(s) for s in seg_ids if s]))
    return rows


def _manifest_segment_order(ctx: Any) -> list[str]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return []
    manifest = ctx.read_json("segments/manifest.json")
    return [
        str(row.get("segment_id"))
        for row in (manifest.get("segments") or [])
        if isinstance(row, dict) and row.get("segment_id")
    ]


def _sort_segment_ids_by_manifest(ids: list[str], manifest_order: list[str]) -> list[str]:
    if not manifest_order:
        return list(dict.fromkeys(ids))
    pos = {sid: idx for idx, sid in enumerate(manifest_order)}
    return sorted(dict.fromkeys(ids), key=lambda sid: pos.get(sid, 10**9))


def narrative_chapter_segment_ids(ctx: Any, chapter: dict[str, Any]) -> list[str]:
    """
    Effective segment_ids for a narrative_plan chapter.

    LLM output uses suggested_open_segment_id + topic_tags; lint/repair need segment_ids.
    Prefer explicit segment_ids when present; otherwise infer from topic evidence.
    """
    manifest_ids, tag_to_segments = _manifest_ids_and_tags(ctx)
    manifest_order = _manifest_segment_order(ctx)

    existing = chapter.get("segment_ids")
    if isinstance(existing, list) and existing:
        cleaned = _sanitize_topic_segment_ids(existing, manifest_ids)
        return _sort_segment_ids_by_manifest(cleaned, manifest_order)

    inferred: list[str] = []
    seen: set[str] = set()

    def _add(raw_ids: list[Any]) -> None:
        for sid in _sanitize_topic_segment_ids(raw_ids, manifest_ids):
            if sid not in seen:
                seen.add(sid)
                inferred.append(sid)

    for tag in chapter.get("topic_tags") or []:
        tag_s = str(tag or "").strip()
        if not tag_s:
            continue
        for topic_name, seg_ids in _content_brief_topic_segment_map(ctx):
            if _topic_name_matches_tag(topic_name, tag_s):
                _add(seg_ids)
        for key in (tag_s, tag_s.lower(), tag_s.replace(" ", "_")):
            _add(tag_to_segments.get(key, []))

    open_sid = str(
        chapter.get("suggested_open_segment_id")
        or chapter.get("anchor_segment_id")
        or chapter.get("opens_with_segment_id")
        or ""
    ).strip()
    if open_sid:
        _add([open_sid])

    return _sort_segment_ids_by_manifest(inferred, manifest_order)


def _fused_survivor_map(ctx: Any) -> dict[str, str]:
    """Retired segment id -> the live manifest row whose ``fused_from`` holds it."""
    out: dict[str, str] = {}
    try:
        if not ctx.artifact_exists("segments/manifest.json"):
            return out
        manifest = ctx.read_json("segments/manifest.json")
    except Exception:
        return out
    rows = (manifest or {}).get("segments") or [] if isinstance(manifest, dict) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        survivor = str(row.get("segment_id") or "")
        if not survivor:
            continue
        for old in row.get("fused_from") or []:
            token = str(old or "")
            if token and token != survivor:
                out.setdefault(token, survivor)
    return out


def repair_narrative_plan(ctx: Any, doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    out = copy.deepcopy(doc)
    applied: list[dict[str, Any]] = []
    manifest_ids, _ = _manifest_ids_and_tags(ctx)
    chapters = out.get("chapters")
    if isinstance(chapters, list) and manifest_ids:
        kept = []
        for ch in chapters:
            if not isinstance(ch, dict):
                continue
            seg_ids = narrative_chapter_segment_ids(ctx, ch)
            prior = ch.get("segment_ids")
            if seg_ids:
                if not isinstance(prior, list) or prior != seg_ids:
                    ch["segment_ids"] = seg_ids
                    if isinstance(prior, list) and prior:
                        if [s for s in prior if str(s) in manifest_ids] != seg_ids:
                            applied.append(
                                {
                                    "action": "drop_orphan_ref",
                                    "chapter_id": ch.get("chapter_id"),
                                }
                            )
                    else:
                        applied.append(
                            {
                                "action": "infer_segment_ids",
                                "chapter_id": ch.get("chapter_id"),
                                "count": len(seg_ids),
                            }
                        )
                kept.append(ch)
                continue
            if isinstance(prior, list) and prior:
                applied.append({"action": "drop_orphan_ref", "chapter_id": ch.get("chapter_id")})
            applied.append({"action": "drop_row", "chapter_id": ch.get("chapter_id")})
        out["chapters"] = kept
        if not kept and manifest_ids:
            # Never land empty chapters — rebuild single body chapter from manifest.
            order = sorted(manifest_ids)
            try:
                from interview_mux.talking_points_authority import synthesize_narrative_from_coverage

                salvaged = synthesize_narrative_from_coverage(ctx)
                if isinstance(salvaged, dict) and (salvaged.get("chapters") or []):
                    out["chapters"] = salvaged["chapters"]
                    if salvaged.get("arc_summary") and not out.get("arc_summary"):
                        out["arc_summary"] = salvaged["arc_summary"]
                    applied.append({"action": "rebuild_from_coverage_synthesize"})
                else:
                    out["chapters"] = [
                        {
                            "chapter_id": "ch_01_body",
                            "title": "Episode body",
                            "suggested_open_segment_id": order[0],
                            "segment_ids": order,
                        }
                    ]
                    applied.append({"action": "rebuild_single_chapter_from_manifest"})
            except Exception:
                out["chapters"] = [
                    {
                        "chapter_id": "ch_01_body",
                        "title": "Episode body",
                        "suggested_open_segment_id": order[0],
                        "segment_ids": order,
                    }
                ]
                applied.append({"action": "rebuild_single_chapter_from_manifest"})
    # Ordering constraints must name live segments. After connector fusion
    # and resplit the LLM still sees the ids the brief cited, and writes
    # constraints for segments that no longer exist; the pre-flush lint then
    # refuses the whole plan and the run halts (one-hour source, seg_052 and
    # seg_057 cited against a 26-row manifest, ISSUES 81). A retired id whose
    # tape lives on in a fused survivor is remapped to it; the rest are dropped.
    constraints = out.get("ordering_constraints")
    if isinstance(constraints, list) and manifest_ids:
        survivor_of = _fused_survivor_map(ctx)
        kept_c: list[Any] = []
        remapped = dropped = 0
        for row in constraints:
            if not isinstance(row, dict):
                continue
            row = dict(row)
            ok = True
            for keys in (
                ("before_segment_id", "before", "setup_segment_id"),
                ("after_segment_id", "after", "payoff_segment_id"),
            ):
                key = next((k for k in keys if row.get(k)), None)
                if not key:
                    continue
                sid = str(row.get(key) or "").strip()
                if sid in manifest_ids:
                    continue
                target = survivor_of.get(sid)
                if target and target in manifest_ids:
                    row[key] = target
                    remapped += 1
                else:
                    ok = False
                    break
            legacy = [str(x) for x in (row.get("segment_ids") or row.get("ordered_segment_ids") or []) if x]
            if ok and legacy and any(x not in manifest_ids for x in legacy):
                ok = False
            before_v = str(
                row.get("before_segment_id") or row.get("before") or row.get("setup_segment_id") or ""
            )
            after_v = str(
                row.get("after_segment_id") or row.get("after") or row.get("payoff_segment_id") or ""
            )
            if ok and before_v and after_v and before_v == after_v:
                ok = False  # remapped onto the same survivor: nothing to order
            if ok:
                kept_c.append(row)
            else:
                dropped += 1
        if remapped or dropped:
            out["ordering_constraints"] = kept_c
            applied.append(
                {
                    "action": "resolve_constraint_refs_to_manifest",
                    "remapped": remapped,
                    "dropped": dropped,
                }
            )
    # Clamp chapter count to delivery_brief budget max (pre-flush XV / lint).
    chapters_now = out.get("chapters")
    if isinstance(chapters_now, list) and chapters_now:
        max_chapters = 8
        try:
            if ctx.artifact_exists("understanding/delivery_brief.json"):
                brief = ctx.read_json("understanding/delivery_brief.json")
                budget = (brief or {}).get("chapter_budget") if isinstance(brief, dict) else {}
                if isinstance(budget, dict) and budget.get("max") is not None:
                    max_chapters = max(1, int(budget["max"]))
        except Exception:
            pass
        if len(chapters_now) > max_chapters:
            pos: dict[str, int] = {}
            try:
                if ctx.artifact_exists("segments/manifest.json"):
                    man = ctx.read_json("segments/manifest.json")
                    for i, s in enumerate((man or {}).get("segments") or []):
                        if isinstance(s, dict) and s.get("segment_id"):
                            pos[str(s["segment_id"])] = i
            except Exception:
                pass
            new_chapters = [dict(ch) for ch in chapters_now if isinstance(ch, dict)]
            while len(new_chapters) > max_chapters:
                best_i = 0
                best_cost = 10**9
                for i in range(len(new_chapters) - 1):
                    a = new_chapters[i].get("segment_ids") or []
                    b = new_chapters[i + 1].get("segment_ids") or []
                    cost = len(a) + len(b)
                    if i == 0 or i + 1 == len(new_chapters) - 1:
                        cost += 3
                    if cost < best_cost:
                        best_cost = cost
                        best_i = i
                left = dict(new_chapters[best_i])
                right = new_chapters[best_i + 1]
                left_ids = [str(s) for s in (left.get("segment_ids") or []) if s]
                right_ids = [str(s) for s in (right.get("segment_ids") or []) if s]
                combined = list(dict.fromkeys([*left_ids, *right_ids]))
                combined.sort(key=lambda sid: pos.get(sid, 10**9))
                left["segment_ids"] = combined
                if not str(left.get("title") or "").strip():
                    left["title"] = str(right.get("title") or "")
                new_chapters = [
                    *new_chapters[:best_i],
                    left,
                    *new_chapters[best_i + 2 :],
                ]
                applied.append(
                    {
                        "action": "merge_chapters_to_budget",
                        "max": max_chapters,
                        "merged_at": best_i,
                    }
                )
            out["chapters"] = new_chapters
    for entry in applied:
        _append_repair_meta(out, entry)
    return out, applied


def enrich_narrative_plan_for_persist(ctx: Any, doc: dict[str, Any]) -> dict[str, Any]:
    """Populate chapters[].segment_ids from inference before disk write."""
    out = copy.deepcopy(doc)
    chapters = out.get("chapters")
    if not isinstance(chapters, list):
        return out
    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        seg_ids = narrative_chapter_segment_ids(ctx, ch)
        if seg_ids:
            ch["segment_ids"] = seg_ids
    return out


def _rewrite_segment_id_list(ids: list[Any], parent: str, children: list[str]) -> list[str]:
    out: list[str] = []
    for raw in ids:
        s = str(raw)
        if s == parent:
            out.extend(children)
        elif s not in out:
            out.append(s)
    return out


def _brief_remap_permitted(ctx: Any) -> bool:
    """May the running stage rewrite content_brief.json for a segment-id remap?

    The remap is a courtesy to later readers, not this stage's output. Asking
    the ownership table first keeps a refused courtesy write from being logged
    as an authority denial, which after two occurrences halts the run
    (ISSUES 87: full_master_ranking under pre_soft_freeze).
    """
    try:
        from interview_mux.artifact_ownership import write_permitted
        from interview_mux.write_staging import active_stage_id

        stage = str(active_stage_id() or "").strip()
        ok, reason = write_permitted(
            ctx, "understanding/content_brief.json", stage or None, verb="persist"
        )
    except Exception:
        return True
    if ok:
        return True
    try:
        ctx.log(
            "segment-id remap skipped for understanding/content_brief.json: "
            f"{reason} (owner rewrites it on its next pass)",
            level="info",
            stage=stage or "artifact_repairs",
        )
    except Exception:
        pass
    return False


def propagate_nle_split_segment_refs(
    ctx: Any,
    parent_id: str,
    child_ids: list[str],
) -> list[str]:
    """
    Rewrite parent segment_id references to NLE split children in upstream artifacts.

    Returns human-readable paths updated.
    """
    if not parent_id or not child_ids:
        return []
    updated: list[str] = []

    if ctx.artifact_exists("understanding/content_brief.json") and _brief_remap_permitted(ctx):
        brief = ctx.read_json("understanding/content_brief.json")
        if isinstance(brief, dict):
            changed = False
            for topic in brief.get("topics") or []:
                if not isinstance(topic, dict):
                    continue
                seg_ids = topic.get("segment_ids")
                if isinstance(seg_ids, list) and parent_id in [str(x) for x in seg_ids]:
                    topic["segment_ids"] = _rewrite_segment_id_list(seg_ids, parent_id, child_ids)
                    changed = True
            for claim in brief.get("key_claims") or []:
                if not isinstance(claim, dict):
                    continue
                for key in ("segment_ids", "evidence_segment_ids"):
                    seg_ids = claim.get(key)
                    if isinstance(seg_ids, list) and parent_id in [str(x) for x in seg_ids]:
                        claim[key] = _rewrite_segment_id_list(seg_ids, parent_id, child_ids)
                        changed = True
            if changed:
                from interview_mux.shared_path_commit import commit_content_brief_doc

                # Segment-id remap after split — preserve producer claim.
                commit_content_brief_doc(
                    ctx,
                    brief,
                    claim_producer=False,
                    protect_sacred=True,
                    skip_handoff=True,
                )
                updated.append("understanding/content_brief.json")

    if ctx.artifact_exists("master/coverage_audit.json"):
        audit = ctx.read_json("master/coverage_audit.json")
        if isinstance(audit, dict):
            changed = False
            for key in ("topic_mappings", "claim_mappings"):
                for row in audit.get(key) or []:
                    if not isinstance(row, dict):
                        continue
                    seg_ids = row.get("segment_ids")
                    if isinstance(seg_ids, list) and parent_id in [str(x) for x in seg_ids]:
                        row["segment_ids"] = _rewrite_segment_id_list(seg_ids, parent_id, child_ids)
                        changed = True
            if changed:
                repaired, _ = repair_coverage_audit(ctx, audit)
                ctx.write_json("master/coverage_audit.json", repaired, skip_handoff=True)
                updated.append("master/coverage_audit.json")

    if ctx.artifact_exists("master/narrative_plan.json"):
        plan = ctx.read_json("master/narrative_plan.json")
        if isinstance(plan, dict):
            changed = False
            for ch in plan.get("chapters") or []:
                if not isinstance(ch, dict):
                    continue
                for key in ("segment_ids", "suggested_open_segment_id"):
                    val = ch.get(key)
                    if key == "segment_ids" and isinstance(val, list):
                        if parent_id in [str(x) for x in val]:
                            ch["segment_ids"] = _rewrite_segment_id_list(val, parent_id, child_ids)
                            changed = True
                    elif key == "suggested_open_segment_id" and str(val or "") == parent_id:
                        ch["suggested_open_segment_id"] = child_ids[0]
                        changed = True
            for constraint in plan.get("ordering_constraints") or []:
                if not isinstance(constraint, dict):
                    continue
                for edge_key in ("before_segment_id", "after_segment_id"):
                    if str(constraint.get(edge_key) or "") == parent_id:
                        constraint[edge_key] = child_ids[0]
                        changed = True
            if changed:
                enriched = enrich_narrative_plan_for_persist(ctx, plan)
                ctx.write_json("master/narrative_plan.json", enriched, skip_handoff=True)
                updated.append("master/narrative_plan.json")

    if ctx.artifact_exists("master/selection.json"):
        sel = ctx.read_json("master/selection.json")
        if isinstance(sel, dict):
            changed = False
            ordered = sel.get("ordered_segment_ids")
            if isinstance(ordered, list) and parent_id in [str(x) for x in ordered]:
                sel["ordered_segment_ids"] = _rewrite_segment_id_list(ordered, parent_id, child_ids)
                changed = True
            for ch in sel.get("chapters") or []:
                if not isinstance(ch, dict):
                    continue
                segs = ch.get("segment_ids")
                if isinstance(segs, list) and parent_id in [str(x) for x in segs]:
                    ch["segment_ids"] = _rewrite_segment_id_list(segs, parent_id, child_ids)
                    changed = True
            if changed:
                ctx.write_json("master/selection.json", sel, skip_handoff=True)
                updated.append("master/selection.json")

    if ctx.artifact_exists("master/transitions.json"):
        tr = ctx.read_json("master/transitions.json")
        if isinstance(tr, dict):
            changed = False
            for row in tr.get("transitions") or []:
                if not isinstance(row, dict):
                    continue
                for key in ("after_segment_id", "before_segment_id"):
                    if str(row.get(key) or "") == parent_id:
                        row[key] = child_ids[0]
                        changed = True
            if changed:
                ctx.write_json("master/transitions.json", tr, skip_handoff=True)
                updated.append("master/transitions.json")

    if ctx.artifact_exists("understanding/gap_report.json"):
        gap = ctx.read_json("understanding/gap_report.json")
        if isinstance(gap, dict):
            changed = False
            for ln in gap.get("interviewer_lines") or []:
                if not isinstance(ln, dict):
                    continue
                if str(ln.get("targets_segment_id") or "") == parent_id:
                    ln["targets_segment_id"] = child_ids[0]
                    changed = True
                for key in ("supports_segment_ids", "replaces_source_segments"):
                    val = ln.get(key)
                    if isinstance(val, list) and parent_id in [str(x) for x in val]:
                        ln[key] = _rewrite_segment_id_list(val, parent_id, child_ids)
                        changed = True
            if changed:
                ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)
                updated.append("understanding/gap_report.json")

    if ctx.artifact_exists("understanding/gap_evaluations.json"):
        ge = ctx.read_json("understanding/gap_evaluations.json")
        if isinstance(ge, dict):
            changed = False
            for row in ge.get("evaluations") or []:
                if not isinstance(row, dict):
                    continue
                if str(row.get("segment_id") or "") == parent_id:
                    row["segment_id"] = child_ids[0]
                    changed = True
            if changed:
                ctx.write_json("understanding/gap_evaluations.json", ge, skip_handoff=True)
                updated.append("understanding/gap_evaluations.json")

    return updated


def _normalize_audit_issue_row(row: dict[str, Any], applied: list[dict[str, Any]]) -> dict[str, Any]:
    fixed = dict(row)
    evidence = fixed.get("evidence")
    if evidence is None or not isinstance(evidence, list):
        fixed["evidence"] = []
        applied.append({"action": "default_value", "path": "evidence"})
    if not str(fixed.get("recommended_action") or "").strip():
        fixed["recommended_action"] = "review"
        applied.append({"action": "default_value", "path": "recommended_action"})
    return fixed


def repair_edl_audit(ctx: Any, doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    out = copy.deepcopy(doc)
    applied: list[dict[str, Any]] = []
    # Selection is air-order authority — keep narrative chapters aligned before
    # judging audit complaints about "missing" early-act material.
    try:
        align_notes = align_narrative_plan_to_selection(ctx)
        applied.extend(align_notes)
    except Exception:
        pass
    manifest_ids, _ = _manifest_ids_and_tags(ctx)
    verdict = str(out.get("verdict") or "")
    if verdict and verdict not in ("pass", "warn", "fail"):
        out["verdict"] = "warn"
        applied.append({"action": "infer_enum", "path": "verdict", "value": "warn"})
    issues = out.get("issues")
    if isinstance(issues, list) and manifest_ids:
        kept = []
        for row in issues:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("segment_id") or "")
            if sid and sid not in manifest_ids:
                applied.append({"action": "drop_orphan_ref", "segment_id": sid})
                continue
            kept.append(row)
        out["issues"] = kept
    for key in ("blocking_issues", "warnings"):
        rows = out.get(key)
        if not isinstance(rows, list):
            continue
        out[key] = [
            _normalize_audit_issue_row(row, applied) if isinstance(row, dict) else row
            for row in rows
        ]
    from interview_mux.gates import audit_issue_covers_optional_vo_gap
    from interview_mux.v2.config import v2_g1_optional

    blocking = out.get("blocking_issues")
    if isinstance(blocking, list) and v2_g1_optional():
        kept_blocking: list[dict[str, Any]] = []
        demoted: list[dict[str, Any]] = []
        for row in blocking:
            if isinstance(row, dict) and audit_issue_covers_optional_vo_gap(ctx, row):
                demoted.append(row)
                continue
            if isinstance(row, dict):
                kept_blocking.append(row)
        if demoted:
            warnings = [
                dict(row)
                for row in (out.get("warnings") or [])
                if isinstance(row, dict)
            ]
            for row in demoted:
                warning = dict(row)
                warning.setdefault(
                    "issue",
                    warning.get("issue") or "VO gap skipped (G1 optional)",
                )
                warnings.append(warning)
            out["warnings"] = warnings
            out["blocking_issues"] = kept_blocking
            applied.append(
                {"action": "demote_optional_vo_blocking", "count": len(demoted)}
            )
            blocking = kept_blocking

    # Demote pre-EDL "VO-ingest / NLE placement" fails when pickup WAVs already exist.
    # edl_narrative_audit runs before edl; empty nle_edits is expected until then.
    if isinstance(blocking, list) and blocking:
        kept_blocking = []
        demoted_vo: list[dict[str, Any]] = []
        for row in blocking:
            if isinstance(row, dict) and _edl_issue_premature_vo_nle_placement(ctx, row):
                demoted_vo.append(row)
                continue
            if isinstance(row, dict):
                kept_blocking.append(row)
        if demoted_vo:
            warnings = [
                dict(row)
                for row in (out.get("warnings") or [])
                if isinstance(row, dict)
            ]
            for row in demoted_vo:
                warning = dict(row)
                warning["issue"] = (
                    str(warning.get("issue") or "vo_placement")
                    + " (demoted: vo_pickup WAVs present; NLE placement is edl's job)"
                )
                warnings.append(warning)
            out["warnings"] = warnings
            out["blocking_issues"] = kept_blocking
            applied.append(
                {
                    "action": "demote_premature_vo_nle_placement",
                    "count": len(demoted_vo),
                }
            )
            blocking = kept_blocking

    # Demote "restore excluded / expand ranking" false fails. Creative packs may
    # intentionally drop early-act chapters; selection exclusions are authoritative.
    if isinstance(blocking, list) and blocking:
        kept_blocking = []
        demoted_sel: list[dict[str, Any]] = []
        for row in blocking:
            if isinstance(row, dict) and _edl_issue_demands_restore_excluded(row):
                demoted_sel.append(row)
                continue
            if isinstance(row, dict):
                kept_blocking.append(row)
        if demoted_sel:
            warnings = [
                dict(row)
                for row in (out.get("warnings") or [])
                if isinstance(row, dict)
            ]
            for row in demoted_sel:
                warning = dict(row)
                warning["issue"] = (
                    str(warning.get("issue") or "selection_exclusion")
                    + " (demoted: selection is air-order authority)"
                )
                warnings.append(warning)
            out["warnings"] = warnings
            out["blocking_issues"] = kept_blocking
            applied.append(
                {
                    "action": "demote_restore_excluded_blocking",
                    "count": len(demoted_sel),
                }
            )
            blocking = kept_blocking

    # Demote LLM complaints already falsified by current gap/transitions/VO.
    if isinstance(blocking, list) and blocking:
        kept_blocking = []
        demoted_stale: list[dict[str, Any]] = []
        for row in blocking:
            if isinstance(row, dict) and _edl_issue_contradicted_by_disk(ctx, row):
                demoted_stale.append(row)
                continue
            if isinstance(row, dict):
                kept_blocking.append(row)
        if demoted_stale:
            warnings = [
                dict(row)
                for row in (out.get("warnings") or [])
                if isinstance(row, dict)
            ]
            for row in demoted_stale:
                warning = dict(row)
                warning["issue"] = (
                    str(warning.get("issue") or "stale_audit")
                    + " (demoted: current artifacts contradict this complaint)"
                )
                warnings.append(warning)
            out["warnings"] = warnings
            out["blocking_issues"] = kept_blocking
            applied.append(
                {
                    "action": "demote_stale_audit_vs_disk",
                    "count": len(demoted_stale),
                }
            )
            blocking = kept_blocking

    # Selection frozen after VO: complaints whose only remedy is a re-rank can
    # never be acted on (the seat freeze refuses the rewrite), so blocking on
    # them stops the run for good (exec_055, ISSUES entry 70). Record them as
    # warnings for the operator instead.
    blocking = out.get("blocking_issues")
    if isinstance(blocking, list) and blocking and _order_frozen(ctx):
        kept_blocking = []
        demoted_frozen: list[dict[str, Any]] = []
        for row in blocking:
            if isinstance(row, dict) and _issue_needs_rerank(row):
                demoted_frozen.append(row)
            else:
                kept_blocking.append(row)
        if demoted_frozen:
            warnings = [dict(r) for r in (out.get("warnings") or []) if isinstance(r, dict)]
            for row in demoted_frozen:
                warning = dict(row)
                warning["issue"] = (
                    str(warning.get("issue") or "order")
                    + " (demoted: selection frozen after VO; needs operator re-rank)"
                )
                warnings.append(warning)
            out["warnings"] = warnings
            out["blocking_issues"] = kept_blocking
            applied.append({"action": "demote_rerank_under_freeze", "count": len(demoted_frozen)})

    if out.get("blocking_issues"):
        out["verdict"] = "fail"
    elif str(out.get("verdict") or "").lower() == "fail":
        out["verdict"] = "warn" if out.get("warnings") else "pass"
        applied.append({"action": "upgrade_verdict", "value": out["verdict"]})
    for entry in applied:
        _append_repair_meta(out, entry)
    return out, applied


def _edl_issue_demands_restore_excluded(row: dict[str, Any]) -> bool:
    if str(row.get("code") or "").strip().lower() == "selection_excluded_intentional":
        return True
    text = " ".join(
        str(x)
        for x in (
            row.get("issue"),
            row.get("detail"),
            row.get("recommended_action"),
            " ".join(str(e) for e in (row.get("evidence") or [])),
        )
        if x
    ).lower()
    restore_markers = (
        "zero segments in selection",
        "restore representative",
        "reinstate the constrained",
        "redo full_master_ranking",
        "revisit selection to align with narrative_plan",
        "were excluded",
        "excluded_segment_ids",
        "only act-",
        "wiping out the set-up",
        "source segments were dropped",
    )
    return any(m in text for m in restore_markers)


def _edl_issue_premature_vo_nle_placement(ctx: Any, row: dict[str, Any]) -> bool:
    """True when audit blocks on missing NLE/EDL VO placement but pickup WAVs exist.

    ``edl_narrative_audit`` runs before ``edl``; empty ``nle_edits`` / no timeline
    VO clips is expected. Required lines are covered once ``vo_pickup/*.wav`` exist
    (full speech-QA resolve is ``edl`` / ``vo_ingest`` work).
    """
    code = str(row.get("code") or "").strip().lower()
    text = " ".join(
        str(x)
        for x in (
            row.get("issue"),
            row.get("detail"),
            row.get("recommended_action"),
            " ".join(str(e) for e in (row.get("evidence") or [])),
        )
        if x
    ).lower()
    placement_markers = (
        "vo-ingest",
        "vo_ingest",
        "nle placement",
        "nle_edits",
        "no evidenced vo",
        "evidenced vo-ingest",
    )
    if code != "pre_edl_vo_placement_missing" and not any(
        m in text for m in placement_markers
    ):
        return False
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return False

    def _wav_exists(line: dict[str, Any]) -> bool:
        pickup = ctx.final_path("vo_pickup")
        lid = str(line.get("line_id") or "")
        seg = str(line.get("targets_segment_id") or "")
        for base in (
            pickup / "matched",
            pickup / "synthesized",
            pickup / "clean",
            pickup / "normalized",
            pickup,
        ):
            for key in (lid, seg):
                if key and (base / f"{key}.wav").is_file():
                    return True
        return False

    report = ctx.read_json("understanding/gap_report.json")
    lines = [
        ln
        for ln in (report.get("interviewer_lines") or [])
        if isinstance(ln, dict)
        and bool(ln.get("required"))
        and str(ln.get("severity") or "").lower() == "high"
        and str(ln.get("delivery") or "").lower() in {"record", "synthesize", ""}
        and not ln.get("skipped_optional")
    ]
    if not lines:
        cited = {
            m.group(0)
            for m in __import__("re").finditer(r"vo_[a-z0-9_]+", text)
        }
        lines = [
            ln
            for ln in (report.get("interviewer_lines") or [])
            if isinstance(ln, dict)
            and str(ln.get("line_id") or "") in cited
        ]
    if not lines:
        return False
    return all(_wav_exists(ln) for ln in lines)


def _cited_transition_pairs(row: dict[str, Any]) -> list[tuple[str, str]]:
    """Extract after→before pairs from audit evidence / prose."""
    import re

    blob = " ".join(
        str(x)
        for x in (
            row.get("issue"),
            row.get("detail"),
            row.get("recommended_action"),
            " ".join(str(e) for e in (row.get("evidence") or [])),
        )
        if x
    )
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in re.finditer(
        r"after_segment_id\s*=\s*(seg_\d+)\s*,\s*before_segment_id\s*=\s*(seg_\d+)",
        blob,
        flags=re.IGNORECASE,
    ):
        pair = (match.group(1), match.group(2))
        if pair not in seen:
            seen.add(pair)
            pairs.append(pair)
    for match in re.finditer(
        r"(seg_\d+)\s*(?:→|->|to)\s*(seg_\d+)",
        blob,
        flags=re.IGNORECASE,
    ):
        pair = (match.group(1), match.group(2))
        if pair not in seen:
            seen.add(pair)
            pairs.append(pair)
    for match in re.finditer(
        r"prior_segment_id\s*=\s*(seg_\d+).*?targets_segment_id\s*=\s*(seg_\d+)",
        blob,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        pair = (match.group(1), match.group(2))
        if pair not in seen:
            seen.add(pair)
            pairs.append(pair)
    return pairs


def _adjacency_has_vo_and_transition(
    ctx: Any,
    after: str,
    before: str,
    *,
    gap: dict[str, Any] | None,
    transitions: dict[str, Any] | None,
) -> bool:
    """True only when both a covering gap VO and a spoken transition remain."""
    from interview_mux.gap_framing import (
        _gap_line_covers_seam,
        _transition_item_for_pair,
    )

    has_transition = _transition_item_for_pair(transitions, after, before) is not None
    if not has_transition:
        return False
    if not isinstance(gap, dict):
        return False
    seated_ids: set[str] = set()
    omitted_ids: set[str] = set()
    try:
        from interview_mux.gap_framing import _air_script_seat_sets

        seated_ids, omitted_ids = _air_script_seat_sets(ctx=ctx, plan=None)
    except Exception:
        seated_ids, omitted_ids = set(), set()
    for line in gap.get("interviewer_lines") or []:
        if _gap_line_covers_seam(
            line,
            after,
            before,
            seated_ids=seated_ids,
            omitted_ids=omitted_ids,
        ):
            return True
    return False


def _duplicate_vo_transition_resolved(ctx: Any, row: dict[str, Any]) -> bool:
    """True when cited (or all selected) adjacencies no longer dual-occupy."""
    gap = (
        ctx.read_json("understanding/gap_report.json")
        if ctx.artifact_exists("understanding/gap_report.json")
        else {}
    )
    transitions = (
        ctx.read_json("master/transitions.json")
        if ctx.artifact_exists("master/transitions.json")
        else {"transitions": []}
    )
    if not isinstance(gap, dict):
        gap = {}
    if not isinstance(transitions, dict):
        transitions = {"transitions": []}
    pairs = _cited_transition_pairs(row)
    if not pairs and ctx.artifact_exists("master/selection.json"):
        sel = ctx.read_json("master/selection.json")
        ordered = [
            str(x)
            for x in ((sel or {}).get("ordered_segment_ids") or [])
            if x
        ]
        pairs = list(zip(ordered, ordered[1:]))
    if not pairs:
        # No adjacency to check — treat as unresolved so we do not soft-pass.
        return False
    return not any(
        _adjacency_has_vo_and_transition(
            ctx, after, before, gap=gap, transitions=transitions
        )
        for after, before in pairs
    )


_RERANK_RE = re.compile(
    r"\b(re-?run|redo) full_master_ranking\b|\bre-?rank\b|\breorder the selection\b",
    flags=re.IGNORECASE,
)


def _issue_needs_rerank(row: dict[str, Any]) -> bool:
    """True when the audit's own remedy for this issue is a selection re-rank."""
    text = " ".join(
        str(x) for x in (row.get("recommended_action"), row.get("issue")) if x
    )
    return bool(_RERANK_RE.search(text))


def _order_frozen(ctx: Any) -> bool:
    try:
        from interview_mux.seat_authority import hard_freeze_active

        return bool(hard_freeze_active(ctx))
    except Exception:
        return False


def _ordering_constraints_satisfied(ctx: Any) -> bool:
    """True when every committed narrative ordering constraint holds on air.

    A constraint naming a segment that is not on air is vacuous. False when
    the plan or the selection is missing, so nothing is demoted on guesswork.
    """
    if not (
        ctx.artifact_exists("master/narrative_plan.json")
        and ctx.artifact_exists("master/selection.json")
    ):
        return False
    plan = ctx.read_json("master/narrative_plan.json")
    sel = ctx.read_json("master/selection.json")
    if not isinstance(plan, dict) or not isinstance(sel, dict):
        return False
    ordered = [str(x) for x in (sel.get("ordered_segment_ids") or []) if x]
    if not ordered:
        return False
    pos = {sid: i for i, sid in enumerate(ordered)}
    for row in plan.get("ordering_constraints") or []:
        if not isinstance(row, dict):
            continue
        before = str(row.get("before_segment_id") or "")
        after = str(row.get("after_segment_id") or "")
        if before in pos and after in pos and pos[before] >= pos[after]:
            return False
    return True


def _deferred_pair_keys(ctx: Any) -> set[tuple[str, str]]:
    """Deferred transition pairs with spoken text (synthesized at mix last-chance)."""
    if not ctx.artifact_exists("master/transitions.json"):
        return set()
    try:
        doc = ctx.read_json("master/transitions.json")
    except Exception:
        return set()
    out: set[tuple[str, str]] = set()
    for tr in (doc or {}).get("deferred_transition_pairs") or [] if isinstance(doc, dict) else []:
        if not isinstance(tr, dict):
            continue
        a = str(tr.get("after_segment_id") or "")
        b = str(tr.get("before_segment_id") or "")
        if a and b and str(tr.get("text") or tr.get("spoken_text") or "").strip():
            out.add((a, b))
    return out


def _edl_issue_contradicted_by_disk(ctx: Any, row: dict[str, Any]) -> bool:
    """True when the audit issue no longer matches current gap/transitions/VO."""
    code = str(row.get("code") or "").strip().lower()
    # A deferred transition pair is by design synthesized at mix last-chance,
    # after this audit runs. "transition missing" for such a pair is premature,
    # the same shape as the VO-placement demotion (exec_055 seg_037->seg_041,
    # ISSUES entry 71).
    if code == "transition_missing":
        import re as _re

        blob = " ".join(
            str(x)
            for x in (
                row.get("issue"),
                row.get("recommended_action"),
                " ".join(str(e) for e in (row.get("evidence") or [])),
            )
            if x
        )
        ids = _re.findall(r"seg_[0-9]+[a-z]*", blob)
        deferred = _deferred_pair_keys(ctx)
        if deferred and any((ids[i], ids[i + 1]) in deferred for i in range(len(ids) - 1)):
            return True
    if code == "duplicate_spoken_seam" and ctx.artifact_exists(
        "master/seam_occupancy.json"
    ):
        occupancy = ctx.read_json("master/seam_occupancy.json")
        if isinstance(occupancy, dict) and occupancy.get("clean") is True:
            return True
    text = " ".join(
        str(x)
        for x in (
            row.get("issue"),
            row.get("detail"),
            row.get("recommended_action"),
            " ".join(str(e) for e in (row.get("evidence") or [])),
        )
        if x
    ).lower()
    # Chapter membership filled after LLM audit (exec_13198 seg_012/028).
    if code == "chapter_continuity_broken" or any(
        needle in text
        for needle in (
            "not assigned to any selection chapter",
            "breaks the chapter map",
            "chapter map discontinuous",
            "omitted from its membership",
        )
    ):
        if ctx.artifact_exists("master/selection.json"):
            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict):
                try:
                    from interview_mux.media_ip_cta import on_air_orphaned_cta_scrap_ids

                    # Filling chapters does not hide leftover CTA children (exec_002).
                    if on_air_orphaned_cta_scrap_ids(ctx, sel):
                        return False
                except Exception:
                    pass
                ordered = [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]
                owned: set[str] = set()
                for ch in sel.get("chapters") or []:
                    if not isinstance(ch, dict):
                        continue
                    owned.update(str(x) for x in (ch.get("segment_ids") or []) if x)
                if ordered and all(sid in owned for sid in ordered):
                    return True
    # Ordering complaints are checked against the plan actually on disk. The
    # audit runs after align_narrative_plan_to_selection rewrote the plan's
    # constraints to the air order, so a complaint about the constraints the
    # ranking was shown (cyclic, from the narrative_arc_plan model) is stale
    # once every committed constraint holds (exec_049, ISSUES entry 48).
    if code == "ordering_constraint_broken" or (
        "ordering constraint" in text or "ordering_constraint" in text
    ):
        if _ordering_constraints_satisfied(ctx):
            return True
    # Blank scraps kept by hard-keep stay on-air by policy (exec_13198 seg_028).
    if code == "blank_segment" or (
        "blank" in text and "segment" in text and ("drop" in text or "backchannel" in text)
    ):
        if ctx.artifact_exists("master/selection.json"):
            import re

            sel = ctx.read_json("master/selection.json")
            ordered = {
                str(s)
                for s in ((sel or {}).get("ordered_segment_ids") or [])
                if s
            } if isinstance(sel, dict) else set()
            mentioned = set(re.findall(r"seg_\d+", text))
            sid = str(row.get("segment_id") or "").strip()
            if sid:
                mentioned.add(sid)
            on_air = (mentioned & ordered) if mentioned else set()
            if on_air:
                try:
                    from interview_mux.hard_keep import hard_keep_segment_ids

                    hard = {str(s) for s in (hard_keep_segment_ids(ctx) or []) if s}
                except Exception:
                    hard = set()
                if on_air <= hard:
                    return True
    if code == "opening_orientation_invalid" or any(
        needle in text
        for needle in (
            "meta-question",
            "opening-orientation",
            "episode framing",
            "vo_preface_episode_orientation",
        )
    ):
        if ctx.artifact_exists("understanding/gap_report.json"):
            from interview_mux.opening_orientation import (
                is_episode_orientation,
                orientation_copy_unusable,
            )

            gap = ctx.read_json("understanding/gap_report.json")
            for line in (gap.get("interviewer_lines") or []) if isinstance(gap, dict) else []:
                if isinstance(line, dict) and is_episode_orientation(line):
                    return not orientation_copy_unusable(str(line.get("text") or ""))
    if (
        code == "duplicate_spoken_seam"
        or any(
            needle in text
            for needle in (
                "identical selected-order",
                "competing spoken",
                "two different transition",
                "three entries after_segment",
                "three competing",
            )
        )
    ) and ctx.artifact_exists("master/transitions.json"):
        from collections import Counter

        tr = ctx.read_json("master/transitions.json")
        pairs: list[tuple[str, str]] = []
        for item in (tr.get("transitions") or []) if isinstance(tr, dict) else []:
            if not isinstance(item, dict):
                continue
            pairs.append(
                (
                    str(item.get("after_segment_id") or ""),
                    str(item.get("before_segment_id") or ""),
                )
            )
        counts = Counter(pairs)
        return bool(pairs) and all(c == 1 for c in counts.values())
    # LLM often re-asserts VO+transition duplicate after framing dedupe already
    # dropped the transition (exec_13157 Chapter 3→4 / seg_023→seg_025).
    if code == "duplicate_spoken_seam" or any(
        needle in text
        for needle in (
            "two spoken bridges",
            "duplicate framing",
            "same selected adjacency",
            "duplicate vo + transition",
            "duplicate vo and transition",
        )
    ):
        return _duplicate_vo_transition_resolved(ctx, row)
    if (
        code == "transition_adjacency_invalid"
        or any(
            needle in text
            for needle in (
                "not adjacent",
                "selected-order adjacenc",
                "do not match selected-order",
            )
        )
    ) and ctx.artifact_exists("master/transitions.json"):
        from interview_mux.artifact_cross_validate import _transitions_match_selection_order

        return _transitions_match_selection_order(ctx)
    if any(
        needle in text
        for needle in (
            "zero coverage",
            "uncovered claim",
            "coverage audit reports",
            "empty chapter",
            "outside selection",
            "outside declared chapter",
            "retained timeline material outside",
        )
    ):
        sel_ids: set[str] = set()
        if ctx.artifact_exists("master/selection.json"):
            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict):
                sel_ids = {
                    str(x) for x in (sel.get("ordered_segment_ids") or []) if x
                }
                chapters = sel.get("chapters") or []
                if chapters and all(
                    isinstance(ch, dict) and (ch.get("segment_ids") or [])
                    for ch in chapters
                ):
                    if "empty chapter" in text or "outside" in text:
                        return True
        if "coverage" in text or "uncovered claim" in text:
            if ctx.artifact_exists("master/coverage_audit.json") and sel_ids:
                cov = ctx.read_json("master/coverage_audit.json")
                if isinstance(cov, dict):
                    for key in ("topic_mappings", "claim_mappings"):
                        for row in cov.get(key) or []:
                            if not isinstance(row, dict) or not row.get("covered"):
                                continue
                            mapped = {
                                str(s) for s in (row.get("segment_ids") or []) if s
                            }
                            if mapped & sel_ids:
                                return True
    return False


def _persist_soundscape_policy(ctx: Any, policy: dict[str, Any]) -> None:
    """Commit soundscape policy even when another stage owns the write staging root.

    ``sound_design_plan`` only flushes ``understanding/sound_design_plan.json``.
    Cue-slot injections written via ``ctx.write_json`` would otherwise stay in
    ``.pending_writes/`` and never reach post-commit validation.

    Ownership ALLOW is ``soundscape_policy_build`` only — pass that stage_key so
    soft-freeze assert_write does not AuthorityDeny the slot inject
    (exec_13167: theme_underscore cue_slots heal spin).
    """
    try:
        from interview_mux.write_staging import write_committed_json

        write_committed_json(
            ctx,
            "understanding/soundscape_policy.json",
            policy,
            stage_key="soundscape_policy_build",
        )
        return
    except Exception:
        pass
    try:
        ctx.write_json(
            "understanding/soundscape_policy.json",
            policy,
            stage_key="soundscape_policy_build",
        )
    except Exception:
        try:
            ctx.write_json("understanding/soundscape_policy.json", policy)
        except Exception:
            pass


def prune_reverse_jump_transitions(
    ctx: Any,
    transitions_doc: dict[str, Any],
    ordered: list[str],
) -> tuple[dict[str, Any], list[str]]:
    """Drop transitions with reverse tape jumps or late opening-tape landings."""
    from interview_mux.air_order_integrity import (
        opening_body_start_index,
        opening_tape_segment_ids,
        pair_source_gap_ms,
        resolved_segment_starts,
        reverse_jump_margin_ms,
    )

    out = copy.deepcopy(transitions_doc) if isinstance(transitions_doc, dict) else {"transitions": []}
    notes: list[str] = []
    items = list(out.get("transitions") or [])
    if not items:
        return out, notes
    starts = resolved_segment_starts(ctx)
    if not starts:
        return out, notes
    order = [str(s) for s in (ordered or []) if s]
    pos = {sid: idx for idx, sid in enumerate(order)}
    opening_ids = opening_tape_segment_ids(order, starts)
    margin = reverse_jump_margin_ms(ctx=ctx)
    body_start = opening_body_start_index(ctx=ctx)
    kept: list[dict[str, Any]] = []
    pruned = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        after = str(item.get("after_segment_id") or "")
        before = str(item.get("before_segment_id") or "")
        gap = item.get("source_gap_ms")
        if gap is None and after and before:
            gap = pair_source_gap_ms(after, before, starts)
        if gap is not None and int(gap) < -margin:
            pruned += 1
            continue
        if before in opening_ids and pos.get(before, 0) >= body_start:
            pruned += 1
            continue
        kept.append(item)
    out["transitions"] = kept
    if pruned:
        out["reverse_jump_pruned_count"] = pruned
        notes.append(f"pruned_reverse_jump_transitions:{pruned}")
    return out, notes


def repair_transitions(ctx: Any, doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Keep one spoken bridge per selected-order adjacency."""
    from interview_mux.gap_framing import (
        dedupe_transitions_by_adjacency,
        prune_transitions_outside_selection,
    )

    out = copy.deepcopy(doc) if isinstance(doc, dict) else {"transitions": []}
    applied: list[dict[str, Any]] = []
    before = len(out.get("transitions") or [])
    sel_ids: list[str] = []
    try:
        if ctx.artifact_exists("master/selection.json"):
            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict):
                sel_ids = [str(x) for x in (sel.get("ordered_segment_ids") or []) if x]
    except Exception:
        sel_ids = []
    out = prune_transitions_outside_selection(out, sel_ids)
    pruned = int(out.get("outside_selection_pruned_count") or 0)
    if pruned:
        applied.append({"action": "prune_transitions_outside_selection", "count": pruned})
    out, rnotes = prune_reverse_jump_transitions(ctx, out, sel_ids)
    if rnotes:
        applied.append({"action": "prune_reverse_jump_transitions", "notes": rnotes[:4]})
    out = dedupe_transitions_by_adjacency(out)
    extras = int(out.get("adjacency_deduped_count") or 0)
    if extras:
        applied.append({"action": "dedupe_transitions_by_adjacency", "count": extras})
    after = len(out.get("transitions") or [])
    if after != before and not applied:
        applied.append({"action": "normalize_transitions", "before": before, "after": after})
    return out, applied


def repair_sound_design_plan(ctx: Any, doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize cue placements and seed minimum creative-delivery density."""
    out = copy.deepcopy(doc)
    applied: list[dict[str, Any]] = []

    # After vernacular sanitize, LLM stages often cite parent ids (seg_070). Map to children.
    manifest_ids: set[str] = set()
    parent_to_children: dict[str, list[str]] = {}
    if ctx.artifact_exists("segments/manifest.json"):
        manifest = ctx.read_json("segments/manifest.json")
        for row in (manifest.get("segments") or []) if isinstance(manifest, dict) else []:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("segment_id") or "")
            if not sid:
                continue
            manifest_ids.add(sid)
            parent = str(row.get("parent_segment_id") or "")
            if parent:
                parent_to_children.setdefault(parent, []).append(sid)

    def _resolve_seg(sid: str) -> str | None:
        s = str(sid or "").strip()
        if not s:
            return None
        if not manifest_ids or s in manifest_ids:
            return s
        kids = parent_to_children.get(s) or []
        return kids[0] if kids else None

    for pal in out.get("palettes") or []:
        if not isinstance(pal, dict):
            continue
        raw = pal.get("segment_ids")
        if not isinstance(raw, list):
            continue
        mapped: list[str] = []
        seen: set[str] = set()
        changed = False
        for sid in raw:
            resolved = _resolve_seg(str(sid))
            if resolved is None:
                changed = True
                continue
            if resolved != str(sid):
                changed = True
            if resolved not in seen:
                seen.add(resolved)
                mapped.append(resolved)
        if changed:
            pal["segment_ids"] = mapped
            applied.append({"action": "remap_palette_parent_segment_ids", "palette_id": pal.get("palette_id")})

    flow_plans = out.get("flow_plans")
    if not isinstance(flow_plans, dict):
        flow_plans = {}
        out["flow_plans"] = flow_plans
    podcast = flow_plans.get("podcast")
    if not isinstance(podcast, dict):
        podcast = {}
        flow_plans["podcast"] = podcast
    cues = podcast.get("cues")
    if not isinstance(cues, list):
        cues = []
        podcast["cues"] = cues

    known = ("under_segment", "before_segment", "after_segment")
    cleaned_cues: list[dict[str, Any]] = []
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        if not str(cue.get("asset_id") or "").strip():
            applied.append({"action": "drop_cue_missing_asset_id", "cue_id": cue.get("cue_id")})
            continue
        for key in ("segment_id", "before_segment_id", "after_segment_id"):
            if cue.get(key):
                resolved = _resolve_seg(str(cue.get(key)))
                if resolved and resolved != str(cue.get(key)):
                    cue[key] = resolved
                    applied.append({"action": "remap_cue_parent_segment_id", "cue_id": cue.get("cue_id"), "field": key})
                elif resolved is None and manifest_ids:
                    cue.pop(key, None)
                    applied.append({"action": "drop_orphan_cue_segment", "cue_id": cue.get("cue_id"), "field": key})
        placement = str(cue.get("placement") or "")
        if placement in known:
            cleaned_cues.append(cue)
            continue
        low = placement.lower()
        fixed = None
        for k in known:
            if low.startswith(k):
                fixed = k
                break
        if fixed is None and str(cue.get("cue_id") or "").startswith("bed_"):
            fixed = "under_segment"
        if fixed is None:
            fixed = "before_segment"
        cue["placement"] = fixed
        applied.append({"action": "normalize_cue_placement", "cue_id": cue.get("cue_id"), "to": fixed})
        cleaned_cues.append(cue)
    if len(cleaned_cues) != len(cues):
        podcast["cues"] = cleaned_cues
        cues = cleaned_cues
    else:
        cues = cleaned_cues
        podcast["cues"] = cues

    # Ensure segment anchors when possible.
    selection_ids: list[str] = []
    if ctx.artifact_exists("master/selection.json"):
        sel = ctx.read_json("master/selection.json")
        if isinstance(sel, dict):
            selection_ids = [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]
    selection_set = set(selection_ids)
    # Drop cues anchored off the ranked selection before any bed seeding
    # (exec_13177: stale bed_coverage_seed_11 on seg_028 thrash after order shrink).
    if selection_set:
        kept_early: list[dict[str, Any]] = []
        dropped_early = 0
        for cue in cues:
            if not isinstance(cue, dict):
                continue
            anchors = [
                str(cue.get(k) or "")
                for k in (
                    "segment_id",
                    "before_segment_id",
                    "after_segment_id",
                    "under_segment_id",
                )
                if cue.get(k)
            ]
            if anchors and any(a and a not in selection_set for a in anchors):
                dropped_early += 1
                applied.append(
                    {
                        "action": "drop_cue_outside_selection",
                        "cue_id": cue.get("cue_id"),
                        "anchors": anchors,
                        "phase": "pre_seed",
                    }
                )
                continue
            kept_early.append(cue)
        if dropped_early:
            podcast["cues"] = kept_early
            cues = kept_early
    # Palette segment_ids must stay inside ranked selection (sanitize gate).
    if selection_set:
        for pal in out.get("palettes") or []:
            if not isinstance(pal, dict):
                continue
            before = [str(x) for x in (pal.get("segment_ids") or []) if x]
            after = [s for s in before if s in selection_set]
            if after != before:
                pal["segment_ids"] = after
                applied.append(
                    {
                        "action": "prune_palette_segment_ids",
                        "removed": [s for s in before if s not in selection_set][:12],
                    }
                )
    banned_bed_segs: set[str] = set()
    try:
        from interview_mux.sonic_context import load_sonic_context

        sonic = load_sonic_context(ctx) or {}
        flags = sonic.get("segment_flags") if isinstance(sonic.get("segment_flags"), dict) else {}
        banned_bed_segs.update(str(x) for x in (flags.get("overlap_high") or []) if x)
        banned_bed_segs.update(str(x) for x in (flags.get("trauma_adjacent") or []) if x)
    except Exception:
        banned_bed_segs = set()
    meta_in = out.get("_meta") if isinstance(out.get("_meta"), dict) else {}
    banned_bed_segs.update(
        str(x) for x in (meta_in.get("banned_bed_segment_ids") or []) if x
    )
    coh_in = out.get("coherence") if isinstance(out.get("coherence"), dict) else {}
    banned_bed_segs.update(
        str(x) for x in (coh_in.get("banned_bed_segment_ids") or []) if x
    )
    palette_seg_ids: list[str] = []
    seen_pal: set[str] = set()
    for pal in out.get("palettes") or []:
        if not isinstance(pal, dict):
            continue
        for sid in pal.get("segment_ids") or []:
            s = str(sid)
            if s and s not in seen_pal:
                seen_pal.add(s)
                palette_seg_ids.append(s)
    # Beds may only sit on palette-mapped segments (lint + sdp_cross_validate).
    bed_anchor_pool = [
        s
        for s in palette_seg_ids
        if s not in banned_bed_segs and (not selection_set or s in selection_set)
    ]
    if not bed_anchor_pool:
        bed_anchor_pool = [
            s
            for s in (list(palette_seg_ids) or list(selection_ids))
            if s not in banned_bed_segs and (not selection_set or s in selection_set)
        ]
    # Contiguous music continuity: when coverage floors require more bed time than
    # the thin palette allows, extend anchors across selection quartiles.
    if selection_ids and len(bed_anchor_pool) < max(4, min(12, len(selection_ids) // 3 or 1)):
        expanded: list[str] = list(bed_anchor_pool)
        seen_anchor = set(expanded)
        n = len(selection_ids)
        for frac in (0.12, 0.37, 0.62, 0.87):
            sid = selection_ids[min(n - 1, max(0, int(n * frac)))]
            if sid not in seen_anchor and sid not in banned_bed_segs:
                expanded.append(sid)
                seen_anchor.add(sid)
        # Also take every ~Nth selected segment for denser contiguous coverage.
        step = max(1, n // 8)
        for sid in selection_ids[::step]:
            if sid not in seen_anchor and sid not in banned_bed_segs:
                expanded.append(sid)
                seen_anchor.add(sid)
        if expanded != bed_anchor_pool:
            pals = out.get("palettes") if isinstance(out.get("palettes"), list) else []
            if pals and isinstance(pals[0], dict):
                ids = [str(x) for x in (pals[0].get("segment_ids") or [])]
                for sid in expanded:
                    if sid not in ids:
                        ids.append(sid)
                pals[0]["segment_ids"] = ids
                applied.append(
                    {
                        "action": "expand_palette_for_contiguous_beds",
                        "count": len(expanded) - len(bed_anchor_pool),
                    }
                )
            bed_anchor_pool = expanded
    assets = [a for a in (out.get("assets") or []) if isinstance(a, dict)]
    try:
        from interview_mux.music_motif import (
            THEME_BED_ROLES,
            THEME_PUNCTUATOR_ROLES,
            asset_id_is_banned,
            build_music_brief,
            ensure_motif_on_plan,
            is_banned_role,
            is_theme_role,
        )

        brief = build_music_brief(ctx)
        out = ensure_motif_on_plan(out, brief)
        assets = [a for a in (out.get("assets") or []) if isinstance(a, dict)]
        applied.append({"action": "ensure_motif_family_music_only"})
    except Exception:
        THEME_BED_ROLES = frozenset({"theme_underscore"})
        THEME_PUNCTUATOR_ROLES = frozenset(
            {"theme_cold_open", "theme_emphasis", "theme_chapter_resolve", "theme_outro", "theme_transition"}
        )

        def asset_id_is_banned(_aid: str) -> bool:  # type: ignore
            return False

        def is_banned_role(_r: str) -> bool:  # type: ignore
            return False

        def is_theme_role(r: str) -> bool:  # type: ignore
            return str(r or "").startswith("theme_")

    # Drop banned non-music assets/cues from creative plans.
    cleaned_assets: list[dict[str, Any]] = []
    for a in assets:
        role = str(a.get("role") or "")
        aid = str(a.get("asset_id") or a.get("id") or "")
        if is_banned_role(role) or asset_id_is_banned(aid):
            applied.append({"action": "drop_banned_sfx_asset", "asset_id": aid, "role": role})
            continue
        cleaned_assets.append(a)
    if cleaned_assets != assets:
        out["assets"] = cleaned_assets
        assets = cleaned_assets
    asset_ids = [str(a.get("asset_id") or a.get("id") or "") for a in assets if a.get("asset_id") or a.get("id")]
    assets_by_id = {
        str(a.get("asset_id") or a.get("id") or ""): a for a in assets if a.get("asset_id") or a.get("id")
    }
    # Strip banned cues still pointing at legacy murmur/tick assets.
    kept_cues: list[dict[str, Any]] = []
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        aid = str(cue.get("asset_id") or "")
        role = str(cue.get("role") or (assets_by_id.get(aid) or {}).get("role") or "")
        if asset_id_is_banned(aid) or is_banned_role(role):
            applied.append({"action": "drop_banned_sfx_cue", "cue_id": cue.get("cue_id"), "asset_id": aid})
            continue
        if (
            str(cue.get("placement") or "") == "under_segment"
            and str(cue.get("segment_id") or "") in banned_bed_segs
        ):
            banned_bed_segs.add(str(cue.get("segment_id") or ""))
            applied.append(
                {
                    "action": "drop_overlap_high_bed",
                    "cue_id": cue.get("cue_id"),
                    "segment_id": cue.get("segment_id"),
                }
            )
            continue
        kept_cues.append(cue)
    if len(kept_cues) != len(cues):
        podcast["cues"] = kept_cues
        cues = kept_cues
    if banned_bed_segs:
        meta_out = dict(out.get("_meta") or {}) if isinstance(out.get("_meta"), dict) else {}
        meta_out["banned_bed_segment_ids"] = sorted(banned_bed_segs)
        out["_meta"] = meta_out

    palette_set = set(palette_seg_ids)
    if palette_set:
        pals = out.get("palettes") if isinstance(out.get("palettes"), list) else []
        for cue in cues:
            if not isinstance(cue, dict) or cue.get("placement") != "under_segment" or cue.get("skip"):
                continue
            seg = str(cue.get("segment_id") or "")
            if seg and seg in palette_set and (not selection_set or seg in selection_set):
                continue
            if seg in banned_bed_segs:
                continue
            if seg and (not selection_set or seg in selection_set) and pals and isinstance(pals[0], dict):
                ids = [str(x) for x in (pals[0].get("segment_ids") or [])]
                if seg not in ids:
                    pals[0]["segment_ids"] = ids + [seg]
                    palette_set.add(seg)
                    applied.append({"action": "extend_palette_for_bed_segment", "segment_id": seg})
                continue
            target = next((s for s in bed_anchor_pool if s not in banned_bed_segs), None)
            if not target:
                continue
            cue["segment_id"] = target
            applied.append(
                {
                    "action": "remap_bed_to_palette_segment",
                    "cue_id": cue.get("cue_id"),
                    "from": seg or None,
                    "to": target,
                }
            )

    def _add_cue(*, cue_id: str, placement: str, segment_id: str | None, asset_id: str | None) -> None:
        if placement == "under_segment" and segment_id and str(segment_id) in banned_bed_segs:
            applied.append(
                {
                    "action": "skip_banned_bed_seed",
                    "cue_id": cue_id,
                    "segment_id": segment_id,
                }
            )
            return
        row: dict[str, Any] = {
            "cue_id": cue_id,
            "placement": placement,
            "skip": False,
        }
        if segment_id:
            if placement == "under_segment":
                row["segment_id"] = segment_id
            elif placement == "before_segment":
                row["segment_id"] = segment_id
                row["before_segment_id"] = segment_id
            else:
                row["after_segment_id"] = segment_id
                row["segment_id"] = segment_id
        if asset_id:
            row["asset_id"] = asset_id
        cues.append(row)
        applied.append({"action": "seed_creative_cue", "cue_id": cue_id, "placement": placement})

    from interview_mux.creative_delivery import sdp_compose_deferred

    defer_compose_cues = sdp_compose_deferred(out)
    beds = sum(1 for c in cues if isinstance(c, dict) and c.get("placement") == "under_segment" and not c.get("skip"))
    stingers = sum(
        1
        for c in cues
        if isinstance(c, dict) and c.get("placement") in {"before_segment", "after_segment"} and not c.get("skip")
    )
    try:
        from interview_mux.creative_delivery import min_density_cfg
        from interview_mux.listenability_guards import listenability_guards_cfg

        mins = min_density_cfg()
        guards = listenability_guards_cfg()
        mins = {
            **mins,
            "min_bed_coverage_ratio": max(
                float(mins.get("min_bed_coverage_ratio") or 0.08),
                float(guards.get("bed_coverage_min_ratio") or 0.22),
            ),
        }
    except Exception:
        mins = {"min_beds": 1, "min_stingers": 1, "min_bed_coverage_ratio": 0.22}
    need_beds = 0 if defer_compose_cues else max(0, int(mins.get("min_beds") or 1) - beds)
    need_stingers = 0 if defer_compose_cues else max(0, int(mins.get("min_stingers") or 3) - stingers)
    bed_asset = next(
        (
            str(a.get("asset_id") or "")
            for a in assets
            if str(a.get("role") or "") in THEME_BED_ROLES or str(a.get("role") or "") == "theme_underscore"
        ),
        None,
    )
    if not bed_asset:
        bed_asset = next(
            (aid for aid in asset_ids if "underscore" in aid.lower() or "bed" in aid.lower()),
            asset_ids[0] if asset_ids else None,
        )
    sting_asset = next(
        (
            str(a.get("asset_id") or "")
            for a in assets
            if str(a.get("role") or "")
            in {"theme_chapter_resolve", "theme_emphasis", "theme_transition", "theme_cold_open"}
        ),
        None,
    )
    if not sting_asset:
        sting_asset = next(
            (
                aid
                for aid in asset_ids
                if any(x in aid.lower() for x in ("resolve", "emphasis", "transition", "cold_open", "sting", "accent"))
            ),
            asset_ids[-1] if asset_ids else None,
        )
    if defer_compose_cues:
        applied.append({"action": "skip_density_seed_compose_deferred"})
    else:
        # Palettes stage often has no assets yet — never seed cues without asset_id (schema-required).
        if bed_asset:
            for i in range(need_beds):
                sid = bed_anchor_pool[min(i, len(bed_anchor_pool) - 1)] if bed_anchor_pool else None
                _add_cue(cue_id=f"bed_seed_{i+1}", placement="under_segment", segment_id=sid, asset_id=bed_asset)
        if sting_asset:
            for i in range(need_stingers):
                sid = selection_ids[min(i + 1, len(selection_ids) - 1)] if selection_ids else None
                place = "before_segment" if i % 2 == 0 else "after_segment"
                _add_cue(cue_id=f"theme_seed_{i+1}", placement=place, segment_id=sid, asset_id=sting_asset)
        # Always ensure a musical cold open before first speech when we have a theme_cold_open asset.
        cold_asset = next(
            (str(a.get("asset_id") or "") for a in assets if str(a.get("role") or "") == "theme_cold_open"),
            None,
        )
        has_cold = any(
            isinstance(c, dict)
            and str((assets_by_id.get(str(c.get("asset_id") or "")) or {}).get("role") or c.get("role") or "")
            == "theme_cold_open"
            and not c.get("skip")
            for c in cues
        )
        if cold_asset and not has_cold and selection_ids:
            _add_cue(
                cue_id="theme_cold_open_seed",
                placement="before_segment",
                segment_id=selection_ids[0],
                asset_id=cold_asset,
            )

        # Always ensure musical episode close after last native when theme_outro asset exists.
        from interview_mux.music_lane import pick_theme_outro_asset

        outro_row = pick_theme_outro_asset(assets)
        outro_asset = str(outro_row.get("asset_id") or "") if outro_row else None
        last_native = selection_ids[-1] if selection_ids else ""
        if ctx.artifact_exists("master/edl.json"):
            try:
                from interview_mux.order_hash import last_speech_clip_id

                edl_now = ctx.read_json("master/edl.json")
                clip_last = last_speech_clip_id(edl_now if isinstance(edl_now, dict) else None)
                if clip_last:
                    last_native = clip_last
            except Exception:
                pass
        has_outro = any(
            isinstance(c, dict)
            and str((assets_by_id.get(str(c.get("asset_id") or "")) or {}).get("role") or c.get("role") or "")
            == "theme_outro"
            and not c.get("skip")
            for c in cues
        )
        require_outro = True
        fade_out_ms = 2200
        try:
            from interview_mux.information_packages import information_packages_cfg

            ecfg = information_packages_cfg().get("episode_close") or {}
            require_outro = bool(ecfg.get("require_music", True))
            fade_out_ms = int(ecfg.get("fade_out_ms") or 2200)
            if ctx.artifact_exists("mastering/mastering_plan.json"):
                mp = ctx.read_json("mastering/mastering_plan.json")
                if isinstance(mp, dict) and isinstance(mp.get("episode_close"), dict):
                    music = mp["episode_close"].get("music") or {}
                    if isinstance(music, dict):
                        if music.get("required") is False:
                            require_outro = False
                        if music.get("fade_out_ms") is not None:
                            fade_out_ms = int(music["fade_out_ms"])
        except Exception:
            pass
        if require_outro and outro_asset and last_native:
            hard_frozen = False
            try:
                from interview_mux.seat_authority import hard_freeze_active

                hard_frozen = bool(hard_freeze_active(ctx))
            except Exception:
                hard_frozen = False
            if not has_outro:
                if hard_frozen:
                    # Locked NO: inventing outro cue under hard freeze.
                    applied.append(
                        {
                            "action": "theme_outro_seed_skipped_hard_freeze",
                            "segment_id": last_native,
                            "asset_id": outro_asset,
                        }
                    )
                else:
                    _add_cue(
                        cue_id="theme_outro_seed",
                        placement="after_segment",
                        segment_id=last_native,
                        asset_id=outro_asset,
                    )
            rebound_outro = False
            for c in cues:
                if not isinstance(c, dict):
                    continue
                role = str(
                    (assets_by_id.get(str(c.get("asset_id") or "")) or {}).get("role")
                    or c.get("role")
                    or ""
                )
                if role != "theme_outro" and "outro" not in str(c.get("cue_id") or "").lower():
                    continue
                c["role"] = "theme_outro"
                c["placement"] = "after_segment"
                c["segment_id"] = last_native
                c["after_segment_id"] = last_native
                c["asset_id"] = outro_asset
                c["fade_out_ms"] = max(fade_out_ms, int(c.get("fade_out_ms") or 0) or fade_out_ms)
                c["preserve_full_duration"] = True
                c["skip"] = False
                rebound_outro = True
            if rebound_outro:
                applied.append(
                    {
                        "action": (
                            "sdp_theme_outro_rebind"
                            if has_outro or hard_frozen
                            else "seed_theme_outro"
                        ),
                        "segment_id": last_native,
                        "asset_id": outro_asset,
                        "fade_out_ms": fade_out_ms,
                    }
                )

        # Seed information-package resolve face-outs when packages are committed to air.
        try:
            from interview_mux.information_packages import (
                committed_packages_from_plan,
                packages_affect_air,
            )

            if packages_affect_air() and ctx.artifact_exists("mastering/mastering_plan.json"):
                mp = ctx.read_json("mastering/mastering_plan.json")
                resolve_aid = next(
                    (
                        str(a.get("asset_id") or "")
                        for a in assets
                        if str(a.get("role") or "") == "theme_chapter_resolve"
                    ),
                    None,
                )
                for pkg in committed_packages_from_plan(mp if isinstance(mp, dict) else {}):
                    after_sid = str(pkg.get("after_segment_id") or "")
                    if not after_sid or not resolve_aid or after_sid not in selection_ids:
                        continue
                    # Never place a package resolve on the final native (outro owns bookend).
                    if after_sid == selection_ids[-1]:
                        applied.append(
                            {
                                "action": "skip_package_resolve_final_seam",
                                "package_id": pkg.get("package_id"),
                                "segment_id": after_sid,
                            }
                        )
                        continue
                    already = any(
                        isinstance(c, dict)
                        and not c.get("skip")
                        and str(c.get("segment_id") or "") == after_sid
                        and str(c.get("placement") or "") == "after_segment"
                        and str(
                            (assets_by_id.get(str(c.get("asset_id") or "")) or {}).get("role")
                            or c.get("role")
                            or ""
                        )
                        == "theme_chapter_resolve"
                        for c in cues
                    )
                    if already:
                        continue
                    cue_id = f"info_pkg_resolve_{pkg.get('package_id') or after_sid}"
                    _add_cue(
                        cue_id=cue_id,
                        placement="after_segment",
                        segment_id=after_sid,
                        asset_id=resolve_aid,
                    )
                    for c in cues:
                        if isinstance(c, dict) and str(c.get("cue_id") or "") == cue_id:
                            c["role"] = "theme_chapter_resolve"
                            c["information_package_id"] = pkg.get("package_id")
                            applied.append(
                                {
                                    "action": "seed_information_package_resolve",
                                    "package_id": pkg.get("package_id"),
                                    "segment_id": after_sid,
                                    "asset_id": resolve_aid,
                                }
                            )
                            break
        except Exception as exc:
            applied.append({"action": "information_package_resolve_seed_skipped", "error": str(exc)[:160]})

        # Seed additional under_segment beds on unused palette anchors until coverage floor.
        try:
            min_cov = float(mins.get("min_bed_coverage_ratio") or 0.08)
        except Exception:
            min_cov = 0.08
        if min_cov > 0 and bed_anchor_pool and bed_asset:
            seg_durs: dict[str, int] = {}
            if ctx.artifact_exists("segments/manifest.json"):
                manifest = ctx.read_json("segments/manifest.json")
                for row in (manifest.get("segments") or []) if isinstance(manifest, dict) else []:
                    if not isinstance(row, dict):
                        continue
                    sid = str(row.get("segment_id") or "")
                    if not sid:
                        continue
                    seg_durs[sid] = max(0, int(row.get("end_ms") or 0) - int(row.get("start_ms") or 0))
            total_ms = sum(seg_durs.get(s, 0) for s in selection_ids) or sum(seg_durs.values())
            bedded = {
                str(c.get("segment_id") or "")
                for c in cues
                if isinstance(c, dict)
                and str(c.get("placement") or "") in {"under_segment", "under_segment_span"}
                and not c.get("skip")
            }
            for c in cues:
                if not isinstance(c, dict) or c.get("skip"):
                    continue
                if str(c.get("placement") or "") != "under_segment_span":
                    continue
                for sid in c.get("segment_ids") or []:
                    if sid:
                        bedded.add(str(sid))
            bed_ms = sum(seg_durs.get(s, 0) for s in bedded)
            coverage = (bed_ms / total_ms) if total_ms > 0 else 0.0
            seed_i = 0
            order_pos = {sid: i for i, sid in enumerate(selection_ids)}
            prefer_contiguous = bool(
                ((merged_config().get("mastering") or {}).get("music_continuity") or {}).get(
                    "prefer_contiguous_beds", True
                )
            )

            def _adjacent_to_bedded(sid: str) -> bool:
                i = order_pos.get(sid)
                if i is None:
                    return False
                prev_sid = selection_ids[i - 1] if i > 0 else None
                next_sid = selection_ids[i + 1] if i + 1 < len(selection_ids) else None
                return prev_sid in bedded or next_sid in bedded

            # Coverage-floor seeding must not game the metric with scattered per-clip
            # beds. When `mastering.music_continuity.prefer_contiguous_beds` is set
            # (default), each pass prefers an anchor adjacent to an already-bedded
            # segment so the mix-time contiguous merge (see
            # `sound_design.flow1_overlays_from_sdp`) folds it into one honest
            # scene-length bed instead of another disjoint island; only when no
            # adjacent candidate remains does seeding fall back to the next-longest
            # fresh anchor. Re-ranked every pass since "adjacent" changes as beds grow.
            remaining = [sid for sid in bed_anchor_pool if sid not in bedded]
            while coverage < min_cov and remaining:
                if prefer_contiguous:
                    remaining.sort(key=lambda sid: (0 if _adjacent_to_bedded(sid) else 1, -seg_durs.get(sid, 0)))
                else:
                    remaining.sort(key=lambda sid: -seg_durs.get(sid, 0))
                sid = remaining.pop(0)
                was_adjacent = _adjacent_to_bedded(sid)
                seed_i += 1
                _add_cue(
                    cue_id=f"bed_coverage_seed_{seed_i}",
                    placement="under_segment",
                    segment_id=sid,
                    asset_id=bed_asset,
                )
                bedded.add(sid)
                bed_ms += seg_durs.get(sid, 0)
                coverage = (bed_ms / total_ms) if total_ms > 0 else 0.0
                applied.append(
                    {
                        "action": "seed_bed_for_coverage",
                        "segment_id": sid,
                        "coverage": round(coverage, 4),
                        "contiguous_with_existing_bed": was_adjacent,
                    }
                )
            # Quartile presence: ensure at least one bed in each half of the order.
            if selection_ids and bed_asset:
                n = len(selection_ids)
                for label, idx in (("q1", n // 4), ("q3", (3 * n) // 4)):
                    sid = selection_ids[min(n - 1, max(0, idx))]
                    if sid in bedded:
                        continue
                    seed_i += 1
                    _add_cue(
                        cue_id=f"bed_quartile_seed_{label}",
                        placement="under_segment",
                        segment_id=sid,
                        asset_id=bed_asset,
                    )
                    bedded.add(sid)
                    applied.append(
                        {
                            "action": "seed_bed_for_quartile",
                            "segment_id": sid,
                            "quartile": label,
                        }
                    )
                    pals = out.get("palettes") if isinstance(out.get("palettes"), list) else []
                    if pals and isinstance(pals[0], dict):
                        ids = [str(x) for x in (pals[0].get("segment_ids") or [])]
                        if sid not in ids:
                            pals[0]["segment_ids"] = ids + [sid]

    # Align under_segment beds with soundscape cue_slots and enforce stinger rate.
    # While compose_deferred, skip — strict_slots / inject are compose-owned (S1-C / S4).
    from interview_mux.creative_delivery import sdp_compose_deferred

    if sdp_compose_deferred(out):
        applied.append({"action": "skip_cue_slot_align_compose_deferred"})
    else:
        try:
            from interview_mux.soundscape_policy import load_policy, refresh_cue_slots

            policy = load_policy(ctx)
            if isinstance(policy, dict):
                slots = [s for s in (policy.get("cue_slots") or []) if isinstance(s, dict)]
                amb_segs = [
                    str(s.get("segment_id") or "")
                    for s in slots
                    if (
                        "theme_underscore" in (s.get("allowed_roles") or [])
                        or "ambient_bed" in (s.get("allowed_roles") or [])
                    )
                    and s.get("segment_id")
                ]
                # Sparse slot maps (common after archive/restore) → re-score against selection.
                # Isolate refresh: AuthorityDenied must not abort bed-slot inject
                # (exec_13167: cue_slot_stinger_repair_skipped before inject).
                if selection_ids and len(amb_segs) < max(1, min(3, len(bed_anchor_pool) or 1)):
                    try:
                        policy = refresh_cue_slots(ctx, writer_stage="music_palette_compose")
                        slots = [s for s in (policy.get("cue_slots") or []) if isinstance(s, dict)]
                        amb_segs = [
                            str(s.get("segment_id") or "")
                            for s in slots
                            if (
                                "theme_underscore" in (s.get("allowed_roles") or [])
                                or "ambient_bed" in (s.get("allowed_roles") or [])
                            )
                            and s.get("segment_id")
                        ]
                        applied.append(
                            {
                                "action": "refresh_soundscape_cue_slots",
                                "theme_underscore_slots": len(amb_segs),
                            }
                        )
                    except Exception as refresh_exc:
                        applied.append(
                            {
                                "action": "refresh_soundscape_cue_slots_skipped",
                                "error": str(refresh_exc)[:160],
                            }
                        )
                amb_set = set(amb_segs)
                preferred = [s for s in bed_anchor_pool if s in amb_set]
                if not preferred:
                    preferred = list(bed_anchor_pool) or list(amb_segs)
                # Beds must sit on a palette segment AND a theme_underscore cue_slot.
                # When those sets don't intersect, extend the first palette + inject a slot.
                if preferred and palette_set and not (set(preferred) & amb_set & palette_set):
                    target = next((s for s in bed_anchor_pool if s in palette_set), bed_anchor_pool[0])
                    pals = out.get("palettes") if isinstance(out.get("palettes"), list) else []
                    if pals and isinstance(pals[0], dict) and target not in palette_set:
                        ids = [str(x) for x in (pals[0].get("segment_ids") or [])]
                        if target not in ids:
                            pals[0]["segment_ids"] = ids + [target]
                            palette_set.add(target)
                            applied.append({"action": "extend_palette_for_bed_slot", "segment_id": target})
                    if target not in amb_set:
                        from interview_mux.soundscape_policy import admit_inject_cue_slots

                        policy = admit_inject_cue_slots(
                            ctx,
                            policy,
                            segment_ids=[target],
                            reason="theme_underscore_palette_bed_slot",
                            persist=True,
                            rescore=False,
                            writer_stage="music_palette_compose",
                        )
                        slots = [
                            s
                            for s in (policy.get("cue_slots") or [])
                            if isinstance(s, dict)
                        ]
                        amb_set.add(target)
                        applied.append(
                            {
                                "action": "inject_theme_underscore_cue_slot",
                                "segment_id": target,
                            }
                        )
                    preferred = [target]
                if preferred:
                    pals = out.get("palettes") if isinstance(out.get("palettes"), list) else []
                    slots = list(slots)
                    inject_ids: list[str] = []
                    for cue in cues:
                        if not isinstance(cue, dict) or cue.get("placement") != "under_segment" or cue.get("skip"):
                            continue
                        seg = str(cue.get("segment_id") or "")
                        if not seg:
                            continue
                        # Never re-inflate palette with off-selection bed anchors (i14 cousin).
                        if selection_set and seg not in selection_set:
                            continue
                        # Prefer keeping the planned segment: extend palette + inject theme_underscore slot.
                        if palette_set and seg not in palette_set and pals and isinstance(pals[0], dict):
                            ids = [str(x) for x in (pals[0].get("segment_ids") or [])]
                            if seg not in ids:
                                pals[0]["segment_ids"] = ids + [seg]
                                palette_set.add(seg)
                                applied.append({"action": "extend_palette_for_bed_segment", "segment_id": seg})
                        if amb_set is not None and seg not in amb_set:
                            inject_ids.append(seg)
                            amb_set.add(seg)
                            applied.append({"action": "inject_theme_underscore_cue_slot", "segment_id": seg})
                        # Never remap beds onto a single preferred slot — that collapses
                        # coverage seeding and contiguous music across the selection.
                        if palette_set is not None and seg not in palette_set:
                            if pals and isinstance(pals[0], dict):
                                ids = [str(x) for x in (pals[0].get("segment_ids") or [])]
                                if seg not in ids:
                                    pals[0]["segment_ids"] = ids + [seg]
                            palette_set.add(seg)
                            applied.append({"action": "force_palette_for_bed_segment", "segment_id": seg})
                    if inject_ids:
                        from interview_mux.soundscape_policy import admit_inject_cue_slots

                        policy = admit_inject_cue_slots(
                            ctx,
                            policy,
                            segment_ids=inject_ids,
                            reason="theme_underscore_quartile_spread",
                            persist=True,
                            rescore=False,
                            writer_stage="music_palette_compose",
                        )
                        slots = [
                            s
                            for s in (policy.get("cue_slots") or [])
                            if isinstance(s, dict)
                        ]

                # Drop cues anchored on segments no longer in the ranked selection.
                if selection_set:
                    kept_sel: list[dict[str, Any]] = []
                    dropped_sel = 0
                    for cue in cues:
                        if not isinstance(cue, dict):
                            continue
                        anchors = [
                            str(cue.get(k) or "")
                            for k in (
                                "segment_id",
                                "before_segment_id",
                                "after_segment_id",
                                "under_segment_id",
                            )
                            if cue.get(k)
                        ]
                        if anchors and any(a and a not in selection_set for a in anchors):
                            dropped_sel += 1
                            applied.append(
                                {
                                    "action": "drop_cue_outside_selection",
                                    "cue_id": cue.get("cue_id"),
                                    "anchors": anchors,
                                }
                            )
                            continue
                        kept_sel.append(cue)
                    if dropped_sel:
                        podcast["cues"] = kept_sel
                        cues = kept_sel

                mix = policy.get("mix_contract") if isinstance(policy.get("mix_contract"), dict) else {}
                # Stinger density is governed by hinge coverage ratios — do not hard-trim by /min.
                try:
                    from interview_mux.creative_delivery import creative_delivery_required

                    skip_rate_trim = creative_delivery_required()
                except Exception:
                    skip_rate_trim = True
                if skip_rate_trim:
                    applied.append({"action": "skip_stinger_rate_trim", "reason": "listenability_ratio_guards"})
                else:
                    try:
                        stinger_cap = float(mix.get("stinger_max_per_minute") or policy.get("stinger_max_per_minute") or 4)
                    except (TypeError, ValueError):
                        stinger_cap = 4.0
                    minutes = 1.0
                    if selection_ids and ctx.artifact_exists("segments/manifest.json"):
                        durs: dict[str, float] = {}
                        man = ctx.read_json("segments/manifest.json")
                        for row in (man.get("segments") or []) if isinstance(man, dict) else []:
                            if not isinstance(row, dict):
                                continue
                            sid = str(row.get("segment_id") or "")
                            if not sid:
                                continue
                            durs[sid] = max(0.0, (int(row.get("end_ms") or 0) - int(row.get("start_ms") or 0)) / 1000.0)
                        total_sec = sum(durs.get(s, 0.0) for s in selection_ids)
                        if total_sec > 0:
                            minutes = max(1.0, total_sec / 60.0)
                    max_stingers = max(0, int(stinger_cap * minutes + 1e-9))
                    sting_rows = [
                        c
                        for c in cues
                        if isinstance(c, dict)
                        and not c.get("skip")
                        and str(c.get("placement") or "") in {"before_segment", "after_segment", "between_clips"}
                    ]
                    if len(sting_rows) > max_stingers:
                        keep_ids = {id(c) for c in sting_rows[:max_stingers]}
                        trimmed = 0
                        kept_cues: list[dict[str, Any]] = []
                        for cue in cues:
                            if not isinstance(cue, dict):
                                continue
                            place = str(cue.get("placement") or "")
                            if place in {"before_segment", "after_segment", "between_clips"} and id(cue) not in keep_ids:
                                trimmed += 1
                                continue
                            kept_cues.append(cue)
                        podcast["cues"] = kept_cues
                        cues = kept_cues
                        applied.append(
                            {
                                "action": "trim_stingers_to_rate_cap",
                                "kept": max_stingers,
                                "trimmed": trimmed,
                                "cap_per_min": stinger_cap,
                                "minutes": round(minutes, 2),
                            }
                        )
                _ = mix
        except Exception as exc:
            applied.append({"action": "cue_slot_stinger_repair_skipped", "error": str(exc)[:160]})

    try:
        from interview_mux.creative_delivery import hydrate_flow_cue_segments

        hyd = hydrate_flow_cue_segments(ctx, out)
        for h in hyd:
            applied.append({"action": "hydrate_cue_segment", "detail": h})
        # Final fallback: any still-missing anchors get first/last selection ids.
        podcast = ((out.get("flow_plans") or {}).get("podcast") or {}) if isinstance(out.get("flow_plans"), dict) else {}
        cues = podcast.get("cues") if isinstance(podcast.get("cues"), list) else []
        first = selection_ids[0] if selection_ids else None
        last = selection_ids[-1] if selection_ids else None
        for cue in cues:
            if not isinstance(cue, dict) or cue.get("skip"):
                continue
            place = str(cue.get("placement") or "")
            if place == "before_segment" and not (cue.get("segment_id") or cue.get("before_segment_id")) and first:
                cue["segment_id"] = first
                cue["before_segment_id"] = first
                applied.append({"action": "default_before_anchor", "cue_id": cue.get("cue_id"), "to": first})
            if place == "after_segment" and not (cue.get("after_segment_id") or cue.get("segment_id")) and last:
                cue["after_segment_id"] = last
                cue["segment_id"] = last
                applied.append({"action": "default_after_anchor", "cue_id": cue.get("cue_id"), "to": last})
            if place == "under_segment" and not cue.get("segment_id") and first:
                cue["segment_id"] = first
                applied.append({"action": "default_under_anchor", "cue_id": cue.get("cue_id"), "to": first})
    except Exception as exc:
        applied.append({"action": "hydrate_cue_segments_skipped", "error": str(exc)[:160]})

    # Bind emphasis/resolve/outro cues to matching theme assets; collapse same-window stacks.
    try:
        from interview_mux.music_lane import (
            bind_cues_to_theme_assets,
            collapse_duplicate_music_cues,
            effective_cue_role,
        )

        podcast = ((out.get("flow_plans") or {}).get("podcast") or {}) if isinstance(out.get("flow_plans"), dict) else {}
        cues = podcast.get("cues") if isinstance(podcast.get("cues"), list) else []
        assets = [a for a in (out.get("assets") or []) if isinstance(a, dict)]
        assets_by_id = {
            str(a.get("asset_id")): a for a in assets if isinstance(a, dict) and a.get("asset_id")
        }
        bound, bind_actions = bind_cues_to_theme_assets(cues, assets)
        collapsed, collapse_actions = collapse_duplicate_music_cues(bound, assets_by_id)
        # Keep a single non-skipped theme_cold_open.
        cold_seen = False
        deduped: list[dict[str, Any]] = []
        for cue in collapsed:
            if not isinstance(cue, dict):
                continue
            role = effective_cue_role(cue, assets_by_id.get(str(cue.get("asset_id") or "")))
            if role == "theme_cold_open" and not cue.get("skip"):
                if cold_seen:
                    applied.append({"action": "drop_extra_theme_cold_open", "cue_id": cue.get("cue_id")})
                    continue
                cold_seen = True
            deduped.append(cue)
        if isinstance(podcast, dict):
            podcast["cues"] = deduped
        applied.extend(bind_actions)
        applied.extend(collapse_actions)
    except Exception as exc:
        applied.append({"action": "music_lane_bind_skipped", "error": str(exc)[:160]})

    # Ensure hinge stinger coverage for listenability (chapter resolves on chapter ends).
    # Compose-deferred invent leaves cues empty — do not seed hinges here (S6).
    if defer_compose_cues:
        applied.append({"action": "skip_hinge_resolve_seed_compose_deferred"})
    else:
      try:
        from interview_mux.listenability_guards import hinge_ids, listenability_guards_cfg
        from interview_mux.music_lane import asset_id_for_role

        podcast = ((out.get("flow_plans") or {}).get("podcast") or {}) if isinstance(out.get("flow_plans"), dict) else {}
        cues = podcast.get("cues") if isinstance(podcast.get("cues"), list) else []
        assets = [a for a in (out.get("assets") or []) if isinstance(a, dict)]
        resolve_aid = (
            asset_id_for_role(assets, "theme_chapter_resolve")
            or asset_id_for_role(assets, "theme_transition")
            or asset_id_for_role(assets, "theme_emphasis")
        )
        hinges = hinge_ids(ctx)
        guards = listenability_guards_cfg()
        min_ratio = float(guards.get("hinge_stinger_coverage_min_ratio") or 0.3)
        if resolve_aid and hinges and min_ratio > 0:
            stung: set[str] = set()
            for cue in cues:
                if not isinstance(cue, dict) or cue.get("skip"):
                    continue
                if str(cue.get("placement") or "") not in {"after_segment", "before_segment"}:
                    continue
                for key in ("after_segment_id", "segment_id", "before_segment_id"):
                    if cue.get(key):
                        stung.add(str(cue[key]))
            need = max(0, int(len(hinges) * min_ratio + 0.999) - sum(1 for h in hinges if h in stung))
            seed_i = 0
            for hid in hinges:
                if need <= 0:
                    break
                if hid in stung:
                    continue
                seed_i += 1
                cues.append(
                    {
                        "cue_id": f"hinge_resolve_seed_{seed_i}",
                        "asset_id": resolve_aid,
                        "role": "theme_chapter_resolve",
                        "placement": "after_segment",
                        "after_segment_id": hid,
                        "segment_id": hid,
                    }
                )
                stung.add(hid)
                need -= 1
                applied.append({"action": "seed_hinge_resolve", "segment_id": hid, "asset_id": resolve_aid})
            if isinstance(podcast, dict):
                podcast["cues"] = cues
      except Exception as exc:
        applied.append({"action": "hinge_resolve_seed_skipped", "error": str(exc)[:160]})

    pals = out.get("palettes") if isinstance(out.get("palettes"), list) else []
    seed_ids: list[str] = []
    seen_ids: set[str] = set()
    for cue in ((out.get("flow_plans") or {}).get("podcast") or {}).get("cues") or []:
        if not isinstance(cue, dict):
            continue
        for key in ("segment_id", "before_segment_id", "after_segment_id"):
            sid = str(cue.get(key) or "")
            if sid and sid not in seen_ids:
                seen_ids.add(sid)
                seed_ids.append(sid)
    if not seed_ids:
        seed_ids = list(selection_ids[:24])
    if not seed_ids and ctx.artifact_exists("segments/manifest.json"):
        man = ctx.read_json("segments/manifest.json")
        if isinstance(man, dict):
            for seg in man.get("segments") or []:
                if isinstance(seg, dict) and seg.get("segment_id"):
                    sid = str(seg["segment_id"])
                    if sid and sid not in seen_ids:
                        seen_ids.add(sid)
                        seed_ids.append(sid)
    seed_ids = seed_ids[:48]
    if not pals:
        out["palettes"] = [
            {
                "palette_id": "theme_default",
                "theme_label": "show theme",
                "keywords": ["acoustic", "warm", "conversational", "sparse"],
                "segment_ids": list(seed_ids),
                "ambient_description": "Soft acoustic underscore under conversation",
                "accent_description": "Short motif punctuation at chapter hinges",
                "avoid": ["vocals", "lyrics", "crowd noise"],
            }
        ]
        applied.append({"action": "seed_default_palette", "segment_count": len(seed_ids)})
    elif seed_ids:
        for pal in pals:
            if not isinstance(pal, dict):
                continue
            if pal.get("segment_ids"):
                continue
            pal["segment_ids"] = list(seed_ids)
            applied.append(
                {
                    "action": "fill_palette_segment_ids",
                    "palette_id": pal.get("palette_id"),
                    "segment_count": len(seed_ids),
                }
            )

    coh = out.get("coherence") if isinstance(out.get("coherence"), dict) else {}
    if not str(coh.get("sonic_identity") or "").strip() or not str(coh.get("primary_mood") or "").strip():
        seed_mood = "conversational"
        seed_density = "sparse"
        if ctx.artifact_exists("understanding/sonic_context.json"):
            sonic = ctx.read_json("understanding/sonic_context.json")
            ident = sonic.get("sonic_identity_seed") if isinstance(sonic, dict) else None
            if isinstance(ident, dict):
                seed_mood = str(ident.get("primary_mood") or seed_mood)
                seed_density = str(ident.get("density_hint") or seed_density)
        coh = dict(coh)
        coh.setdefault("sonic_identity", f"{seed_mood} {seed_density} acoustic motif")
        if not str(coh.get("sonic_identity") or "").strip():
            coh["sonic_identity"] = f"{seed_mood} {seed_density} acoustic motif"
        coh.setdefault("primary_mood", seed_mood)
        if not str(coh.get("primary_mood") or "").strip():
            coh["primary_mood"] = seed_mood
        coh.setdefault("density", seed_density)
        if not str(coh.get("density") or "").strip():
            coh["density"] = seed_density
        out["coherence"] = coh
        applied.append({"action": "seed_empty_coherence"})

    # Coverage-floor seeds used one underscore_loop for every clip at a
    # placeholder −26 dB. Post-commit validation requires the audible band
    # (−22…−18) and a loop change every max_scene_segments when optional_loop
    # exists — apply both here so SDP can finalize before music_palette_compose.
    try:
        from interview_mux.creative_delivery import (
            alternate_contiguous_loop_assets,
            audible_bed_level_db,
            clamp_bed_level_db,
        )
        from interview_mux.soundscape_policy import load_policy

        podcast = (
            ((out.get("flow_plans") or {}).get("podcast") or {})
            if isinstance(out.get("flow_plans"), dict)
            else {}
        )
        cues = podcast.get("cues") if isinstance(podcast.get("cues"), list) else []
        assets_now = [a for a in (out.get("assets") or []) if isinstance(a, dict)]
        primary_id = next(
            (
                str(a.get("asset_id") or "")
                for a in assets_now
                if str(a.get("palette_kind") or "") == "underscore_loop"
            ),
            str(bed_asset or ""),
        )
        optional_id = next(
            (
                str(a.get("asset_id") or "")
                for a in assets_now
                if str(a.get("palette_kind") or "") == "optional_loop"
            ),
            None,
        )
        max_run = 4
        try:
            mix_cfg = merged_config().get("mix") or {}
            arr = mix_cfg.get("underbed_arrangement") if isinstance(mix_cfg, dict) else {}
            if isinstance(arr, dict) and arr.get("max_scene_segments") is not None:
                max_run = max(1, int(arr["max_scene_segments"]))
        except (TypeError, ValueError):
            max_run = 4
        n_alt = alternate_contiguous_loop_assets(
            [c for c in cues if isinstance(c, dict)],
            ordered=list(selection_ids or []),
            primary_id=primary_id,
            optional_id=optional_id,
            max_run=max_run,
        )
        if n_alt:
            applied.append(
                {
                    "action": "alternate_optional_loop_on_bed_runs",
                    "changed": n_alt,
                    "max_run": max_run,
                }
            )
        policy = load_policy(ctx)
        mc = (policy or {}).get("mix_contract") if isinstance(policy, dict) else {}
        mc = mc if isinstance(mc, dict) else {}
        target = audible_bed_level_db(mc)
        n_lvl = 0
        for cue in cues:
            if not isinstance(cue, dict) or cue.get("skip"):
                continue
            if str(cue.get("placement") or "") != "under_segment":
                continue
            raw = cue.get("level_db")
            if raw is None:
                cue["level_db"] = target
                n_lvl += 1
                continue
            try:
                clamped = clamp_bed_level_db(float(raw), mc)
            except (TypeError, ValueError):
                clamped = target
            if float(raw) != clamped:
                cue["level_db"] = clamped
                n_lvl += 1
        if n_lvl:
            applied.append({"action": "clamp_bed_cue_levels", "changed": n_lvl, "level_db": target})
        if isinstance(podcast, dict) and isinstance(out.get("flow_plans"), dict):
            podcast["cues"] = cues
            out["flow_plans"]["podcast"] = podcast
    except Exception as exc:
        applied.append({"action": "bed_loop_level_repair_skipped", "error": str(exc)[:160]})

    # Persist seed-lock on coherence (schema allows extra keys). Root _meta is
    # stripped before return so LLM re-validate must read this field.
    if banned_bed_segs:
        coh_lock = dict(out.get("coherence") or {}) if isinstance(out.get("coherence"), dict) else {}
        coh_lock["banned_bed_segment_ids"] = sorted(banned_bed_segs)
        out["coherence"] = coh_lock
    # sound_design_plan.schema.json forbids root additionalProperties (_meta);
    # write_validated_artifact strips/restores _meta, but keep disk payload clean.
    out.pop("_meta", None)
    return out, applied


def apply_repairs_for_stage(
    ctx: Any,
    stage_key: str,
    artifacts: dict[str, Any],
    *,
    rel_path: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rel = rel_path or STAGE_ARTIFACT_DISK_PATHS.get(stage_key) or ""
    if rel.endswith("manifest.json") or stage_key == "segment_classification":
        return repair_manifest_segments(ctx, artifacts)
    if rel.endswith("boundaries.json") or stage_key in ("boundary_detection", "boundary_topic_resplit"):
        return repair_boundaries(ctx, artifacts)
    if rel.endswith("speakers.json") or stage_key == "speaker_roles":
        return repair_speakers(ctx, artifacts)
    if rel.endswith("content_brief.json") or stage_key in ("content_context", "content_brief_reanchor"):
        return repair_content_brief(ctx, artifacts)
    if rel.endswith("gap_evaluations.json") or stage_key == "missing_framing":
        return repair_gap_evaluations(ctx, artifacts)
    if rel.endswith("selection.json") or stage_key == "full_master_ranking":
        return repair_master_selection(ctx, artifacts)
    if rel.endswith("gap_report.json") or stage_key in ("optimal_questions", "gap_framing_compose"):
        return repair_gap_report(ctx, artifacts)
    if rel.endswith("coverage_audit.json") or stage_key == "topic_coverage_audit":
        return repair_coverage_audit(ctx, artifacts)
    if rel.endswith("narrative_plan.json") or stage_key == "narrative_arc_plan":
        return repair_narrative_plan(ctx, artifacts)
    if rel.endswith("edl_narrative_audit.json") or stage_key == "edl_narrative_audit":
        return repair_edl_audit(ctx, artifacts)
    if stage_key == "music_palette_compose":
        # Compose already ran repair_sound_design_plan once; a second full
        # reseed here re-inflates dropped off-selection beds (exec_13177 i14).
        return artifacts, [{"action": "skip_repair_already_composed"}]
    if rel.endswith("sound_design_plan.json") or stage_key in ("sound_design_plan", "sound_design_palettes"):
        return repair_sound_design_plan(ctx, artifacts)
    if rel.endswith("sfx_prompts.json") or stage_key in ("sfx_prompt_craft", "sfx_prompt_refine"):
        return repair_sfx_prompts(ctx, artifacts)
    if rel.endswith("transitions.json") or stage_key == "transitions":
        return repair_transitions(ctx, artifacts)
    return artifacts, []


_DEFAULT_THEME_NEGATIVE = (
    "vocals, lyrics, speech, whispering, singing, choir, crowd, applause, "
    "whoosh, riser, trailer hit, foley, sound effects, sfx, woodblock, tick, "
    "click, slap, boing, HVAC hum, murmur, noise bed, room tone only, "
    "pad-only drone, texture without pulse, comic cartoon sounds, footsteps, door slam, "
    "human voice, spoken word, rap, spoken narration"
)


def _sonic_keyword_tokens(ctx: Any) -> list[str]:
    tokens: list[str] = []
    try:
        if not ctx.artifact_exists("understanding/sonic_context.json"):
            return tokens
        sonic = ctx.read_json("understanding/sonic_context.json")
    except Exception:
        return tokens
    if not isinstance(sonic, dict):
        return tokens
    for row in sonic.get("tag_registry") or []:
        if not isinstance(row, dict):
            continue
        for keyword in row.get("keywords") or []:
            token = str(keyword or "").strip()
            if not token:
                continue
            # Prefer compact mood/topic tokens that fit music prompts.
            if len(token) > 40 or "_" in token and len(token) > 24:
                continue
            tokens.append(token)
        if len(tokens) >= 8:
            break
    return tokens[:8]


def heal_sfx_prompt_row(
    row: dict[str, Any],
    *,
    role: str,
    duration_seconds: float | None,
    sonic_keywords: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Make one prompt row pass `_lint_sfx_prompt_craft` (role, duration, pos/neg hygiene)."""
    import re

    from interview_mux.deterministic_lint import ROLE_DURATION_BANDS

    applied: list[dict[str, Any]] = []
    aid = row.get("asset_id")
    if role and str(row.get("role") or "") != role:
        row["role"] = role
        applied.append({"action": "set_prompt_role", "asset_id": aid, "role": role})

    band = ROLE_DURATION_BANDS.get(role)
    if duration_seconds is not None:
        dur = float(duration_seconds)
        if band:
            dur = max(float(band[0]), min(float(band[1]), dur))
        if float(row.get("duration_seconds") or 0) != dur:
            row["duration_seconds"] = dur
            applied.append({"action": "clamp_prompt_duration", "asset_id": aid, "duration": dur})
    elif band and float(row.get("duration_seconds") or 0):
        dur = float(row["duration_seconds"])
        clamped = max(float(band[0]), min(float(band[1]), dur))
        if clamped != dur:
            row["duration_seconds"] = clamped
            applied.append({"action": "clamp_prompt_duration", "asset_id": aid, "duration": clamped})

    pos = str(row.get("sfx_prompt") or "")
    # Scrub lint-banned positive clauses and speech/lyrics patterns.
    pos2 = re.sub(r"\bno\s+vocals\b", "", pos, flags=re.I)
    pos2 = re.sub(r"\bavoid\s*:", " ", pos2, flags=re.I)
    pos2 = re.sub(
        r"\b(says|saying|spoken|narrator|voice over|lyrics?|verse|chorus)\b",
        " ",
        pos2,
        flags=re.I,
    )
    pos2 = re.sub(r'"[^"]{8,}"', " ", pos2)
    pos2 = re.sub(r"\s+", " ", pos2).strip(" ,.")
    kws = [k for k in (sonic_keywords or []) if k]
    if kws:
        low = pos2.lower()
        missing = [k for k in kws[:4] if k.lower() not in low and not any(
            len(p) >= 4 and p in low for p in k.lower().replace("_", " ").split()
        )]
        if missing:
            pos2 = (pos2 + " Topics: " + ", ".join(missing) + ".").strip()
            applied.append({"action": "inject_sonic_keywords", "asset_id": aid, "keywords": missing})
    while len(pos2.split()) < 40:
        pos2 += (
            " Bright rhythmic documentary instrumental accompaniment "
            "with clear melodic motif and audible pulse."
        )
        applied.append({"action": "pad_positive_prompt", "asset_id": aid})
    if pos2 != pos:
        row["sfx_prompt"] = pos2
        if not any(a.get("action") == "inject_sonic_keywords" for a in applied):
            applied.append({"action": "scrub_positive_prompt", "asset_id": aid})

    neg = str(row.get("negative_prompt") or "")
    neg_words = len(neg.split())
    neg_low = neg.lower()
    needs_vocal_ban = not any(tok in neg_low for tok in ("vocal", "speech", "lyric"))
    if neg_words < 12 or neg_words > 60 or needs_vocal_ban:
        row["negative_prompt"] = _DEFAULT_THEME_NEGATIVE
        applied.append({"action": "replace_theme_negative", "asset_id": aid})
    return applied


def repair_sfx_prompts(ctx: Any, doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Heal theme prompt lint failures + neutralize false-positive diegetic ambient tokens."""
    import re

    from interview_mux.config import merged_config

    out = copy.deepcopy(doc)
    applied: list[dict[str, Any]] = []
    prompts = out.get("prompts")
    if not isinstance(prompts, list):
        return out, applied

    assets_by_id: dict[str, dict[str, Any]] = {}
    try:
        if ctx.artifact_exists("understanding/sound_design_plan.json"):
            plan = ctx.read_json("understanding/sound_design_plan.json")
            if isinstance(plan, dict):
                for item in plan.get("assets") or []:
                    if isinstance(item, dict) and item.get("asset_id"):
                        assets_by_id[str(item["asset_id"])] = item
    except Exception:
        assets_by_id = {}
    sonic_kws = _sonic_keyword_tokens(ctx)

    for row in prompts:
        if not isinstance(row, dict):
            continue
        aid = str(row.get("asset_id") or "")
        asset = assets_by_id.get(aid) or {}
        role = str(asset.get("role") or row.get("role") or "theme_underscore")
        dur = asset.get("duration_seconds")
        applied.extend(
            heal_sfx_prompt_row(
                row,
                role=role,
                duration_seconds=float(dur) if dur is not None else None,
                sonic_keywords=sonic_kws,
            )
        )

    allow_diegetic = bool((merged_config().get("sound_design") or {}).get("allow_diegetic_ambient", False))
    if not allow_diegetic:
        diegetic = re.compile(
            r"\b(diegetic|street|traffic|crowd|cafe|restaurant|office chatter|sirens?)\b",
            re.I,
        )
        for row in prompts:
            if not isinstance(row, dict):
                continue
            if str(row.get("role") or "") != "ambient_bed":
                continue
            text = str(row.get("sfx_prompt") or "")
            if not text or not diegetic.search(text):
                continue
            parts = re.split(r"(\b(?:Forbidden|Avoid)\s*:)", text, maxsplit=1, flags=re.I)
            if len(parts) >= 3:
                head, marker, tail = parts[0], parts[1], "".join(parts[2:])
                fixed = f"{diegetic.sub('ambience', head)}{marker}{diegetic.sub('group-noise', tail)}"
            else:
                fixed = diegetic.sub("ambience", text)
            if fixed != text:
                row["sfx_prompt"] = fixed
                applied.append(
                    {
                        "action": "scrub_diegetic_ambient_tokens",
                        "asset_id": row.get("asset_id"),
                    }
                )
    out.pop("_meta", None)
    # Keep SDP durations aligned with the clamped craft rows.
    if assets_by_id:
        try:
            if ctx.artifact_exists("understanding/sound_design_plan.json"):
                plan = ctx.read_json("understanding/sound_design_plan.json")
                if isinstance(plan, dict):
                    changed = False
                    by_prompt = {
                        str(row.get("asset_id") or ""): row
                        for row in prompts
                        if isinstance(row, dict) and row.get("asset_id")
                    }
                    for item in plan.get("assets") or []:
                        if not isinstance(item, dict) or not item.get("asset_id"):
                            continue
                        row = by_prompt.get(str(item["asset_id"]))
                        if not row or row.get("duration_seconds") is None:
                            continue
                        craft_d = float(row["duration_seconds"])
                        plan_d = item.get("duration_seconds")
                        if plan_d is None or abs(float(plan_d) - craft_d) > 0.01:
                            item["duration_seconds"] = craft_d
                            changed = True
                    if changed:
                        ctx.write_json(
                            "understanding/sound_design_plan.json",
                            plan,
                            skip_handoff=True,
                        )
        except Exception:
            pass
    return out, applied


def _excluded_segment_id(raw: Any) -> str:
    if isinstance(raw, dict):
        return str(raw.get("segment_id") or raw.get("id") or "").strip()
    return str(raw or "").strip()


def prune_stale_exclude_rationales(
    selection: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """`exclude_rationales` may only describe `excluded_segment_ids`, never air-order ids.

    Ranking persist/repair can readmit segments into `ordered_segment_ids` while leaving
    leftover rationale keys. Transitions then sees a fake order/exclude conflict and
    refuses to write `master/transitions.json`.
    """
    out = dict(selection) if isinstance(selection, dict) else {}
    applied: list[dict[str, Any]] = []
    ordered = {str(s) for s in (out.get("ordered_segment_ids") or []) if s}
    excl_rows = list(out.get("excluded_segment_ids") or [])
    excl_ids = {_excluded_segment_id(row) for row in excl_rows}
    excl_ids.discard("")
    reasons_from_rows: dict[str, str] = {}
    for row in excl_rows:
        sid = _excluded_segment_id(row)
        if not sid:
            continue
        if isinstance(row, dict):
            reason = str(row.get("reason") or "").strip()
        else:
            reason = ""
        if reason:
            reasons_from_rows[sid] = reason
    raw = out.get("exclude_rationales") if isinstance(out.get("exclude_rationales"), dict) else {}
    keep: dict[str, str] = {}
    for sid in sorted(excl_ids):
        reason = str(raw.get(sid) or reasons_from_rows.get(sid) or "excluded_from_master").strip()
        keep[sid] = reason or "excluded_from_master"
    dropped_air = sorted(str(k) for k in raw if str(k) in ordered)
    dropped_orphan = sorted(
        str(k) for k in raw if str(k) not in excl_ids and str(k) not in ordered
    )
    if keep != dict(raw) or dropped_air or dropped_orphan:
        out["exclude_rationales"] = keep
        applied.append(
            {
                "action": "prune_stale_exclude_rationales",
                "kept": len(keep),
                "dropped_air": dropped_air[:24],
                "dropped_orphan": dropped_orphan[:24],
            }
        )
    elif "exclude_rationales" not in out:
        out["exclude_rationales"] = keep
    return out, applied


def reconcile_ordered_vs_excluded(selection: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve dual membership: editorial excludes leave air order; else air wins."""
    out = dict(selection) if isinstance(selection, dict) else {}
    ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    rationales = (
        out.get("exclude_rationales") if isinstance(out.get("exclude_rationales"), dict) else {}
    )

    def _sid(raw: Any) -> str:
        if isinstance(raw, dict):
            return str(raw.get("segment_id") or "")
        return str(raw or "")

    def _reason_for(raw: Any, sid: str) -> str:
        if isinstance(raw, dict) and raw.get("reason"):
            return str(raw.get("reason") or "")
        return str((rationales or {}).get(sid) or "")

    try:
        from interview_mux.media_ip_cta import is_editorial_exclude_reason
    except Exception:

        def is_editorial_exclude_reason(reason: str) -> bool:  # type: ignore[misc]
            return bool(reason)

    editorial_drop: set[str] = set()
    excl_kept: list[Any] = []
    for raw in out.get("excluded_segment_ids") or []:
        sid = _sid(raw)
        if not sid:
            continue
        reason = _reason_for(raw, sid)
        if sid in ordered and is_editorial_exclude_reason(reason):
            editorial_drop.add(sid)
            excl_kept.append(
                raw
                if isinstance(raw, dict)
                else {"segment_id": sid, "reason": reason or "editorial_omit"}
            )
            continue
        if sid in ordered:
            # Noise dual-membership without editorial reason — air order wins.
            continue
        excl_kept.append(raw)

    # Rationales that mark editorial omit even when excluded list lagged.
    for sid, reason in (rationales or {}).items():
        key = str(sid or "").strip()
        if key and key in ordered and is_editorial_exclude_reason(str(reason or "")):
            editorial_drop.add(key)
            if key not in {_sid(r) for r in excl_kept}:
                excl_kept.append({"segment_id": key, "reason": str(reason)[:240]})

    if editorial_drop:
        ordered = [s for s in ordered if s not in editorial_drop]
        rat_out = dict(rationales) if isinstance(rationales, dict) else {}
        for sid in editorial_drop:
            rat_out.setdefault(sid, "editorial_omit")
        out["exclude_rationales"] = rat_out

    out["ordered_segment_ids"] = ordered
    out["excluded_segment_ids"] = excl_kept
    out, _pruned = prune_stale_exclude_rationales(out)
    return out


def _closing_ids_safe(ctx: Any, selection: dict[str, Any]) -> set[str]:
    try:
        from interview_mux.air_order_integrity import closing_segment_ids

        ordered = [str(x) for x in (selection.get("ordered_segment_ids") or []) if x]
        return closing_segment_ids(ctx, ordered)
    except Exception:
        return set()


def repair_edl_narrative_selection(ctx: Any) -> list[dict[str, Any]]:
    """Productize post-EDL narrative recovery (exclude framing/blanks, unlock volleys, fix coverage).

    Invoked from EDL narrative QC only — not from generic narrative_qc parsers.
    """
    notes: list[dict[str, Any]] = []
    if not ctx.artifact_exists("master/selection.json"):
        return notes
    try:
        from interview_mux.nle_state import materialize_all_nle_split_children

        n_kids = materialize_all_nle_split_children(ctx)
        if n_kids:
            notes.append({"action": "materialize_nle_split_children", "count": n_kids})
    except Exception:
        pass
    from interview_mux.artifact_lifecycle import fingerprint_artifact, _record_fingerprint

    sel = ctx.read_json("master/selection.json")
    if not isinstance(sel, dict):
        return notes
    sel = reconcile_ordered_vs_excluded(sel)
    order = [str(s) for s in (sel.get("ordered_segment_ids") or [])]
    excl = list(sel.get("excluded_segment_ids") or [])
    have = {str(r.get("segment_id") if isinstance(r, dict) else r) for r in excl}
    drop_ids: set[str] = set()
    try:
        from interview_mux.hard_keep import hard_keep_segment_ids

        hard_keeps = {str(s) for s in (hard_keep_segment_ids(ctx) or []) if s}
    except Exception:
        hard_keeps = set()
    for sid in list(order):
        # Never blank-drop hard-keeps — lattice seal then refuses
        # hard_keep_missing_from_order and EDL/selection diverge (exec_13198 seg_028).
        if _segment_is_blank_or_unusable(ctx, sid) and sid not in hard_keeps:
            drop_ids.add(sid)
    kept_preview = [x for x in order if x not in drop_ids]
    if drop_ids and not kept_preview:
        # Refuse empty air order — mirror repair_master_selection empty-order guard.
        notes.append(
            {
                "action": "keep_blank_segments_refuse_empty_order",
                "ids": sorted(drop_ids)[:24],
            }
        )
        drop_ids = set()
    for sid in drop_ids:
        if sid in order:
            order = [x for x in order if x != sid]
            reason = "blank_or_unusable_answer_audio"
            if sid not in have:
                excl.append({"segment_id": sid, "reason": reason})
                have.add(sid)
            notes.append({"action": "exclude_for_edl_narrative", "segment_id": sid, "reason": reason})
    sel["ordered_segment_ids"] = order
    sel["excluded_segment_ids"] = excl
    # Keep exclude_rationales aligned so narrative audit / lint do not see
    # blank IDs still on air (exec_11630 seg_003a/seg_003j).
    rat = dict(sel.get("exclude_rationales") or {})
    for sid in drop_ids:
        rat[sid] = str(rat.get(sid) or "blank_or_unusable_answer_audio")
    sel["exclude_rationales"] = rat
    sel = reconcile_ordered_vs_excluded(sel)
    sel, _pruned = prune_stale_exclude_rationales(sel)
    order = [str(s) for s in (sel.get("ordered_segment_ids") or [])]
    # Drop blank/unusable IDs from chapter membership too.
    chapters_out: list[dict[str, Any]] = []
    for ch in sel.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        ch = dict(ch)
        ch["segment_ids"] = [
            str(s) for s in (ch.get("segment_ids") or []) if str(s) in set(order)
        ]
        chapters_out.append(ch)
    if chapters_out:
        sel["chapters"] = chapters_out
    # Absorb leftover air-order ids into nearest chapter (same as EDL prepare).
    try:
        from interview_mux.selection_order_repair import fill_chapter_list_membership_gaps

        filled, filled_ids = fill_chapter_list_membership_gaps(
            [dict(ch) for ch in (sel.get("chapters") or []) if isinstance(ch, dict)],
            order,
        )
        if filled_ids:
            sel["chapters"] = filled
            notes.append(
                {
                    "action": "fill_chapter_membership_gaps",
                    "count": len(filled_ids),
                    "ids": filled_ids[:12],
                }
            )
    except Exception:
        pass
    order_set = set(order)
    fp = fingerprint_artifact(sel, "edl_narrative_audit")
    # Persist selection exclude/order repair BEFORE optional coverage mutations so a
    # coverage schema/write failure cannot roll back blank drops (exec_13183
    # seg_025: EDL omitted blank, QC parity failed, repair notes never landed).
    ctx.write_json(
        "master/selection.json",
        fp,
        stage_key="edl_narrative_audit",
        skip_handoff=True,
        mutation_class="narrative_metadata_align",
    )
    h = str((fp.get("_meta") or {}).get("content_hash") or "")
    if h:
        _record_fingerprint(ctx, "master/selection.json", h, "edl_narrative_audit")
    notes.append({"action": "re_fingerprint_selection"})
    if ctx.artifact_exists("master/coverage_audit.json"):
        try:
            cov = ctx.read_json("master/coverage_audit.json")
            if isinstance(cov, dict):
                for key in ("claim_mappings", "topic_mappings"):
                    for m in cov.get(key) or []:
                        if not isinstance(m, dict) or not m.get("covered"):
                            continue
                        mapped = {str(s) for s in (m.get("segment_ids") or []) if s}
                        if mapped and not (mapped & order_set):
                            m["covered"] = False
                            m["coverage_note"] = "mapped segments absent from final selection"
                            notes.append({"action": "uncover_orphan_mapping", "key": key})
                ctx.write_json("master/coverage_audit.json", cov, stage_key="topic_coverage_audit")
        except Exception:
            notes.append({"action": "coverage_audit_repair_skipped"})
    if ctx.artifact_exists("understanding/episode_structure.json"):
        try:
            es = ctx.read_json("understanding/episode_structure.json")
            if isinstance(es, dict):
                changed = False
                for v in es.get("speaker_volleys") or []:
                    if isinstance(v, dict) and v.get("locked"):
                        v["locked"] = False
                        changed = True
                if list(es.get("segment_order") or []) != order:
                    es["segment_order"] = list(order)
                    changed = True
                if changed:
                    ctx.write_json("understanding/episode_structure.json", es, optional=True)
                    notes.append({"action": "unlock_speaker_volleys_for_reorder"})
        except Exception:
            notes.append({"action": "episode_structure_repair_skipped"})
    return notes


def apply_choice_to_boundaries(doc: dict[str, Any], issue: dict[str, Any], choice: Any) -> dict[str, Any]:
    out = copy.deepcopy(doc)
    rows = out.get("boundaries")
    if not isinstance(rows, list):
        return out
    seg_id = str(issue.get("segment_id") or "")
    strategy = str(issue.get("repair_strategy") or "")

    if choice == "delete_segment" or (isinstance(choice, dict) and choice.get("action") == "delete"):
        if seg_id:
            out["boundaries"] = [r for r in rows if str(r.get("segment_id")) != seg_id]
            _append_repair_meta(out, {"action": "operator_delete", "segment_id": seg_id})
        return out

    if choice == "fabricate_all":
        return out

    for row in rows:
        if not isinstance(row, dict) or str(row.get("segment_id")) != seg_id:
            continue
        if strategy in ("infer_segment_types", "llm_pick", "merge_overlap") and isinstance(choice, str):
            if choice in VALID_SEGMENT_TYPES:
                row["type"] = choice
        elif isinstance(choice, dict):
            row.update({k: v for k, v in choice.items() if k in row or k in VALID_SEGMENT_TYPES})
        break
    _append_repair_meta(out, {"action": "operator_choice", "segment_id": seg_id, "choice": choice})
    return out


def apply_choice_to_manifest(manifest: dict[str, Any], issue: dict[str, Any], choice: Any) -> dict[str, Any]:
    out = copy.deepcopy(manifest)
    segs = out.get("segments")
    if not isinstance(segs, list):
        return out
    seg_id = str(issue.get("segment_id") or "")
    strategy = str(issue.get("repair_strategy") or "")

    if choice == "delete_segment" or (isinstance(choice, dict) and choice.get("action") == "delete"):
        out["segments"] = [r for r in segs if str(r.get("segment_id")) != seg_id]
        _append_repair_meta(out, {"action": "operator_delete", "segment_id": seg_id})
        return out

    for row in segs:
        if not isinstance(row, dict) or str(row.get("segment_id")) != seg_id:
            continue
        if strategy in ("infer_segment_types", "llm_pick", "merge_overlap") and isinstance(choice, str):
            if choice in VALID_SEGMENT_TYPES:
                row["type"] = choice
            elif choice in ("interviewer", "interviewee", "unknown"):
                row["speaker_role"] = choice
        elif isinstance(choice, dict):
            row.update({k: v for k, v in choice.items() if k in row or k in VALID_SEGMENT_TYPES})
        break
    _append_repair_meta(out, {"action": "operator_choice", "segment_id": seg_id, "choice": choice})
    return out
