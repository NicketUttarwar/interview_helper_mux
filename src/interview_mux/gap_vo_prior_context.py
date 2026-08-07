"""Prior native-segment context for synthetic gap VO LLM calls and density seeds.

Plan 1: every framing line that targets segment S must see the immediate prior
ordered native segment P (text + impact/complete-thought tags) so VO copy stays
courteous after mic-drop moments instead of interruptive density stock.
"""

from __future__ import annotations

import re
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

GAP_VO_CONTEXT_AUDIT_REL = "understanding/gap_vo_context_audit.json"

# Interruptive openers forbidden after a complete / impactful prior native close.
INTERRUPTIVE_OPENER_RE = re.compile(
    r"^\s*(let me pause you there|hold on(?: a (?:second|sec|moment))?|stop right there|"
    r"wait(?: a (?:second|sec|moment))?|hang on)\b",
    re.IGNORECASE,
)

_INCOMPLETE_TAIL_TOKENS = frozenset(
    {
        "if",
        "and",
        "but",
        "or",
        "because",
        "that",
        "when",
        "while",
        "so",
        "as",
        "than",
        "to",
        "of",
        "the",
        "a",
        "an",
        "my",
        "our",
        "their",
        "i",
        "we",
        "he",
        "she",
        "it",
        "they",
    }
)

_MIC_DROP_HINT_RE = re.compile(
    r"\b(higher than|lower than|never|nobody|nothing|realized|truth is|bottom line|"
    r"cash in|account was|that was the|turning point)\b",
    re.IGNORECASE,
)

GAP_FRAMING_PRIOR_STAGES = frozenset(
    {
        "gap_framing_compose",
        "optimal_questions",
        "missing_framing",
    }
)


def prior_context_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = ((cfg or merged_config()).get("analysis") or {}).get("gap_framing") or {}
    block = raw.get("prior_native_context") if isinstance(raw.get("prior_native_context"), dict) else {}
    defaults = {
        "enabled": True,
        "volley_turns_enabled": True,
        "end_window_chars": 420,
        "full_text_max_chars": 900,
        "micro_max_ms": 2000,
        "micro_max_words": 4,
        "impact_min_words": 18,
        "impact_min_duration_ms": 8000,
        "rewrite_density_seeds": True,
        "relocate_micro_targets": True,
    }
    return {**defaults, **block}


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def _last_token(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9']+", text or "")
    return words[-1].lower() if words else ""


DEFAULT_PAUSE_SPLIT_MS = 400


def ends_complete_thought(
    text: str,
    *,
    next_pause_ms: int | None = None,
    pause_split_ms: int = DEFAULT_PAUSE_SPLIT_MS,
) -> bool:
    """True when text ends on terminal punctuation, or on a non-hanging word
    followed by a pause long enough to read as a finished thought.

    Word choice alone (e.g. any noun/verb close) is no longer sufficient —
    without terminal punctuation we require actual pause evidence
    (``next_pause_ms >= pause_split_ms``) so mid-sentence commas/breaths
    aren't mistaken for a complete thought.
    """
    stripped = (text or "").strip()
    if not stripped:
        return False
    if stripped[-1] in ".!?…":
        return True
    if _last_token(stripped) in _INCOMPLETE_TAIL_TOKENS:
        return False
    return next_pause_ms is not None and next_pause_ms >= pause_split_ms


# Backward-compatible private alias
_ends_complete_thought = ends_complete_thought


def is_micro_segment(seg: dict[str, Any] | None, *, cfg: dict[str, Any]) -> bool:
    if not isinstance(seg, dict):
        return False
    text = str(seg.get("text") or "").strip()
    words = _word_count(text)
    dur = max(0, int(seg.get("end_ms") or 0) - int(seg.get("start_ms") or 0))
    if words <= int(cfg.get("micro_max_words") or 4):
        return True
    if dur > 0 and dur < int(cfg.get("micro_max_ms") or 2000) and words <= 8:
        return True
    return False


_is_micro_segment = is_micro_segment


def looks_like_impact_beat(
    seg: dict[str, Any] | None,
    *,
    cfg: dict[str, Any],
    next_pause_ms: int | None = None,
) -> bool:
    if not isinstance(seg, dict):
        return False
    text = str(seg.get("text") or "").strip()
    if not text or not _ends_complete_thought(text, next_pause_ms=next_pause_ms):
        return False
    words = _word_count(text)
    dur = max(0, int(seg.get("end_ms") or 0) - int(seg.get("start_ms") or 0))
    if words < int(cfg.get("impact_min_words") or 18):
        return False
    if dur > 0 and dur < int(cfg.get("impact_min_duration_ms") or 8000):
        # Short but punchy complete close can still be impactful.
        if not _MIC_DROP_HINT_RE.search(text):
            return False
    if _MIC_DROP_HINT_RE.search(text):
        return True
    # Complete guest answer of decent length with a strong closing sentence.
    last_sentence = re.split(r"[.!?]", text)[-1] if "." in text or "!" in text or "?" in text else text
    if _word_count(last_sentence) >= 8 and words >= int(cfg.get("impact_min_words") or 18):
        return True
    return False


_looks_like_impact_beat = looks_like_impact_beat


def _chapter_title_for(segment_id: str, chapters: list[dict[str, Any]] | None) -> str | None:
    if not chapters:
        return None
    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        ids = [str(s) for s in (ch.get("segment_ids") or [])]
        if segment_id in ids:
            title = str(ch.get("title") or ch.get("name") or "").strip()
            return title or None
    return None


def _end_window(text: str, *, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[-max_chars:].lstrip()


def _quote_span(text: str, *, max_chars: int = 180) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    # Prefer last sentence.
    parts = re.split(r"(?<=[.!?])\s+", t)
    last = (parts[-1] if parts else t).strip()
    if len(last) > max_chars:
        return last[-max_chars:].lstrip()
    return last


def _next_segment_pause_ms(
    seg_id: str,
    *,
    ordered_ids: list[str],
    segments_by_id: dict[str, dict[str, Any]],
) -> int | None:
    """Gap in ms between ``seg_id``'s end and the next ordered segment's start."""
    if seg_id not in ordered_ids:
        return None
    idx = ordered_ids.index(seg_id)
    if idx + 1 >= len(ordered_ids):
        return None
    seg = segments_by_id.get(seg_id)
    nxt = segments_by_id.get(ordered_ids[idx + 1])
    if not isinstance(seg, dict) or not isinstance(nxt, dict):
        return None
    try:
        gap = int(nxt.get("start_ms") or 0) - int(seg.get("end_ms") or 0)
    except (TypeError, ValueError):
        return None
    return max(0, gap)


def build_prior_native_context(
    *,
    target_segment_id: str,
    ordered_ids: list[str],
    segments_by_id: dict[str, dict[str, Any]],
    chapters: list[dict[str, Any]] | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build prior_native_context packet for VO targeting ``target_segment_id``.

    Walks backward past micro/backchannel segments so a VO before a real answer
    still sees the last substantive native beat (e.g. skip \"Okay.\" to the mic-drop).
    """
    settings = cfg or prior_context_cfg()
    if not settings.get("enabled", True):
        return None
    tid = str(target_segment_id or "").strip()
    if not tid or tid not in ordered_ids:
        return None
    idx = ordered_ids.index(tid)
    if idx <= 0:
        return None
    prior_id = None
    for cand in reversed(ordered_ids[:idx]):
        if _is_micro_segment(segments_by_id.get(cand), cfg=settings):
            continue
        prior_id = cand
        break
    if prior_id is None:
        # Only micros behind — still expose the immediate neighbor.
        prior_id = ordered_ids[idx - 1]
    prior = segments_by_id.get(prior_id)
    if not isinstance(prior, dict):
        return None
    text = str(prior.get("text") or "").strip()
    full_max = int(settings.get("full_text_max_chars") or 900)
    end_max = int(settings.get("end_window_chars") or 420)
    next_pause_ms = _next_segment_pause_ms(
        prior_id, ordered_ids=ordered_ids, segments_by_id=segments_by_id
    )
    complete = _ends_complete_thought(text, next_pause_ms=next_pause_ms)
    impact = _looks_like_impact_beat(prior, cfg=settings, next_pause_ms=next_pause_ms)
    return {
        "segment_id": prior_id,
        "speaker_role": str(prior.get("speaker_role") or prior.get("type") or "") or None,
        "speaker_id": str(prior.get("speaker_id") or "") or None,
        "text": text[:full_max] if text else "",
        "end_window_text": _end_window(text, max_chars=end_max),
        "start_ms": int(prior.get("start_ms") or 0),
        "end_ms": int(prior.get("end_ms") or 0),
        "chapter_title": _chapter_title_for(prior_id, chapters),
        "prior_impact_beat": bool(impact),
        "prior_complete_thought": bool(complete),
        "quote_span": _quote_span(text) if impact or complete else _quote_span(text, max_chars=120),
        "target_segment_id": tid,
        "target_is_micro": _is_micro_segment(segments_by_id.get(tid), cfg=settings),
    }


def next_substantive_target(
    *,
    preferred_id: str,
    ordered_ids: list[str],
    segments_by_id: dict[str, dict[str, Any]],
    cfg: dict[str, Any] | None = None,
) -> str:
    """If preferred target is a micro/backchannel, relocate to the next substantive segment."""
    settings = cfg or prior_context_cfg()
    if not settings.get("relocate_micro_targets", True):
        return preferred_id
    tid = str(preferred_id or "").strip()
    if not tid or tid not in ordered_ids:
        return preferred_id
    if not _is_micro_segment(segments_by_id.get(tid), cfg=settings):
        return tid
    idx = ordered_ids.index(tid)
    for sid in ordered_ids[idx + 1 :]:
        if not _is_micro_segment(segments_by_id.get(sid), cfg=settings):
            return sid
    # Fall back to previous substantive if nothing after.
    for sid in reversed(ordered_ids[:idx]):
        if not _is_micro_segment(segments_by_id.get(sid), cfg=settings):
            return sid
    return tid


def load_ordered_and_segments(ctx: RunContext) -> tuple[list[str], dict[str, dict[str, Any]], list[dict[str, Any]] | None]:
    ordered: list[str] = []
    chapters: list[dict[str, Any]] | None = None
    if ctx.artifact_exists("master/selection.json"):
        sel = ctx.read_json("master/selection.json")
        if isinstance(sel, dict):
            ordered = [str(s) for s in (sel.get("ordered_segment_ids") or []) if s]
            ch = sel.get("chapters")
            if isinstance(ch, list):
                chapters = [c for c in ch if isinstance(c, dict)]
    if not chapters and ctx.artifact_exists("master/narrative_plan.json"):
        plan = ctx.read_json("master/narrative_plan.json")
        if isinstance(plan, dict) and isinstance(plan.get("chapters"), list):
            chapters = [c for c in plan["chapters"] if isinstance(c, dict)]
    by_id: dict[str, dict[str, Any]] = {}
    if ctx.artifact_exists("segments/manifest.json"):
        man = ctx.read_json("segments/manifest.json")
        for row in (man.get("segments") or []) if isinstance(man, dict) else []:
            if isinstance(row, dict) and row.get("segment_id"):
                by_id[str(row["segment_id"])] = row
    if not ordered:
        ordered = list(by_id.keys())
    return ordered, by_id, chapters


def build_prior_native_contexts_map(ctx: RunContext) -> dict[str, dict[str, Any]]:
    """Map target_segment_id → prior_native_context for every ordered segment after the first."""
    settings = prior_context_cfg()
    if not settings.get("enabled", True):
        return {}
    ordered, by_id, chapters = load_ordered_and_segments(ctx)
    out: dict[str, dict[str, Any]] = {}
    for tid in ordered:
        pkt = build_prior_native_context(
            target_segment_id=tid,
            ordered_ids=ordered,
            segments_by_id=by_id,
            chapters=chapters,
            cfg=settings,
        )
        if pkt:
            out[tid] = pkt
    return out


def attach_prior_native_contexts_to_payload(ctx: RunContext, payload: dict[str, Any]) -> dict[str, Any]:
    """Attach prior_native_contexts (+ courtesy policy) onto a gap framing stage input."""
    settings = prior_context_cfg()
    if not settings.get("enabled", True):
        return payload
    contexts = build_prior_native_contexts_map(ctx)
    payload["prior_native_contexts"] = contexts
    payload["prior_native_context_policy"] = {
        "require_prior_context": True,
        "forbid_interruptive_openers_after_impact": True,
        "forbidden_openers": [
            "Let me pause you there",
            "Hold on",
            "Stop right there",
            "Wait",
            "Hang on",
        ],
        "prefer_acknowledge_or_soft_bridge_after_impact": True,
        "relocate_micro_targets": bool(settings.get("relocate_micro_targets", True)),
        "notes": (
            "For each interviewer line targeting segment S, use prior_native_contexts[S] "
            "(immediate prior ordered native segment). After prior_impact_beat or a complete "
            "strong close, write courteous follow-through only — never interruptive stock."
        ),
    }
    # Compact highlight list for volley conditioning (impact beats first).
    highlights: list[dict[str, Any]] = []
    for tid, pkt in contexts.items():
        if not pkt.get("prior_impact_beat") and not pkt.get("prior_complete_thought"):
            continue
        highlights.append(
            {
                "before_target": tid,
                "prior_segment_id": pkt.get("segment_id"),
                "prior_impact_beat": pkt.get("prior_impact_beat"),
                "prior_complete_thought": pkt.get("prior_complete_thought"),
                "quote_span": pkt.get("quote_span"),
                "chapter_title": pkt.get("chapter_title"),
                "target_is_micro": pkt.get("target_is_micro"),
            }
        )
    if highlights:
        payload["prior_impact_highlights"] = highlights[:40]
    return payload


def build_target_native_context(
    *,
    target_segment_id: str,
    segments_by_id: dict[str, dict[str, Any]],
    chapters: list[dict[str, Any]] | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Upcoming native clip packet so VO can unlock it without restating it."""
    settings = cfg or prior_context_cfg()
    tid = str(target_segment_id or "").strip()
    seg = segments_by_id.get(tid)
    if not tid or not isinstance(seg, dict):
        return None
    text = str(seg.get("text") or seg.get("text_excerpt") or "").strip()
    full_max = int(settings.get("full_text_max_chars") or 900)
    return {
        "segment_id": tid,
        "speaker_role": str(seg.get("speaker_role") or seg.get("type") or "") or None,
        "speaker_id": str(seg.get("speaker_id") or "") or None,
        "type": seg.get("type"),
        "text": text[:full_max] if text else "",
        "start_ms": int(seg.get("start_ms") or 0),
        "end_ms": int(seg.get("end_ms") or 0),
        "chapter_title": _chapter_title_for(tid, chapters),
        "quote_span": _quote_span(text, max_chars=160),
    }


def build_target_native_contexts_map(
    ctx: RunContext,
    *,
    segment_ids: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    settings = prior_context_cfg()
    ordered, by_id, chapters = load_ordered_and_segments(ctx)
    ids = list(segment_ids) if segment_ids is not None else list(ordered)
    out: dict[str, dict[str, Any]] = {}
    for tid in ids:
        pkt = build_target_native_context(
            target_segment_id=str(tid),
            segments_by_id=by_id,
            chapters=chapters,
            cfg=settings,
        )
        if pkt:
            out[str(tid)] = pkt
    return out


def build_vo_missions_map(
    ctx: RunContext,
    *,
    segment_ids: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Per-target mission: what the synthetic line must accomplish before the clip."""
    evals_by_id: dict[str, dict[str, Any]] = {}
    if ctx.artifact_exists("understanding/gap_evaluations.json"):
        doc = ctx.read_json("understanding/gap_evaluations.json")
        if isinstance(doc, dict):
            for row in doc.get("evaluations") or []:
                if isinstance(row, dict) and row.get("segment_id"):
                    evals_by_id[str(row["segment_id"])] = row

    tp_titles: list[str] = []
    if ctx.artifact_exists("understanding/talking_points.json"):
        tp = ctx.read_json("understanding/talking_points.json")
        if isinstance(tp, dict):
            for row in tp.get("talking_points") or []:
                if isinstance(row, dict) and row.get("title"):
                    tp_titles.append(str(row["title"]))

    ordered, _, _ = load_ordered_and_segments(ctx)
    ids = list(segment_ids) if segment_ids is not None else list(ordered)
    out: dict[str, dict[str, Any]] = {}
    for tid in ids:
        sid = str(tid)
        ev = evals_by_id.get(sid) or {}
        confusion = str(ev.get("listener_confusion") or "").strip()
        gap_type = str(ev.get("gap_type") or "").strip()
        recommended = str(ev.get("recommended_framing") or "").strip()
        mission = recommended or confusion
        if not mission:
            if gap_type and gap_type not in ("ok_with_light_bridge", "none", "ok"):
                mission = f"Orient the listener for gap_type={gap_type} before the next native beat."
            else:
                mission = "Add conversational value that unlocks the next native clip without restating it."
        out[sid] = {
            "segment_id": sid,
            "gap_type": gap_type or None,
            "severity": ev.get("severity"),
            "listener_confusion": confusion or None,
            "recommended_framing": recommended or None,
            "mission": mission,
            "related_talking_point_titles": tp_titles[:8] if tp_titles else [],
        }
    return out


def attach_vo_partner_context_to_payload(
    ctx: RunContext,
    payload: dict[str, Any],
    *,
    segment_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Attach target clip text + VO missions so compose can act as a conversation partner."""
    targets = build_target_native_contexts_map(ctx, segment_ids=segment_ids)
    missions = build_vo_missions_map(ctx, segment_ids=segment_ids)
    if targets:
        payload["target_native_contexts"] = targets
    if missions:
        payload["vo_missions"] = missions
    payload["vo_partner_policy"] = {
        "must_add_conversational_value": True,
        "never_restate_next_clip": True,
        "require_rationale": True,
        "allowed_pov": ["host_first_person", "host_second_person", "expository_third_person"],
        "notes": (
            "Each synthetic line is a conversation-partner turn: unlock stakes, ask a real "
            "follow-up, define assumed knowledge, or bridge topics. Use target_native_contexts[S] "
            "to know what the next clip already says — do not paraphrase it. Honor vo_missions[S]."
        ),
    }
    if "talking_points" not in payload and ctx.artifact_exists("understanding/talking_points.json"):
        tp = ctx.read_json("understanding/talking_points.json")
        if isinstance(tp, dict):
            payload["talking_points"] = {
                "strategy_summary": tp.get("strategy_summary"),
                "through_line": tp.get("through_line"),
                "talking_points": [
                    {
                        "talking_point_id": row.get("talking_point_id"),
                        "title": row.get("title"),
                        "importance": row.get("importance"),
                        "why_it_matters": row.get("why_it_matters"),
                    }
                    for row in (tp.get("talking_points") or [])
                    if isinstance(row, dict)
                ][:40],
            }
    return payload


def vo_value_gate_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = ((cfg or merged_config()).get("analysis") or {}).get("gap_framing") or {}
    block = raw.get("vo_value_gate") if isinstance(raw.get("vo_value_gate"), dict) else {}
    defaults = {
        "enabled": True,
        "require_rationale": True,
        "restate_overlap_max": 0.42,
        "restate_min_vo_tokens": 6,
        "allow_summary_overlap_max": 0.62,
        "enforce_courtesy": True,
    }
    return {**defaults, **block}


def _tokenize_for_overlap(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def vo_target_overlap_ratio(vo_text: str, target_text: str) -> float:
    """Fraction of VO tokens that also appear in the target clip (content-word overlap)."""
    vo_toks = _tokenize_for_overlap(vo_text)
    tgt_toks = set(_tokenize_for_overlap(target_text))
    if len(vo_toks) < 1 or not tgt_toks:
        return 0.0
    # Drop ultra-common stopwords from VO side so short bridges aren't false-positives.
    stop = {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "to",
        "of",
        "in",
        "on",
        "for",
        "is",
        "are",
        "was",
        "were",
        "that",
        "this",
        "it",
        "you",
        "we",
        "i",
        "he",
        "she",
        "they",
        "what",
        "how",
        "why",
        "when",
        "with",
        "as",
        "at",
        "be",
        "so",
        "if",
        "from",
        "about",
        "just",
        "like",
        "here",
        "next",
        "now",
    }
    content = [t for t in vo_toks if t not in stop]
    if not content:
        return 0.0
    hits = sum(1 for t in content if t in tgt_toks)
    return hits / len(content)


def vo_value_violations(
    lines: list[dict[str, Any]],
    *,
    segments_by_id: dict[str, dict[str, Any]] | None = None,
    cfg: dict[str, Any] | None = None,
) -> list[str]:
    """Deterministic VO partner quality: rationale + no-restate + courtesy."""
    settings = vo_value_gate_cfg(cfg)
    if not settings.get("enabled", True):
        return []
    errs: list[str] = []
    segs = segments_by_id or {}
    overlap_max = float(settings.get("restate_overlap_max") or 0.42)
    summary_max = float(settings.get("allow_summary_overlap_max") or 0.62)
    min_toks = int(settings.get("restate_min_vo_tokens") or 6)

    if settings.get("enforce_courtesy", True):
        errs.extend(courtesy_violations(lines))

    for line in lines:
        if not isinstance(line, dict):
            continue
        lid = str(line.get("line_id") or line.get("targets_segment_id") or "?")
        text = str(line.get("text") or "").strip()
        if settings.get("require_rationale", True):
            rationale = str(line.get("rationale") or "").strip()
            if text and not rationale:
                errs.append(f"{lid}: missing rationale (conversation-partner value)")
        tid = str(line.get("targets_segment_id") or line.get("segment_id") or "").strip()
        if not tid or not text:
            continue
        target = segs.get(tid) or {}
        target_text = str(target.get("text") or target.get("text_excerpt") or "")
        if not target_text:
            continue
        vo_toks = _tokenize_for_overlap(text)
        if len(vo_toks) < min_toks:
            continue
        ratio = vo_target_overlap_ratio(text, target_text)
        category = str(line.get("line_category") or "").strip().lower()
        limit = summary_max if category == "segment_summary" else overlap_max
        if ratio > limit:
            errs.append(
                f"{lid}: VO restates next clip (overlap={ratio:.2f} > {limit:.2f} for {category or 'line'})"
            )
    return errs


def is_interruptive_opener(text: str) -> bool:
    return bool(INTERRUPTIVE_OPENER_RE.match(text or ""))


def courtesy_seed_text(prior: dict[str, Any] | None, *, category: str) -> str:
    """Deterministic courteous density-seed copy conditioned on prior native beat."""
    quote = ""
    impact = False
    complete = False
    if isinstance(prior, dict):
        quote = str(prior.get("quote_span") or prior.get("end_window_text") or "").strip()
        impact = bool(prior.get("prior_impact_beat"))
        complete = bool(prior.get("prior_complete_thought"))
    # Truncate quote for spoken VO length.
    if len(quote) > 110:
        quote = quote[:107].rstrip() + "…"

    if category == "episode_preface":
        if impact and quote:
            return f"That landing stays with you — next, here's where this chapter goes from there."
        return "Coming up next — here's where this chapter leads."

    if category == "segment_summary":
        if quote:
            return f"Keep that beat in mind — here's the claim that follows."
        return "Here's the beat we're about to hear — the claim that matters for this chapter."

    if category == "story_bridge":
        if impact and quote:
            return f"That's a sharp point — hold onto it, because it sets up what comes next."
        if complete and quote:
            return "That lands — and it sets up what comes next."
        return "That's a sharp point — hold onto that, because it sets up what comes next."

    # framing_question (default)
    if impact and quote:
        return f"Given what you just said — how did that reshape what came next?"
    if complete and quote:
        return "Building on that — what was the turning point in that stretch?"
    return "What was the turning point in that stretch?"


def enrich_line_with_prior_context(
    line: dict[str, Any],
    *,
    prior: dict[str, Any] | None,
    density_forced: bool = False,
) -> dict[str, Any]:
    """Stamp provenance fields onto an interviewer line from prior_native_context."""
    out = dict(line)
    if not isinstance(prior, dict):
        # Still coerce nulls left by LLM merges when no prior packet is available.
        for key in ("prior_impact_beat", "prior_complete_thought", "density_forced"):
            if key in out:
                out[key] = bool(out.get(key))
        return out
    sid = str(prior.get("segment_id") or "").strip()
    out["prior_segment_id"] = sid or None
    out["prior_impact_beat"] = bool(prior.get("prior_impact_beat"))
    out["prior_complete_thought"] = bool(prior.get("prior_complete_thought"))
    out["density_forced"] = bool(density_forced or out.get("density_forced"))
    return out


def apply_prior_context_to_density_seed(
    ctx: RunContext,
    *,
    target_segment_id: str,
    category: str,
    text: str,
) -> tuple[str, str, dict[str, Any] | None, dict[str, Any]]:
    """Relocate micro targets + rewrite interruptive/density stock using prior context.

    Returns (final_target_id, final_text, prior_packet, provenance_fields).
    """
    settings = prior_context_cfg()
    ordered, by_id, chapters = load_ordered_and_segments(ctx)
    sid = str(target_segment_id)
    if settings.get("relocate_micro_targets", True):
        sid = next_substantive_target(
            preferred_id=sid,
            ordered_ids=ordered,
            segments_by_id=by_id,
            cfg=settings,
        )
    prior = build_prior_native_context(
        target_segment_id=sid,
        ordered_ids=ordered,
        segments_by_id=by_id,
        chapters=chapters,
        cfg=settings,
    )
    final_text = text
    if settings.get("rewrite_density_seeds", True):
        if is_interruptive_opener(text) or (prior and prior.get("prior_impact_beat")):
            final_text = courtesy_seed_text(prior, category=category)
    prov = enrich_line_with_prior_context(
        {"targets_segment_id": sid, "text": final_text, "line_category": category},
        prior=prior,
        density_forced=True,
    )
    return sid, final_text, prior, prov


def build_prior_context_volley_turns(stage_input: dict[str, Any]) -> list[dict[str, str]]:
    """Sequential user/assistant turns that condition the gap framing LLM on prior beats."""
    settings = prior_context_cfg()
    if not settings.get("enabled", True) or not settings.get("volley_turns_enabled", True):
        return []
    highlights = stage_input.get("prior_impact_highlights")
    contexts = stage_input.get("prior_native_contexts")
    if not isinstance(highlights, list):
        highlights = []
    if not highlights and isinstance(contexts, dict):
        for tid, pkt in list(contexts.items())[:12]:
            if isinstance(pkt, dict):
                highlights.append(
                    {
                        "before_target": tid,
                        "prior_segment_id": pkt.get("segment_id"),
                        "prior_impact_beat": pkt.get("prior_impact_beat"),
                        "quote_span": pkt.get("quote_span"),
                    }
                )
    if not highlights and not isinstance(contexts, dict):
        return []

    # Cap volley payload size.
    sample = []
    for h in highlights[:8]:
        if not isinstance(h, dict):
            continue
        sample.append(
            {
                "prior_segment_id": h.get("prior_segment_id"),
                "before_target": h.get("before_target"),
                "prior_impact_beat": bool(h.get("prior_impact_beat")),
                "quote_span": h.get("quote_span"),
                "chapter_title": h.get("chapter_title"),
                "target_is_micro": h.get("target_is_micro"),
            }
        )
    user1 = (
        "PRIOR NATIVE BEATS (immediate previous ordered segments before VO targets).\n"
        "Absorb these before writing host lines. Mic-drop / complete closes must be honored — "
        "do not interrupt them with stock 'pause you there' language.\n\n"
        f"{sample if sample else 'No prior beats listed; still use prior_native_contexts in the stage input JSON.'}"
    )
    assistant1 = (
        "Understood. I will condition every interviewer line on prior_native_contexts for its "
        "targets_segment_id. After prior_impact_beat or a complete strong close I will use courteous "
        "acknowledge / soft-bridge / follow-from-what-was-said wording only, never interruptive openers, "
        "and I will not aim framing questions at micro backchannels like 'Okay.'"
    )
    user2 = (
        "Now write the gap framing interviewer_lines (and optional gap_framing_plan) for the full "
        "stage input in the next user message. Apply prior_native_context_policy strictly."
    )
    return [
        {"role": "user", "content": user1},
        {"role": "assistant", "content": assistant1},
        {"role": "user", "content": user2},
    ]


def stamp_lines_prior_provenance(
    ctx: RunContext,
    lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Ensure every line carries prior_segment_id / prior_impact_beat when resolvable."""
    settings = prior_context_cfg()
    if not settings.get("enabled", True):
        return lines
    ordered, by_id, chapters = load_ordered_and_segments(ctx)
    out: list[dict[str, Any]] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        row = dict(line)
        tid = str(row.get("targets_segment_id") or "").strip()
        if not tid:
            out.append(row)
            continue
        prior = build_prior_native_context(
            target_segment_id=tid,
            ordered_ids=ordered,
            segments_by_id=by_id,
            chapters=chapters,
            cfg=settings,
        )
        out.append(enrich_line_with_prior_context(row, prior=prior, density_forced=bool(row.get("density_forced"))))
    return out


def write_gap_vo_context_audit(ctx: RunContext, lines: list[dict[str, Any]]) -> None:
    """Debug/smoke artifact: sampled lines with prior provenance + courtesy flags."""
    samples: list[dict[str, Any]] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        text = str(line.get("text") or "")
        samples.append(
            {
                "line_id": line.get("line_id"),
                "targets_segment_id": line.get("targets_segment_id"),
                "prior_segment_id": line.get("prior_segment_id"),
                "prior_impact_beat": bool(line.get("prior_impact_beat")),
                "prior_complete_thought": bool(line.get("prior_complete_thought")),
                "density_forced": bool(line.get("density_forced")),
                "interruptive_opener": is_interruptive_opener(text),
                "courtesy_ok": not (
                    bool(line.get("prior_impact_beat")) and is_interruptive_opener(text)
                ),
                "text_preview": text[:160],
            }
        )
        if len(samples) >= 40:
            break
    doc = {
        "version": 1,
        "sample_count": len(samples),
        "lines": samples,
        "policy": (prior_context_cfg()),
    }
    try:
        ctx.write_json(GAP_VO_CONTEXT_AUDIT_REL, doc)
    except Exception:
        pass


def courtesy_violations(lines: list[dict[str, Any]]) -> list[str]:
    """Return human-readable courtesy violations (impact prior + interruptive opener)."""
    errs: list[str] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        if line.get("prior_impact_beat") and is_interruptive_opener(str(line.get("text") or "")):
            lid = line.get("line_id") or line.get("targets_segment_id") or "?"
            errs.append(f"{lid}: interruptive opener after prior_impact_beat")
    return errs
