from __future__ import annotations

from typing import Any

from interview_mux.coherence.theme_alignment import score_window_themes


def detect_missing_callbacks(
    *,
    content_brief: dict[str, Any],
    windows: list[dict[str, Any]],
    manifest: dict[str, Any] | None,
    duration_ms: int,
    threshold: float,
) -> list[dict[str, Any]]:
    topics = content_brief.get("topics") or []
    if not topics or duration_ms <= 0:
        return []

    half_ms = duration_ms // 2
    segments = (manifest or {}).get("segments") or []
    seg_by_topic: dict[str, list[dict[str, Any]]] = {}
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        for tag in seg.get("topic_tags") or []:
            seg_by_topic.setdefault(str(tag), []).append(seg)

    returns_to: set[str] = set()
    for rel in content_brief.get("topic_relationships") or []:
        if not isinstance(rel, dict):
            continue
        if rel.get("relation") in ("returns_to", "example_of", "prerequisite"):
            returns_to.add(str(rel.get("to_topic") or rel.get("from_topic") or ""))

    risks: list[dict[str, Any]] = []
    for topic in topics:
        if not isinstance(topic, dict):
            continue
        name = str(topic.get("name") or "")
        if not name:
            continue
        early_segs = [
            sid
            for sid in (topic.get("segment_ids") or [])
            if _segment_start(segments, sid) < half_ms
        ]
        if not early_segs and not returns_to.intersection({name, str(topic.get("id") or "")}):
            continue

        later_hits = _later_coverage(name, topic, windows, segments, half_ms)
        if later_hits:
            continue

        confidence = threshold if name in returns_to or early_segs else threshold * 0.85
        risks.append(
            {
                "risk_id": f"missing_cb_{name.replace(' ', '_')[:40]}",
                "kind": "missing_callback",
                "time_ms": half_ms,
                "window_id": None,
                "theme_id": str(topic.get("id") or name),
                "claim_id": None,
                "confidence": round(confidence, 3),
                "blocking": False,
                "evidence": {
                    "topic": name,
                    "early_segment_ids": early_segs[:5],
                    "expected_return": name in returns_to,
                },
                "suggested_action": {
                    "type": "rerun_stage",
                    "stage": "topic_coverage_audit",
                },
                "status": "open",
            }
        )
    return risks[:8]


def _segment_start(segments: list[dict[str, Any]], seg_id: str) -> int:
    for seg in segments:
        if str(seg.get("segment_id") or seg.get("id")) == seg_id:
            return int(seg.get("start_ms", 0))
    return 0


def _later_coverage(
    name: str,
    topic: dict[str, Any],
    windows: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    half_ms: int,
) -> bool:
    for sid in topic.get("segment_ids") or []:
        if _segment_start(segments, str(sid)) >= half_ms:
            return True
    for win in windows:
        if int(win.get("start_ms", 0)) < half_ms:
            continue
        alignment, _ = score_window_themes(win, [topic])
        if alignment >= 0.35:
            return True
        text = str(win.get("text_span") or "").lower()
        if name.lower() in text:
            return True
    return False
