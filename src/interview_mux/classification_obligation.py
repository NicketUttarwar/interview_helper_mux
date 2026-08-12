"""Classification obligation matrix for segment_classification volley."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.stage_coupling import contract_segment_ids, read_segment_contract


@dataclass(frozen=True)
class AnswerOnlyAllowance:
    """Whether uniform ``interviewee_answer`` typing is expected for this source."""

    allowed: bool
    reason: str
    topology_class: str | None = None


def allows_all_interviewee_answer(ctx: RunContext) -> AnswerOnlyAllowance:
    """True for monologue / content-dominant sources; False when Q&A diversity is expected.

    Guest-only (or near-guest-only) interviews legitimately classify every segment as
    ``interviewee_answer``. Multi-speaker / clear host-frame topologies still require
    type diversity.
    """
    from interview_mux.conversation_context import (
        load_conversation_context,
        role_is_content,
        role_is_frame,
    )
    from interview_mux.source_topology import load_topology

    try:
        from interview_mux.segment_timeline_standard import segmentation_cfg

        if not bool(segmentation_cfg().get("require_type_diversity", True)):
            return AnswerOnlyAllowance(True, "policy_disabled")
    except Exception:
        pass

    th = (merged_config().get("source_topology") or {}).get("thresholds") or {}
    mono = float(th.get("monologue_talk_ratio", 0.80))
    sparse_frame = float(th.get("sparse_host_frame_ratio", 0.15))

    topo = load_topology(ctx) or {}
    cls = str(topo.get("topology_class") or "").strip() or None
    stats = [s for s in (topo.get("speaker_stats") or []) if isinstance(s, dict)]

    if cls in {"monologue_heavy", "multi_idea_sparse_host"}:
        return AnswerOnlyAllowance(True, f"topology:{cls}", cls)

    if stats:
        frame_r = sum(
            float(s.get("talk_ratio") or 0)
            for s in stats
            if role_is_frame(str(s.get("role_hint") or s.get("role") or ""))
        )
        content_r = sum(
            float(s.get("talk_ratio") or 0)
            for s in stats
            if role_is_content(str(s.get("role_hint") or s.get("role") or ""))
        )
        dominant = float(stats[0].get("talk_ratio") or 0)
        if len(stats) == 1 or dominant >= mono:
            return AnswerOnlyAllowance(True, "dominant_talk_ratio", cls)
        if frame_r < sparse_frame and content_r >= (1.0 - sparse_frame):
            return AnswerOnlyAllowance(True, "sparse_frame", cls)

    conv = load_conversation_context(ctx)
    if not conv.frame_ids and conv.content_ids:
        return AnswerOnlyAllowance(True, "zero_frame_speakers", cls)
    if conv.format_class in {"fireside", "media_profile"} or conv.topology_hint == "monologue_heavy":
        return AnswerOnlyAllowance(True, f"format:{conv.format_class or conv.topology_hint}", cls)

    if conv.frame_ids and cls in {
        None,
        "",
        "one_on_one_asymmetric",
        "one_on_one_balanced",
        "panel_multi_guest",
        "co_host_frame",
    }:
        return AnswerOnlyAllowance(False, "qa_frame_present", cls)

    # Unknown topology: only require diversity when a frame speaker is present.
    if conv.frame_ids:
        return AnswerOnlyAllowance(False, "default_require_diversity", cls)
    return AnswerOnlyAllowance(True, "no_frame_default_allow", cls)


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
    # Obligation lint has no RunContext; callers with ctx should use
    # allows_all_interviewee_answer. Keep a soft note only when diversity is
    # structurally impossible to judge here.
    if types and types.count("interviewee_answer") == len(types) and len(types) >= 2:
        # Without ctx we cannot adapt; leave to deterministic_lint / repairs.
        pass
    return errors
