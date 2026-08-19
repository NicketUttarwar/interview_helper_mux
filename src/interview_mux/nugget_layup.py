"""Nugget Layup System — flagship full-tape mining → per-native pre-VO lay-ups.

Authoritative planner for contentful ``before`` synthetic VO. Publishes into
``understanding/gap_report.json`` for G1 synthesis and EDL placement.
"""

from __future__ import annotations

import math
import re
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

CORPUS_REL = "understanding/nugget_corpus.json"
PLAN_REL = "understanding/nugget_layup_plan.json"
GAP_REL = "understanding/gap_report.json"
QC_REL = "understanding/nugget_layup_qc.json"
MASKS_REL = "understanding/native_comprehension_masks.json"
COMPREHENSION_INDEX_REL = "understanding/nugget_comprehension_index.json"

# LLM analysis fields that make a lay-up a *constructed* next-native setup
# instead of a generic hinge. Required on every non-skip row.
ANALYSIS_FIELDS = ("target_beat", "listener_need_entering_T", "forward_unlock")

# Body lines that may legitimately survive publish under layup authority.
AUTHORITY_BODY_ORIGINS = frozenset({"nugget_layup", "operator"})

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[A-Za-z0-9₹$%]+")
_UNLOCK_STOPWORDS = frozenset(
    {
        "a", "after", "an", "and", "are", "as", "at", "be", "been", "by", "come",
        "comes", "did", "do", "does", "for", "from", "had", "happen", "happens",
        "how", "in", "is", "it", "its", "made", "make", "next", "of", "on",
        "once", "point", "shape", "so", "story", "that", "the", "then", "there",
        "this", "to", "was", "were", "what", "when", "where", "which", "with",
    }
)
_GENERIC_UNLOCK_STARTS = (
    "what changed",
    "what happened",
    "what comes",
    "what follows",
    "what shifted",
    "what did that",
    "how did that",
    "where does this",
    "coming up",
    "stepping back",
)


def nugget_layup_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    root = cfg if isinstance(cfg, dict) else merged_config()
    analysis = root.get("analysis") if isinstance(root.get("analysis"), dict) else {}
    block = analysis.get("nugget_layup") if isinstance(analysis.get("nugget_layup"), dict) else {}
    return {
        "enabled": bool(block.get("enabled", True)),
        "require_layup_per_native": bool(block.get("require_layup_per_native", True)),
        "min_layup_coverage": float(block.get("min_layup_coverage", 0.4)),
        "min_layup_words": int(block.get("min_layup_words", 18)),
        "max_layup_words": int(block.get("max_layup_words", 90)),
        "prefer_excluded_nuggets": bool(block.get("prefer_excluded_nuggets", True)),
        "segment_text_max_chars": int(block.get("segment_text_max_chars", 1500)),
        "prior_close_excerpt_chars": int(block.get("prior_close_excerpt_chars", 480)),
        "max_open_nuggets_per_target": int(block.get("max_open_nuggets_per_target", 8)),
        # Ranked open-nugget rows are pointers into top-level nugget_corpus (claims live once).
        "slim_open_nuggets": bool(block.get("slim_open_nuggets", True)),
        # Flagship compose shards when the air order is long (input + output token budgets).
        "compose_batch_max_natives": int(block.get("compose_batch_max_natives", 32)),
        "require_analysis_fields": bool(block.get("require_analysis_fields", True)),
        "ban_canned_air": bool(block.get("ban_canned_air", True)),
        "unique_nuggets_across_layups": bool(
            block.get("unique_nuggets_across_layups", True)
        ),
        "max_cross_layup_overlap": float(block.get("max_cross_layup_overlap", 0.6)),
        "max_target_restate_overlap": float(block.get("max_target_restate_overlap", 0.75)),
        "suppress_placeholder_seams_when_layup": bool(
            block.get("suppress_placeholder_seams_when_layup", True)
        ),
        "demote_synthetic_framing_content": bool(
            block.get("demote_synthetic_framing_content", True)
        ),
        "authoritative_gap_report": bool(block.get("authoritative_gap_report", True)),
        "block_on_open_must_keep": bool(block.get("block_on_open_must_keep", True)),
        "honor_information_package_dense_budget": bool(
            block.get("honor_information_package_dense_budget", True)
        ),
        "degraded_layup": {
            "enabled": True,
            "comprehensible_min_token_conf": 0.85,
            "grace_min_layup_words": 12,
            "allow_thinner_forward_unlock": True,
            "extra_degraded_regenerate": True,
            "exclude_unclear_from_llm_verbatim": True,
            "include_unclear_span_summaries": True,
            **(
                block.get("degraded_layup")
                if isinstance(block.get("degraded_layup"), dict)
                else {}
            ),
        },
    }


def nugget_layup_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(nugget_layup_cfg(cfg).get("enabled", True))


def _ordered_ids(ctx: RunContext) -> list[str]:
    if not ctx.artifact_exists("master/selection.json"):
        return []
    sel = ctx.read_json("master/selection.json")
    if not isinstance(sel, dict):
        return []
    return [str(x) for x in (sel.get("ordered_segment_ids") or []) if x]


def _manifest_segments(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return []
    man = ctx.read_json("segments/manifest.json")
    if not isinstance(man, dict):
        return []
    rows = man.get("segments") or []
    return [r for r in rows if isinstance(r, dict)]


def _clip_text(text: str, max_chars: int) -> str:
    t = " ".join(str(text or "").split())
    if len(t) <= max_chars:
        return t
    return t[: max(0, max_chars - 1)].rstrip() + "…"


def _clip_tail(text: str, max_chars: int) -> str:
    t = " ".join(str(text or "").split())
    if len(t) <= max_chars:
        return t
    return "…" + t[-max(0, max_chars - 1) :].lstrip()


def _norm(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def _tokens(text: str) -> set[str]:
    return {w.casefold() for w in _WORD.findall(_norm(text)) if len(w) > 2}


def _overlap(a: set[str], b: set[str]) -> float:
    if len(a) < 4 or len(b) < 4:
        return 0.0
    return len(a & b) / max(1, min(len(a), len(b)))


def layup_freshness_errors(
    ctx: RunContext,
    plan: dict[str, Any] | None = None,
) -> list[str]:
    """Reasons the on-disk lay-up plan no longer matches the committed air order."""
    if not nugget_layup_enabled():
        return []
    if plan is None:
        plan = ctx.read_json(PLAN_REL) if ctx.artifact_exists(PLAN_REL) else {}
    if not isinstance(plan, dict) or not (plan.get("layups") or plan.get("ordered_segment_ids")):
        return []
    errors: list[str] = []
    meta = plan.get("_meta") if isinstance(plan.get("_meta"), dict) else {}
    if meta.get("stale"):
        errors.append(
            "nugget_layup_plan marked stale "
            f"({meta.get('stale_reason') or 'upstream fix'}) — re-run nugget_layup_compose"
        )
    selection = _ordered_ids(ctx)
    planned = [str(x) for x in (plan.get("ordered_segment_ids") or []) if x]
    if selection and planned != selection:
        missing = [sid for sid in selection if sid not in set(planned)]
        extra = [sid for sid in planned if sid not in set(selection)]
        errors.append(
            "nugget_layup_plan ordered_segment_ids do not match master/selection.json "
            f"(missing={missing[:8]}, stale={extra[:8]})"
        )
    # Order-lock revision mismatch even when lists somehow match.
    try:
        from interview_mux.order_hash import get_order_lock, order_locks_match

        if ctx.artifact_exists("master/selection.json"):
            sel_doc = ctx.read_json("master/selection.json")
            if isinstance(sel_doc, dict) and get_order_lock(sel_doc) and get_order_lock(plan):
                if not order_locks_match(sel_doc, plan):
                    errors.append(
                        "nugget_layup_plan order_lock diverges from selection "
                        f"(sel_rev={(get_order_lock(sel_doc) or {}).get('revision')}, "
                        f"plan_rev={(get_order_lock(plan) or {}).get('revision')})"
                    )
    except Exception:
        pass
    return errors


def assert_layup_fresh_vs_selection(
    ctx: RunContext,
    plan: dict[str, Any] | None = None,
    *,
    stage: str = "nugget_layup_compose",
) -> None:
    """Fail closed rather than publish a lay-up plan built for a different order."""
    errors = layup_freshness_errors(ctx, plan)
    if not errors:
        return
    from interview_mux.loud_fail import raise_loud_failure

    raise_loud_failure(
        ctx,
        "Nugget layup plan is stale vs selection: " + "; ".join(errors[:4]),
        stage=stage,
        reason="nugget_layup_plan_stale",
        detail={"errors": errors[:8]},
    )


_CANNED_AIR_CACHE: frozenset[str] | None = None


def canned_air_phrases() -> frozenset[str]:
    """Normalized deterministic hinges that must never ship as lay-up air copy."""
    global _CANNED_AIR_CACHE
    if _CANNED_AIR_CACHE is None:
        from interview_mux.seam_glue import (
            CANNED_BRIDGE_TEXT,
            FORWARD_HINGES,
            GENERIC_RELATIVE_HINGES,
            REVERSE_HINGES,
        )

        raw = {
            CANNED_BRIDGE_TEXT,
            *FORWARD_HINGES,
            *REVERSE_HINGES,
            *GENERIC_RELATIVE_HINGES,
        }
        _CANNED_AIR_CACHE = frozenset(_canned_key(p) for p in raw if p)
    return _CANNED_AIR_CACHE


def _canned_key(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", _norm(text).casefold()).strip()


def _is_generic_unlock(sentence: str) -> bool:
    key = _canned_key(sentence)
    if not key.startswith(_GENERIC_UNLOCK_STARTS):
        return False
    content = [w for w in key.split() if w not in _UNLOCK_STOPWORDS]
    return len(content) <= 3


def canned_air_violations(text: str) -> list[str]:
    """Canned hinge / generic-unlock sentences inside a lay-up line."""
    clean = _norm(text)
    if not clean:
        return []
    try:
        from interview_mux.media_ip_cta import is_lets_hear_hinge
    except Exception:
        is_lets_hear_hinge = lambda _t: False  # noqa: E731
    menu = canned_air_phrases()
    violations: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(clean):
        key = _canned_key(sentence)
        if not key:
            continue
        if is_lets_hear_hinge(sentence):
            continue
        if key in menu:
            violations.append(f"canned_hinge:{sentence.strip()}")
        elif _is_generic_unlock(sentence):
            violations.append(f"generic_unlock:{sentence.strip()}")
    return list(dict.fromkeys(violations))


def build_corpus_mine_input(ctx: RunContext) -> dict[str, Any]:
    """Compact full-tape packet for flagship corpus mining."""
    cfg = nugget_layup_cfg()
    max_chars = int(cfg["segment_text_max_chars"])
    ordered = _ordered_ids(ctx)
    oset = set(ordered)
    excluded_meta: dict[str, dict[str, Any]] = {}
    if ctx.artifact_exists("master/selection.json"):
        sel = ctx.read_json("master/selection.json")
        if isinstance(sel, dict):
            for ex in sel.get("excluded_segment_ids") or []:
                if isinstance(ex, dict):
                    sid = str(ex.get("segment_id") or "")
                    if sid:
                        excluded_meta[sid] = {
                            "reason": str(ex.get("reason") or "excluded"),
                            "why_dropped": str(
                                ex.get("why_dropped") or ex.get("reason") or "excluded"
                            ),
                            "recovery_value": str(
                                ex.get("recovery_value")
                                or ex.get("salience")
                                or "medium"
                            ),
                        }
                else:
                    sid = str(ex or "")
                    if sid:
                        excluded_meta[sid] = {
                            "reason": "excluded",
                            "why_dropped": "excluded_from_selection",
                            "recovery_value": "medium",
                        }
    segments: list[dict[str, Any]] = []
    for row in _manifest_segments(ctx):
        sid = str(row.get("segment_id") or "")
        if not sid:
            continue
        seg: dict[str, Any] = {
            "segment_id": sid,
            "speaker_id": row.get("speaker_id"),
            "speaker_role": row.get("speaker_role"),
            "start_ms": row.get("start_ms"),
            "end_ms": row.get("end_ms"),
            "type": row.get("type"),
            "in_selection": sid in oset,
            "text": _clip_text(str(row.get("text") or ""), max_chars),
        }
        if sid in excluded_meta:
            seg["why_dropped"] = excluded_meta[sid]["why_dropped"]
            seg["recovery_value"] = excluded_meta[sid]["recovery_value"]
        try:
            from interview_mux.media_ip_cta import never_touch_segment_ids

            if sid in never_touch_segment_ids(ctx):
                seg["never_touch_cta"] = True
                seg["recovery_value"] = "none"
        except Exception:
            pass
        segments.append(seg)
    talking_points = (
        ctx.read_json("understanding/talking_points.json")
        if ctx.artifact_exists("understanding/talking_points.json")
        else {}
    )
    ideal_cuts = (
        ctx.read_json("understanding/ideal_cuts.json")
        if ctx.artifact_exists("understanding/ideal_cuts.json")
        else {}
    )
    gap_evals = (
        ctx.read_json("understanding/gap_evaluations.json")
        if ctx.artifact_exists("understanding/gap_evaluations.json")
        else {}
    )
    content_brief = (
        ctx.read_json("understanding/content_brief.json")
        if ctx.artifact_exists("understanding/content_brief.json")
        else {}
    )
    payload = {
        "ordered_segment_ids": ordered,
        "segments": segments,
        "talking_points": talking_points if isinstance(talking_points, dict) else {},
        "ideal_cuts": ideal_cuts if isinstance(ideal_cuts, dict) else {},
        "gap_evaluations_hint": _compact_gap_evals(gap_evals if isinstance(gap_evals, dict) else {}),
        "content_brief": {
            "thesis": (content_brief or {}).get("thesis") if isinstance(content_brief, dict) else None,
            "topics": (content_brief or {}).get("topics") if isinstance(content_brief, dict) else [],
            "key_claims": (content_brief or {}).get("key_claims") if isinstance(content_brief, dict) else [],
        },
        "prefer_excluded_nuggets": bool(cfg["prefer_excluded_nuggets"]),
        "partial_evidence_doctrine": (
            "Prefer high-confidence spans for evidence_quote. When evidence sits in a "
            "low-conf cluster, set evidence_partial:true and quote only comprehensible tokens."
        ),
    }
    try:
        from interview_mux.media_ip_cta import attach_to_mine_input

        return attach_to_mine_input(ctx, payload)
    except Exception:
        return payload


def _compact_gap_evals(doc: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in doc.get("evaluations") or []:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "segment_id": row.get("segment_id"),
                "gap_type": row.get("gap_type"),
                "severity": row.get("severity"),
                "recommended_framing": row.get("recommended_framing"),
                "listener_confusion": _clip_text(str(row.get("listener_confusion") or ""), 180),
            }
        )
        if len(out) >= 80:
            break
    return out


def _salience_weight(nugget: dict[str, Any]) -> float:
    return {"critical": 1.0, "high": 0.8, "medium": 0.4, "low": 0.1}.get(
        str(nugget.get("salience") or "").lower(), 0.3
    )


def rank_open_nuggets_for_target(
    target_text: str,
    nuggets: list[dict[str, Any]],
    *,
    exclude_ids: set[str] | frozenset[str] | None = None,
    limit: int = 8,
    prefer_excluded: bool = True,
    slim: bool = False,
) -> list[dict[str, Any]]:
    """Open corpus nuggets ranked for one upcoming native (excluded tape first).

    When ``slim`` is true, ranked rows are pointers only (``nugget_id`` + scores);
    look up ``text_claim`` / ``evidence_quote`` in the top-level ``nugget_corpus``.
    """
    skip = {str(x) for x in (exclude_ids or set())}
    target_tokens = _tokens(target_text)
    scored: list[tuple[float, dict[str, Any]]] = []
    for nug in nuggets:
        if not isinstance(nug, dict):
            continue
        nid = str(nug.get("nugget_id") or "")
        if not nid or nid in skip:
            continue
        if nug.get("already_aired_in_selection"):
            continue
        claim = f"{nug.get('text_claim') or ''} {nug.get('evidence_quote') or ''}"
        relevance = _overlap(target_tokens, _tokens(claim))
        score = relevance * 2.0 + _salience_weight(nug)
        if prefer_excluded and not nug.get("in_selection"):
            score += 0.5
        row: dict[str, Any] = {
            "nugget_id": nid,
            "salience": nug.get("salience"),
            "in_selection": bool(nug.get("in_selection")),
            "relevance_to_target": round(relevance, 3),
        }
        if not slim:
            row["text_claim"] = _clip_text(str(nug.get("text_claim") or ""), 240)
            row["evidence_quote"] = _clip_text(str(nug.get("evidence_quote") or ""), 180)
            row["talking_point_ids"] = [
                str(x) for x in (nug.get("talking_point_ids") or []) if x
            ]
        scored.append((score, row))
    scored.sort(key=lambda row: (-row[0], row[1]["nugget_id"]))
    return [row[1] for row in scored[: max(0, limit)]]


def compact_nugget_corpus_for_compose(corpus: dict[str, Any]) -> dict[str, Any]:
    """Keep claim/evidence fields the compose prompt needs; drop mine-only noise."""
    nuggets_out: list[dict[str, Any]] = []
    for nug in (corpus.get("nuggets") or []) if isinstance(corpus, dict) else []:
        if not isinstance(nug, dict):
            continue
        nid = str(nug.get("nugget_id") or "")
        if not nid:
            continue
        nuggets_out.append(
            {
                "nugget_id": nid,
                "text_claim": _clip_text(str(nug.get("text_claim") or ""), 240),
                "evidence_quote": _clip_text(str(nug.get("evidence_quote") or ""), 180),
                "salience": nug.get("salience"),
                "in_selection": bool(nug.get("in_selection")),
                "talking_point_ids": [
                    str(x) for x in (nug.get("talking_point_ids") or []) if x
                ],
                "source_segment_ids": [
                    str(x) for x in (nug.get("source_segment_ids") or []) if x
                ][:6],
                "supports_targets": [
                    str(x) for x in (nug.get("supports_targets") or []) if x
                ][:8],
                "speakability": nug.get("speakability"),
            }
        )
    return {"nuggets": nuggets_out, "version": (corpus or {}).get("version", 1)}


def merge_layup_plan_parts(
    parts: list[dict[str, Any]],
    *,
    ordered_segment_ids: list[str],
) -> dict[str, Any]:
    """Merge sharded ``nugget_layup_compose`` artifacts into one plan."""
    layups_by_tid: dict[str, dict[str, Any]] = {}
    discharged_tp: list[str] = []
    open_tp: list[str] = []
    discharged_nug: list[str] = []
    open_high: list[str] = []
    waived: list[Any] = []
    warnings: list[Any] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        for row in part.get("layups") or []:
            if not isinstance(row, dict):
                continue
            tid = str(row.get("target_segment_id") or "").strip()
            if not tid or tid in layups_by_tid:
                continue
            layups_by_tid[tid] = row
        for key, bucket in (
            ("discharged_talking_point_ids", discharged_tp),
            ("open_talking_point_ids", open_tp),
            ("discharged_nugget_ids", discharged_nug),
            ("open_high_salience_nugget_ids", open_high),
        ):
            for raw in part.get(key) or []:
                sid = str(raw or "")
                if sid and sid not in bucket:
                    bucket.append(sid)
        for raw in part.get("waived_nugget_ids") or []:
            waived.append(raw)
        for raw in part.get("warnings") or []:
            warnings.append(raw)
    # Prefer last shard's open ledgers (they see the most already-aired state).
    if parts:
        last = parts[-1] if isinstance(parts[-1], dict) else {}
        if isinstance(last.get("open_talking_point_ids"), list):
            open_tp = [str(x) for x in last["open_talking_point_ids"] if x]
        if isinstance(last.get("open_high_salience_nugget_ids"), list):
            open_high = [str(x) for x in last["open_high_salience_nugget_ids"] if x]
    layups = [layups_by_tid[sid] for sid in ordered_segment_ids if sid in layups_by_tid]
    return {
        "ordered_segment_ids": list(ordered_segment_ids),
        "layups": layups,
        "discharged_talking_point_ids": discharged_tp,
        "open_talking_point_ids": open_tp,
        "discharged_nugget_ids": discharged_nug,
        "open_high_salience_nugget_ids": open_high,
        "waived_nugget_ids": waived,
        "warnings": warnings,
    }


def dedupe_layup_rows_by_target(plan: dict[str, Any] | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Keep one deterministic layup row per native target before QC or publish.

    LLM retries and shard merges can emit both a skip and a thin non-skip row for
    one target.  Prefer a contentful row with construction analysis, but never
    publish both: duplicate rows make the spoken-copy corpus self-collide.
    """
    out = dict(plan) if isinstance(plan, dict) else {}
    rows = [dict(row) for row in (out.get("layups") or []) if isinstance(row, dict)]
    chosen: dict[str, dict[str, Any]] = {}
    notes: list[dict[str, Any]] = []

    def score(row: dict[str, Any]) -> tuple[int, int, int]:
        text = str(row.get("text") or "").strip()
        fields = sum(bool(str(row.get(key) or "").strip()) for key in ANALYSIS_FIELDS)
        return (
            int(not row.get("skip") and bool(text)),
            fields,
            len(text.split()),
        )

    for row in rows:
        target = str(row.get("target_segment_id") or "").strip()
        if not target:
            continue
        current = chosen.get(target)
        if current is None:
            chosen[target] = row
            continue
        if score(row) > score(current):
            kept, dropped = row, current
            chosen[target] = row
        else:
            kept, dropped = current, row
        notes.append(
            {
                "action": "dedupe_layup_target",
                "target_segment_id": target,
                "kept_line_id": kept.get("line_id"),
                "dropped_line_id": dropped.get("line_id"),
            }
        )

    ordered = [str(s) for s in (out.get("ordered_segment_ids") or []) if s]
    order_index = {sid: index for index, sid in enumerate(ordered)}
    out["layups"] = sorted(
        chosen.values(),
        key=lambda row: (
            order_index.get(str(row.get("target_segment_id") or ""), len(order_index)),
            str(row.get("target_segment_id") or ""),
        ),
    )
    if notes:
        out["layup_dedupe_notes"] = notes
    return out, notes


def degraded_layup_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    block = nugget_layup_cfg(cfg).get("degraded_layup") or {}
    return block if isinstance(block, dict) else {}


def _load_transcript_words(ctx: RunContext) -> list[dict[str, Any]]:
    if not ctx.artifact_exists("transcript/full.json"):
        return []
    try:
        doc = ctx.read_json("transcript/full.json")
    except Exception:
        return []
    rows = (doc.get("words") or []) if isinstance(doc, dict) else []
    words = [w for w in rows if isinstance(w, dict) and (w.get("text") or w.get("word"))]
    words.sort(key=lambda w: (int(w.get("start_ms") or 0), int(w.get("end_ms") or 0)))
    return words


def _word_conf_value(w: dict[str, Any]) -> float | None:
    value = w.get("confidence")
    if value is None:
        value = w.get("conf")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_comprehension_mask_for_span(
    words: list[dict[str, Any]],
    *,
    start_ms: int,
    end_ms: int,
    min_conf: float = 0.85,
) -> dict[str, Any]:
    """Deterministic spine + unclear spans for one native time window."""
    span = [
        w
        for w in words
        if int(w.get("start_ms") or 0) < int(end_ms) and int(w.get("end_ms") or 0) > int(start_ms)
    ]
    comprehensible: list[str] = []
    unclear: list[dict[str, Any]] = []
    unclear_run: list[dict[str, Any]] = []
    high = 0
    low = 0

    def _flush_unclear() -> None:
        nonlocal unclear_run
        if not unclear_run:
            return
        s0 = int(unclear_run[0].get("start_ms") or 0)
        e0 = int(unclear_run[-1].get("end_ms") or s0)
        unclear.append(
            {
                "start_ms": s0,
                "end_ms": e0,
                "placeholder": "[unclear_lexicon]",
                "low_ratio": 1.0,
                "approx_ms": max(0, e0 - s0),
            }
        )
        unclear_run = []

    for w in span:
        conf = _word_conf_value(w)
        text = str(w.get("text") or w.get("word") or "").strip()
        if not text:
            continue
        # Null confidence → mid → treat as comprehensible for spine.
        ok = conf is None or conf >= float(min_conf)
        if ok:
            high += 1
            _flush_unclear()
            comprehensible.append(text)
        else:
            low += 1
            unclear_run.append(w)
    _flush_unclear()

    total = max(1, high + low)
    high_ratio = high / total
    if low == 0:
        quality = "clear"
    elif high_ratio < 0.45:
        quality = "heavily_degraded"
    else:
        quality = "degraded_lexicon_island"

    return {
        "comprehensible_text": " ".join(comprehensible).strip(),
        "unclear_spans": unclear,
        "transcript_quality": quality,
        "high_conf_char_ratio": round(high_ratio, 4),
        "unclear_span_count": len(unclear),
        "word_count": high + low,
        "low_word_count": low,
    }


def build_native_comprehension_masks(ctx: RunContext) -> dict[str, Any]:
    """Layer 2 — per-native comprehensible spine masks written before compose."""
    deg = degraded_layup_cfg()
    min_conf = float(deg.get("comprehensible_min_token_conf") or 0.85)
    words = _load_transcript_words(ctx)
    must_keep: set[str] = set()
    if ctx.artifact_exists("analysis/low_conf_must_keep.json"):
        try:
            mk = ctx.read_json("analysis/low_conf_must_keep.json")
            if isinstance(mk, dict):
                must_keep = {str(x) for x in (mk.get("must_keep_segment_ids") or []) if x}
        except Exception:
            must_keep = set()

    natives: dict[str, Any] = {}
    for row in _manifest_segments(ctx):
        sid = str(row.get("segment_id") or "")
        if not sid:
            continue
        mask = build_comprehension_mask_for_span(
            words,
            start_ms=int(row.get("start_ms") or 0),
            end_ms=int(row.get("end_ms") or 0),
            min_conf=min_conf,
        )
        fused = bool(row.get("fused_from"))
        if sid in must_keep and mask["transcript_quality"] == "clear" and fused:
            mask["transcript_quality"] = "degraded_lexicon_island"
        mask["segment_id"] = sid
        mask["in_low_conf_must_keep"] = sid in must_keep
        mask["fused_from"] = list(row.get("fused_from") or []) if fused else []
        natives[sid] = mask

    doc = {"version": 1, "natives": natives, "generated_for": "nugget_layup_compose"}
    ctx.write_json(MASKS_REL, doc)

    index = {
        "version": 1,
        "by_segment": {
            sid: {
                "high_conf_char_ratio": row.get("high_conf_char_ratio"),
                "unclear_span_count": row.get("unclear_span_count"),
                "transcript_quality": row.get("transcript_quality"),
            }
            for sid, row in natives.items()
        },
    }
    ctx.write_json(COMPREHENSION_INDEX_REL, index)
    return doc


def _mask_for(masks: dict[str, Any], segment_id: str) -> dict[str, Any]:
    natives = masks.get("natives") if isinstance(masks, dict) else {}
    row = (natives or {}).get(segment_id) if isinstance(natives, dict) else None
    return row if isinstance(row, dict) else {}


def is_degraded_target(mask: dict[str, Any]) -> bool:
    q = str(mask.get("transcript_quality") or "clear")
    return q in ("degraded_lexicon_island", "heavily_degraded") or bool(
        mask.get("in_low_conf_must_keep")
    ) or bool(mask.get("fused_from"))


def _seam_reason(prev_row: dict[str, Any] | None, row: dict[str, Any]) -> str:
    """Why the listener needs help entering this native (edit-order seam shape)."""
    from interview_mux.seam_glue import CHAPTER_SCALE_GAP_MS

    if not prev_row:
        return "episode_open"
    try:
        gap = int(row.get("start_ms") or 0) - int(prev_row.get("end_ms") or 0)
    except (TypeError, ValueError):
        return "unknown"
    if abs(gap) >= CHAPTER_SCALE_GAP_MS:
        return "chapter_scale_reverse_jump" if gap < 0 else "chapter_scale_forward_jump"
    if gap < -2500:
        return "reverse_jump"
    if gap > 2500:
        return "forward_jump"
    return "source_contiguous"


def _nuggets_spoken_by(nuggets: list[dict[str, Any]], segment_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for nug in nuggets:
        if not isinstance(nug, dict):
            continue
        sources = {str(x) for x in (nug.get("source_segment_ids") or []) if x}
        if segment_id and segment_id in sources:
            out.append(nug)
    return out


def build_layup_compose_input(
    ctx: RunContext,
    *,
    target_segment_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Packet for per-native lay-up composition.

    Each native carries the construction material for the *next* clip: the prior
    native's closing words, the full upcoming text, the seam that created the
    need, and the still-open corpus nuggets ranked for that beat. The
    ``already_aired_*`` fields walk the air order so no fact is claimed twice.

    When ``target_segment_ids`` is set, only those natives are included (shard),
    but ``already_aired_*`` still walks the full air order so uniqueness holds.
    """
    cfg = nugget_layup_cfg()
    deg = degraded_layup_cfg(cfg)
    max_chars = int(cfg["segment_text_max_chars"])
    slim_open = bool(cfg.get("slim_open_nuggets", True))
    ordered = _ordered_ids(ctx)
    want = {str(x) for x in target_segment_ids} if target_segment_ids is not None else None
    by_id = {
        str(r.get("segment_id")): r
        for r in _manifest_segments(ctx)
        if r.get("segment_id")
    }
    masks = build_native_comprehension_masks(ctx) if deg.get("enabled", True) else {"natives": {}}
    corpus = ctx.read_json(CORPUS_REL) if ctx.artifact_exists(CORPUS_REL) else {"nuggets": []}
    corpus = corpus if isinstance(corpus, dict) else {"nuggets": []}
    nuggets = [n for n in (corpus.get("nuggets") or []) if isinstance(n, dict)]
    try:
        from interview_mux.media_ip_cta import nugget_from_never_touch

        nuggets = [n for n in nuggets if not nugget_from_never_touch(ctx, n)]
    except Exception:
        pass
    prior_plan = ctx.read_json(PLAN_REL) if ctx.artifact_exists(PLAN_REL) else {}
    prior_by_target = {
        str(r.get("target_segment_id") or ""): r
        for r in ((prior_plan.get("layups") or []) if isinstance(prior_plan, dict) else [])
        if isinstance(r, dict) and r.get("target_segment_id")
    }
    opening_owned = _opening_owned_targets(ctx)
    gap_need_by_sid: dict[str, str] = {}
    if ctx.artifact_exists("understanding/gap_evaluations.json"):
        try:
            ge = ctx.read_json("understanding/gap_evaluations.json")
            for row in _compact_gap_evals(ge if isinstance(ge, dict) else {}):
                sid = str(row.get("segment_id") or "")
                need = str(row.get("listener_confusion") or row.get("recommended_framing") or "").strip()
                if sid and need:
                    gap_need_by_sid[sid] = need
        except Exception:
            gap_need_by_sid = {}

    natives: list[dict[str, Any]] = []
    aired_ids: list[str] = []
    claimed_facts: list[str] = []
    for index, sid in enumerate(ordered):
        row = by_id.get(sid) or {}
        prev_row = by_id.get(ordered[index - 1]) if index else None
        mask = _mask_for(masks, sid)
        prior_mask = _mask_for(masks, ordered[index - 1]) if index else {}
        degraded = is_degraded_target(mask) or is_degraded_target(prior_mask)
        spine = str(mask.get("comprehensible_text") or "")
        verbatim = spine if (degraded and deg.get("exclude_unclear_from_llm_verbatim", True)) else str(
            row.get("text") or ""
        )
        unclear_summary = []
        if deg.get("include_unclear_span_summaries", True):
            for span in mask.get("unclear_spans") or []:
                if not isinstance(span, dict):
                    continue
                ms = int(span.get("approx_ms") or 0)
                unclear_summary.append(
                    {
                        "approx_sec": round(ms / 1000.0, 2),
                        "placeholder": span.get("placeholder") or "[unclear_lexicon]",
                    }
                )
        include_row = want is None or sid in want
        if include_row:
            comp = _clip_text(spine, max_chars)
            text = _clip_text(verbatim, max_chars if not degraded else max(max_chars, 2200))
            handoff = gap_need_by_sid.get(sid) or ""
            if not handoff:
                handoff = _seam_reason(prev_row, row)
            native_row: dict[str, Any] = {
                "segment_id": sid,
                "air_index": index,
                "speaker_id": row.get("speaker_id"),
                "type": row.get("type"),
                "start_ms": row.get("start_ms"),
                "end_ms": row.get("end_ms"),
                "text": text,
                "comprehensible_text": comp,
                "unclear_spans": unclear_summary,
                "transcript_quality": mask.get("transcript_quality") or "clear",
                "degraded_lexicon_island": degraded,
                "degraded_path": degraded,
                "fused_from": list(row.get("fused_from") or []),
                "prior_segment_id": ordered[index - 1] if index else None,
                "prior_closing_excerpt": _clip_tail(
                    str(
                        (prior_mask.get("comprehensible_text") if prior_mask else None)
                        or (prev_row or {}).get("text")
                        or ""
                    ),
                    int(cfg["prior_close_excerpt_chars"]),
                ),
                "seam_reason": _seam_reason(prev_row, row),
                "handoff_need": _clip_text(handoff, 220),
                "opening_owner": sid in opening_owned,
                "already_aired_nugget_ids": list(aired_ids),
                "already_claimed_facts": [
                    _clip_text(f, 120) for f in claimed_facts[-24:]
                ],
                "open_nuggets_ranked": rank_open_nuggets_for_target(
                    spine or str(row.get("text") or ""),
                    nuggets,
                    exclude_ids=set(aired_ids),
                    limit=int(cfg["max_open_nuggets_per_target"]),
                    prefer_excluded=bool(cfg["prefer_excluded_nuggets"]),
                    slim=slim_open,
                ),
                "work_around_doctrine": (
                    "Orient and unlock from comprehensible spine + corpus only; "
                    "never invent unclear lexicon tokens; no on-air apology about audio."
                    if degraded
                    else None
                ),
            }
            # Avoid triplicating the same string when the clip is clear.
            if degraded or text != comp:
                native_row["high_conf_text"] = comp
            natives.append(native_row)
        # Facts this native speaks itself, plus anything a prior compose pass
        # already assigned here, are discharged for every later target.
        for nug in _nuggets_spoken_by(nuggets, sid):
            nid = str(nug.get("nugget_id") or "")
            if nid and nid not in aired_ids:
                aired_ids.append(nid)
                claim = _clip_text(str(nug.get("text_claim") or ""), 180)
                if claim:
                    claimed_facts.append(claim)
        prior_row = prior_by_target.get(sid) or {}
        for nid in row_nugget_ids(prior_row):
            if nid and nid not in aired_ids:
                aired_ids.append(nid)

    talking_points = (
        ctx.read_json("understanding/talking_points.json")
        if ctx.artifact_exists("understanding/talking_points.json")
        else {}
    )
    dense_targets: dict[str, Any] = {}
    dense_max = int(cfg["max_layup_words"])
    if cfg.get("honor_information_package_dense_budget", True):
        try:
            from interview_mux.information_packages import (
                dense_targets_from_plan,
                information_packages_cfg,
                packages_affect_air,
            )

            if packages_affect_air() and ctx.artifact_exists("mastering/mastering_plan.json"):
                mp = ctx.read_json("mastering/mastering_plan.json")
                dense_targets = dense_targets_from_plan(mp if isinstance(mp, dict) else {})
                dense_max = int(
                    information_packages_cfg().get("dense_max_layup_words") or max(dense_max, 140)
                )
        except Exception:
            dense_targets = {}
    scope_ids = [str(x) for x in (target_segment_ids or ordered) if x]
    payload = {
        "ordered_segment_ids": scope_ids,
        "full_ordered_segment_ids": list(ordered),
        "opening_owned_segment_ids": sorted(opening_owned),
        "natives": natives,
        "nugget_corpus": compact_nugget_corpus_for_compose(
            corpus if isinstance(corpus, dict) else {"nuggets": []}
        ),
        "talking_points": talking_points if isinstance(talking_points, dict) else {},
        "min_layup_words": int(cfg["min_layup_words"]),
        "grace_min_layup_words": int(deg.get("grace_min_layup_words") or 12),
        "max_layup_words": int(cfg["max_layup_words"]),
        "dense_max_layup_words": dense_max,
        "information_package_dense_targets": dense_targets,
        "require_layup_per_native": bool(cfg["require_layup_per_native"]),
        "prefer_excluded_nuggets": bool(cfg["prefer_excluded_nuggets"]),
        "required_analysis_fields": list(ANALYSIS_FIELDS) if cfg["require_analysis_fields"] else [],
        "banned_air_phrases": sorted(canned_air_phrases()) if cfg["ban_canned_air"] else [],
        "degraded_layup": deg,
        "slim_open_nuggets": slim_open,
        "typed_skip_required_fields": [
            "skip_reason_code",
            "evidence_refs",
            "value_forgone",
            "compensating_path",
            "revisit_if",
            "decision_confidence",
            "owner_stage",
        ],
        "uniqueness_rule": (
            "Each nugget_id may be claimed by at most one lay-up. Honor each "
            "native's already_aired_nugget_ids / already_claimed_facts. "
            "Look up claim/evidence text in nugget_corpus by nugget_id when "
            "open_nuggets_ranked rows are slim pointers."
        ),
        "degraded_doctrine": (
            "When degraded_lexicon_island is true: work around missing context; "
            "convey what IS known from comprehensible_text + corpus; never invent "
            "unclear tokens; keep air text speakable (no bracket placeholders)."
        ),
        "order_lock_note": (
            "Do not emit order_lock or order_content_hash — code stamps them "
            "from master/selection.json after compose."
        ),
    }
    try:
        from interview_mux.media_ip_cta import attach_to_compose_input

        return attach_to_compose_input(ctx, payload)
    except Exception:
        return payload


def _word_count(text: str) -> int:
    return len([w for w in str(text or "").split() if w])


def row_nugget_ids(row: dict[str, Any]) -> list[str]:
    """Nuggets a lay-up row claims (``nugget_ids`` ∪ analysis ``selected_nugget_ids``)."""
    ids: list[str] = []
    for key in ("nugget_ids", "selected_nugget_ids"):
        for raw in (row.get(key) or []) if isinstance(row, dict) else []:
            nid = str(raw or "")
            if nid and nid not in ids:
                ids.append(nid)
    return ids


def layup_line_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a plan layup row into a gap_report interviewer_line (or None if skip)."""
    if not isinstance(row, dict):
        return None
    if row.get("skip"):
        return None
    text = str(row.get("text") or "").strip()
    from interview_mux.spoken_copy_guard import dedupe_sentences

    text = dedupe_sentences(text)
    tid = str(row.get("target_segment_id") or "").strip()
    if not text or not tid:
        return None
    lid = str(row.get("line_id") or "").strip() or f"vo_layup_{tid}"
    nugget_ids = row_nugget_ids(row)
    tp_ids = [str(x) for x in (row.get("talking_point_ids") or []) if x]
    detail_budget = str(row.get("detail_budget") or "").strip() or None
    line = {
        "line_id": lid,
        "gap_type": "nugget_layup",
        "line_category": "extracted_context",
        "text": text,
        "targets_segment_id": tid,
        "placement": "before",
        "delivery": "synthesize",
        "supports_segment_ids": [tid],
        "rationale": str(row.get("why_relevant_to_target") or "nugget_layup").strip(),
        "origin": "nugget_layup",
        "nugget_ids": nugget_ids,
        "recovery_of_talking_point_ids": tp_ids,
        "forward_cue_ok": bool(row.get("forward_cue_ok", True)),
        "word_count": int(row.get("word_count") or _word_count(text)),
        "severity": "high" if tp_ids or nugget_ids else "medium",
    }
    if detail_budget:
        line["detail_budget"] = detail_budget
    if row.get("information_package_id"):
        line["information_package_id"] = row.get("information_package_id")
    if row.get("cta_cover"):
        line["cta_cover"] = True
        line["cta_cover_regenerate"] = True
        line["clone_adjacency_exempt"] = True
        if row.get("vo_shape"):
            line["vo_shape"] = row.get("vo_shape")
    elif row.get("clone_adjacency_exempt"):
        line["clone_adjacency_exempt"] = True
    return line


def _opening_owned_targets(ctx: RunContext) -> set[str]:
    """Segment ids whose before-VO slot is owned by episode orientation."""
    owned: set[str] = set()
    ordered = _ordered_ids(ctx)
    if ordered:
        owned.add(str(ordered[0]))
    try:
        from interview_mux.opening_orientation import native_cold_open_segment_id

        hook = native_cold_open_segment_id(ctx, ordered)
        if hook:
            owned.add(str(hook))
    except Exception:
        pass
    return {sid for sid in owned if sid}


def _opening_layup_skip_spec(ctx: RunContext, target_segment_id: str) -> tuple[str, str]:
    """Skip code + compensating path for an opening-owned before-VO slot.

    When the native open already greets / introduces, orientation is omitted
    (``native_open_self_orients``). Claiming ``opening_orientation_owns_target``
    in that case leaves omit-ledger ``suppress`` pointing at a missing
    episode-orientation line and fails post-master air-contract QC.
    """
    try:
        from interview_mux.opening_orientation import native_open_already_orients

        if native_open_already_orients(
            ctx, _ordered_ids(ctx), target_segment_id=target_segment_id
        ):
            return "episode_open_native_self_orients", "native_self_orients"
    except Exception:
        pass
    return "opening_orientation_owns_target", "opening_orientation"


_COVERAGE_EXEMPT_SKIP_REASONS = frozenset(
    {
        "spoken_copy_unhealable",
        "opening_orientation_owns_target",
        "clone_voice_adjacency",
        "media_ip_cta_hole",
    }
)

# Closed skip codes that may count toward coverage when typed fields are present
# (or soft-migrated from known exempt codes).
JUSTIFIED_SKIP_REASON_CODES = frozenset(
    {
        "spoken_copy_unhealable",
        "opening_orientation_owns_target",
        "clone_voice_adjacency",
        "media_ip_cta_hole",
        "episode_open_native_self_orients",
        "self_explanatory_native",
        "native_self_orients",
        "no_unrecovered_high_salience",
        "listener_already_oriented",
        "superseded_by_dense_package",
        "operator_waive",
        "compensated_by_prior_layup",
        "closing_credits",
        "outro_self_sufficient",
        "native_audio_self_orients",
        "non_editorial_outro",
        "no_eligible_unspent_nugget",
    }
)

_DEFAULT_COMPENSATING_PATHS = {
    "spoken_copy_unhealable": "omit_unsafe_spoken_copy",
    "opening_orientation_owns_target": "opening_orientation",
    "clone_voice_adjacency": "clone_voice_policy",
    "media_ip_cta_hole": "media_ip_cta_omit",
    "episode_open_native_self_orients": "native_self_orients",
    "self_explanatory_native": "native_self_orients",
    "native_self_orients": "native_self_orients",
    "native_audio_self_orients": "native_self_orients",
    "no_unrecovered_high_salience": "no_open_high_salience_need",
    "listener_already_oriented": "prior_layup_or_native",
    "superseded_by_dense_package": "information_package_dense",
    "operator_waive": "operator_waive",
    "compensated_by_prior_layup": "prior_layup",
    "closing_credits": "native_credits_self_contained",
    "outro_self_sufficient": "native_credits_self_contained",
    "non_editorial_outro": "native_credits_self_contained",
    "no_eligible_unspent_nugget": "no_open_high_salience_need",
}


def stamp_typed_skip(
    row: dict[str, Any],
    *,
    reason_code: str,
    evidence_refs: list[str] | None = None,
    value_forgone: list[str] | None = None,
    compensating_path: str | None = None,
    revisit_if: list[str] | None = None,
    decision_confidence: float = 0.85,
    owner_stage: str = "nugget_layup_compose",
) -> dict[str, Any]:
    """Stamp a skip row with full decision metadata (mutates and returns ``row``)."""
    row["skip"] = True
    row["text"] = ""
    row["word_count"] = 0
    row["skip_reason_code"] = reason_code
    refs = list(evidence_refs or [])
    tid = str(row.get("target_segment_id") or "")
    if tid and f"target:{tid}" not in refs:
        refs.append(f"target:{tid}")
    if reason_code and f"skip_reason:{reason_code}" not in refs:
        refs.append(f"skip_reason:{reason_code}")
    row["evidence_refs"] = refs
    forgone = list(value_forgone) if value_forgone is not None else list(
        row.get("value_forgone") or []
    )
    if not forgone:
        forgone = [str(x) for x in row_nugget_ids(row) if x]
    row["value_forgone"] = forgone
    path = compensating_path or _DEFAULT_COMPENSATING_PATHS.get(reason_code) or "typed_skip"
    row["compensating_path"] = path
    row["revisit_if"] = list(
        revisit_if
        if revisit_if is not None
        else (row.get("revisit_if") or ["selection_change", "new_grounded_copy"])
    )
    row["decision_confidence"] = float(decision_confidence)
    row["owner_stage"] = owner_stage
    return row


def is_justified_skip_row(
    row: dict[str, Any] | None,
    *,
    soft_migrate: bool = True,
) -> bool:
    """True when a skip row is intentional listener coverage (not a bare hole).

    Requires a known reason code and a compensating path. Known exempt codes
    soft-migrate without requiring previously stamped typed fields.
    """
    if not isinstance(row, dict) or not row.get("skip"):
        return False
    reason = str(row.get("skip_reason_code") or "").strip()
    if not reason or reason == "empty_or_skip":
        return False
    if reason not in JUSTIFIED_SKIP_REASON_CODES:
        return False
    path = str(row.get("compensating_path") or "").strip()
    if path:
        return True
    if soft_migrate and reason in _COVERAGE_EXEMPT_SKIP_REASONS:
        return True
    if soft_migrate and reason in _DEFAULT_COMPENSATING_PATHS:
        return True
    return False


def coverage_exempt_target_ids(
    ctx: RunContext,
    plan: dict[str, Any] | None = None,
) -> set[str]:
    """Targets that do not count against layup coverage denominator."""
    exempt = set(_opening_owned_targets(ctx))
    doc = plan if isinstance(plan, dict) else (
        ctx.read_json(PLAN_REL) if ctx.artifact_exists(PLAN_REL) else {}
    )
    for row in (doc.get("layups") or []) if isinstance(doc, dict) else []:
        if not isinstance(row, dict):
            continue
        tid = str(row.get("target_segment_id") or "")
        if not tid:
            continue
        if is_justified_skip_row(row, soft_migrate=True):
            exempt.add(tid)
    try:
        from interview_mux.air_script import VO_SEAT_MOVES, load_air_script
        from interview_mux.mastering_plan_loader import load_plan_raw

        mastering = load_plan_raw(ctx)
        script = load_air_script(mastering)
        if script and str(script.get("pass") or "") == "pass_b":
            for beat in script.get("beats") or []:
                if not isinstance(beat, dict):
                    continue
                if str(beat.get("montage_move") or "") in VO_SEAT_MOVES:
                    continue
                sid = str(beat.get("segment_id") or "")
                if sid:
                    exempt.add(sid)
    except Exception:
        pass
    return exempt


def uncovered_high_value_forgone(
    ctx: RunContext,
    plan: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """High-salience value_forgone claims with no compensating path / discharge."""
    if plan is None:
        plan = ctx.read_json(PLAN_REL) if ctx.artifact_exists(PLAN_REL) else {}
    plan = plan if isinstance(plan, dict) else {}
    corpus = ctx.read_json(CORPUS_REL) if ctx.artifact_exists(CORPUS_REL) else {}
    nug_by_id = {
        str(n.get("nugget_id") or ""): n
        for n in ((corpus.get("nuggets") or []) if isinstance(corpus, dict) else [])
        if isinstance(n, dict) and n.get("nugget_id")
    }
    discharged = {str(x) for x in (plan.get("discharged_nugget_ids") or []) if x}
    waived = {
        str(x.get("nugget_id") or x)
        for x in (plan.get("waived_nugget_ids") or [])
        if isinstance(x, (dict, str))
    }
    claimed: set[str] = set()
    for row in plan.get("layups") or []:
        if isinstance(row, dict) and not row.get("skip"):
            claimed.update(row_nugget_ids(row))
    out: list[dict[str, Any]] = []
    for row in plan.get("layups") or []:
        if not isinstance(row, dict) or not row.get("skip"):
            continue
        if is_justified_skip_row(row, soft_migrate=True) and str(
            row.get("compensating_path") or ""
        ).strip():
            continue
        for nid in [str(x) for x in (row.get("value_forgone") or row_nugget_ids(row)) if x]:
            if nid in discharged or nid in waived or nid in claimed:
                continue
            nug = nug_by_id.get(nid) or {}
            sal = str(nug.get("salience") or "")
            if sal not in ("high", "critical") and nid not in {
                str(x) for x in (plan.get("open_high_salience_nugget_ids") or []) if x
            }:
                continue
            out.append(
                {
                    "nugget_id": nid,
                    "target_segment_id": row.get("target_segment_id"),
                    "salience": sal or "high",
                    "skip_reason_code": row.get("skip_reason_code"),
                }
            )
    return out


def strip_model_order_lock(plan: dict[str, Any] | None) -> dict[str, Any]:
    """Discard any LLM-authored selection lock before stamping from selection."""
    out = dict(plan) if isinstance(plan, dict) else {}
    out.pop("order_lock", None)
    out.pop("order_content_hash", None)
    meta = out.get("_meta")
    if isinstance(meta, dict):
        meta = dict(meta)
        meta.pop("stale", None)
        meta.pop("stale_reason", None)
        out["_meta"] = meta
    return out


def _strip_trailing_canned_unlock(text: str) -> str:
    """Drop a trailing canned/generic unlock sentence from spoken lay-up text."""
    clean = _norm(text)
    if not clean:
        return ""
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(clean) if p.strip()]
    if not parts:
        return clean
    if canned_air_violations(parts[-1]):
        parts = parts[:-1]
    return " ".join(parts).strip()


def derive_forward_unlock(
    row: dict[str, Any],
    *,
    target_text: str = "",
) -> str:
    """Build a concrete, non-canned forward_unlock from beat / listener need / target."""
    existing = str(row.get("forward_unlock") or "").strip()
    try:
        from interview_mux.media_ip_cta import is_lets_hear_hinge
    except Exception:
        is_lets_hear_hinge = lambda _t: False  # noqa: E731
    if existing and is_lets_hear_hinge(existing):
        return existing
    if (
        existing
        and not canned_air_violations(existing)
        and not _is_generic_unlock(existing)
    ):
        return existing if existing.endswith("?") else existing.rstrip(".!") + "?"

    beat = str(row.get("target_beat") or "").strip()
    listener = str(row.get("listener_need_entering_T") or "").strip()
    seed = beat or listener
    if seed:
        stem = seed.rstrip(".!")
        low = stem[:1].lower() + stem[1:] if stem else stem
        if stem.lower().startswith(("why ", "how ", "what ", "when ", "where ", "which ")):
            candidate = stem if stem.endswith("?") else f"{stem}?"
        else:
            candidate = f"Why does {low} matter for what follows?"
        if not canned_air_violations(candidate) and not _is_generic_unlock(candidate):
            return candidate

    from interview_mux.gap_vo_prior_context import _target_aware_forward_cues

    for cue in _target_aware_forward_cues(
        target_text or beat,
        category=str(row.get("line_category") or "extracted_context"),
    ):
        cue = " ".join(str(cue or "").split()).strip()
        if not cue:
            continue
        if not cue.endswith("?"):
            cue = cue.rstrip(".!") + "?"
        if canned_air_violations(cue) or _is_generic_unlock(cue):
            continue
        return cue
    return "Why does that beat change what the listener hears next?"


def heal_layup_analysis_fields(
    ctx: RunContext,
    plan: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Fill missing analysis fields and replace banned generic unlocks before QC.

    LLM/schema paths often omit ``forward_unlock`` while appending canned
    ``What comes next?`` to ``text``. That combination hard-fails craft QC and
    cannot be fixed by re-mining alone.
    """
    out = dict(plan) if isinstance(plan, dict) else {"layups": []}
    layups = [dict(r) for r in (out.get("layups") or []) if isinstance(r, dict)]
    by_id = {
        str(row.get("segment_id") or ""): row
        for row in _manifest_segments(ctx)
        if isinstance(row, dict) and row.get("segment_id")
    }
    notes: list[dict[str, Any]] = []
    for row in layups:
        if row.get("skip") or not str(row.get("text") or "").strip():
            continue
        tid = str(row.get("target_segment_id") or "")
        target_text = str((by_id.get(tid) or {}).get("text") or "")
        before = str(row.get("text") or "").strip()
        stripped = _strip_trailing_canned_unlock(before)
        unlock = derive_forward_unlock(row, target_text=target_text)
        changed = False
        if unlock != str(row.get("forward_unlock") or "").strip():
            row["forward_unlock"] = unlock
            changed = True
        if not str(row.get("listener_need_entering_T") or "").strip():
            beat = str(row.get("target_beat") or "").strip()
            if beat:
                row["listener_need_entering_T"] = (
                    f"The prior stretch left this unresolved: {beat.rstrip('.')}."
                )
                changed = True
        body = stripped or _strip_trailing_canned_unlock(before)
        if not body:
            body = str(row.get("setup_from_nuggets") or row.get("target_beat") or "").strip()
        try:
            from interview_mux.media_ip_cta import is_lets_hear_hinge
        except Exception:
            is_lets_hear_hinge = lambda _t: False  # noqa: E731
        # Compose's third-person + "let's hear…" hinge wins — do not restyle into a WH-question.
        if body and (is_lets_hear_hinge(body) or is_lets_hear_hinge(unlock)):
            text = body if is_lets_hear_hinge(body) else f"{body.rstrip('.!?')}. {unlock}".strip()
        elif body and not body.rstrip().endswith("?"):
            text = f"{body.rstrip('.!?')}. {unlock}"
        elif body and canned_air_violations(body):
            text = f"{_strip_trailing_canned_unlock(body).rstrip('.!?')}. {unlock}".strip()
            if text.startswith("."):
                text = unlock
        else:
            # Already ends in a question — prefer derived unlock when the trailing
            # sentence is still a banned generic.
            parts = [p.strip() for p in _SENTENCE_SPLIT.split(body) if p.strip()]
            if parts and canned_air_violations(parts[-1]):
                text = (" ".join(parts[:-1]).rstrip('.!?') + f". {unlock}").strip()
            else:
                text = body
        text = " ".join(text.split()).strip()
        if text and text != before:
            row["text"] = text
            row["word_count"] = _word_count(text)
            row["forward_cue_ok"] = True
            changed = True
        if changed:
            notes.append(
                {
                    "action": "heal_layup_analysis_fields",
                    "target_segment_id": tid,
                    "forward_unlock": unlock,
                }
            )
    out["layups"] = layups
    return out, notes


def apply_clone_voice_adjacency_skips(
    ctx: RunContext, plan: dict[str, Any] | None = None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Skip non-recovery before-VO that would abut the clone source speaker.

    Publishing those rows makes ``avoid_clone_voice_adjacency`` retarget many
    lines onto the same next non-clone native, collapsing unique gap_report
    coverage below ``min_layup_coverage``. Prefer a typed plan skip (coverage
    exempt) over silent retarget stacking.
    """
    out, notes = dedupe_layup_rows_by_target(plan)
    try:
        from interview_mux.media_ip_cta import apply_cover_policy

        out, cover_notes = apply_cover_policy(ctx, out)
        notes.extend(cover_notes)
    except Exception:
        pass
    try:
        from interview_mux.gap_framing import is_cut_recovery_vo
        from interview_mux.source_topology import pickup_eligible_speaker_id
    except Exception:
        return out, notes

    voice = str(pickup_eligible_speaker_id(ctx) or "").strip()
    if not voice:
        return out, notes

    by_id = {
        str(row.get("segment_id") or ""): row
        for row in _manifest_segments(ctx)
        if isinstance(row, dict) and row.get("segment_id")
    }
    ordered = _ordered_ids(ctx)
    corpus = ctx.read_json(CORPUS_REL) if ctx.artifact_exists(CORPUS_REL) else {}
    corpus = corpus if isinstance(corpus, dict) else {}

    for row in out.get("layups") or []:
        if not isinstance(row, dict) or row.get("skip"):
            continue
        if row.get("cta_cover") or row.get("clone_adjacency_exempt"):
            continue
        tid = str(row.get("target_segment_id") or "").strip()
        if not tid:
            continue
        target_speaker = str((by_id.get(tid) or {}).get("speaker_id") or "").strip()
        if not target_speaker or target_speaker != voice:
            continue
        probe = {
            "origin": "nugget_layup",
            "delivery": str(row.get("delivery") or "synthesize"),
            "nugget_ids": row_nugget_ids(row),
            "targets_segment_id": tid,
            "replaces_source_segments": list(row.get("replaces_source_segments") or []),
            "supports_segment_ids": list(row.get("supports_segment_ids") or []),
        }
        if is_cut_recovery_vo(
            probe, ordered_segment_ids=ordered, nugget_corpus=corpus
        ):
            continue
        stamp_typed_skip(
            row,
            reason_code="clone_voice_adjacency",
            evidence_refs=[
                f"target:{tid}",
                f"clone_speaker:{voice}",
                "clone_voice_policy:before_slot_abuts_source",
            ],
            value_forgone=row_nugget_ids(row),
            compensating_path="clone_voice_policy",
            revisit_if=["clone_speaker_change", "cut_recovery_nuggets"],
            decision_confidence=0.95,
            owner_stage="nugget_layup_compose",
        )
        notes.append(
            {
                "action": "skip_clone_voice_adjacency",
                "target_segment_id": tid,
                "line_id": row.get("line_id"),
                "clone_speaker_id": voice,
            }
        )
    return out, notes


def _speaker_role_map(ctx: RunContext) -> dict[str, str]:
    """Map speaker_id → role from speakers.json when available."""
    roles: dict[str, str] = {}
    if not ctx.artifact_exists("understanding/speakers.json"):
        return roles
    doc = ctx.read_json("understanding/speakers.json")
    if not isinstance(doc, dict):
        return roles
    for sp in doc.get("speakers") or []:
        if not isinstance(sp, dict):
            continue
        sid = str(sp.get("speaker_id") or "").strip()
        if sid:
            roles[sid] = str(sp.get("role") or "").strip().lower()
    return roles


def _segment_role(row: dict[str, Any] | None, role_map: dict[str, str]) -> str:
    if not isinstance(row, dict):
        return ""
    direct = str(row.get("speaker_role") or row.get("role") or "").strip().lower()
    if direct:
        return direct
    sid = str(row.get("speaker_id") or "").strip()
    return role_map.get(sid, "")


def _clear_native_interviewer_handoff(
    prior: dict[str, Any] | None,
    target: dict[str, Any] | None,
    *,
    role_map: dict[str, str],
) -> bool:
    """True when prior interviewer already cues the next guest answer."""
    from interview_mux.conversation_context import role_is_content, role_is_frame

    prior_role = _segment_role(prior, role_map)
    target_role = _segment_role(target, role_map)
    if not (role_is_frame(prior_role) and role_is_content(target_role)):
        return False
    prior_text = str((prior or {}).get("text") or (prior or {}).get("text_excerpt") or "").strip()
    # Strong signal: interviewer question → guest answer.
    if prior_text.rstrip().endswith("?"):
        return True
    # Softer: role change alone still means the native seam is conversational.
    return len(prior_text.split()) >= 4


def apply_clear_native_handoff_skips(
    ctx: RunContext, plan: dict[str, Any] | None = None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Skip non-recovery VO when native interviewer→guest handoff is already clear."""
    out, notes = apply_clone_voice_adjacency_skips(ctx, plan)
    try:
        from interview_mux.gap_framing import is_cut_recovery_vo
    except Exception:
        return out, notes

    by_id = {
        str(row.get("segment_id") or ""): row
        for row in _manifest_segments(ctx)
        if isinstance(row, dict) and row.get("segment_id")
    }
    ordered = _ordered_ids(ctx)
    position = {sid: i for i, sid in enumerate(ordered)}
    role_map = _speaker_role_map(ctx)
    corpus = ctx.read_json(CORPUS_REL) if ctx.artifact_exists(CORPUS_REL) else {}
    corpus = corpus if isinstance(corpus, dict) else {}

    for row in out.get("layups") or []:
        if not isinstance(row, dict) or row.get("skip"):
            continue
        if row.get("cta_cover"):
            continue
        tid = str(row.get("target_segment_id") or "").strip()
        if not tid or tid not in position or position[tid] <= 0:
            continue
        prior_id = ordered[position[tid] - 1]
        prior = by_id.get(prior_id)
        target = by_id.get(tid)
        if not _clear_native_interviewer_handoff(prior, target, role_map=role_map):
            continue
        probe = {
            "origin": "nugget_layup",
            "delivery": str(row.get("delivery") or "synthesize"),
            "nugget_ids": row_nugget_ids(row),
            "targets_segment_id": tid,
            "replaces_source_segments": list(row.get("replaces_source_segments") or []),
            "supports_segment_ids": list(row.get("supports_segment_ids") or []),
        }
        if is_cut_recovery_vo(
            probe, ordered_segment_ids=ordered, nugget_corpus=corpus
        ):
            continue
        # Empty setup means no recovered facts — pure framing on a clear seam.
        setup = str(row.get("setup_from_nuggets") or "").strip()
        if setup and row_nugget_ids(row):
            # Still allow recovery VO with grounded nuggets even on Q→A seams.
            continue
        stamp_typed_skip(
            row,
            reason_code="native_self_orients",
            evidence_refs=[
                f"target:{tid}",
                f"prior:{prior_id}",
                "native_handoff:interviewer_to_guest",
            ],
            value_forgone=row_nugget_ids(row),
            compensating_path="native_self_orients",
            revisit_if=["excluded_nugget_recovery", "prior_role_change"],
            decision_confidence=0.9,
            owner_stage="nugget_layup_compose",
        )
        notes.append(
            {
                "action": "skip_clear_native_handoff",
                "target_segment_id": tid,
                "prior_segment_id": prior_id,
                "line_id": row.get("line_id"),
            }
        )
    return out, notes


def stamp_valueless_skips(
    ctx: RunContext, plan: dict[str, Any] | None = None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Stamp skip holes that carry no recoverable listener value.

    Shrinks the coverage denominator to real VO candidates. Never pastes
    analysis fields into spoken text and never lowers ``min_layup_coverage``.
    """
    out = plan if isinstance(plan, dict) else (
        ctx.read_json(PLAN_REL) if ctx.artifact_exists(PLAN_REL) else {}
    )
    out = dict(out) if isinstance(out, dict) else {"layups": []}
    notes: list[dict[str, Any]] = []
    sparse = False
    try:
        from interview_mux.source_topology import vo_posture_is_sparse_omit

        sparse = vo_posture_is_sparse_omit(ctx)
    except Exception:
        sparse = False
    corpus = ctx.read_json(CORPUS_REL) if ctx.artifact_exists(CORPUS_REL) else {}
    high_ids: set[str] = set()
    for nug in (corpus.get("nuggets") or []) if isinstance(corpus, dict) else []:
        if not isinstance(nug, dict):
            continue
        nid = str(nug.get("nugget_id") or "")
        if nid and str(nug.get("salience") or "") in {"high", "critical"}:
            high_ids.add(nid)

    def _stamp(row: dict[str, Any], reason: str) -> None:
        tid = str(row.get("target_segment_id") or "")
        stamp_typed_skip(
            row,
            reason_code=reason,
            evidence_refs=[
                f"target:{tid}",
                f"skip_reason:{reason}",
                "valueless_skip:stamp",
            ],
            value_forgone=row_nugget_ids(row),
            compensating_path=_DEFAULT_COMPENSATING_PATHS.get(reason) or "typed_skip",
            revisit_if=["selection_change", "new_grounded_copy"],
            decision_confidence=0.82,
            owner_stage="nugget_layup_compose",
        )
        notes.append(
            {
                "action": "stamp_valueless_skip",
                "target_segment_id": tid,
                "reason_code": reason,
                "line_id": row.get("line_id"),
            }
        )

    for row in out.get("layups") or []:
        if not isinstance(row, dict) or not row.get("skip"):
            continue
        if is_justified_skip_row(row, soft_migrate=True):
            continue
        nids = row_nugget_ids(row)
        has_high = any(nid in high_ids for nid in nids)
        if not nids or not has_high:
            _stamp(
                row,
                "no_unrecovered_high_salience" if not nids else "self_explanatory_native",
            )

    if sparse:
        for row in out.get("layups") or []:
            if not isinstance(row, dict) or not row.get("skip"):
                continue
            if is_justified_skip_row(row, soft_migrate=True):
                continue
            _stamp(row, "self_explanatory_native")
    return out, notes


def analysis_fields_leaked_into_text(row: dict[str, Any]) -> list[str]:
    """Return analysis field names whose prose was pasted into spoken text."""
    text = str(row.get("text") or "").strip()
    if not text:
        return []
    text_fold = text.casefold()
    leaked: list[str] = []
    for field in ANALYSIS_FIELDS:
        val = str(row.get(field) or "").strip()
        if len(val) < 20:
            continue
        if val.casefold() in text_fold:
            leaked.append(field)
    setup = str(row.get("setup_from_nuggets") or "").strip()
    if setup and len(setup) >= 20 and setup.casefold() != text.casefold():
        # setup_from_nuggets is allowed as the body of air copy when distinct.
        pass
    return leaked


def prepare_layup_plan_for_persist(ctx: RunContext, plan: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize, strip model lock, attach selection lock — before freshness assert."""
    doc = strip_model_order_lock(plan)
    doc = normalize_layup_talking_point_ledger(ctx, doc)
    doc, _notes = heal_layup_analysis_fields(ctx, doc)
    doc, _clone_notes = apply_clear_native_handoff_skips(ctx, doc)
    doc, _skip_notes = stamp_valueless_skips(ctx, doc)
    return attach_selection_order_lock(ctx, doc)


def repair_or_skip_spoken_copy_layups(
    ctx: RunContext, plan: dict[str, Any] | None = None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Use grounded recovery copy, otherwise explicitly skip unsafe layups.

    A target beat commonly paraphrases the following native verbatim.  It is
    useful planning metadata but is not safe listener-facing copy by itself.
    Never leave that row required after it fails the spoken-copy guard: G1 and
    EDL would both be unable to make progress.
    """
    out, notes = apply_clear_native_handoff_skips(ctx, plan)
    corpus = ctx.read_json(CORPUS_REL) if ctx.artifact_exists(CORPUS_REL) else {}
    nuggets = {
        str(nugget.get("nugget_id") or ""): nugget
        for nugget in (corpus.get("nuggets") or []) if isinstance(nugget, dict)
    }
    by_id = {
        str(row.get("segment_id") or ""): row
        for row in _manifest_segments(ctx)
        if isinstance(row, dict) and row.get("segment_id")
    }
    from interview_mux.spoken_copy_guard import spoken_copy_violations
    from interview_mux.gap_vo_prior_context import (
        _target_aware_forward_cues,
        has_forward_cue,
        repair_last_sentence_layup,
        vo_target_overlap_ratio,
    )
    from interview_mux.opening_orientation import orientation_copy_unusable

    opening_targets = _opening_owned_targets(ctx)

    def _scrub_edit_structure(text: str) -> str:
        """Drop edit-unit nouns that trip spoken_edit_structure_ref."""
        scrubbed = re.sub(
            r"\b(?:the|this|that|our)\s+clips?'?s?\b",
            "this moment",
            text,
            flags=re.IGNORECASE,
        )
        scrubbed = re.sub(
            r"\b(?:the|this|that|our)\s+segments?'?s?\b",
            "this stretch",
            scrubbed,
            flags=re.IGNORECASE,
        )
        return " ".join(scrubbed.split()).strip()

    seen: list[str] = []
    for row in out.get("layups") or []:
        if not isinstance(row, dict) or row.get("skip"):
            continue
        target = str(row.get("target_segment_id") or "")
        if target and target in opening_targets:
            skip_code, skip_path = _opening_layup_skip_spec(ctx, target)
            stamp_typed_skip(
                row,
                reason_code=skip_code,
                evidence_refs=[
                    f"target:{target}",
                    "opening_orientation:owns_before_slot",
                ],
                value_forgone=row_nugget_ids(row),
                compensating_path=skip_path,
                revisit_if=["orientation_disabled", "opening_slot_freed"],
                decision_confidence=0.95,
                owner_stage="nugget_layup_compose",
            )
            notes.append(
                {
                    "action": "skip_unhealable_spoken_copy_layup",
                    "target_segment_id": target,
                    "line_id": row.get("line_id"),
                    "violations": ["opening_adjacency_with_orientation"],
                }
            )
            continue
        target_text = str((by_id.get(target) or {}).get("text") or "")
        text = str(row.get("text") or "").strip()
        leaked = analysis_fields_leaked_into_text(row)
        setup = str(row.get("setup_from_nuggets") or "").strip()
        if orientation_copy_unusable(text):
            core = setup or str(row.get("target_beat") or "").strip()
            if core:
                core = " ".join(core.split()).strip()
                if core[-1:] not in ".!":
                    core = core.rstrip("?") + "."
                rewritten = f"{core} Let's hear what that means for what follows."
                row["text"] = rewritten
                row["word_count"] = _word_count(rewritten)
                notes.append(
                    {
                        "action": "rewrite_meta_question_layup",
                        "target_segment_id": target,
                        "line_id": row.get("line_id"),
                    }
                )
                text = rewritten
        if leaked:
            unlock_early = str(row.get("forward_unlock") or "").strip()
            recover_bits = [
                " ".join(bit for bit in (setup, unlock_early) if bit).strip(),
                setup,
            ]
            recovered_early = ""
            for candidate in recover_bits:
                candidate = " ".join(candidate.split()).strip()
                if not candidate or len(candidate.split()) < 6:
                    continue
                if candidate[-1:] not in ".!?":
                    candidate += "?"
                probe = dict(row)
                probe["text"] = candidate
                if analysis_fields_leaked_into_text(probe):
                    continue
                if spoken_copy_violations(
                    candidate,
                    evidence={
                        "target_excerpt": target_text,
                        "before_excerpt": "",
                        "after_topic": str(row.get("target_beat") or ""),
                        "strict_grounding": False,
                    },
                    seen_texts=seen,
                ):
                    continue
                recovered_early = candidate
                break
            if recovered_early:
                row["text"] = recovered_early
                row["word_count"] = _word_count(recovered_early)
                row["spoken_copy_recovered"] = True
                text = recovered_early
                notes.append(
                    {
                        "action": "repair_spoken_copy_layup",
                        "target_segment_id": target,
                        "line_id": row.get("line_id"),
                        "from": "analysis_leak_scrub",
                    }
                )
            else:
                stamp_typed_skip(
                    row,
                    reason_code="spoken_copy_unhealable",
                    evidence_refs=[
                        f"target:{target}",
                        *[f"analysis_leak:{f}" for f in leaked],
                    ],
                    value_forgone=row_nugget_ids(row),
                    compensating_path="omit_unsafe_spoken_copy",
                    revisit_if=[
                        "grounded_recovery_copy",
                        "rewrite_without_planner_fields",
                    ],
                    decision_confidence=0.95,
                    owner_stage="nugget_layup_compose",
                )
                row["spoken_copy_violations"] = [
                    "spoken_planner_meta",
                    *[f"analysis_leak:{f}" for f in leaked],
                ]
                notes.append(
                    {
                        "action": "skip_unhealable_spoken_copy_layup",
                        "target_segment_id": target,
                        "line_id": row.get("line_id"),
                        "violations": row["spoken_copy_violations"],
                    }
                )
                continue
        if text and "spoken_edit_structure_ref" in (
            spoken_copy_violations(
                text,
                evidence={
                    "target_excerpt": target_text,
                    "before_excerpt": str(row.get("listener_need_entering_T") or ""),
                    "after_topic": str(row.get("target_beat") or ""),
                    "strict_grounding": False,
                },
                seen_texts=seen,
            )
        ):
            scrubbed = _scrub_edit_structure(text)
            if scrubbed and scrubbed != text:
                text = scrubbed
                row["text"] = scrubbed
                row["word_count"] = _word_count(scrubbed)
        evidence = {
            "target_excerpt": target_text,
            "before_excerpt": str(row.get("listener_need_entering_T") or ""),
            "after_topic": str(row.get("target_beat") or ""),
            "strict_grounding": False,
        }
        violations = spoken_copy_violations(text, evidence=evidence, seen_texts=seen)
        # vo_value restatement / missing forward cue can fail delivery even when
        # spoken_copy_guard's coarser restatement check is quiet.
        soft_bad = False
        if text and not has_forward_cue(text):
            soft_bad = True
            violations = list(violations) + ["missing_forward_cue"]
        if (
            text
            and target_text
            and vo_target_overlap_ratio(text, target_text) > 0.75
        ):
            soft_bad = True
            if "spoken_next_clip_restatement" not in violations:
                violations = list(violations) + ["spoken_next_clip_restatement"]
        if not violations and not soft_bad:
            seen.append(text)
            continue

        unlock = str(row.get("forward_unlock") or "").strip()
        nugget_bits = [
            str((nuggets.get(nid) or {}).get("text_claim") or "").strip()
            for nid in row_nugget_ids(row)
        ]
        restates = bool(
            target_text and text and vo_target_overlap_ratio(text, target_text) > 0.75
        )
        # Restating bodies cannot be salvaged by appending a cue — that still
        # fails spoken_copy on publish. Prefer unlock/nugget/cue-only recovery.
        # Never recover by pasting analysis fields (listener_need / target_beat).
        seed_for_repair = "" if restates else text
        candidates = [
            " ".join(bit for bit in (*nugget_bits[:2], unlock) if bit).strip(),
            unlock,
            repair_last_sentence_layup(
                seed_for_repair,
                target_text=target_text,
                category=str(row.get("line_category") or "extracted_context"),
                target_segment_id=target,
            ),
        ]
        if setup and setup.casefold() not in {
            str(row.get(f) or "").strip().casefold() for f in ANALYSIS_FIELDS
        }:
            candidates.insert(0, " ".join(bit for bit in (setup, unlock) if bit).strip())
        if restates:
            candidates.extend(
                _target_aware_forward_cues(
                    target_text,
                    category=str(row.get("line_category") or "extracted_context"),
                )
            )
        recovered = ""
        for candidate in candidates:
            candidate = " ".join(candidate.split()).strip()
            if candidate and candidate[-1:] not in ".!?":
                candidate += "?"
            if not candidate:
                continue
            if spoken_copy_violations(candidate, evidence=evidence, seen_texts=seen):
                continue
            if not has_forward_cue(candidate):
                continue
            if target_text and vo_target_overlap_ratio(candidate, target_text) > 0.75:
                continue
            # Reject recovery that still embeds planner analysis prose.
            probe = dict(row)
            probe["text"] = candidate
            if analysis_fields_leaked_into_text(probe):
                continue
            recovered = candidate
            break
        if recovered:
            row["text"] = recovered
            row["word_count"] = _word_count(recovered)
            row["spoken_copy_recovered"] = True
            row["forward_cue_ok"] = True
            notes.append(
                {
                    "action": "repair_spoken_copy_layup",
                    "target_segment_id": target,
                    "line_id": row.get("line_id"),
                }
            )
            seen.append(recovered)
            continue

        stamp_typed_skip(
            row,
            reason_code="spoken_copy_unhealable",
            evidence_refs=[
                f"target:{target}",
                *[f"spoken_copy:{v}" for v in violations[:6]],
            ],
            value_forgone=row_nugget_ids(row),
            compensating_path="omit_unsafe_spoken_copy",
            revisit_if=["grounded_recovery_copy", "target_text_change"],
            decision_confidence=0.9,
            owner_stage="nugget_layup_compose",
        )
        row["spoken_copy_violations"] = violations
        notes.append(
            {
                "action": "skip_unhealable_spoken_copy_layup",
                "target_segment_id": target,
                "line_id": row.get("line_id"),
                "violations": violations,
            }
        )
    return out, notes


def dedupe_gap_report_nugget_claims(
    gap_report: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Keep the first owner of each nugget_id across interviewer_lines.

    Dense-package injection can stamp the same package nuggets onto an empty
    layup row that later rows already claim explicitly — strip later/dup claims.
    """
    report = dict(gap_report) if isinstance(gap_report, dict) else {}
    lines = [ln for ln in (report.get("interviewer_lines") or []) if isinstance(ln, dict)]
    owner: dict[str, str] = {}
    notes: list[dict[str, Any]] = []
    out_lines: list[dict[str, Any]] = []
    for ln in lines:
        lid = str(ln.get("line_id") or ln.get("targets_segment_id") or "")
        nids = [str(x) for x in (ln.get("nugget_ids") or []) if x]
        if not nids:
            out_lines.append(ln)
            continue
        kept: list[str] = []
        dropped: list[str] = []
        for nid in nids:
            if nid in owner and owner[nid] != lid:
                dropped.append(nid)
                continue
            owner.setdefault(nid, lid)
            kept.append(nid)
        if dropped:
            ln = dict(ln)
            ln["nugget_ids"] = kept
            notes.append(
                {
                    "action": "dedupe_nugget_claim",
                    "line_id": lid,
                    "dropped_nugget_ids": dropped,
                    "kept_by": {nid: owner[nid] for nid in dropped},
                }
            )
        out_lines.append(ln)
    if not notes:
        return report, []
    report["interviewer_lines"] = out_lines
    return report, notes


def attach_selection_order_lock(ctx: RunContext, plan: dict[str, Any]) -> dict[str, Any]:
    """Copy selection order_lock onto a layup plan document."""
    out = dict(plan)
    if not ctx.artifact_exists("master/selection.json"):
        return out
    try:
        from interview_mux.order_hash import copy_order_lock, get_order_lock

        sel = ctx.read_json("master/selection.json")
        if isinstance(sel, dict) and (get_order_lock(sel) or sel.get("ordered_segment_ids")):
            out = copy_order_lock(sel, out)
    except Exception:
        pass
    return out


def publish_layup_plan_to_gap_report(
    ctx: RunContext,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge lay-up before-VO into gap_report while preserving episode orientation."""
    from interview_mux.opening_orientation import (
        ensure_episode_orientation,
        is_episode_orientation,
        orientation_omitted,
    )
    from interview_mux.artifact_writes import write_validated_artifact

    if plan is None:
        plan = ctx.read_json(PLAN_REL) if ctx.artifact_exists(PLAN_REL) else {}
    if not isinstance(plan, dict):
        plan = {}
    plan, _ = apply_clone_voice_adjacency_skips(ctx, plan)
    plan, _ = dedupe_layup_rows_by_target(plan)
    plan = attach_selection_order_lock(ctx, plan)
    # Publishing a plan built for a different air order silently mis-times every
    # before-VO — refuse instead.
    assert_layup_fresh_vs_selection(ctx, plan)

    existing = ctx.read_json(GAP_REL) if ctx.artifact_exists(GAP_REL) else {}
    if not isinstance(existing, dict):
        existing = {}
    prior_lines = [ln for ln in (existing.get("interviewer_lines") or []) if isinstance(ln, dict)]
    orientation = [ln for ln in prior_lines if is_episode_orientation(ln)]

    body: list[dict[str, Any]] = []
    seen_targets: set[str] = set()
    dense_meta: dict[str, dict[str, Any]] = {}
    try:
        from interview_mux.information_packages import (
            dense_targets_from_plan,
            packages_affect_air,
        )

        if packages_affect_air() and ctx.artifact_exists("mastering/mastering_plan.json"):
            mp = ctx.read_json("mastering/mastering_plan.json")
            dense_meta = dense_targets_from_plan(mp if isinstance(mp, dict) else {})
    except Exception:
        dense_meta = {}

    # Explicit plan claims win over dense-package backfill so package-shared
    # nugget lists cannot collide with later layups that already own them.
    claimed_nugs: set[str] = set()
    for row in plan.get("layups") or []:
        if isinstance(row, dict):
            claimed_nugs.update(row_nugget_ids(row))

    # Orientation already owns the opening handoff into the first native. A
    # second before-VO on that same target is the opening-adjacency conflict
    # that edl_narrative_audit rejects (orientation + opening layup both fire
    # before clip one). Suppress the duplicate layup row at publish time.
    orientation_targets = _opening_owned_targets(ctx)

    for row in plan.get("layups") or []:
        if not isinstance(row, dict):
            continue
        row_d = row
        tid = str(row_d.get("target_segment_id") or "").strip()
        if tid and tid in orientation_targets:
            skip_code, skip_path = _opening_layup_skip_spec(ctx, tid)
            stamp_typed_skip(
                row_d,
                reason_code=skip_code,
                evidence_refs=[
                    f"target:{tid}",
                    "opening_orientation:owns_before_slot",
                ],
                compensating_path=skip_path,
                revisit_if=["orientation_disabled", "opening_slot_freed"],
                decision_confidence=0.95,
            )
            continue
        if tid and tid in dense_meta:
            row_d["detail_budget"] = "dense"
            row_d["information_package_id"] = dense_meta[tid].get("package_id")
            # Prefer unclaimed package-cited nuggets when the layup row is empty.
            if not row_nugget_ids(row_d) and dense_meta[tid].get("nugget_ids"):
                injected = [
                    str(n)
                    for n in (dense_meta[tid].get("nugget_ids") or [])
                    if n and str(n) not in claimed_nugs
                ]
                if injected:
                    row_d["nugget_ids"] = injected
                    claimed_nugs.update(injected)
        line = layup_line_from_row(row_d)
        if not line:
            continue
        tid = str(line["targets_segment_id"])
        if tid in seen_targets:
            continue
        if tid in orientation_targets:
            continue
        seen_targets.add(tid)
        body.append(line)

    # Keep non-orientation operator pins that are not superseded by a layup target.
    for ln in prior_lines:
        if is_episode_orientation(ln):
            continue
        if str(ln.get("origin") or "") == "operator":
            tid = str(ln.get("targets_segment_id") or "")
            if tid and tid not in seen_targets:
                body.append(ln)
                seen_targets.add(tid)

    report = {
        **{k: v for k, v in existing.items() if k not in ("interviewer_lines", "_meta")},
        "interviewer_lines": orientation + body,
        "nugget_layup_authority": True,
    }
    report, _dedupe_notes = dedupe_gap_report_nugget_claims(report)
    ordered = _ordered_ids(ctx)
    report, _notes = ensure_episode_orientation(ctx, report, ordered)
    if orientation_omitted(report):
        for row in plan.get("layups") or []:
            if not isinstance(row, dict):
                continue
            tid = str(row.get("target_segment_id") or "").strip()
            if tid and tid in orientation_targets:
                stamp_typed_skip(
                    row,
                    reason_code="episode_open_native_self_orients",
                    evidence_refs=[
                        f"target:{tid}",
                        "opening_orientation:native_open_self_orients",
                    ],
                    compensating_path="native_self_orients",
                    revisit_if=["orientation_disabled", "opening_slot_freed"],
                    decision_confidence=0.95,
                )
        try:
            ctx.write_json(PLAN_REL, plan, skip_handoff=True)
        except Exception:
            pass
    if ctx.artifact_exists("segments/manifest.json"):
        from interview_mux.gap_framing import avoid_clone_voice_adjacency
        from interview_mux.source_topology import pickup_eligible_speaker_id

        manifest = ctx.read_json("segments/manifest.json")
        segments_by_id = {
            str(segment.get("segment_id")): segment
            for segment in ((manifest if isinstance(manifest, dict) else {}).get("segments") or [])
            if isinstance(segment, dict) and segment.get("segment_id")
        }
        corpus = (
            ctx.read_json(CORPUS_REL) if ctx.artifact_exists(CORPUS_REL) else {}
        )
        report, clone_notes = avoid_clone_voice_adjacency(
            report,
            segments_by_id,
            ordered_segment_ids=ordered,
            clone_speaker_id=pickup_eligible_speaker_id(ctx),
            nugget_corpus=corpus if isinstance(corpus, dict) else {},
        )
        if clone_notes:
            ctx.log(
                f"nugget_layup: adjusted {len(clone_notes)} clone-adjacent VO line(s)",
                level="info",
                stage="nugget_layup_compose",
            )
    write_validated_artifact(
        ctx,
        GAP_REL,
        report,
        merge_from_disk=False,
        stage_key="nugget_layup_compose",
    )
    try:
        from interview_mux.omit_ledger import rebuild_and_write_omit_ledger

        rebuild_and_write_omit_ledger(ctx, plan=plan, gap_report=report)
    except Exception as exc:
        ctx.log(
            f"omit_ledger rebuild failed (non-fatal): {exc}",
            level="warning",
            stage="nugget_layup_compose",
        )
    return report


def gap_has_layup_before(gap_report: dict[str, Any] | None, segment_id: str) -> bool:
    """True when a contentful before-VO (layup or framing) targets this segment."""
    if not isinstance(gap_report, dict) or not segment_id:
        return False
    for ln in gap_report.get("interviewer_lines") or []:
        if not isinstance(ln, dict):
            continue
        if str(ln.get("placement") or "") != "before":
            continue
        if str(ln.get("targets_segment_id") or "") != segment_id:
            continue
        if not str(ln.get("text") or "").strip():
            continue
        # Orientation is not a per-native layup substitute for seam suppression
        # when it targets a different open segment — still counts for its target.
        return True
    return False


def gap_report_has_layup_authority(gap_report: dict[str, Any] | None) -> bool:
    """True when the published gap_report is owned by the Nugget Layup System."""
    if not isinstance(gap_report, dict):
        return False
    if not nugget_layup_enabled():
        return False
    if not nugget_layup_cfg().get("authoritative_gap_report", True):
        return False
    return bool(gap_report.get("nugget_layup_authority"))


def _body_lines(gap_report: dict[str, Any]) -> list[dict[str, Any]]:
    from interview_mux.opening_orientation import is_episode_orientation

    return [
        ln
        for ln in (gap_report.get("interviewer_lines") or [])
        if isinstance(ln, dict) and not is_episode_orientation(ln)
    ]


def lint_gap_report_layup_authority(
    ctx: RunContext,
    gap_report: dict[str, Any] | None = None,
) -> list[str]:
    """Authority lint: only lay-up copy in the body, at coverage, with no canned air."""
    if gap_report is None:
        gap_report = ctx.read_json(GAP_REL) if ctx.artifact_exists(GAP_REL) else {}
    if not gap_report_has_layup_authority(gap_report if isinstance(gap_report, dict) else None):
        return []
    cfg = nugget_layup_cfg()
    report = gap_report if isinstance(gap_report, dict) else {}
    body = _body_lines(report)
    errors: list[str] = []

    # The ``before`` slot is the lay-up slot; other placements may still carry
    # deterministic density seeds.
    foreign = sorted(
        {
            str(ln.get("origin") or "unknown")
            for ln in body
            if str(ln.get("placement") or "") == "before"
            and str(ln.get("origin") or "unknown") not in AUTHORITY_BODY_ORIGINS
        }
    )
    if foreign:
        errors.append(
            "gap_report before-VO written outside the layup publish path "
            f"(origins={foreign[:6]})"
        )

    ordered = _ordered_ids(ctx)
    exempt = coverage_exempt_target_ids(ctx)
    covered = {
        str(ln.get("targets_segment_id") or "")
        for ln in body
        if str(ln.get("origin") or "") == "nugget_layup"
        and str(ln.get("placement") or "") == "before"
        and str(ln.get("text") or "").strip()
    }
    eligible = [sid for sid in ordered if sid not in exempt]
    if eligible:
        coverage = len(covered & set(eligible)) / len(eligible)
        floor = float(cfg["min_layup_coverage"])
        if coverage + 1e-9 < floor:
            errors.append(
                f"gap_report layup coverage={coverage:.3f} below min_layup_coverage={floor}"
            )

    if cfg["ban_canned_air"]:
        for ln in body:
            violations = canned_air_violations(str(ln.get("text") or ""))
            if violations:
                errors.append(
                    f"canned air on {ln.get('line_id') or ln.get('targets_segment_id')}: "
                    + "; ".join(violations[:2])
                )

    if cfg["unique_nuggets_across_layups"]:
        owner: dict[str, str] = {}
        for ln in body:
            lid = str(ln.get("line_id") or ln.get("targets_segment_id") or "")
            for nid in [str(x) for x in (ln.get("nugget_ids") or []) if x]:
                if nid in owner and owner[nid] != lid:
                    errors.append(f"nugget {nid} claimed by {owner[nid]} and {lid}")
                else:
                    owner.setdefault(nid, lid)
    return list(dict.fromkeys(errors))


def assert_gap_report_layup_authority(
    ctx: RunContext,
    gap_report: dict[str, Any] | None = None,
    *,
    stage: str = "nugget_layup_compose",
) -> None:
    errors = lint_gap_report_layup_authority(ctx, gap_report)
    if not errors:
        return
    from interview_mux.loud_fail import raise_loud_failure

    raise_loud_failure(
        ctx,
        "Nugget layup authority violated in gap_report: " + "; ".join(errors[:4]),
        stage=stage,
        reason="nugget_layup_authority_violated",
        detail={"errors": errors[:8]},
    )


def restore_layup_lines(
    ctx: RunContext,
    gap_report: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Re-inject lay-up before-VO that another writer dropped from the body.

    Under authority the publish path owns body ``interviewer_lines``; a recompose
    or rebase that rewrites the artifact must not be able to wipe recovery copy.
    """
    report = dict(gap_report) if isinstance(gap_report, dict) else {}
    if not nugget_layup_enabled() or not nugget_layup_cfg().get("authoritative_gap_report", True):
        return report, []
    if not ctx.artifact_exists(PLAN_REL):
        return report, []
    plan = ctx.read_json(PLAN_REL)
    if not isinstance(plan, dict) or not plan.get("layups"):
        return report, []
    if layup_freshness_errors(ctx, plan):
        return report, []

    lines = [ln for ln in (report.get("interviewer_lines") or []) if isinstance(ln, dict)]
    have = {
        str(ln.get("targets_segment_id") or "")
        for ln in lines
        if str(ln.get("origin") or "") == "nugget_layup"
        and str(ln.get("text") or "").strip()
    }
    seen_texts = [
        str(ln.get("text") or "")
        for ln in lines
        if str(ln.get("text") or "").strip() and not ln.get("skipped_optional")
    ]
    ordered = set(_ordered_ids(ctx))
    opening_targets = _opening_owned_targets(ctx)
    restored: list[dict[str, Any]] = []
    from interview_mux.spoken_copy_guard import spoken_copy_violations

    for row in plan.get("layups") or []:
        line = layup_line_from_row(row if isinstance(row, dict) else {})
        if not line:
            continue
        tid = str(line["targets_segment_id"])
        if tid in opening_targets:
            continue
        if isinstance(row, dict) and is_justified_skip_row(row, soft_migrate=True):
            continue
        if tid in have or (ordered and tid not in ordered):
            continue
        text = str(line.get("text") or "").strip()
        if spoken_copy_violations(text, evidence={}, seen_texts=seen_texts):
            continue
        have.add(tid)
        lines.append(line)
        seen_texts.append(text)
        restored.append({"action": "restore_nugget_layup_line", "line_id": line["line_id"]})
    if not restored:
        return report, []
    report["interviewer_lines"] = lines
    report["nugget_layup_authority"] = True
    return report, restored


def normalize_layup_talking_point_ledger(
    ctx: RunContext, plan: dict[str, Any]
) -> dict[str, Any]:
    """Reconcile discharged/open talking-point ids before QC.

    LLMs often leave should_keep ids in ``open_talking_point_ids`` or list the
    same must_keep id in both open and discharged. Layup attachments win.
    """
    out = dict(plan) if isinstance(plan, dict) else {}
    layups = [r for r in (out.get("layups") or []) if isinstance(r, dict)]
    layup_tps = {
        str(x)
        for row in layups
        for x in (row.get("talking_point_ids") or [])
        if x
    }
    discharged = {
        str(x) for x in (out.get("discharged_talking_point_ids") or []) if x
    } | layup_tps
    must_keep_ids: set[str] = set()
    if ctx.artifact_exists("understanding/talking_points.json"):
        tp_doc = ctx.read_json("understanding/talking_points.json")
        for tp in (tp_doc.get("talking_points") or []) if isinstance(tp_doc, dict) else []:
            if not isinstance(tp, dict):
                continue
            if str(tp.get("importance") or "") != "must_keep":
                continue
            tpid = str(tp.get("talking_point_id") or "")
            if tpid:
                must_keep_ids.add(tpid)
    open_ids = []
    seen: set[str] = set()
    for raw in out.get("open_talking_point_ids") or []:
        tpid = str(raw or "")
        if not tpid or tpid in seen:
            continue
        seen.add(tpid)
        if tpid in must_keep_ids and tpid not in discharged:
            open_ids.append(tpid)
    for tpid in sorted(must_keep_ids):
        if tpid not in discharged and tpid not in seen:
            open_ids.append(tpid)
            seen.add(tpid)
    out["discharged_talking_point_ids"] = sorted(discharged)
    out["open_talking_point_ids"] = open_ids
    return out


def _talking_point_evidence_text(tp: dict[str, Any]) -> str:
    parts = [str(tp.get("title") or ""), str(tp.get("why_it_matters") or "")]
    for quote in tp.get("evidence_quotes") or []:
        parts.append(str(quote or ""))
    return " ".join(parts)


def _text_covers_talking_point(text: str, tp: dict[str, Any]) -> bool:
    hay = _norm(text).casefold()
    if not hay:
        return False
    for quote in tp.get("evidence_quotes") or []:
        qn = _norm(str(quote or "")).casefold()
        if len(qn) >= 6 and qn in hay:
            return True
    title = _norm(str(tp.get("title") or "")).casefold()
    if len(title) >= 8 and title in hay:
        return True
    return _overlap(_tokens(hay), _tokens(_talking_point_evidence_text(tp))) >= 0.35


def recover_open_must_keep_talking_points(
    ctx: RunContext,
    plan: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Attach or discharge leftover must_keep talking points already on tape.

    LLMs often leave must_keep ids open even when selected natives or existing
    layup copy already carry the thesis. Attach the id onto a matching layup
    row, or discharge when selected native text overlaps title/quotes. Do not
    invent new VO.
    """
    out = dict(plan) if isinstance(plan, dict) else {}
    out = normalize_layup_talking_point_ledger(ctx, out)
    open_ids = [str(x) for x in (out.get("open_talking_point_ids") or []) if x]
    if not open_ids:
        return out, []
    tp_by_id: dict[str, dict[str, Any]] = {}
    if ctx.artifact_exists("understanding/talking_points.json"):
        tp_doc = ctx.read_json("understanding/talking_points.json")
        for row in (tp_doc.get("talking_points") or []) if isinstance(tp_doc, dict) else []:
            if not isinstance(row, dict):
                continue
            tpid = str(row.get("talking_point_id") or "")
            if tpid:
                tp_by_id[tpid] = row
    layups = [r for r in (out.get("layups") or []) if isinstance(r, dict)]
    ordered = [str(x) for x in (out.get("ordered_segment_ids") or _ordered_ids(ctx)) if x]
    ordered_set = set(ordered)
    segs_by_id: dict[str, dict[str, Any]] = {}
    if ctx.artifact_exists("segments/manifest.json"):
        man = ctx.read_json("segments/manifest.json")
        if isinstance(man, dict):
            for row in man.get("segments") or []:
                if isinstance(row, dict) and row.get("segment_id"):
                    segs_by_id[str(row["segment_id"])] = row
    native_blob = " ".join(
        str((segs_by_id.get(sid) or {}).get("text") or "") for sid in ordered
    )
    notes: list[str] = []
    discharged = {str(x) for x in (out.get("discharged_talking_point_ids") or []) if x}
    remaining: list[str] = []
    for tpid in open_ids:
        tp = tp_by_id.get(tpid) or {}
        bound = {str(x) for x in (tp.get("segment_ids") or []) if x} & ordered_set
        attached = False
        for row in layups:
            if row.get("skip"):
                continue
            tid = str(row.get("target_segment_id") or "")
            blob = " ".join(
                str(row.get(k) or "")
                for k in ("text", "forward_unlock", "target_beat", "setup_from_nuggets")
            )
            if tid in bound or _text_covers_talking_point(blob, tp):
                ids = [str(x) for x in (row.get("talking_point_ids") or []) if x]
                if tpid not in ids:
                    ids.append(tpid)
                    row["talking_point_ids"] = ids
                discharged.add(tpid)
                attached = True
                notes.append(f"attached:{tpid}:{tid or 'layup'}")
                break
        if attached:
            continue
        if bound or _text_covers_talking_point(native_blob, tp):
            discharged.add(tpid)
            notes.append(f"already_on_tape:{tpid}")
            continue
        remaining.append(tpid)
    out["layups"] = layups
    out["discharged_talking_point_ids"] = sorted(discharged)
    out["open_talking_point_ids"] = remaining
    return normalize_layup_talking_point_ledger(ctx, out), notes


def evaluate_layup_qc(
    ctx: RunContext,
    plan: dict[str, Any] | None = None,
    corpus: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Coverage / recovery QC for the lay-up plan."""
    cfg = nugget_layup_cfg()
    if plan is None:
        plan = ctx.read_json(PLAN_REL) if ctx.artifact_exists(PLAN_REL) else {}
    if corpus is None:
        corpus = ctx.read_json(CORPUS_REL) if ctx.artifact_exists(CORPUS_REL) else {}
    plan, _ = dedupe_layup_rows_by_target(plan)
    plan = normalize_layup_talking_point_ledger(ctx, plan if isinstance(plan, dict) else {})
    corpus = corpus if isinstance(corpus, dict) else {}

    ordered = [str(x) for x in (plan.get("ordered_segment_ids") or _ordered_ids(ctx)) if x]
    layups = [r for r in (plan.get("layups") or []) if isinstance(r, dict)]
    by_target = {str(r.get("target_segment_id") or ""): r for r in layups if r.get("target_segment_id")}

    present = 0
    skips: list[dict[str, Any]] = []
    missing: list[str] = []
    for sid in ordered:
        row = by_target.get(sid)
        if row is None:
            missing.append(sid)
            continue
        if row.get("skip") or not str(row.get("text") or "").strip():
            skips.append(
                {
                    "segment_id": sid,
                    "skip_reason_code": row.get("skip_reason_code") or "empty_or_skip",
                }
            )
            continue
        present += 1

    eligible = [
        sid
        for sid in ordered
        if sid not in coverage_exempt_target_ids(ctx, plan)
    ]
    coverage = (present / len(eligible)) if eligible else 1.0
    open_must = [str(x) for x in (plan.get("open_talking_point_ids") or []) if x]

    open_high = [str(x) for x in (plan.get("open_high_salience_nugget_ids") or []) if x]
    for nug in corpus.get("nuggets") or []:
        if not isinstance(nug, dict):
            continue
        if nug.get("already_aired_in_selection"):
            continue
        sal = str(nug.get("salience") or "")
        if sal not in ("high", "critical"):
            continue
        if nug.get("in_selection") and not cfg.get("prefer_excluded_nuggets"):
            continue
        nid = str(nug.get("nugget_id") or "")
        if not nid:
            continue
        discharged_n = {str(x) for x in (plan.get("discharged_nugget_ids") or []) if x}
        waived = {
            str(x.get("nugget_id") or x)
            for x in (plan.get("waived_nugget_ids") or [])
            if isinstance(x, (dict, str))
        }
        assigned = False
        for row in layups:
            if nid in row_nugget_ids(row):
                assigned = True
                break
        if not assigned and nid not in discharged_n and nid not in waived and nid not in open_high:
            if not nug.get("in_selection"):
                open_high.append(nid)

    errors: list[str] = []
    if eligible and coverage + 1e-9 < float(cfg["min_layup_coverage"]):
        errors.append(
            f"layup_coverage={coverage:.3f} below min_layup_coverage={cfg['min_layup_coverage']}"
        )
    missing_required = [sid for sid in missing if sid not in set(ordered) - set(eligible)]
    if missing_required and cfg.get("require_layup_per_native"):
        errors.append(f"missing_layup_rows={missing_required[:12]}")
    if open_must and cfg.get("block_on_open_must_keep"):
        errors.append(f"open_must_keep_talking_points={open_must[:12]}")

    craft = evaluate_layup_craft(ctx, layups, cfg=cfg)
    errors.extend(craft["errors"])

    return {
        "version": 1,
        "ordered_count": len(ordered),
        "layup_present_count": present,
        "layup_coverage": round(coverage, 4),
        "skips": skips,
        "missing_targets": missing,
        "open_must_keep_talking_point_ids": open_must,
        "open_high_salience_nugget_ids": open_high,
        "canned_air_lines": craft["canned_air_lines"],
        "insufficient_analysis_targets": craft["insufficient_analysis_targets"],
        "duplicate_nugget_ids": craft["duplicate_nugget_ids"],
        "errors": errors,
        "ok": not errors,
    }


def evaluate_layup_craft(
    ctx: RunContext,
    layups: list[dict[str, Any]],
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Per-line construction QC: analysis depth, canned air, restates, uniqueness."""
    settings = cfg or nugget_layup_cfg()
    deg = settings.get("degraded_layup") if isinstance(settings.get("degraded_layup"), dict) else {}
    by_id = {
        str(r.get("segment_id")): r
        for r in _manifest_segments(ctx)
        if r.get("segment_id")
    }
    masks = {}
    if ctx.artifact_exists(MASKS_REL):
        try:
            loaded = ctx.read_json(MASKS_REL)
            if isinstance(loaded, dict):
                masks = loaded
        except Exception:
            masks = {}
    errors: list[str] = []
    warnings: list[str] = []
    canned_lines: list[dict[str, Any]] = []
    thin: list[str] = []
    duplicates: list[str] = []
    invented: list[str] = []
    owner: dict[str, str] = {}
    texts: list[tuple[str, set[str]]] = []
    seen_air_texts: list[str] = []
    grace_floor = int(deg.get("grace_min_layup_words") or 12)

    for row in layups:
        tid = str(row.get("target_segment_id") or "")
        text = _norm(str(row.get("text") or ""))
        if row.get("skip") or not text:
            continue
        mask = _mask_for(masks, tid)
        degraded = is_degraded_target(mask) or bool(row.get("degraded_lexicon_island"))
        if settings["require_analysis_fields"]:
            required = ("target_beat", "forward_unlock") if degraded else ANALYSIS_FIELDS
            absent = [f for f in required if not str(row.get(f) or "").strip()]
            soft_absent = []
            if degraded:
                soft_absent = [
                    f for f in ANALYSIS_FIELDS if f not in required and not str(row.get(f) or "").strip()
                ]
            if absent:
                thin.append(tid)
                errors.append(f"insufficient_analysis[{tid}]: missing {','.join(absent)}")
            elif soft_absent:
                warnings.append(f"soft_analysis[{tid}]: missing {','.join(soft_absent)}")
        if settings["ban_canned_air"]:
            violations = canned_air_violations(text)
            if violations:
                canned_lines.append({"target_segment_id": tid, "violations": violations})
                errors.append(f"canned_air[{tid}]: " + "; ".join(violations[:2]))
        try:
            from interview_mux.media_ip_cta import air_overlaps_never_touch

            if air_overlaps_never_touch(ctx, text):
                errors.append(f"never_touch_cta[{tid}]: lay-up reuses dropped CTA wording")
        except Exception:
            pass
        from interview_mux.spoken_copy_guard import spoken_copy_violations

        target_text = str(
            mask.get("comprehensible_text")
            or (by_id.get(tid) or {}).get("text")
            or ""
        )
        copy_hits = spoken_copy_violations(
            text,
            evidence={
                "target_excerpt": target_text,
                "before_excerpt": str(row.get("listener_need_entering_T") or ""),
                "after_topic": str(row.get("target_beat") or ""),
                "strict_grounding": False,
            },
            seen_texts=seen_air_texts,
        )
        if copy_hits:
            errors.append(f"spoken_copy[{tid}]: " + ", ".join(copy_hits[:3]))
        # Invented island claim: air text contains bracket placeholders / "unclear audio".
        low = text.casefold()
        if "[unclear" in low or "unclear audio" in low or "garbled" in low:
            invented.append(tid)
            errors.append(f"invented_island_claim[{tid}]: air text must not narrate unclear tokens")
        words = _word_count(text)
        # Grace floor only on degraded targets (clear targets keep the historical
        # compose budget without a hard craft fail on short fixtures).
        if degraded and words < grace_floor:
            errors.append(f"thin_layup[{tid}]: words={words} below grace_floor={grace_floor}")
        if target_text:
            restate = _overlap(_tokens(text), _tokens(target_text))
            if restate >= float(settings["max_target_restate_overlap"]):
                errors.append(f"restates_target[{tid}]: overlap={restate:.2f}")
        for nid in row_nugget_ids(row):
            if nid in owner and owner[nid] != tid:
                duplicates.append(nid)
                if settings["unique_nuggets_across_layups"]:
                    errors.append(
                        f"duplicate_nugget[{nid}]: claimed by {owner[nid]} and {tid}"
                    )
            else:
                owner.setdefault(nid, tid)
        tokens = _tokens(text)
        for other_tid, other_tokens in texts:
            overlap = _overlap(tokens, other_tokens)
            if overlap >= float(settings["max_cross_layup_overlap"]):
                errors.append(
                    f"cross_layup_overlap[{other_tid}->{tid}]: overlap={overlap:.2f}"
                )
        texts.append((tid, tokens))
        seen_air_texts.append(text)

    return {
        "errors": list(dict.fromkeys(errors)),
        "warnings": list(dict.fromkeys(warnings)),
        "canned_air_lines": canned_lines,
        "insufficient_analysis_targets": sorted(set(thin)),
        "duplicate_nugget_ids": sorted(set(duplicates)),
        "invented_island_targets": sorted(set(invented)),
    }


def assert_layup_qc_or_raise(ctx: RunContext, qc: dict[str, Any]) -> None:
    from interview_mux.artifact_writes import write_validated_artifact

    # QC artifact may lack a dedicated schema validator — write via ctx.
    try:
        write_validated_artifact(
            ctx,
            QC_REL,
            qc,
            merge_from_disk=False,
            stage_key="nugget_layup_compose",
        )
    except Exception:
        ctx.write_json(QC_REL, qc)
    if qc.get("ok"):
        return
    from interview_mux.loud_fail import raise_loud_failure

    raise_loud_failure(
        ctx,
        "Nugget layup QC failed: " + "; ".join(str(e) for e in (qc.get("errors") or [])[:8]),
        stage="nugget_layup_compose",
        reason="nugget_layup_qc_failed",
    )

def materialize_over_skipped_layups(
    ctx: RunContext,
    plan: dict[str, Any] | None = None,
    *,
    target_coverage: float | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Turn analysis-rich skip rows into spoken before-VO when LLM over-skipped.

    Uses forward_unlock / target_beat / corpus nuggets already attached to the
    row (or open must-keep talking points) so coverage can recover without canned hinges.
    """
    cfg = nugget_layup_cfg()
    floor = float(target_coverage if target_coverage is not None else cfg["min_layup_coverage"])
    notes: list[str] = []
    if plan is None:
        plan = ctx.read_json(PLAN_REL) if ctx.artifact_exists(PLAN_REL) else {}
    plan = normalize_layup_talking_point_ledger(ctx, plan if isinstance(plan, dict) else {})
    layups = [r for r in (plan.get("layups") or []) if isinstance(r, dict)]
    if not layups:
        return plan, ["no_layups"]

    corpus = ctx.read_json(CORPUS_REL) if ctx.artifact_exists(CORPUS_REL) else {}
    nug_by_id = {
        str(n.get("nugget_id") or ""): n
        for n in (corpus.get("nuggets") or [])
        if isinstance(n, dict) and n.get("nugget_id")
    }
    tp_doc = (
        ctx.read_json("understanding/talking_points.json")
        if ctx.artifact_exists("understanding/talking_points.json")
        else {}
    )
    tp_by_id = {
        str(tp.get("id") or tp.get("talking_point_id") or ""): tp
        for tp in (tp_doc.get("talking_points") or [])
        if isinstance(tp, dict)
    }

    ordered = [str(x) for x in (plan.get("ordered_segment_ids") or []) if x]
    by_target = {str(r.get("target_segment_id") or ""): r for r in layups if r.get("target_segment_id")}
    exempt = coverage_exempt_target_ids(ctx, plan)
    present = sum(
        1
        for sid in ordered
        if sid not in exempt
        and (row := by_target.get(sid))
        and not row.get("skip")
        and str(row.get("text") or "").strip()
    )
    eligible_n = max(1, len([sid for sid in ordered if sid not in exempt])) if ordered else 1
    need = max(0, int(math.ceil(floor * eligible_n - 1e-12)) - present)
    open_tps = [str(x) for x in (plan.get("open_talking_point_ids") or []) if x]
    claimed_nugs: set[str] = set()
    for row in layups:
        for nid in row_nugget_ids(row):
            claimed_nugs.add(nid)

    filled = 0
    for row in layups:
        if filled >= need and not open_tps:
            break
        if not row.get("skip") and str(row.get("text") or "").strip():
            continue
        tid = str(row.get("target_segment_id") or "")
        reason = str(row.get("skip_reason_code") or "")
        if is_justified_skip_row(row, soft_migrate=True):
            notes.append(f"preserve_justified_skip:{tid}:{reason or 'typed'}")
            continue
        if reason in {
            "spoken_copy_unhealable",
            "opening_orientation_owns_target",
            "clone_voice_adjacency",
            "media_ip_cta_hole",
        }:
            notes.append(f"preserve_unhealable_skip:{tid}:{reason}")
            continue
        if reason == "opening_orientation_owns_target":
            notes.append(f"preserve_opening_owned_skip:{tid}")
            continue
        if reason == "episode_open_native_self_orients" and filled >= need:
            continue
        unlock = str(row.get("forward_unlock") or "").strip()
        beat = str(row.get("target_beat") or "").strip()
        setup = str(row.get("setup_from_nuggets") or "").strip()
        listener = str(row.get("listener_need_entering_T") or "").strip()
        assigned_tps = [str(x) for x in (row.get("talking_point_ids") or []) if x]
        if not assigned_tps and open_tps:
            assigned_tps = [open_tps.pop(0)]
            row["talking_point_ids"] = list(
                dict.fromkeys([*(row.get("talking_point_ids") or []), *assigned_tps])
            )
        nug_bits: list[str] = []
        for nid in row_nugget_ids(row):
            nug = nug_by_id.get(nid)
            if not isinstance(nug, dict):
                continue
            bit = str(
                nug.get("text")
                or nug.get("text_claim")
                or nug.get("claim")
                or nug.get("summary")
                or ""
            ).strip()
            if bit:
                nug_bits.append(bit.rstrip(".") + ".")
                claimed_nugs.add(nid)
        if not nug_bits:
            for tpid in assigned_tps:
                tp = tp_by_id.get(tpid) or {}
                bit = str(tp.get("text") or tp.get("point") or tp.get("summary") or "").strip()
                if bit:
                    nug_bits.append(bit.rstrip(".") + ".")
                    break
            if not nug_bits:
                for nug in corpus.get("nuggets") or []:
                    if not isinstance(nug, dict):
                        continue
                    nid = str(nug.get("nugget_id") or "")
                    if not nid or nid in claimed_nugs:
                        continue
                    covers = {
                        str(x)
                        for x in (
                            nug.get("talking_point_ids")
                            or nug.get("covers_talking_point_ids")
                            or []
                        )
                        if x
                    }
                    if assigned_tps and covers.isdisjoint(assigned_tps):
                        continue
                    bit = str(
                        nug.get("text")
                        or nug.get("text_claim")
                        or nug.get("claim")
                        or nug.get("summary")
                        or ""
                    ).strip()
                    if not bit:
                        continue
                    nug_bits.append(bit.rstrip(".") + ".")
                    row["selected_nugget_ids"] = list(
                        dict.fromkeys([*(row.get("selected_nugget_ids") or []), nid])
                    )
                    row["nugget_ids"] = list(dict.fromkeys([*(row.get("nugget_ids") or []), nid]))
                    claimed_nugs.add(nid)
                    break
        parts = [
            p
            for p in (
                setup,
                *nug_bits[:2],
                unlock or beat,
                listener if len(listener) < 120 else "",
            )
            if p
        ]
        text = " ".join(parts).strip()
        text = " ".join(text.split())
        if len(text.split()) < int(cfg.get("min_layup_words") or 18):
            if beat and beat.lower() not in text.lower():
                text = f"{text} {beat}".strip() if text else beat
            text = " ".join(text.split())
        if len(text.split()) < 8:
            notes.append(f"skip_unmaterializable:{tid}")
            continue
        # Ensure last sentence satisfies has_forward_cue (question / next-beat cue).
        if unlock and not text.rstrip().endswith("?"):
            unlock_core = unlock.rstrip(".!?").strip()
            if unlock_core and unlock_core.casefold() in text.casefold():
                # Unlock body already present — don't append a duplicated
                # "What happens when …?" paraphrase (spoken_repeated_sentence).
                if not text.rstrip().endswith("?"):
                    text = text.rstrip(".!") + "?"
                row["forward_unlock"] = str(row.get("forward_unlock") or unlock).strip() or unlock
            else:
                cue = unlock if unlock.endswith("?") else (
                    unlock.rstrip(".!")
                    if unlock.lower().startswith(("what", "how", "why", "where", "when", "which"))
                    else f"What happens when {unlock[0].lower() + unlock[1:].rstrip('.!')}?"
                )
                if not cue.endswith("?"):
                    cue = cue.rstrip(".!") + "?"
                if canned_air_violations(cue) or _is_generic_unlock(cue):
                    cue = derive_forward_unlock(row, target_text=str(beat or ""))
                text = f"{text.rstrip('.!?')}. {cue}"
                text = " ".join(text.split())
                row["forward_unlock"] = str(row.get("forward_unlock") or cue).strip() or cue
        elif not text.rstrip().endswith("?"):
            cue = derive_forward_unlock(row, target_text=str(beat or ""))
            text = f"{text.rstrip('.!?')}. {cue}"
            text = " ".join(text.split())
            row["forward_unlock"] = str(row.get("forward_unlock") or cue).strip() or cue
        row["skip"] = False
        row.pop("skip_reason_code", None)
        row["text"] = text
        row["word_count"] = _word_count(text)
        row["forward_cue_ok"] = True
        row["materialized_from_skip"] = True
        filled += 1
        notes.append(f"materialized:{tid}")

    discharged = {str(x) for x in (plan.get("discharged_talking_point_ids") or []) if x}
    for row in layups:
        if row.get("skip") or not str(row.get("text") or "").strip():
            continue
        for tpid in row.get("talking_point_ids") or []:
            if tpid:
                discharged.add(str(tpid))
    plan["discharged_talking_point_ids"] = sorted(discharged)
    plan["layups"] = layups
    plan = normalize_layup_talking_point_ledger(ctx, plan)
    notes.append(f"filled={filled}")
    return plan, notes

