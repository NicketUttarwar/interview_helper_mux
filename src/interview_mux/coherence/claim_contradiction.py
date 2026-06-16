from __future__ import annotations

import re
from typing import Any

from interview_mux.coherence.theme_alignment import _tokenize

_NEGATION = re.compile(r"\b(not|never|no longer|actually|correction|contradict|instead|rather)\b", re.I)


def detect_claim_contradictions(
    *,
    content_brief: dict[str, Any],
    windows: list[dict[str, Any]],
    duration_ms: int,
    threshold: float,
    blocking: bool,
) -> list[dict[str, Any]]:
    claims = content_brief.get("key_claims") or []
    if not claims or not windows:
        return []

    first_cutoff = int(duration_ms * 0.4) if duration_ms else 0
    later_windows = [w for w in windows if int(w.get("start_ms", 0)) >= first_cutoff]
    risks: list[dict[str, Any]] = []

    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_text = str(claim.get("claim") or "").strip()
        if not claim_text:
            continue
        claim_id = str(claim.get("id") or claim_text[:40])
        claim_tokens = _tokenize(claim_text)
        if not claim_tokens:
            continue

        for win in later_windows:
            text = str(win.get("text_span") or "")
            if not text:
                continue
            win_tokens = _tokenize(text)
            if not win_tokens:
                continue
            overlap = len(claim_tokens & win_tokens) / len(claim_tokens)
            has_negation = bool(_NEGATION.search(text))
            if overlap >= 0.25 and has_negation:
                confidence = round(min(1.0, overlap + 0.35), 3)
            elif overlap >= 0.4 and overlap < 0.55:
                confidence = round(overlap, 3)
            else:
                continue
            if confidence < threshold:
                continue
            time_ms = int(win.get("start_ms", 0))
            risks.append(
                {
                    "risk_id": f"claim_contra_{claim_id}_{win.get('window_id')}",
                    "kind": "claim_contradiction",
                    "time_ms": time_ms,
                    "window_id": win.get("window_id"),
                    "theme_id": None,
                    "claim_id": claim_id,
                    "confidence": confidence,
                    "blocking": blocking and confidence >= threshold,
                    "evidence": {
                        "claim_text": claim_text[:200],
                        "window_text": text[:200],
                        "token_overlap": round(overlap, 3),
                        "negation_detected": has_negation,
                    },
                    "suggested_action": {
                        "type": "rerun_stage",
                        "stage": "content_brief_reanchor",
                    },
                    "status": "open",
                }
            )

    for rel in content_brief.get("topic_relationships") or []:
        if not isinstance(rel, dict):
            continue
        if rel.get("relation") != "contradicts":
            continue
        from_topic = str(rel.get("from_topic") or "")
        to_topic = str(rel.get("to_topic") or "")
        if not from_topic or not to_topic:
            continue
        for win in later_windows:
            text = str(win.get("text_span") or "").lower()
            if from_topic.lower() in text and to_topic.lower() in text:
                time_ms = int(win.get("start_ms", 0))
                risks.append(
                    {
                        "risk_id": f"rel_contra_{from_topic}_{to_topic}_{win.get('window_id')}",
                        "kind": "claim_contradiction",
                        "time_ms": time_ms,
                        "window_id": win.get("window_id"),
                        "theme_id": from_topic,
                        "claim_id": None,
                        "confidence": threshold,
                        "blocking": blocking,
                        "evidence": {
                            "relationship": "contradicts",
                            "from_topic": from_topic,
                            "to_topic": to_topic,
                        },
                        "suggested_action": {
                            "type": "rerun_stage",
                            "stage": "content_brief_reanchor",
                        },
                        "status": "open",
                    }
                )
    return _dedupe_risks(risks)[:10]


def _dedupe_risks(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in risks:
        rid = str(r.get("risk_id") or "")
        if rid in seen:
            continue
        seen.add(rid)
        out.append(r)
    return out
