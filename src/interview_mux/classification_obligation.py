"""Classification obligation matrix for segment_classification volley."""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.stage_coupling import contract_segment_ids, read_segment_contract


def classification_context_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis = (cfg or merged_config()).get("analysis") or {}
    context = analysis.get("context") or {}
    defaults = {
        "classification_obligation_enabled": True,
        "classification_excerpt_max_chars": 600,
        "per_segment_shard_max": 20,
        "proactive_decompose_segments": 40,
    }
    return {**defaults, **{k: context.get(k, v) for k, v in defaults.items()}}


def segment_text_excerpt(
    ctx: RunContext,
    start_ms: int,
    end_ms: int,
    *,
    max_chars: int | None = None,
) -> str:
    if not ctx.artifact_exists("transcript/full.json"):
        return ""
    tr = ctx.read_json("transcript/full.json")
    words = tr.get("words") or [] if isinstance(tr, dict) else []
    if not isinstance(words, list):
        return ""
    cap = max_chars or int(classification_context_cfg().get("classification_excerpt_max_chars", 600))
    span = [
        w
        for w in words
        if isinstance(w, dict)
        and int(w.get("start_ms", 0)) < end_ms
        and int(w.get("end_ms", 0)) > start_ms
    ]
    text = " ".join(str(w.get("text", "")) for w in span if w.get("text"))
    if len(text) > cap:
        return text[: cap - 3] + "..."
    return text


def segment_type_hints(
    boundary_row: dict[str, Any],
    speakers_by_id: dict[str, str],
) -> dict[str, Any]:
    start = int(boundary_row.get("start_ms", 0))
    end = int(boundary_row.get("end_ms", 0))
    speaker_id = str(boundary_row.get("speaker_id") or "")
    role = speakers_by_id.get(speaker_id, "unknown")
    excerpt = str(boundary_row.get("_text_excerpt") or "")
    return {
        "turn_length_ms": max(0, end - start),
        "speaker_role": role,
        "has_question_mark": "?" in excerpt,
        "word_count": len(excerpt.split()) if excerpt else 0,
    }


def build_obligation(
    ctx: RunContext,
    boundaries_doc: dict[str, Any],
    speakers_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build classification_obligation from boundaries contract."""
    from interview_mux.stage_coupling import contract_timeline_valid

    contract = read_segment_contract(boundaries_doc)
    if not contract_timeline_valid(boundaries_doc):
        return {
            "required_segment_ids": [],
            "required_count": 0,
            "segments": [],
            "segment_contract": contract,
            "timeline_invalid": True,
        }
    segment_ids = contract_segment_ids(boundaries_doc)
    speakers_by_id: dict[str, str] = {}
    if isinstance(speakers_doc, dict):
        for sp in speakers_doc.get("speakers") or []:
            if isinstance(sp, dict) and sp.get("speaker_id"):
                speakers_by_id[str(sp["speaker_id"])] = str(sp.get("role") or "unknown")

    boundary_rows = {
        str(b["segment_id"]): b
        for b in (boundaries_doc.get("boundaries") or [])
        if isinstance(b, dict) and b.get("segment_id")
    }

    segments_out: list[dict[str, Any]] = []
    for seg_id in segment_ids:
        row = dict(boundary_rows.get(seg_id) or {"segment_id": seg_id})
        start_ms = int(row.get("start_ms", 0))
        end_ms = int(row.get("end_ms", 0))
        excerpt = ""
        if start_ms < end_ms:
            excerpt = segment_text_excerpt(ctx, start_ms, end_ms)
        row["_text_excerpt"] = excerpt
        hints = segment_type_hints(row, speakers_by_id)
        segments_out.append(
            {
                "segment_id": seg_id,
                "start_ms": row.get("start_ms"),
                "end_ms": row.get("end_ms"),
                "speaker_id": row.get("speaker_id"),
                "speaker_role": speakers_by_id.get(str(row.get("speaker_id") or ""), "unknown"),
                "text_excerpt": excerpt,
                "hints": hints,
            }
        )

    contract = read_segment_contract(boundaries_doc)
    return {
        "required_segment_ids": segment_ids,
        "required_count": len(segment_ids),
        "segments": segments_out,
        "segment_contract": contract,
    }


def missing_segment_ids(obligation: dict[str, Any], envelope_segments: list[Any]) -> list[str]:
    required = set(obligation.get("required_segment_ids") or [])
    if not required:
        return []
    covered = {
        str(s.get("segment_id"))
        for s in envelope_segments
        if isinstance(s, dict) and s.get("segment_id")
    }
    return sorted(required - covered)


def obligation_lint_errors(
    obligation: dict[str, Any],
    envelope_segments: list[Any],
) -> list[str]:
    """Pre-arbiter obligation checks."""
    errors: list[str] = []
    required_count = int(obligation.get("required_count") or 0)
    if required_count <= 0:
        return errors
    missing = missing_segment_ids(obligation, envelope_segments)
    if missing:
        ratio = (required_count - len(missing)) / required_count
        errors.append(
            f"segment_coverage_ratio: {ratio:.2f} < 1.0 "
            f"({required_count - len(missing)}/{required_count} segments); "
            f"missing: {', '.join(missing[:4])}"
        )
    types = [
        str(s.get("type", ""))
        for s in envelope_segments
        if isinstance(s, dict) and s.get("type")
    ]
    if types and types.count("interviewee_answer") == len(types) and len(types) >= 2:
        errors.append("all segments typed interviewee_answer")
    return errors
