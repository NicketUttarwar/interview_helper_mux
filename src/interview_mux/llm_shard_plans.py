"""Deterministic shard plans when arbiter requests decompose but omits shard_plan."""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config

DECOMPOSE_ELIGIBLE = frozenset(
    {
        "content_context",
        "content_brief_reanchor",
        "boundary_detection",
        "segment_classification",
        "missing_framing",
        "topic_coverage_audit",
        "full_master_ranking",
        "highlight_selection",
    }
)


def _context_cfg() -> dict[str, Any]:
    return (merged_config().get("analysis") or {}).get("context") or {}


def _max_transcript_shards() -> int:
    return int(_context_cfg().get("max_transcript_shards", 12))


def build_deterministic_shard_plan(
    stage_key: str,
    stage_input: dict[str, Any],
    *,
    truncation_flags: list[str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """
    Build shard_plan from caps when arbiter decomposes without a plan.
    Returns (shard_plan, source) where source is 'deterministic' or 'empty'.
    """
    flags = truncation_flags or []
    if not flags and stage_key not in (
        "segment_classification",
        "missing_framing",
        "boundary_detection",
        "content_context",
        "content_brief_reanchor",
        "topic_coverage_audit",
        "full_master_ranking",
        "highlight_selection",
    ):
        return [], "empty"

    if stage_key == "content_context":
        return _transcript_chunks(stage_input), "deterministic"
    if stage_key == "boundary_detection":
        return _boundary_batches(stage_input), "deterministic"
    if stage_key in (
        "segment_classification",
        "content_brief_reanchor",
        "topic_coverage_audit",
        "highlight_selection",
    ):
        return _segment_batches(stage_input), "deterministic"
    if stage_key == "missing_framing":
        return _gap_segment_batches(stage_input), "deterministic"
    if stage_key == "full_master_ranking":
        return _ranking_batches(stage_input), "deterministic"
    return [], "empty"


def _transcript_chunks(stage_input: dict[str, Any]) -> list[dict[str, Any]]:
    tr = stage_input.get("transcript")
    text = ""
    if isinstance(tr, dict):
        text = str(tr.get("text", ""))
    elif isinstance(tr, str):
        text = tr
    full_cap = int(_context_cfg().get("transcript_full_chars", 72000))
    max_shards = _max_transcript_shards()
    if len(text) <= full_cap:
        return []
    chunk_size = max(1, full_cap // max(4, max_shards // 2))
    chunks: list[dict[str, Any]] = []
    for i, start in enumerate(range(0, len(text), chunk_size)):
        end = min(start + chunk_size, len(text))
        chunks.append({"label": f"transcript_{i + 1}", "text_start": start, "text_end": end})
    return chunks[:max_shards]


def _segment_batches(stage_input: dict[str, Any]) -> list[dict[str, Any]]:
    segs = _all_segments(stage_input)
    batch_size = int(_context_cfg().get("max_segments_in_context", 100)) // 2 or 50
    if len(segs) <= batch_size:
        return []
    batches: list[dict[str, Any]] = []
    for i in range(0, len(segs), batch_size):
        batch = segs[i : i + batch_size]
        ids = [s.get("segment_id") for s in batch if isinstance(s, dict) and s.get("segment_id")]
        if ids:
            batches.append({"label": f"segments_{i // batch_size + 1}", "segment_ids": ids})
    return batches[:_max_transcript_shards()]


def _gap_segment_batches(stage_input: dict[str, Any]) -> list[dict[str, Any]]:
    segs = _all_segments(stage_input)
    cap = int(_context_cfg().get("max_gap_evaluations", 50)) // 2 or 25
    if len(segs) <= cap:
        return []
    batches: list[dict[str, Any]] = []
    for i in range(0, len(segs), cap):
        batch = segs[i : i + cap]
        ids = [s.get("segment_id") for s in batch if isinstance(s, dict) and s.get("segment_id")]
        if ids:
            batches.append({"label": f"gaps_{i // cap + 1}", "segment_ids": ids})
    return batches[:_max_transcript_shards()]


def _boundary_batches(stage_input: dict[str, Any]) -> list[dict[str, Any]]:
    tr = stage_input.get("transcript")
    items = tr.get("items") if isinstance(tr, dict) else None
    if not items or len(items) < 400:
        return _segment_batches(stage_input)
    batch = len(items) // 4
    plans: list[dict[str, Any]] = []
    for i in range(0, len(items), batch):
        chunk = items[i : i + batch]
        if not chunk:
            continue
        start_ms = chunk[0].get("start_ms", 0)
        end_ms = chunk[-1].get("end_ms", start_ms)
        plans.append({"label": f"time_{i // batch + 1}", "start_ms": start_ms, "end_ms": end_ms})
    return plans[:_max_transcript_shards()]


def _ranking_batches(stage_input: dict[str, Any]) -> list[dict[str, Any]]:
    plan = stage_input.get("narrative_plan") or {}
    chapters = plan.get("chapters") or []
    if chapters:
        batches: list[dict[str, Any]] = []
        for ch in chapters[:_max_transcript_shards()]:
            if not isinstance(ch, dict):
                continue
            seg_ids = ch.get("segment_ids") or []
            if seg_ids:
                batches.append(
                    {
                        "label": ch.get("title", ch.get("chapter_id", "chapter")),
                        "segment_ids": list(seg_ids),
                    }
                )
        if batches:
            return batches
    return _segment_batches(stage_input)


def _all_segments(stage_input: dict[str, Any]) -> list[dict[str, Any]]:
    segs = stage_input.get("segments")
    if isinstance(segs, dict):
        return [s for s in (segs.get("segments") or []) if isinstance(s, dict)]
    if isinstance(segs, list):
        return [s for s in segs if isinstance(s, dict)]
    return []


def transcript_length_for_stage_input(stage_input: dict[str, Any]) -> int:
    """Return character length of transcript text in stage input."""
    tr = stage_input.get("transcript")
    if isinstance(tr, dict):
        return len(str(tr.get("text", "")))
    if isinstance(tr, str):
        return len(tr)
    return 0


def should_proactive_decompose_content_context(stage_input: dict[str, Any]) -> bool:
    cfg = _context_cfg()
    threshold = int(cfg.get("proactive_decompose_chars", cfg.get("transcript_full_chars", 72000)))
    return transcript_length_for_stage_input(stage_input) > threshold
