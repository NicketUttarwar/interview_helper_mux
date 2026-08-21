"""Deterministic topic_tags enrichment for sparse segment classification."""

from __future__ import annotations

import re
from typing import Any

from interview_mux.run_context import RunContext


def _topic_slug(name: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(name or "").lower()).strip("_")
    return text[:64] if text else ""


def _topic_keywords(name: str) -> set[str]:
    slug = _topic_slug(name)
    parts = {p for p in slug.split("_") if len(p) >= 4}
    if slug:
        parts.add(slug)
    return parts


def _parse_approx_time_range_ms(text: str) -> tuple[int, int] | None:
    m = re.match(r"(\d+):(\d+)\s*-\s*(\d+):(\d+)", str(text or "").strip())
    if not m:
        return None
    start = int(m.group(1)) * 60_000 + int(m.group(2)) * 1000
    end = int(m.group(3)) * 60_000 + int(m.group(4)) * 1000
    if end <= start:
        return None
    return start, end


def _segment_overlaps_range(seg: dict[str, Any], start_ms: int, end_ms: int) -> bool:
    seg_start = int(seg.get("start_ms") or 0)
    seg_end = int(seg.get("end_ms") or seg_start)
    return seg_end >= start_ms and seg_start <= end_ms


def _score_topic_for_segment(topic: dict[str, Any], seg: dict[str, Any]) -> float:
    score = 0.0
    text = str(seg.get("text") or "").lower()
    keywords = _topic_keywords(str(topic.get("name") or ""))
    if keywords and text:
        hits = sum(1 for kw in keywords if kw in text)
        if hits:
            score += min(1.0, hits / max(1, len(keywords))) * 0.7
    approx = _parse_approx_time_range_ms(str(topic.get("approx_time_range") or ""))
    if approx and _segment_overlaps_range(seg, approx[0], approx[1]):
        score += 0.45
    existing = seg.get("topic_tags") or []
    slug = _topic_slug(str(topic.get("name") or ""))
    if slug and isinstance(existing, list) and slug in {str(t).lower() for t in existing}:
        score += 0.2
    return score


def bootstrap_manifest_topic_tags(ctx: RunContext, *, min_score: float = 0.45) -> int:
    """
    Patch sparse manifest topic_tags using content_brief topics (text + time overlap).
    Returns count of segments updated.
    """
    if not ctx.artifact_exists("segments/manifest.json") or not ctx.artifact_exists(
        "understanding/content_brief.json"
    ):
        return 0
    manifest = ctx.read_json("segments/manifest.json")
    brief = ctx.read_json("understanding/content_brief.json")
    segments = manifest.get("segments") or []
    topics = [t for t in (brief.get("topics") or []) if isinstance(t, dict) and t.get("name")]
    if not isinstance(segments, list) or not topics:
        return 0

    applied = 0
    untagged: list[dict[str, Any]] = []
    for seg in segments:
        if not isinstance(seg, dict) or not seg.get("segment_id"):
            continue
        tags = seg.get("topic_tags")
        if isinstance(tags, list) and tags:
            continue
        best_slug = ""
        best_score = 0.0
        for topic in topics:
            score = _score_topic_for_segment(topic, seg)
            if score > best_score:
                best_score = score
                best_slug = _topic_slug(str(topic.get("name") or ""))
        if best_slug and best_score >= min_score:
            seg["topic_tags"] = [best_slug]
            applied += 1
        else:
            untagged.append(seg)

    # When classification left every (or most) rows untagged, force a best-effort
    # slug so content_brief_reanchor host repair can map segment_ids. Prefer the
    # highest-scoring topic even below min_score; fall back to chronological buckets.
    if untagged and applied == 0:
        topic_slugs = [_topic_slug(str(t.get("name") or "")) for t in topics]
        topic_slugs = [s for s in topic_slugs if s]
        if topic_slugs:
            for idx, seg in enumerate(untagged):
                best_slug = ""
                best_score = -1.0
                for topic in topics:
                    score = _score_topic_for_segment(topic, seg)
                    slug = _topic_slug(str(topic.get("name") or ""))
                    if slug and score > best_score:
                        best_score = score
                        best_slug = slug
                if not best_slug:
                    best_slug = topic_slugs[idx % len(topic_slugs)]
                seg["topic_tags"] = [best_slug]
                applied += 1

    if not applied:
        return 0

    manifest["segments"] = segments
    from interview_mux.llm_flow_hardening import flow_hardening_enabled

    if flow_hardening_enabled():
        from interview_mux.artifact_writes import write_validated_artifact

        write_validated_artifact(
            ctx,
            "segments/manifest.json",
            manifest,
            merge_from_disk=False,
            stage_key="segment_classification",
        )
    else:
        ctx.write_json("segments/manifest.json", manifest)
    return applied
