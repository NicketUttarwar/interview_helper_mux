"""Rebuild reorder bridges and auto-mint pair-specific spoken glue for naked seams."""

from __future__ import annotations

import hashlib
from typing import Any

from interview_mux.run_context import RunContext

# Chapter-scale source jump — spoken hinge required (and stinger when music on).
CHAPTER_SCALE_GAP_MS = 60_000

# Only used when mastering.synthetic_framing.allow_canned_bridge_fallback is on.
CANNED_BRIDGE_TEXT = "There is more to that story."

# Deterministic hinge menus for seams with no topic labels. Exported so the
# Nugget Layup System can ban the same strings as air copy under its authority.
REVERSE_HINGES = (
    "What had shaped the decision by that point?",
    "How had the story reached that turn?",
    "At that earlier point, what was already changing?",
    "What had set that choice in motion?",
    "At that stage, what mattered most?",
    "How had things shifted before that moment?",
    "What context had led to that point?",
    "At the outset, what was driving the change?",
    "What had already changed by then?",
    "How had that situation taken shape?",
    "At that point, what was guiding the choice?",
    "What had brought events to that moment?",
)
FORWARD_HINGES = (
    "What shifted from there?",
    "How did that shape what followed?",
    "What changed at that point?",
    "How did the situation develop from there?",
    "What became possible from that point?",
    "How did that decision change the course?",
    "What did that set in motion?",
    "Where did the story turn from there?",
    "How did events move forward from that point?",
    "What changed once that was in place?",
    "How did that lead into the later decision?",
    "What did that moment make possible?",
)
GENERIC_RELATIVE_HINGES = (
    "Stepping back, what set this part of the story in motion?",
    "What changed after that?",
)


def _chapter_ends_from_plan(plan: dict[str, Any] | None) -> set[str]:
    ends: set[str] = set()
    if not isinstance(plan, dict):
        return ends
    for ch in plan.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        ids = [str(x) for x in (ch.get("segment_ids") or []) if x]
        if ids:
            ends.add(ids[-1])
    return ends


def _narrative_mode(ctx: RunContext) -> str | None:
    for rel in (
        "mastering/mastering_plan.json",
        "master/narrative_plan.json",
    ):
        if not ctx.artifact_exists(rel):
            continue
        doc = ctx.read_json(rel)
        if isinstance(doc, dict) and doc.get("narrative_mode"):
            return str(doc.get("narrative_mode"))
    return None


def rebuild_reorder_bridges(
    ctx: RunContext,
    ordered: list[str],
    segments_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Rebuild + annotate bridges from the air order about to enter EDL."""
    from interview_mux.bridge_voice_policy import annotate_reorder_bridges
    from interview_mux.reorder_bridges import build_reorder_bridges

    plan = (
        ctx.read_json("master/narrative_plan.json")
        if ctx.artifact_exists("master/narrative_plan.json")
        else None
    )
    chapter_ends = _chapter_ends_from_plan(plan if isinstance(plan, dict) else None)
    # Also treat selection chapter last members as ends when narrative plan thin
    if ctx.artifact_exists("master/selection.json"):
        sel = ctx.read_json("master/selection.json")
        if isinstance(sel, dict):
            chapter_ends |= _chapter_ends_from_plan(sel)

    bridges = annotate_reorder_bridges(
        build_reorder_bridges(
            [str(s) for s in ordered if s],
            segments_by_id,
            chapter_ends=chapter_ends,
        ),
        narrative_mode=_narrative_mode(ctx),
    )
    ctx.write_json("understanding/reorder_bridges.json", bridges)
    return bridges


def _clip_excerpt(raw: Any, *, max_chars: int = 72) -> str:
    text = " ".join(str(raw or "").strip().split())
    if not text:
        return ""
    # Prefer a clean clause; strip trailing punctuation for hinge phrasing.
    if len(text) > max_chars:
        cut = text[:max_chars].rsplit(" ", 1)[0]
        text = cut or text[:max_chars]
    return text.rstrip(".,;:!—–- ").strip()


def _listener_topic(segment: dict[str, Any]) -> str:
    """Return a short listener-facing topic label, never an internal identifier."""
    candidates: list[Any] = [
        segment.get("topic"),
        segment.get("topic_label"),
        segment.get("title"),
    ]
    tags = segment.get("topic_tags")
    if isinstance(tags, list):
        candidates.extend(tags)
    for raw in candidates:
        text = _clip_excerpt(raw, max_chars=48)
        if not text:
            continue
        low = text.lower()
        if low.startswith(("seg_", "segment_", "segment ")):
            continue
        return text
    return ""


def _hinge_with_excerpt(lead_in: str, excerpt: str) -> str:
    """Join a short lead-in to an excerpt without doubled capitals after the dash."""
    ex = excerpt.strip()
    if ex and ex[0].isupper() and (len(ex) == 1 or not ex[1].isupper()):
        ex = ex[0].lower() + ex[1:]
    return f"{lead_in}{ex}."


def enrich_bridge_pair_excerpts(
    pair: dict[str, Any],
    segments_by_id: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    """Attach short after/before excerpts so fallback hinges stay pair-specific."""
    out = dict(pair)
    if not isinstance(segments_by_id, dict):
        return out
    after = str(out.get("after_segment_id") or out.get("after_id") or "")
    before = str(out.get("before_segment_id") or out.get("before_id") or "")
    for sid, key in ((after, "after_excerpt"), (before, "before_excerpt")):
        if out.get(key) or not sid:
            continue
        seg = segments_by_id.get(sid) or {}
        if not isinstance(seg, dict):
            continue
        excerpt = _clip_excerpt(seg.get("text") or seg.get("text_excerpt") or "")
        if excerpt:
            out[key] = excerpt
    for sid, key in ((after, "after_topic"), (before, "before_topic")):
        if out.get(key) or not sid:
            continue
        seg = segments_by_id.get(sid) or {}
        if not isinstance(seg, dict):
            continue
        topic = _listener_topic(seg)
        if topic:
            out[key] = topic
    return out


def bridge_guard_evidence(pair: dict[str, Any]) -> dict[str, Any]:
    """Map edit-side after/before fields to listener chronology for the guard."""
    return {
        **pair,
        "before_topic": pair.get("after_topic"),
        "after_topic": pair.get("before_topic"),
        "before_excerpt": pair.get("after_excerpt"),
        "after_excerpt": pair.get("before_excerpt"),
        "strict_grounding": True,
    }


def default_bridge_text(
    pair: dict[str, Any],
    *,
    used_texts: set[str] | frozenset[str] | None = None,
) -> str:
    """Deterministic listener-facing hinge with no internal metadata.

    Do **not** embed the next native excerpt ("And then—{before_excerpt}").
    Prefer topic labels when available. Otherwise use a semantic relative hinge;
    segment IDs are edit metadata and must never be spoken.

    When ``used_texts`` is provided, walk the hinge menu from the hash index
    until an unused line is found so adjacent seams don't collide.
    """
    from interview_mux.spoken_copy_guard import grounded_fallback_for_evidence

    fallback = grounded_fallback_for_evidence(bridge_guard_evidence(pair))
    if fallback not in set(GENERIC_RELATIVE_HINGES):
        return fallback
    # Reverse-order joins without topic labels previously all received the same
    # stock sentence, so three or more seams failed bridge completeness. Keep
    # the language chronology-safe while deterministically varying it per pair.
    reverse_hinges = REVERSE_HINGES
    forward_hinges = FORWARD_HINGES
    pair_key = (
        f"{pair.get('after_segment_id') or pair.get('after_id') or ''}->"
        f"{pair.get('before_segment_id') or pair.get('before_id') or ''}"
    )
    index = int(hashlib.sha256(pair_key.encode("utf-8")).hexdigest()[:8], 16)
    try:
        reverse = int(pair.get("source_gap_ms") or 0) < 0
    except (TypeError, ValueError):
        reverse = False
    hinges = reverse_hinges if reverse else forward_hinges
    used_norm = {
        " ".join(str(t or "").strip().lower().split())
        for t in (used_texts or set())
        if str(t or "").strip()
    }
    for offset in range(len(hinges)):
        candidate = hinges[(index + offset) % len(hinges)]
        norm = " ".join(candidate.strip().lower().split())
        if norm not in used_norm:
            return candidate
    return hinges[index % len(hinges)]


def is_chapter_scale_pair(pair: dict[str, Any]) -> bool:
    kind = str(pair.get("kind") or "")
    if kind == "chapter_jump":
        return True
    try:
        gap = int(pair.get("source_gap_ms")) if pair.get("source_gap_ms") is not None else 0
    except (TypeError, ValueError):
        gap = 0
    return abs(gap) >= CHAPTER_SCALE_GAP_MS


def mint_missing_transitions(
    ctx: RunContext,
    missing: list[dict[str, Any]],
    *,
    transitions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append pair-bound transition entries for every missing reorder seam.

    Returns the updated transitions document (also written to disk).
    """
    from interview_mux.spoken_copy_guard import assert_guarded_spoken_copy

    doc: dict[str, Any]
    if isinstance(transitions, dict):
        doc = dict(transitions)
    elif ctx.artifact_exists("master/transitions.json"):
        loaded = ctx.read_json("master/transitions.json")
        doc = dict(loaded) if isinstance(loaded, dict) else {"transitions": []}
    else:
        doc = {"transitions": []}

    items = [t for t in (doc.get("transitions") or []) if isinstance(t, dict)]
    existing = {
        (
            str(t.get("after_segment_id") or ""),
            str(t.get("before_segment_id") or ""),
        )
        for t in items
    }
    used_bridge_texts: set[str] = {
        str(t.get("text") or "").strip()
        for t in items
        if str(t.get("text") or "").strip()
    }
    if ctx.artifact_exists("understanding/gap_report.json"):
        gr_early = ctx.read_json("understanding/gap_report.json")
        if isinstance(gr_early, dict):
            for ln in gr_early.get("interviewer_lines") or []:
                if not isinstance(ln, dict) or ln.get("skipped_optional"):
                    continue
                txt = str(ln.get("text") or "").strip()
                if txt:
                    used_bridge_texts.add(txt)

    synthetic_plan = (
        ctx.read_json("understanding/synthetic_framing_plan.json")
        if ctx.artifact_exists("understanding/synthetic_framing_plan.json")
        else None
    )
    from interview_mux.synthetic_framing import (
        planned_transition_for_pair,
        synthetic_framing_cfg,
    )

    segments_by_id: dict[str, dict[str, Any]] = {}
    if ctx.artifact_exists("segments/manifest.json"):
        man = ctx.read_json("segments/manifest.json")
        segments_by_id = {
            str(s["segment_id"]): s
            for s in ((man or {}).get("segments") or [])
            if isinstance(s, dict) and s.get("segment_id")
        }

    minted = 0
    unplanned: list[str] = []
    allow_canned = bool(
        synthetic_framing_cfg().get("allow_canned_bridge_fallback", False)
    )
    gap_report = (
        ctx.read_json("understanding/gap_report.json")
        if ctx.artifact_exists("understanding/gap_report.json")
        else None
    )
    from interview_mux.gap_framing import transition_redundant_with_framing
    from interview_mux.nugget_layup import (
        PLAN_REL,
        gap_has_layup_before,
        nugget_layup_cfg,
        nugget_layup_enabled,
    )

    layup_cfg = nugget_layup_cfg()
    suppress_when_layup = bool(
        nugget_layup_enabled()
        and layup_cfg.get("suppress_placeholder_seams_when_layup", True)
    )
    # Under layup authority every known native gets constructed air copy; a canned
    # hinge here would ship interchangeable filler instead. Fail so the driver can
    # recompose the plan.
    ban_canned_air = bool(
        nugget_layup_enabled()
        and layup_cfg.get("ban_canned_air", True)
        and layup_cfg.get("authoritative_gap_report", True)
        and ctx.artifact_exists(PLAN_REL)
    )
    layup_targets: set[str] = set()
    if ban_canned_air:
        plan = ctx.read_json(PLAN_REL)
        if isinstance(plan, dict):
            # A deliberate skip (self-explanatory clip) may still take a hinge;
            # a target the plan never composed for must not.
            skipped = {
                str(row.get("target_segment_id") or "")
                for row in (plan.get("layups") or [])
                if isinstance(row, dict) and row.get("skip")
            }
            layup_targets = {
                str(x)
                for x in (plan.get("ordered_segment_ids") or [])
                if x and str(x) not in skipped
            }

    for pair in missing:
        if not isinstance(pair, dict):
            continue
        pair = enrich_bridge_pair_excerpts(pair, segments_by_id)
        a = str(pair.get("after_segment_id") or "")
        b = str(pair.get("before_segment_id") or "")
        if not a or not b or (a, b) in existing:
            continue
        if transition_redundant_with_framing(gap_report, a, b):
            continue
        # Contentful lay-up before the next native already covers the seam.
        if suppress_when_layup and gap_has_layup_before(gap_report if isinstance(gap_report, dict) else None, b):
            existing.add((a, b))
            continue
        planned = planned_transition_for_pair(synthetic_plan, a, b)
        if not planned:
            if ban_canned_air and b in layup_targets:
                from interview_mux.loud_fail import raise_loud_failure

                raise_loud_failure(
                    ctx,
                    "Canned seam air blocked under nugget layup authority: "
                    f"{a}->{b} has no composed lay-up or planned transition",
                    stage="edl",
                    reason="canned_air_under_layup_authority",
                    detail={"after_segment_id": a, "before_segment_id": b},
                )
            # Prefer pair-aware default glue over aborting remaster. The canned
            # phrase is only used when explicitly allowed; otherwise mint a
            # deterministic hinge from default_bridge_text so mix can proceed.
            if allow_canned:
                text = CANNED_BRIDGE_TEXT
                canned = True
            else:
                text = default_bridge_text(pair, used_texts=used_bridge_texts)
                canned = False
                unplanned.append(f"{a}->{b}")
            decision = assert_guarded_spoken_copy(
                text,
                evidence=bridge_guard_evidence(pair),
                purpose=f"transition[{a}->{b}]",
            )
            text = str(decision["text"])
            canned = bool(canned and decision["action"] == "allow")
            tr_type = "chapter" if is_chapter_scale_pair(pair) else "bridge"
            items.append(
                {
                    "after_segment_id": a,
                    "before_segment_id": b,
                    "text": text,
                    "type": tr_type,
                    "auto_minted": True,
                    "canned_bridge_fallback": canned,
                    "default_bridge_fallback": not canned,
                    "spoken_copy_guard": {
                        "action": decision["action"],
                        "script_hash": decision["script_hash"],
                        "context_hash": decision["context_hash"],
                    },
                    "kind": pair.get("kind") or "reorder",
                    "source_gap_ms": pair.get("source_gap_ms"),
                }
            )
            if text.strip():
                used_bridge_texts.add(text.strip())
            existing.add((a, b))
            minted += 1
            continue
        text = str(planned.get("text") or "").strip()
        decision = assert_guarded_spoken_copy(
            text,
            evidence=bridge_guard_evidence(pair),
            purpose=f"transition[{a}->{b}]",
        )
        text = str(decision["text"])
        tr_type = "chapter" if is_chapter_scale_pair(pair) else "bridge"
        items.append(
            {
                "after_segment_id": a,
                "before_segment_id": b,
                "text": text,
                "type": tr_type,
                "auto_minted": False,
                "synthetic_plan_line_id": planned.get("line_id"),
                "target_duration_ms": planned.get("target_duration_ms"),
                "comprehension_reason": planned.get("comprehension_reason"),
                "kind": pair.get("kind") or "reorder",
                "source_gap_ms": pair.get("source_gap_ms"),
                "spoken_copy_guard": {
                    "action": decision["action"],
                    "script_hash": decision["script_hash"],
                    "context_hash": decision["context_hash"],
                },
            }
        )
        if text.strip():
            used_bridge_texts.add(text.strip())
        existing.add((a, b))
        minted += 1

    if unplanned:
        ctx.log(
            "seam_glue: filled "
            + str(len(unplanned))
            + " reorder seam(s) with default_bridge_text (synthetic plan incomplete): "
            + ", ".join(unplanned[:8]),
            level="warning",
            stage="edl",
            detail={"missing_pairs": unplanned},
        )
    doc["transitions"] = items
    if minted:
        ctx.write_json("master/transitions.json", doc)
        ctx.log(
            f"seam_glue: materialized {minted} planned spoken transition(s) for reorder joins",
            level="info",
            stage="edl",
            detail={"minted": minted},
        )
    return doc


def ensure_seam_glue(
    ctx: RunContext,
    *,
    ordered: list[str],
    segments_by_id: dict[str, dict[str, Any]],
    gap_report: dict[str, Any] | None,
    transitions: dict[str, Any] | None,
    soft: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Rebuild bridges, mint missing transitions, assert pair-specific completeness.

    Returns (bridges, transitions_doc, completeness_doc).
    """
    from interview_mux.bridge_completeness import (
        assert_bridges_complete,
        missing_reorder_bridges,
    )

    bridges = rebuild_reorder_bridges(ctx, ordered, segments_by_id)
    missing = missing_reorder_bridges(
        bridges,
        gap_report=gap_report,
        transitions=transitions,
    )
    transitions_doc = transitions if isinstance(transitions, dict) else {"transitions": []}
    if missing:
        transitions_doc = mint_missing_transitions(
            ctx, missing, transitions=transitions_doc
        )
    completeness = assert_bridges_complete(
        bridges,
        gap_report=gap_report,
        transitions=transitions_doc,
        soft=soft,
    )
    ctx.write_json("master/bridge_completeness.json", completeness)
    return bridges, transitions_doc, completeness
