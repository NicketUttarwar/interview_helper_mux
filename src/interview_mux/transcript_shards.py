"""Contiguous overlapping transcript shards for full-tape analysis coverage.

v2 uses deterministic proactive batching (classification-style), not LLM-arbiter
shard/collate. Shards together cover 100% of transcript characters/words.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from interview_mux.config import merged_config

_IMPORTANCE_RANK = {"must_keep": 0, "should_keep": 1, "optional": 2}


@dataclass(frozen=True)
class TranscriptShard:
    """One contiguous window of transcript text for a proactive analysis pass."""

    shard_index: int
    shard_total: int
    text: str
    char_start: int
    char_end: int
    start_ms: int | None = None
    end_ms: int | None = None

    def meta(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "index": self.shard_index,
            "total": self.shard_total,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }
        if self.start_ms is not None:
            out["start_ms"] = self.start_ms
        if self.end_ms is not None:
            out["end_ms"] = self.end_ms
        return out


def analysis_context_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    return ((cfg or merged_config()).get("analysis") or {}).get("context") or {}


def proactive_decompose_chars(cfg: dict[str, Any] | None = None) -> int:
    return max(1000, int(analysis_context_cfg(cfg).get("proactive_decompose_chars") or 72000))


def segment_text_max_chars(cfg: dict[str, Any] | None = None) -> int:
    return max(40, int(analysis_context_cfg(cfg).get("segment_text_max_chars") or 400))


def transcript_shard_overlap_ratio(cfg: dict[str, Any] | None = None) -> float:
    raw = analysis_context_cfg(cfg).get("transcript_shard_overlap_ratio", 0.08)
    try:
        ratio = float(raw)
    except (TypeError, ValueError):
        ratio = 0.08
    return min(0.25, max(0.0, ratio))


def max_transcript_shards(cfg: dict[str, Any] | None = None) -> int:
    return max(1, int(analysis_context_cfg(cfg).get("max_transcript_shards") or 12))


def needs_transcript_sharding(text: str, cfg: dict[str, Any] | None = None) -> bool:
    return len((text or "").strip()) > proactive_decompose_chars(cfg)


def build_transcript_shards(
    text: str,
    *,
    words: list[dict[str, Any]] | None = None,
    max_chars: int | None = None,
    overlap_ratio: float | None = None,
    max_shards: int | None = None,
    cfg: dict[str, Any] | None = None,
) -> list[TranscriptShard]:
    """Split transcript into contiguous overlapping windows covering all characters.

    Prefer word timestamps when present so shard boundaries land on word edges.
    When text fits in one window, returns a single shard with the full text.
    """
    cleaned = text or ""
    if not cleaned.strip():
        return [
            TranscriptShard(
                shard_index=1,
                shard_total=1,
                text="",
                char_start=0,
                char_end=0,
            )
        ]

    limit = max_chars if max_chars is not None else proactive_decompose_chars(cfg)
    overlap = overlap_ratio if overlap_ratio is not None else transcript_shard_overlap_ratio(cfg)
    ceiling = max_shards if max_shards is not None else max_transcript_shards(cfg)
    limit = max(1000, int(limit))
    ceiling = max(1, int(ceiling))
    overlap = min(0.25, max(0.0, float(overlap)))

    if len(cleaned) <= limit:
        start_ms = end_ms = None
        if words:
            start_ms = _first_ms(words)
            end_ms = _last_ms(words)
        return [
            TranscriptShard(
                shard_index=1,
                shard_total=1,
                text=cleaned,
                char_start=0,
                char_end=len(cleaned),
                start_ms=start_ms,
                end_ms=end_ms,
            )
        ]

    # Grow window size if needed so ceiling shards still cover the full tape.
    min_window = max(1000, int((len(cleaned) + ceiling - 1) / ceiling))
    window = max(limit, min_window)
    step = max(1, int(window * (1.0 - overlap)))

    if words:
        return _shards_from_words(
            cleaned,
            words,
            window_chars=window,
            step_chars=step,
            ceiling=ceiling,
        )
    return _shards_from_text(cleaned, window_chars=window, step_chars=step, ceiling=ceiling)


def _first_ms(words: list[dict[str, Any]]) -> int | None:
    for w in words:
        if isinstance(w, dict) and w.get("start_ms") is not None:
            try:
                return int(w["start_ms"])
            except (TypeError, ValueError):
                continue
    return None


def _last_ms(words: list[dict[str, Any]]) -> int | None:
    for w in reversed(words):
        if isinstance(w, dict) and w.get("end_ms") is not None:
            try:
                return int(w["end_ms"])
            except (TypeError, ValueError):
                continue
        if isinstance(w, dict) and w.get("start_ms") is not None:
            try:
                return int(w["start_ms"])
            except (TypeError, ValueError):
                continue
    return None


def _shards_from_text(
    text: str,
    *,
    window_chars: int,
    step_chars: int,
    ceiling: int,
) -> list[TranscriptShard]:
    n = len(text)
    if n <= window_chars:
        return [
            TranscriptShard(
                shard_index=1,
                shard_total=1,
                text=text,
                char_start=0,
                char_end=n,
            )
        ]

    # Place starts so windows cover [0, n) with overlap; grow window if ceiling binds.
    window = window_chars
    while True:
        step = max(1, int(window * (step_chars / max(window_chars, 1))))
        step = max(1, min(step, window))
        starts: list[int] = [0]
        pos = 0
        while pos + window < n and len(starts) < ceiling:
            pos += step
            if pos >= n:
                break
            if pos > starts[-1]:
                starts.append(pos)
        # Force last window to reach EOF.
        last_start = max(0, n - window)
        if last_start > starts[-1]:
            if len(starts) < ceiling:
                starts.append(last_start)
            else:
                starts[-1] = last_start
        # If ceiling replacement left a hole before the last start, enlarge window.
        hole = False
        for i in range(len(starts) - 1):
            if starts[i] + window < starts[i + 1]:
                hole = True
                break
        if not hole and starts[-1] + window >= n:
            break
        # Grow window to cover with this many shards / largest start gap.
        max_gap = 0
        for i in range(len(starts) - 1):
            max_gap = max(max_gap, starts[i + 1] - starts[i])
        needed = max(int((n + max(len(starts), 1) - 1) / max(len(starts), 1)), max_gap + 1)
        window = max(window + max(1, window // 10), needed)
        if window >= n:
            return [
                TranscriptShard(
                    shard_index=1,
                    shard_total=1,
                    text=text,
                    char_start=0,
                    char_end=n,
                )
            ]

    total = len(starts)
    out: list[TranscriptShard] = []
    for i, start in enumerate(starts):
        if i == total - 1:
            end = n
        else:
            end = min(n, max(start + window, starts[i + 1]))
        out.append(
            TranscriptShard(
                shard_index=i + 1,
                shard_total=total,
                text=text[start:end],
                char_start=start,
                char_end=end,
            )
        )
    return out


def _shards_from_words(
    text: str,
    words: list[dict[str, Any]],
    *,
    window_chars: int,
    step_chars: int,
    ceiling: int,
) -> list[TranscriptShard]:
    """Build shards by walking word tokens so boundaries stay on word edges."""
    tokens: list[tuple[str, int | None, int | None]] = []
    for w in words:
        if not isinstance(w, dict):
            continue
        tok = str(w.get("text") or "").strip()
        if not tok:
            continue
        try:
            sm = int(w["start_ms"]) if w.get("start_ms") is not None else None
        except (TypeError, ValueError):
            sm = None
        try:
            em = int(w["end_ms"]) if w.get("end_ms") is not None else None
        except (TypeError, ValueError):
            em = None
        tokens.append((tok, sm, em))

    if not tokens:
        return _shards_from_text(text, window_chars=window_chars, step_chars=step_chars, ceiling=ceiling)

    # Approximate char positions by joining with spaces (same as sampling helpers).
    joined_parts: list[str] = []
    char_of_token: list[int] = []
    cursor = 0
    for i, (tok, _, _) in enumerate(tokens):
        if i:
            cursor += 1  # space
        char_of_token.append(cursor)
        joined_parts.append(tok)
        cursor += len(tok)
    joined = " ".join(joined_parts)
    # Prefer original full text when it matches closely; else use word join.
    base = text if abs(len(text) - len(joined)) < max(50, len(joined) // 20) else joined
    if base is text:
        # Fall back to char slicing on original text (word edges approximate).
        return _shards_from_text(text, window_chars=window_chars, step_chars=step_chars, ceiling=ceiling)

    n = len(joined)
    token_starts: list[int] = []
    pos = 0
    while pos < n and len(token_starts) < ceiling:
        # Snap to nearest token start at/after pos
        idx = _token_index_at_or_after(char_of_token, pos)
        snap = char_of_token[idx] if idx is not None else pos
        if token_starts and snap <= token_starts[-1]:
            snap = min(n - 1, token_starts[-1] + step_chars)
            idx = _token_index_at_or_after(char_of_token, snap)
            snap = char_of_token[idx] if idx is not None else snap
        token_starts.append(snap)
        if snap + window_chars >= n:
            break
        pos = snap + step_chars

    if token_starts and token_starts[-1] + window_chars < n:
        last_idx = _token_index_at_or_after(char_of_token, max(0, n - window_chars))
        last_start = char_of_token[last_idx] if last_idx is not None else max(0, n - window_chars)
        if last_start > token_starts[-1]:
            if len(token_starts) < ceiling:
                token_starts.append(last_start)
            else:
                token_starts[-1] = last_start

    total = len(token_starts)
    out: list[TranscriptShard] = []
    for i, start in enumerate(token_starts):
        end = n if i == total - 1 else min(n, start + window_chars)
        # Expand end to token boundary
        end_idx = _token_index_covering(char_of_token, tokens, end)
        if end_idx is not None and i < total - 1:
            tok_start = char_of_token[end_idx]
            tok_len = len(tokens[end_idx][0])
            end = min(n, tok_start + tok_len)
        start_tok = _token_index_at_or_after(char_of_token, start) or 0
        end_tok = _token_index_covering(char_of_token, tokens, end) or (len(tokens) - 1)
        out.append(
            TranscriptShard(
                shard_index=i + 1,
                shard_total=total,
                text=joined[start:end],
                char_start=start,
                char_end=end,
                start_ms=tokens[start_tok][1],
                end_ms=tokens[end_tok][2] or tokens[end_tok][1],
            )
        )
    return out


def _token_index_at_or_after(char_of_token: list[int], pos: int) -> int | None:
    if not char_of_token:
        return None
    for i, c in enumerate(char_of_token):
        if c >= pos:
            return i
    return len(char_of_token) - 1


def _token_index_covering(
    char_of_token: list[int],
    tokens: list[tuple[str, int | None, int | None]],
    pos: int,
) -> int | None:
    if not char_of_token:
        return None
    best = 0
    for i, c in enumerate(char_of_token):
        if c <= pos:
            best = i
        else:
            break
    return best


def merge_talking_points_artifacts(parts: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge shard talking_points outputs: dedupe by title, prefer higher importance."""
    by_title: dict[str, dict[str, Any]] = {}
    hard_excludes: list[dict[str, Any]] = []
    warnings: list[str] = []
    summaries: list[str] = []
    through_lines: list[str] = []

    for part in parts:
        if not isinstance(part, dict):
            continue
        summary = str(part.get("strategy_summary") or "").strip()
        if summary:
            summaries.append(summary)
        through = str(part.get("through_line") or "").strip()
        if through:
            through_lines.append(through)
        for tp in part.get("talking_points") or []:
            if not isinstance(tp, dict):
                continue
            title = str(tp.get("title") or "").strip()
            if not title:
                continue
            key = _norm_title(title)
            existing = by_title.get(key)
            if existing is None:
                by_title[key] = dict(tp)
                continue
            if _importance_rank(tp.get("importance")) < _importance_rank(existing.get("importance")):
                merged = dict(tp)
            else:
                merged = dict(existing)
            # Prefer richer why / evidence
            if len(str(tp.get("why_it_matters") or "")) > len(str(merged.get("why_it_matters") or "")):
                merged["why_it_matters"] = tp.get("why_it_matters")
            quotes_a = list(existing.get("evidence_quotes") or [])
            quotes_b = list(tp.get("evidence_quotes") or [])
            seen_q: set[str] = set()
            merged_quotes: list[str] = []
            for q in quotes_a + quotes_b:
                qs = str(q).strip()
                if qs and qs not in seen_q:
                    seen_q.add(qs)
                    merged_quotes.append(qs)
            if merged_quotes:
                merged["evidence_quotes"] = merged_quotes
            by_title[key] = merged
        for hx in part.get("hard_excludes") or []:
            if isinstance(hx, dict):
                hard_excludes.append(hx)
        for w in part.get("warnings") or []:
            ws = str(w).strip()
            if ws and ws not in warnings:
                warnings.append(ws)

    points = list(by_title.values())
    points.sort(key=lambda p: (_importance_rank(p.get("importance")), str(p.get("title") or "")))
    if not points:
        points = [
            {
                "talking_point_id": "tp_merged_empty",
                "title": "Coverage incomplete",
                "importance": "optional",
                "why_it_matters": "Shard merge produced no talking points",
            }
        ]

    strategy = " ".join(summaries).strip()
    if len(strategy) > 1200:
        strategy = strategy[:1197].rstrip() + "…"
    if not strategy:
        strategy = "Merged talking points across full transcript shards."

    through_line = through_lines[0] if through_lines else strategy.split(".")[0][:200]
    out: dict[str, Any] = {
        "strategy_summary": strategy,
        "through_line": through_line,
        "talking_points": points,
    }
    if hard_excludes:
        out["hard_excludes"] = hard_excludes
    if warnings:
        out["warnings"] = warnings
    return out


def merge_content_brief_artifacts(parts: list[dict[str, Any]]) -> dict[str, Any]:
    """Union topics/claims/entities from shard content_brief outputs."""
    theses: list[str] = []
    topics_by_name: dict[str, dict[str, Any]] = {}
    claims: list[dict[str, Any]] = []
    claim_keys: set[str] = set()
    relationships: list[dict[str, Any]] = []
    rel_keys: set[str] = set()
    entities: list[Any] = []
    entity_keys: set[str] = set()
    era_tags: list[Any] = []
    moat: str | None = None

    for part in parts:
        if not isinstance(part, dict):
            continue
        thesis = str(part.get("thesis") or "").strip()
        if thesis:
            theses.append(thesis)
        if moat is None and part.get("strategic_moat_concept"):
            moat = str(part.get("strategic_moat_concept"))
        for t in part.get("topics") or []:
            if not isinstance(t, dict) or not t.get("name"):
                continue
            key = str(t["name"]).strip().lower()
            existing = topics_by_name.get(key)
            if existing is None or len(str(t.get("summary") or "")) > len(str(existing.get("summary") or "")):
                topics_by_name[key] = dict(t)
            else:
                # Merge segment_ids
                ids = list(existing.get("segment_ids") or [])
                for sid in t.get("segment_ids") or []:
                    if sid not in ids:
                        ids.append(sid)
                if ids:
                    existing["segment_ids"] = ids
        for c in part.get("key_claims") or []:
            if not isinstance(c, dict):
                continue
            ck = _norm_title(str(c.get("claim") or c.get("id") or ""))
            if not ck or ck in claim_keys:
                continue
            claim_keys.add(ck)
            claims.append(dict(c))
        for rel in part.get("topic_relationships") or []:
            if not isinstance(rel, dict):
                continue
            rk = f"{rel.get('from_topic')}|{rel.get('to_topic')}|{rel.get('relation')}"
            if rk in rel_keys:
                continue
            rel_keys.add(rk)
            relationships.append(dict(rel))
        for ent in part.get("entities") or []:
            ek = str(ent.get("name") if isinstance(ent, dict) else ent).strip().lower()
            if not ek or ek in entity_keys:
                continue
            entity_keys.add(ek)
            entities.append(ent)
        for tag in part.get("era_tags") or []:
            era_tags.append(tag)

    if not theses:
        thesis = "Interview content brief"
    elif len(theses) == 1:
        thesis = theses[0]
    else:
        joined = " | ".join(theses)
        thesis = joined if len(joined) <= 800 else theses[-1]

    topics = list(topics_by_name.values())
    if not topics:
        topics = [{"name": "general", "summary": thesis}]

    out: dict[str, Any] = {"thesis": thesis, "topics": topics}
    if claims:
        out["key_claims"] = claims
    if relationships:
        out["topic_relationships"] = relationships
    if entities:
        out["entities"] = entities
    if era_tags:
        out["era_tags"] = era_tags
    if moat:
        out["strategic_moat_concept"] = moat
    return out


def _norm_title(title: str) -> str:
    return " ".join(title.lower().split())


def _importance_rank(value: Any) -> int:
    return _IMPORTANCE_RANK.get(str(value or "").strip().lower(), 9)


__all__ = [
    "TranscriptShard",
    "analysis_context_cfg",
    "build_transcript_shards",
    "max_transcript_shards",
    "merge_content_brief_artifacts",
    "merge_talking_points_artifacts",
    "needs_transcript_sharding",
    "proactive_decompose_chars",
    "segment_text_max_chars",
    "transcript_shard_overlap_ratio",
]
