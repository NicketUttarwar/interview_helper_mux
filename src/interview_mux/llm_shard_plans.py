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
    ):
        # Truncation / field clips: prefer per-segment shards so boost + slice can clear markers.
        trunc_ish = any(
            f in (truncation_flags or [])
            for f in (
                "field_truncated",
                "max_stage_data_chars",
                "framer_digest_truncated",
                "volley_middle_truncated",
                "lint_retry_force_decompose",
                "proactive_per_segment",
            )
        )
        if trunc_ish:
            per_seg = _per_segment_shards(stage_input)
            if per_seg:
                return per_seg, "deterministic"
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

def _per_segment_shards(stage_input: dict[str, Any]) -> list[dict[str, Any]]:
    segs = _all_segments(stage_input)
    if not segs:
        return []
    plans: list[dict[str, Any]] = []
    for row in segs:
        if not isinstance(row, dict) or not row.get("segment_id"):
            continue
        sid = str(row["segment_id"])
        plans.append({"label": sid, "segment_ids": [sid]})
    max_shards = _max_transcript_shards()
    return plans[:max_shards]

def should_proactive_decompose_segment_classification(stage_input: dict[str, Any]) -> bool:
    from interview_mux.classification_obligation import classification_context_cfg

    threshold = int(classification_context_cfg().get("proactive_decompose_segments", 0))
    if threshold <= 0:
        return False
    return len(_all_segments(stage_input)) <= threshold

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

def _finalize_boundary_plans(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Snap adjacent shard windows contiguous and attach span metadata."""
    if not plans:
        return plans
    finalized: list[dict[str, Any]] = []
    for idx, plan in enumerate(plans):
        entry = dict(plan)
        if idx > 0 and entry.get("start_ms") is not None and finalized[-1].get("end_ms") is not None:
            entry["start_ms"] = int(finalized[-1]["end_ms"])
        start = entry.get("start_ms")
        end = entry.get("end_ms")
        if start is not None and end is not None:
            entry["shard_span_ms"] = max(0, int(end) - int(start))
        finalized.append(entry)
    return finalized

def _boundary_batches(stage_input: dict[str, Any]) -> list[dict[str, Any]]:
    tr = stage_input.get("transcript")
    words = tr.get("words") if isinstance(tr, dict) else None
    if isinstance(words, list) and len(words) >= 400:
        batch = max(1, len(words) // 4)
        plans: list[dict[str, Any]] = []
        for i in range(0, len(words), batch):
            chunk = words[i : i + batch]
            if not chunk:
                continue
            start_ms = chunk[0].get("start_ms", 0)
            end_ms = chunk[-1].get("end_ms", start_ms)
            plans.append({"label": f"time_{i // batch + 1}", "start_ms": start_ms, "end_ms": end_ms})
        if plans:
            return _finalize_boundary_plans(plans[:_max_transcript_shards()])
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
    return _finalize_boundary_plans(plans[:_max_transcript_shards()])

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
        found = [s for s in (segs.get("segments") or []) if isinstance(s, dict)]
        if found:
            return found
    elif isinstance(segs, list):
        found = [s for s in segs if isinstance(s, dict)]
        if found:
            return found
    boundaries = stage_input.get("boundaries")
    if isinstance(boundaries, dict):
        return [b for b in (boundaries.get("boundaries") or []) if isinstance(b, dict)]
    return []

def _canonical_segment_ids(stage_key: str, stage_input: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for row in _all_segments(stage_input):
        sid = row.get("segment_id")
        if sid is not None and str(sid).strip():
            ids.append(str(sid))
    return ids

def _resolve_shard_segment_id(raw: Any, id_universe: list[str]) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        if text in id_universe:
            return text
        if text.isdigit():
            return _resolve_shard_segment_id(int(text), id_universe)
        return text
    if isinstance(raw, int):
        if 1 <= raw <= len(id_universe):
            return id_universe[raw - 1]
        if 0 <= raw < len(id_universe):
            return id_universe[raw]
    return str(raw)

def normalize_shard_plan(
    stage_key: str,
    stage_input: dict[str, Any],
    shard_plan: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Coerce arbiter shard segment_ids to canonical string ids from stage input."""
    if not shard_plan:
        return []
    id_universe = _canonical_segment_ids(stage_key, stage_input)
    normalized: list[dict[str, Any]] = []
    for shard in shard_plan:
        if not isinstance(shard, dict):
            continue
        raw_ids = shard.get("segment_ids") or []
        if not isinstance(raw_ids, list):
            raw_ids = [raw_ids]
        resolved = [
            sid
            for sid in (_resolve_shard_segment_id(raw, id_universe) for raw in raw_ids)
            if sid
        ]
        entry = dict(shard)
        if resolved:
            entry["segment_ids"] = resolved
        elif raw_ids and id_universe:
            entry["segment_ids"] = [str(x) for x in raw_ids]
        normalized.append(entry)
    return normalized

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

def should_proactive_decompose_boundary_detection(
    stage_input: dict[str, Any],
    ctx: Any | None = None,
) -> bool:
    from interview_mux.boundary_observability import oversplit_risk_from_hints, spine_truncation_risk
    from interview_mux.segment_timeline_standard import segmentation_cfg

    seg_cfg = segmentation_cfg()
    pace_classes = set(seg_cfg.get("boundary_proactive_decompose_pace_classes") or ["calm", "brisk"])
    sap = stage_input.get("source_acoustic_profile") if isinstance(stage_input.get("source_acoustic_profile"), dict) else {}
    pacing = sap.get("pacing") if isinstance(sap.get("pacing"), dict) else {}
    pace_class = str(pacing.get("pace_class") or stage_input.get("pace_class") or "").strip().lower()
    hints = stage_input.get("pause_ladder_hints")
    oversplit = oversplit_risk_from_hints(hints if isinstance(hints, dict) else None)

    tr = stage_input.get("transcript")
    duration_ms = 0
    if isinstance(tr, dict) and tr.get("words"):
        words = tr["words"]
        if words:
            duration_ms = int(words[-1].get("end_ms", 0))

    if duration_ms and duration_ms < 60_000 and not oversplit:
        return False

    if oversplit and (not pace_classes or pace_class in pace_classes or not pace_class):
        return True
    if ctx is not None and spine_truncation_risk(ctx):
        return True
    cfg = _context_cfg()
    max_chars = int(cfg.get("max_stage_data_chars", 64000))
    import json

    est = len(json.dumps(stage_input, default=str))
    return est > int(max_chars * 0.9)
