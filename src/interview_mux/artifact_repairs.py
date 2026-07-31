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

    # Infer segment types when all same
    types = [str(r.get("type")) for r in out["segments"] if isinstance(r, dict) and r.get("type")]
    if types and types.count("interviewee_answer") == len(types) and len(types) >= 2:
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


def _infer_speaker_role(ctx: Any, speaker_id: str) -> str:
    """Heuristic role from transcript question density."""
    if not ctx.artifact_exists("transcript/normalized.json"):
        return "interviewee"
    try:
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
            if "?" in text[:120]:
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
        if role == "unknown" or all_unknown:
            inferred = _infer_speaker_role(ctx, sid)
            row["role"] = inferred
            applied.append({"action": "infer_speaker_role", "speaker_id": sid, "value": inferred})
    # Tie-break: among dual unknowns resolved to same role, prefer question-dense as interviewer.
    roles_now = [
        str(r.get("role") or "unknown")
        for r in rows
        if isinstance(r, dict)
    ]
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
    return manifest_ids, tag_to_segments


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
        # Reanchor completeness requires segment_ids once a segment manifest exists.
        # content_context runs before boundary/classification — keep unanchored topics then.
        if not (topic.get("segment_ids") or []):
            if manifest_ids:
                applied.append({"action": "drop_row", "path": f"topics[{i}]", "reason": "empty_segment_ids"})
                continue
        kept_topics.append(topic)
    out["topics"] = kept_topics

    for entry in applied:
        _append_repair_meta(out, entry)
    return out, applied


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
    ctx.write_json("understanding/content_brief.json", repaired, skip_handoff=True)
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
        # Add missing evaluation rows
        present = {str(r.get("segment_id")) for r in kept if isinstance(r, dict)}
        for sid in sorted(manifest_ids - present):
            kept.append(
                {
                    "segment_id": sid,
                    "self_explanatory": True,
                    "gap_type": "ok_with_light_bridge",
                    "severity": "low",
                    "listener_confusion": "",
                    "ready": True,
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
            if row.get("severity") and row.get("gap_type"):
                continue
            if not row.get("severity"):
                row["severity"] = "low"
                applied.append({"action": "default_value", "path": f"evaluations[{i}].severity", "value": "low"})
            if not row.get("gap_type"):
                row["gap_type"] = "ok_with_light_bridge"
                applied.append(
                    {
                        "action": "default_value",
                        "path": f"evaluations[{i}].gap_type",
                        "value": "ok_with_light_bridge",
                    }
                )
            if "self_explanatory" not in row:
                row["self_explanatory"] = True
            if "listener_confusion" not in row:
                row["listener_confusion"] = ""
    for entry in applied:
        _append_repair_meta(out, entry)
    return out, applied


def repair_master_selection(ctx: Any, doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
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
        out["ordered_segment_ids"] = deduped
        # Drop blank / unusable answer segments (blank-safe for later chapter repairs).
        blank_drop = [s for s in deduped if _segment_is_blank_or_unusable(ctx, s)]
        if blank_drop:
            kept = [s for s in deduped if s not in set(blank_drop)]
            out["ordered_segment_ids"] = kept
            excl = list(out.get("excluded_segment_ids") or [])
            have = {str(r.get("segment_id") if isinstance(r, dict) else r) for r in excl}
            for sid in blank_drop:
                if sid not in have:
                    excl.append({"segment_id": sid, "reason": "blank_or_unusable_answer_audio"})
                    have.add(sid)
            out["excluded_segment_ids"] = excl
            applied.append({"action": "drop_blank_segments", "ids": blank_drop})
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
        out["excluded_segment_ids"] = normalized
        if normalized:
            out["exclude_rationales"] = rationales
            applied.append({"action": "sync_exclude_rationales", "count": len(rationales)})
    elif out.get("excluded_segment_ids") and out.get("exclude_rationales") is None:
        out["exclude_rationales"] = {}
        applied.append({"action": "default_value", "path": "exclude_rationales"})
    # Cross-validate requires narrative_plan chapter segments to appear in ordered_segment_ids.
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
                # Prepend missing chapter segments so narrative order stays front-loaded.
                out["ordered_segment_ids"] = missing + [str(s) for s in ordered]
                applied.append(
                    {
                        "action": "include_narrative_chapter_segments",
                        "count": len(missing),
                    }
                )
                # Drop them from exclusions if present.
                excl = out.get("excluded_segment_ids")
                if isinstance(excl, list):
                    miss_set = set(missing)
                    kept_ex = [
                        row
                        for row in excl
                        if not (
                            (isinstance(row, dict) and str(row.get("segment_id") or "") in miss_set)
                            or (isinstance(row, str) and row in miss_set)
                        )
                    ]
                    if len(kept_ex) != len(excl):
                        out["excluded_segment_ids"] = kept_ex
                        applied.append({"action": "unexclude_narrative_segments", "count": len(missing)})
                rats = out.get("exclude_rationales")
                if isinstance(rats, dict):
                    for sid in missing:
                        rats.pop(sid, None)
    # EDL narrative QC requires selection chapters to be contiguous + non-overlapping
    # in ordered_segment_ids. Ranking often interleaves chapter members — regroup.
    ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    chapters = out.get("chapters")
    if isinstance(chapters, list) and ordered:
        order_set = set(ordered)
        pos = {sid: idx for idx, sid in enumerate(ordered)}
        assigned: set[str] = set()
        new_order: list[str] = []
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
                new_order.append(sid)
            row = dict(ch)
            row["segment_ids"] = ids
            new_chapters.append(row)
        leftovers = [sid for sid in ordered if sid not in assigned]
        if leftovers and new_order:
            # Never dump leftovers after the finale chapter — insert before last span.
            insert_at = max(0, len(new_order) - max(1, len(new_chapters[-1].get("segment_ids") or []) if new_chapters else 1))
            # Prefer: attach leftovers to the last-but-one chapter block when present.
            if len(new_chapters) >= 2:
                prev_ids = list(new_chapters[-2].get("segment_ids") or [])
                # Rebuild new_order without a finale-tail append
                rebuilt: list[str] = []
                for i, ch in enumerate(new_chapters):
                    ids = list(ch.get("segment_ids") or [])
                    if i == len(new_chapters) - 2:
                        ids = ids + [s for s in leftovers if s not in ids]
                        ch["segment_ids"] = ids
                    rebuilt.extend(ids)
                new_order = rebuilt
            else:
                new_order[insert_at:insert_at] = leftovers
            changed = True
            applied.append(
                {
                    "action": "insert_chapter_leftovers_before_finale",
                    "count": len(leftovers),
                    "ids": leftovers[:12],
                }
            )
        elif leftovers:
            new_order.extend(leftovers)
            changed = True
        if new_order != ordered:
            out["ordered_segment_ids"] = new_order
            changed = True
            applied.append(
                {
                    "action": "reorder_segments_by_chapter_contiguity",
                    "count": len(new_order),
                }
            )
        # Topo-satisfy narrative_plan constraints after contiguity regroup
        if ctx.artifact_exists("master/narrative_plan.json"):
            try:
                from interview_mux.selection_order_repair import repair_selection_order

                plan_doc = ctx.read_json("master/narrative_plan.json")
                repaired, topo_applied = repair_selection_order(out, plan_doc if isinstance(plan_doc, dict) else None)
                if topo_applied:
                    out["ordered_segment_ids"] = repaired.get("ordered_segment_ids") or out.get(
                        "ordered_segment_ids"
                    )
                    applied.extend(topo_applied)
                    changed = True
            except Exception:
                pass
        if changed:
            out["chapters"] = new_chapters
            applied.append(
                {
                    "action": "normalize_chapter_segment_contiguity",
                    "count": len(new_chapters),
                }
            )
    for entry in applied:
        _append_repair_meta(out, entry)
    return out, applied


def _seed_missing_high_gap_interviewer_lines(
    ctx: Any,
    out: dict[str, Any],
    *,
    manifest_ids: set[str],
    applied: list[dict[str, Any]],
) -> None:
    """Ensure every high-severity gap evaluation has a targeting interviewer line.

    Post-commit lint rejects gap_report when a high gap lacks coverage. LLMs
    occasionally omit one segment (especially unfinished/crosstalk clips); seed a
    short synthesize bridge so compose can commit without a full re-volley.
    """
    if not ctx.artifact_exists("understanding/gap_evaluations.json"):
        return
    try:
        evals = ctx.read_json("understanding/gap_evaluations.json")
    except Exception:
        return
    if not isinstance(evals, dict):
        return
    high_rows = [
        r
        for r in (evals.get("evaluations") or [])
        if isinstance(r, dict)
        and str(r.get("severity", "")).lower() == "high"
        and str(r.get("segment_id") or "").strip()
    ]
    if not high_rows:
        return
    lines = out.get("interviewer_lines")
    if not isinstance(lines, list):
        lines = []
        out["interviewer_lines"] = lines
    targeted = {
        str(ln.get("targets_segment_id") or ln.get("segment_id") or "")
        for ln in lines
        if isinstance(ln, dict)
    }
    voice = ""
    try:
        from interview_mux.source_topology import pickup_eligible_speaker_id

        voice = str(pickup_eligible_speaker_id(ctx) or "").strip()
    except Exception:
        voice = ""
    from interview_mux.gap_framing import GAP_TYPE_TO_CATEGORY

    for row in high_rows:
        seg_id = str(row.get("segment_id") or "").strip()
        if not seg_id or seg_id in targeted:
            continue
        if manifest_ids and seg_id not in manifest_ids:
            continue
        # Never seed on-air VO for blank/unusable answer audio — exclude instead.
        if _segment_is_blank_or_unusable(ctx, seg_id):
            applied.append({"action": "skip_seed_blank_segment", "segment_id": seg_id})
            continue
        gap_type = str(row.get("gap_type") or "ok_with_light_bridge").strip() or "ok_with_light_bridge"
        category = GAP_TYPE_TO_CATEGORY.get(gap_type, "story_bridge")
        confusion = str(row.get("listener_confusion") or "").strip()
        blankish = any(
            tok in confusion.lower()
            for tok in ("blank", "no transcript", "empty answer", "unusable", "silence where")
        )
        if blankish:
            applied.append({"action": "skip_seed_meta_blank_copy", "segment_id": seg_id})
            continue
        if confusion:
            words = confusion.split()
            snippet = " ".join(words[:18]).rstrip(".,;:")
            text = f"Quickly — {snippet}, then continue."
        else:
            text = "Let's clarify that beat before we continue."
        seeded = {
            "line_id": f"vo_seed_{seg_id}",
            "gap_type": gap_type,
            "line_category": category,
            "text": text,
            "targets_segment_id": seg_id,
            "placement": "before",
            "delivery": "synthesize",
            "rationale": "Auto-seeded for high-severity gap missing an interviewer line.",
            "supports_segment_ids": [seg_id],
            "replaces_source_segments": [],
            "estimated_duration_sec": 6,
            "severity": "high",
            "suggested_tone": "neutral",
            "extracted_from": {
                "artifact": "gap_evaluations",
                "path": f"repair_seed:{seg_id}",
            },
        }
        if voice:
            seeded["voice_speaker_id"] = voice
        lines.append(seeded)
        targeted.add(seg_id)
        applied.append({"action": "seed_high_gap_line", "segment_id": seg_id})


def _segment_is_blank_or_unusable(ctx: Any, seg_id: str) -> bool:
    if not ctx.artifact_exists("segments/manifest.json"):
        return False
    man = ctx.read_json("segments/manifest.json")
    for row in (man.get("segments") or []) if isinstance(man, dict) else []:
        if not isinstance(row, dict):
            continue
        if str(row.get("segment_id") or "") != seg_id:
            continue
        text = str(row.get("text") or "").strip()
        dur = max(0, int(row.get("end_ms") or 0) - int(row.get("start_ms") or 0))
        if not text or dur < 400:
            return True
        return False
    return False


def _enforce_min_vo_insert_ratio(ctx: Any, out: dict[str, Any], *, applied: list[dict[str, Any]]) -> None:
    """Hard floor: ceil(selected_speech * min_vo_insert_ratio) host VO lines."""
    import math

    from interview_mux.config import merged_config

    gf = ((merged_config().get("analysis") or {}).get("gap_framing") or {})
    ratio = float(gf.get("min_vo_insert_ratio") or 0.20)
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
    # Midpoints of long same-speaker runs (≥28s).
    mono_breaks: list[str] = []
    try:
        man = ctx.read_json("segments/manifest.json") if ctx.artifact_exists("segments/manifest.json") else {}
        by_id = {
            str(r.get("segment_id")): r
            for r in ((man or {}).get("segments") or [])
            if isinstance(r, dict) and r.get("segment_id")
        }
        run_ms = 0
        run_spk = ""
        run_start_idx = 0
        for i, sid in enumerate(ordered):
            row = by_id.get(sid) or {}
            spk = str(row.get("speaker_id") or "")
            dur = max(0, int(row.get("end_ms") or 0) - int(row.get("start_ms") or 0))
            if spk and spk == run_spk:
                run_ms += dur
            else:
                if run_ms >= 25000 and run_start_idx < i:
                    mid = ordered[run_start_idx + (i - run_start_idx) // 2]
                    if mid not in covered:
                        mono_breaks.append(mid)
                run_spk = spk
                run_ms = dur
                run_start_idx = i
        if run_ms >= 25000 and run_start_idx < len(ordered):
            mid = ordered[run_start_idx + (len(ordered) - run_start_idx) // 2]
            if mid not in covered:
                mono_breaks.append(mid)
    except Exception:
        mono_breaks = []
    stride = max(1, len(ordered) // max(1, floor))
    priority = list(dict.fromkeys(mono_breaks + [s for s in ordered if s in chapter_ends] + ordered))
    # Variety mix ≈ 40% framing questions / 30% reactions / 20% bridges / 10% prefaces.
    variety_cycle = (
        [("framing_question", "Let me pause you there — what was the turning point in that stretch?")] * 4
        + [
            (
                "story_bridge",
                "That's a sharp point — hold onto that, because it sets up what comes next.",
            )
        ]
        * 3
        + [
            (
                "segment_summary",
                "Here's the beat we're about to hear — the claim that matters for this chapter.",
            )
        ]
        * 2
        + [("episode_preface", "Coming up next — here's where this chapter leads.")]
    )
    seed_i = 0
    for i, sid in enumerate(priority):
        if len([ln for ln in lines if isinstance(ln, dict) and not ln.get("skipped_optional")]) >= floor:
            break
        if sid in covered:
            continue
        # Always take monologue/chapter seeds; otherwise stride-sample.
        if sid not in mono_breaks and sid not in chapter_ends:
            try:
                oi = ordered.index(sid)
            except ValueError:
                continue
            if oi % stride != 0:
                continue
        covered.add(sid)
        if sid in mono_breaks:
            cat, text = "framing_question", "Let me pause you there — what was the turning point in that stretch?"
        elif sid in chapter_ends:
            cat, text = "episode_preface", "Coming up next — here's where this chapter leads."
        else:
            cat, text = variety_cycle[seed_i % len(variety_cycle)]
            seed_i += 1
        lines.append(
            {
                "line_id": f"vo_density_{sid}",
                "gap_type": "missing_followup",
                "line_category": cat,
                "text": text,
                "targets_segment_id": sid,
                "placement": "before",
                "delivery": "synthesize",
                "rationale": f"Density floor seed (min_vo_insert_ratio={ratio})",
                "supports_segment_ids": [sid],
                "replaces_source_segments": [],
                "estimated_duration_sec": 5,
                "severity": "medium",
                "suggested_tone": "neutral",
            }
        )
        applied.append({"action": "seed_vo_density_floor", "segment_id": sid, "category": cat})

def repair_gap_report(ctx: Any, doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
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
            # Schema requires arrays; LLMs often emit null for unused lists.
            for arr_key in ("replaces_source_segments", "supports_segment_ids"):
                if arr_key in fixed and fixed.get(arr_key) is None:
                    fixed[arr_key] = []
                    applied.append({"action": "null_to_empty_array", "path": arr_key})
                elif arr_key in fixed and not isinstance(fixed.get(arr_key), list):
                    fixed[arr_key] = []
                    applied.append({"action": "coerce_array", "path": arr_key})
            cleaned.append(fixed)
        lines = cleaned
        out["interviewer_lines"] = cleaned
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
    _seed_missing_high_gap_interviewer_lines(
        ctx, out, manifest_ids=set(manifest_ids or ()), applied=applied
    )
    _enforce_min_vo_insert_ratio(ctx, out, applied=applied)
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
    for entry in applied:
        _append_repair_meta(out, entry)
    return out, applied


def repair_coverage_audit(ctx: Any, doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    out = copy.deepcopy(doc)
    applied: list[dict[str, Any]] = []
    manifest_ids, _ = _manifest_ids_and_tags(ctx)
    brief_topics: set[str] = set()
    if ctx.artifact_exists("understanding/content_brief.json"):
        brief = ctx.read_json("understanding/content_brief.json")
        for t in (brief.get("topics") or []) if isinstance(brief, dict) else []:
            if isinstance(t, dict) and t.get("name"):
                brief_topics.add(str(t["name"]).lower())
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

    if ctx.artifact_exists("understanding/content_brief.json"):
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
                ctx.write_json("understanding/content_brief.json", brief, skip_handoff=True)
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


def repair_edl_audit(ctx: Any, doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    out = copy.deepcopy(doc)
    applied: list[dict[str, Any]] = []
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
    if out.get("blocking_issues"):
        out["verdict"] = "fail"
    elif str(out.get("verdict") or "").lower() == "fail":
        out["verdict"] = "warn" if out.get("warnings") else "pass"
        applied.append({"action": "upgrade_verdict", "value": out["verdict"]})
    for entry in applied:
        _append_repair_meta(out, entry)
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
    bed_anchor_pool = [s for s in palette_seg_ids if not selection_set or s in selection_set]
    if not bed_anchor_pool:
        bed_anchor_pool = list(palette_seg_ids) or list(selection_ids)
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
        kept_cues.append(cue)
    if len(kept_cues) != len(cues):
        podcast["cues"] = kept_cues
        cues = kept_cues

    palette_set = set(palette_seg_ids)
    if palette_set:
        pals = out.get("palettes") if isinstance(out.get("palettes"), list) else []
        for cue in cues:
            if not isinstance(cue, dict) or cue.get("placement") != "under_segment" or cue.get("skip"):
                continue
            seg = str(cue.get("segment_id") or "")
            if seg and seg in palette_set and (not selection_set or seg in selection_set):
                continue
            if seg and (not selection_set or seg in selection_set) and pals and isinstance(pals[0], dict):
                ids = [str(x) for x in (pals[0].get("segment_ids") or [])]
                if seg not in ids:
                    pals[0]["segment_ids"] = ids + [seg]
                    palette_set.add(seg)
                    applied.append({"action": "extend_palette_for_bed_segment", "segment_id": seg})
                continue
            target = bed_anchor_pool[0] if bed_anchor_pool else None
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
    need_beds = max(0, int(mins.get("min_beds") or 1) - beds)
    need_stingers = max(0, int(mins.get("min_stingers") or 3) - stingers)
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
            if isinstance(c, dict) and c.get("placement") == "under_segment" and not c.get("skip")
        }
        bed_ms = sum(seg_durs.get(s, 0) for s in bedded)
        coverage = (bed_ms / total_ms) if total_ms > 0 else 0.0
        seed_i = 0
        for sid in bed_anchor_pool:
            if coverage >= min_cov:
                break
            if sid in bedded:
                continue
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
                }
            )

    # Align under_segment beds with soundscape cue_slots and enforce stinger rate.
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
            if selection_ids and len(amb_segs) < max(1, min(3, len(bed_anchor_pool) or 1)):
                policy = refresh_cue_slots(ctx)
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
                applied.append({"action": "refresh_soundscape_cue_slots", "theme_underscore_slots": len(amb_segs)})
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
                    slots = list(slots)
                    slots.append(
                        {
                            "slot_id": f"bed_{target}",
                            "segment_id": target,
                            "placement": "under_segment",
                            "allowed_roles": ["theme_underscore"],
                            "priority": 0.5,
                            "reason": "theme_underscore_palette_bed_slot",
                        }
                    )
                    policy["cue_slots"] = slots
                    try:
                        ctx.write_json("understanding/soundscape_policy.json", policy)
                    except Exception:
                        pass
                    amb_set.add(target)
                    applied.append({"action": "inject_theme_underscore_cue_slot", "segment_id": target})
                preferred = [target]
            if preferred:
                pals = out.get("palettes") if isinstance(out.get("palettes"), list) else []
                slots = list(slots)
                slots_changed = False
                for cue in cues:
                    if not isinstance(cue, dict) or cue.get("placement") != "under_segment" or cue.get("skip"):
                        continue
                    seg = str(cue.get("segment_id") or "")
                    if not seg:
                        continue
                    # Prefer keeping the planned segment: extend palette + inject theme_underscore slot.
                    if palette_set and seg not in palette_set and pals and isinstance(pals[0], dict):
                        ids = [str(x) for x in (pals[0].get("segment_ids") or [])]
                        if seg not in ids:
                            pals[0]["segment_ids"] = ids + [seg]
                            palette_set.add(seg)
                            applied.append({"action": "extend_palette_for_bed_segment", "segment_id": seg})
                    if amb_set and seg not in amb_set:
                        slots.append(
                            {
                                "slot_id": f"bed_{seg}",
                                "segment_id": seg,
                                "placement": "under_segment",
                                "allowed_roles": ["theme_underscore"],
                                "priority": 0.55,
                                "reason": "theme_underscore_quartile_spread",
                            }
                        )
                        amb_set.add(seg)
                        slots_changed = True
                        applied.append({"action": "inject_theme_underscore_cue_slot", "segment_id": seg})
                    ok = (not amb_set or seg in amb_set) and (not palette_set or seg in palette_set)
                    if ok:
                        continue
                    # Last resort remap only when segment is unusable.
                    target = next(
                        (s for s in preferred if (not amb_set or s in amb_set) and (not palette_set or s in palette_set)),
                        preferred[0],
                    )
                    cue["segment_id"] = target
                    applied.append(
                        {
                            "action": "remap_bed_to_cue_slot_segment",
                            "cue_id": cue.get("cue_id"),
                            "from": seg or None,
                            "to": target,
                        }
                    )
                if slots_changed:
                    policy["cue_slots"] = slots
                    try:
                        ctx.write_json("understanding/soundscape_policy.json", policy)
                    except Exception:
                        pass

            # Drop cues anchored on segments no longer in the ranked selection.
            if selection_set:
                kept_sel: list[dict[str, Any]] = []
                dropped_sel = 0
                for cue in cues:
                    if not isinstance(cue, dict):
                        continue
                    anchors = [
                        str(cue.get(k) or "")
                        for k in ("segment_id", "before_segment_id", "after_segment_id")
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
    if rel.endswith("sound_design_plan.json") or stage_key in ("sound_design_plan", "sound_design_palettes"):
        return repair_sound_design_plan(ctx, artifacts)
    if rel.endswith("sfx_prompts.json") or stage_key in ("sfx_prompt_craft", "sfx_prompt_refine"):
        return repair_sfx_prompts(ctx, artifacts)
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
    return out, applied


def repair_edl_narrative_selection(ctx: Any) -> list[dict[str, Any]]:
    """Productize post-EDL narrative recovery (exclude framing/blanks, unlock volleys, fix coverage).

    Invoked from EDL narrative QC only — not from generic narrative_qc parsers.
    """
    notes: list[dict[str, Any]] = []
    if not ctx.artifact_exists("master/selection.json"):
        return notes
    from interview_mux.artifact_lifecycle import fingerprint_artifact, _record_fingerprint
    from interview_mux.gap_framing import ranking_exclude_segment_ids

    sel = ctx.read_json("master/selection.json")
    if not isinstance(sel, dict):
        return notes
    order = [str(s) for s in (sel.get("ordered_segment_ids") or [])]
    excl = list(sel.get("excluded_segment_ids") or [])
    have = {str(r.get("segment_id") if isinstance(r, dict) else r) for r in excl}
    drop_ids = set(ranking_exclude_segment_ids(ctx))
    for sid in list(order):
        if _segment_is_blank_or_unusable(ctx, sid):
            drop_ids.add(sid)
    for sid in drop_ids:
        if sid in order:
            order = [x for x in order if x != sid]
            reason = (
                "covered_by_framing_vo"
                if sid in set(ranking_exclude_segment_ids(ctx))
                else "blank_or_unusable_answer_audio"
            )
            if sid not in have:
                excl.append({"segment_id": sid, "reason": reason})
                have.add(sid)
            notes.append({"action": "exclude_for_edl_narrative", "segment_id": sid, "reason": reason})
    sel["ordered_segment_ids"] = order
    sel["excluded_segment_ids"] = excl
    order_set = set(order)
    if ctx.artifact_exists("master/coverage_audit.json"):
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
    if ctx.artifact_exists("understanding/episode_structure.json"):
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
                ctx.write_json("understanding/episode_structure.json", es)
                notes.append({"action": "unlock_speaker_volleys_for_reorder"})
    fp = fingerprint_artifact(sel, "full_master_ranking")
    ctx.write_json("master/selection.json", fp, stage_key="full_master_ranking", skip_handoff=True)
    h = str((fp.get("_meta") or {}).get("content_hash") or "")
    if h:
        _record_fingerprint(ctx, "master/selection.json", h, "full_master_ranking")
    notes.append({"action": "re_fingerprint_selection"})
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
