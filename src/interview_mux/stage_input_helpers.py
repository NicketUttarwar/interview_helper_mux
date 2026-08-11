"""Small helpers for stage input shaping (v2 — no volley/disfluency)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from interview_mux.run_context import RunContext


@dataclass
class StagePlan:
    task_line: str = ""
    prior_stages: tuple[str, ...] = ()
    profile_keys: tuple[str, ...] = ()
    investigation_kinds: frozenset[str] = field(default_factory=frozenset)
    max_investigations: int = 0


STAGE_PLANS: dict[str, StagePlan] = {}


def plan_for_stage(stage_key: str) -> StagePlan:
    return STAGE_PLANS.get(stage_key, StagePlan())


def _format_profile_slice(state: dict[str, Any], profile_keys: tuple[str, ...]) -> str:
    if not profile_keys:
        return ""
    parts: list[str] = []
    for key in profile_keys:
        val = state.get(key)
        if val:
            parts.append(f"{key}: {val}")
    return "\n".join(parts)[:2000]


def transcript_quality_for_ctx(ctx: RunContext) -> dict[str, Any]:
    """Optional transcript quality summary for LLM stage inputs."""
    out: dict[str, Any] = {}
    if ctx.artifact_exists("transcript/review_queue.json"):
        try:
            q = ctx.read_json("transcript/review_queue.json")
            if isinstance(q, dict):
                chunks = q.get("chunks") if isinstance(q.get("chunks"), list) else None
                items = q.get("items") if isinstance(q.get("items"), list) else None
                out["review_queue_size"] = len(chunks if chunks is not None else (items or []))
        except Exception:
            pass
    if ctx.artifact_exists("analysis/run_golden_facts.json"):
        try:
            gf = ctx.read_json("analysis/run_golden_facts.json")
            if isinstance(gf, dict):
                run = gf.get("run") if isinstance(gf.get("run"), dict) else {}
                out["golden_facts"] = {
                    k: run.get(k)
                    for k in (
                        "has_in_flow_vernacular",
                        "has_non_english_spans",
                        "has_uncommon_english",
                        "has_high_passion",
                        "has_pull_quote",
                        "has_affect_burst",
                        "has_crosstalk",
                        "has_bleed",
                        "has_unintelligible",
                        "has_payoff",
                        "has_sensitive_disclosure",
                        "enforcement_mode",
                        "vernacular_must_keep_segment_ids",
                        "special_keywords",
                        "special_speaker_flow_ids",
                    )
                    if k in run
                }
        except Exception:
            pass
    if ctx.artifact_exists("transcript/protected_zones.json"):
        try:
            pz = ctx.read_json("transcript/protected_zones.json")
            if isinstance(pz, dict):
                zones = pz.get("zones") or []
                out["protected_zones_summary"] = [
                    {
                        "zone_id": z.get("zone_id"),
                        "speaker_flow_id": z.get("speaker_flow_id"),
                        "start_ms": z.get("start_ms"),
                        "end_ms": z.get("end_ms"),
                        "keywords": (z.get("keywords") or [])[:8],
                        "segment_ids": z.get("segment_ids") or [],
                        "retention": z.get("retention"),
                    }
                    for z in zones
                    if isinstance(z, dict)
                ][:40]
        except Exception:
            pass
    return out


def compact_transcript_for_boundaries(transcript: dict[str, Any]) -> dict[str, Any]:
    """Compact STT for boundary LLM calls.

    Long interviews blow flagship context when every word is serialized (~140k+
    tokens). Prefer contiguous speaker turns with timing; keep a short word
    sample only when the interview is short enough to fit safely.
    """
    words_in = transcript.get("words") or []
    words: list[dict[str, Any]] = []
    for row in words_in:
        if not isinstance(row, dict) or not row.get("text"):
            continue
        words.append(
            {
                "text": row.get("text"),
                "start_ms": row.get("start_ms"),
                "end_ms": row.get("end_ms"),
                "speaker_id": row.get("speaker_id"),
            }
        )
    text = str(transcript.get("text") or "").strip()
    if not text and words:
        text = " ".join(str(w.get("text", "")) for w in words)
    duration_ms = int(words[-1].get("end_ms") or 0) if words else 0

    turns: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for w in words:
        sid = w.get("speaker_id")
        if current is None or current.get("speaker_id") != sid:
            if current is not None:
                turns.append(current)
            current = {
                "speaker_id": sid,
                "start_ms": w.get("start_ms"),
                "end_ms": w.get("end_ms"),
                "text": str(w.get("text") or ""),
                "word_count": 1,
            }
        else:
            current["end_ms"] = w.get("end_ms")
            current["text"] = f"{current['text']} {w.get('text') or ''}".strip()
            current["word_count"] = int(current.get("word_count") or 0) + 1
    if current is not None:
        turns.append(current)

    # Word arrays dominate tokens; keep them only for short sources.
    # ~1500 words ≈ safe with prompt pack + schema under a 200k context window.
    include_words = len(words) <= 1500
    out: dict[str, Any] = {
        "text": text,
        "word_count": len(words),
        "duration_ms": duration_ms,
        "turn_count": len(turns),
        "turns": turns,
        "timing_resolution": "words" if include_words else "speaker_turns",
    }
    if include_words:
        out["words"] = words
    return out


def attach_disfluency_context(payload: dict[str, Any], ctx: RunContext) -> dict[str, Any]:
    """Attach this-tape must-keep IDs and STT island excerpts (not pipeline metadata)."""
    out = dict(payload)
    try:
        from interview_mux.hard_keep import hard_keep_segment_ids

        keeps = sorted(hard_keep_segment_ids(ctx))
        if keeps:
            out["must_keep_segment_ids"] = keeps
    except Exception:
        keeps = []
    excerpts: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    if ctx.artifact_exists("segments/manifest.json"):
        try:
            man = ctx.read_json("segments/manifest.json")
            by_id = {
                str(s.get("segment_id") or ""): s
                for s in ((man or {}).get("segments") or [])
                if isinstance(s, dict) and s.get("segment_id")
            }
        except Exception:
            by_id = {}
    island_ids: list[str] = []
    for rel in (
        "transcript/low_conf_islands.json",
        "transcript/vernacular_islands.json",
        "analysis/stt_lexicon_islands.json",
    ):
        if not ctx.artifact_exists(rel):
            continue
        try:
            doc = ctx.read_json(rel)
        except Exception:
            continue
        rows = doc.get("islands") if isinstance(doc, dict) else doc
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("segment_id") or "")
            if sid:
                island_ids.append(sid)
            text = str(row.get("text") or row.get("excerpt") or "").strip()
            if not text and sid and sid in by_id:
                text = str(by_id[sid].get("text") or "")[:280]
            if text:
                excerpts.append({"segment_id": sid, "excerpt": text[:280]})
            if len(excerpts) >= 24:
                break
        if len(excerpts) >= 24:
            break
    if not excerpts:
        for sid in (keeps or [])[:12]:
            text = str((by_id.get(sid) or {}).get("text") or "").strip()
            if text:
                excerpts.append({"segment_id": sid, "excerpt": text[:280]})
    if excerpts:
        out["stt_island_excerpts"] = excerpts
    if island_ids:
        out["stt_island_segment_ids"] = sorted(set(island_ids))[:40]
    return out


def interviewer_sample_lines(ctx: RunContext, *, limit: int = 8) -> list[str]:
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return []
    try:
        report = ctx.read_json("understanding/gap_report.json")
    except Exception:
        return []
    lines: list[str] = []
    for row in report.get("interviewer_lines") or []:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or row.get("line") or "").strip()
        if text:
            lines.append(text[:240])
        if len(lines) >= limit:
            break
    return lines


def truncation_flags_for_volley(volley: list[dict[str, str]] | None) -> list[str]:
    _ = volley
    return []


def volley_char_estimate(volley: list[dict[str, str]] | None) -> int:
    total = 0
    for msg in volley or []:
        if isinstance(msg, dict):
            total += len(str(msg.get("content") or ""))
    return total
