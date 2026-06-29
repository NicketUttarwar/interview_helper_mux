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


def _text_jaccard(a: str, b: str) -> float:
    ta = set(a.lower().split())
    tb = set(b.lower().split())
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


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
    if role == "interviewer":
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

    # Normalize null arrays and roles on each row
    for i, row in enumerate(segs):
        if not isinstance(row, dict):
            continue
        if row.get("topic_tags") is None:
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
    if ctx.artifact_exists("segments/boundaries.json"):
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


def repair_boundaries(ctx: Any, doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    out = copy.deepcopy(doc)
    applied: list[dict[str, Any]] = []
    itr_cfg = (merged_config().get("analysis") or {}).get("artifact_issue_triage") or {}
    merge_threshold = int(itr_cfg.get("boundary_merge_threshold_ms") or 500)
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

    kept = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not row.get("speaker_id") and default_spk:
            row["speaker_id"] = default_spk
            applied.append({"action": "default_value", "path": "speaker_id", "value": default_spk})
        s, e = row.get("start_ms"), row.get("end_ms")
        if s is not None and e is not None and int(e) <= int(s):
            applied.append({"action": "drop_row", "segment_id": row.get("segment_id")})
            continue
        kept.append(row)

    sorted_rows = sort_segments_by_start_ms(kept)
    cfg = segment_timeline_cfg()
    allow_overlap = int(cfg.get("allow_overlap_ms", 0))
    prev_end: int | None = None
    trimmed: list[dict[str, Any]] = []
    for row in sorted_rows:
        if row.get("start_ms") is None or row.get("end_ms") is None:
            trimmed.append(row)
            continue
        start = int(row["start_ms"])
        end = int(row["end_ms"])
        if prev_end is not None and start < prev_end - allow_overlap:
            row = dict(row)
            row["start_ms"] = prev_end
            applied.append({"action": "trim_overlap", "segment_id": row.get("segment_id")})
        span = int(row["end_ms"]) - int(row["start_ms"])
        if span < merge_threshold and trimmed:
            prev = trimmed[-1]
            prev["end_ms"] = max(int(prev.get("end_ms", 0)), int(row["end_ms"]))
            applied.append({"action": "merge_micro_boundary", "segment_id": row.get("segment_id")})
        else:
            trimmed.append(row)
        prev_end = max(prev_end or 0, int(row.get("end_ms", end)))
    out["boundaries"] = trimmed
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
    all_unknown = all(
        isinstance(r, dict) and str(r.get("role") or r.get("speaker_role") or "unknown") == "unknown"
        for r in rows
    ) or False
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        if row.get("label") is None and row.get("display_name"):
            row["label"] = row["display_name"]
            applied.append({"action": "default_value", "path": f"speakers[{i}].label"})
        if row.get("confidence") is None:
            row["confidence"] = 0.5
            applied.append({"action": "default_value", "path": f"speakers[{i}].confidence", "value": 0.5})
        role = str(row.get("role") or row.get("speaker_role") or "unknown")
        if role == "moderator":
            row["role"] = "interviewer"
            applied.append({"action": "infer_enum", "path": f"speakers[{i}].role", "value": "interviewer"})
        elif all_unknown and role == "unknown":
            spk = str(row.get("speaker_id") or "")
            inferred = _infer_speaker_role(ctx, spk)
            row["role"] = inferred
            applied.append({"action": "infer_role", "path": f"speakers[{i}].role", "value": inferred})
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
            evidence = claim.get("evidence") or claim.get("evidence_anchors") or claim.get("segment_ids")
            if not evidence and str(claim.get("claim") or claim.get("text") or "").strip():
                applied.append({"action": "drop_row", "path": f"key_claims[{i}]", "reason": "no_evidence"})
                continue
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
        if isinstance(seg_ids, list) and manifest_ids:
            cleaned = [s for s in seg_ids if str(s) in manifest_ids]
            if cleaned != seg_ids:
                topic["segment_ids"] = cleaned
                applied.append({"action": "drop_orphan_ref", "path": f"topics[{i}].segment_ids"})
        if not topic.get("segment_ids"):
            norm_name = name.replace(" ", "_")
            matched: list[str] = []
            for tag, sids in tag_to_segments.items():
                if norm_name and (norm_name in tag or tag in norm_name):
                    matched.extend(sids)
            if matched:
                topic["segment_ids"] = sorted(set(matched))
                applied.append({"action": "map_topic_segments", "path": f"topics[{i}].segment_ids"})
        kept_topics.append(topic)
    out["topics"] = kept_topics

    for entry in applied:
        _append_repair_meta(out, entry)
    return out, applied


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
            kept.append({"segment_id": sid, "self_explanatory": False, "ready": False})
            applied.append({"action": "fabricate_evaluation", "segment_id": sid})
        out["evaluations"] = kept
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
    if out.get("excluded_segment_ids") and out.get("exclude_rationales") is None:
        out["exclude_rationales"] = {}
        applied.append({"action": "default_value", "path": "exclude_rationales"})
    for entry in applied:
        _append_repair_meta(out, entry)
    return out, applied


def repair_gap_report(ctx: Any, doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    out = copy.deepcopy(doc)
    applied: list[dict[str, Any]] = []
    manifest_ids, _ = _manifest_ids_and_tags(ctx)
    lines = out.get("interviewer_lines")
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
    for entry in applied:
        _append_repair_meta(out, entry)
    return out, applied


def repair_coverage_audit(ctx: Any, doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    out = copy.deepcopy(doc)
    applied: list[dict[str, Any]] = []
    brief_topics: set[str] = set()
    if ctx.artifact_exists("understanding/content_brief.json"):
        brief = ctx.read_json("understanding/content_brief.json")
        for t in (brief.get("topics") or []) if isinstance(brief, dict) else []:
            if isinstance(t, dict) and t.get("name"):
                brief_topics.add(str(t["name"]).lower())
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
    if out.get("coverage_score") is None and out.get("topics_covered") is not None:
        out["coverage_score"] = float(out.get("topics_covered") or 0)
        applied.append({"action": "default_value", "path": "coverage_score"})
    for entry in applied:
        _append_repair_meta(out, entry)
    return out, applied


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
            seg_ids = ch.get("segment_ids")
            if isinstance(seg_ids, list):
                cleaned = [s for s in seg_ids if str(s) in manifest_ids]
                if cleaned != seg_ids:
                    ch["segment_ids"] = cleaned
                    applied.append({"action": "drop_orphan_ref", "chapter_id": ch.get("chapter_id")})
            if not ch.get("segment_ids"):
                applied.append({"action": "drop_row", "chapter_id": ch.get("chapter_id")})
                continue
            kept.append(ch)
        out["chapters"] = kept
    for entry in applied:
        _append_repair_meta(out, entry)
    return out, applied


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
    for entry in applied:
        _append_repair_meta(out, entry)
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
    if rel.endswith("boundaries.json") or stage_key == "boundary_detection":
        return repair_boundaries(ctx, artifacts)
    if rel.endswith("speakers.json") or stage_key == "speaker_roles":
        return repair_speakers(ctx, artifacts)
    if rel.endswith("content_brief.json") or stage_key in ("content_context", "content_brief_reanchor"):
        return repair_content_brief(ctx, artifacts)
    if rel.endswith("gap_evaluations.json") or stage_key == "missing_framing":
        return repair_gap_evaluations(ctx, artifacts)
    if rel.endswith("selection.json") or stage_key == "full_master_ranking":
        return repair_master_selection(ctx, artifacts)
    if rel.endswith("gap_report.json") or stage_key == "optimal_questions":
        return repair_gap_report(ctx, artifacts)
    if rel.endswith("coverage_audit.json") or stage_key == "topic_coverage_audit":
        return repair_coverage_audit(ctx, artifacts)
    if rel.endswith("narrative_plan.json") or stage_key == "narrative_arc_plan":
        return repair_narrative_plan(ctx, artifacts)
    if rel.endswith("edl_narrative_audit.json") or stage_key == "edl_narrative_audit":
        return repair_edl_audit(ctx, artifacts)
    return artifacts, []


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
