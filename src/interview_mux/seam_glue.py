"""Rebuild reorder bridges and auto-mint pair-specific spoken glue for naked seams."""

from __future__ import annotations

import re
from typing import Any

from interview_mux.run_context import RunContext

_TRANSCRIPT_FILLER = re.compile(
    r"^(?:okay\.?|well\.?|you know,?|so,?|right\??|um+|uh+)\s+",
    re.IGNORECASE,
)
_TOPIC_STOP = frozenset(
    """
    a an and as at be but by for from had has have how i if in is it its
    just like of on or our so that the this to was we well were what when
    where which with you your okay right yeah
    """.split()
)
_SIGNOFF = re.compile(
    r"\b(?:that was a great conversation|what did you think|best wishes|"
    r"thank(?:s| you)|co-?founder|that is fantastic)\b",
    re.IGNORECASE,
)
_TOPIC_PREFER = re.compile(
    r"cell|blood|biops|tumor|assay|scan|captur|diagnos|cancer|liquid|"
    r"tissue|market|company|found|product|patient",
    re.IGNORECASE,
)

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
# Relative filler hinges are banned; keep the empty tuple for callers that
# still check membership when preferring grounded topic fallbacks.
GENERIC_RELATIVE_HINGES: tuple[str, ...] = ()


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

    vo_shape = None
    try:
        from interview_mux.speaker_delivery_plan import episode_vo_identity

        vo_shape = str((episode_vo_identity(ctx) or {}).get("vo_shape") or "") or None
    except Exception:
        vo_shape = None
    bridges = annotate_reorder_bridges(
        build_reorder_bridges(
            [str(s) for s in ordered if s],
            segments_by_id,
            chapter_ends=chapter_ends,
        ),
        narrative_mode=_narrative_mode(ctx),
        episode_vo_shape=vo_shape,
    )
    # Bridge rebuild also runs from sealed consumers (edl). When the owner has
    # frozen reorder_bridges, hand the rebuilt body back in memory rather than
    # rewriting the sealed artifact.
    if not _bridges_write_permitted(ctx):
        return bridges
    ctx.write_json("understanding/reorder_bridges.json", bridges)
    try:
        from interview_mux.write_staging import write_committed_json

        write_committed_json(
            ctx,
            "understanding/reorder_bridges.json",
            bridges,
            stage_key="edl",
        )
    except Exception:
        pass
    return bridges


def _bridges_write_permitted(ctx: RunContext) -> bool:
    """True when the active stage may persist understanding/reorder_bridges.json."""
    try:
        from interview_mux.artifact_ownership import write_permitted
        from interview_mux.write_staging import active_stage_id

        stage_now = str(active_stage_id() or "")
        allowed, reason = write_permitted(
            ctx,
            "understanding/reorder_bridges.json",
            stage_now,
            role="producer",
            verb="persist",
        )
    except Exception:
        return True
    if not allowed:
        ctx.log(
            "seam glue: reorder_bridges frozen — keeping rebuild in memory "
            f"(stage={stage_now or 'unknown'}, {reason})",
            level="info",
            stage=stage_now or None,
        )
        return False
    return True


def _clip_excerpt(raw: Any, *, max_chars: int = 72) -> str:
    text = " ".join(str(raw or "").strip().split())
    if not text:
        return ""
    # Prefer a clean clause; strip trailing punctuation for hinge phrasing.
    if len(text) > max_chars:
        cut = text[:max_chars].rsplit(" ", 1)[0]
        text = cut or text[:max_chars]
    return text.rstrip(".,;:!—–- ").strip()


def _topic_from_transcript(raw: Any) -> str:
    """Short content phrase from native text when topic tags are empty."""
    blob = " ".join(str(raw or "").split())
    if not blob:
        return ""
    blob = re.split(
        r"\b(?:thanks\.|thank you|that is fantastic|mohan, thank)\b",
        blob,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    sentences = [s.strip() for s in re.split(r"[.!?]+", blob) if len(s.strip()) >= 18]
    grams: list[tuple[int, str]] = []
    for sent in sentences:
        if _SIGNOFF.search(sent):
            continue
        while True:
            nxt = _TRANSCRIPT_FILLER.sub("", sent).strip()
            if nxt == sent:
                break
            sent = nxt
        words = [
            token.rstrip("'")
            for token in re.findall(r"[A-Za-z][A-Za-z'-]*", sent)
            if token.rstrip("'").casefold() not in _TOPIC_STOP
        ]
        for i in range(len(words) - 1):
            a, b = words[i], words[i + 1]
            if len(a) < 4 or len(b) < 4:
                continue
            phrase = f"{a} {b}"
            score = sum(1 for token in (a, b) if _TOPIC_PREFER.search(token))
            grams.append((score, phrase))
    if not grams:
        return ""
    best_score = max(item[0] for item in grams)
    if best_score > 0:
        phrase = next(item[1] for item in reversed(grams) if item[0] == best_score)
    else:
        # Prefer an early content bigram over a trailing filler gram.
        phrase = grams[0][1]
    return _clip_excerpt(phrase, max_chars=48)


def _is_internal_topic_label(raw: Any) -> bool:
    """True for pipeline/snake_case tags that must never be spoken on air."""
    text = str(raw or "").strip()
    if not text:
        return True
    low = text.casefold()
    if low.startswith(("seg_", "segment_", "segment ")):
        return True
    # chapter_close_hitch, air_script_omit, etc.
    if re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)+", low):
        return True
    if "_" in text and " " not in text:
        return True
    return False


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
        if not text or _is_internal_topic_label(text):
            continue
        return text
    return _topic_from_transcript(segment.get("text") or segment.get("text_excerpt") or "")


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


def pair_covered_without_spoken_glue(
    ctx: RunContext,
    after_id: str,
    before_id: str,
    *,
    justified_skip_targets: set[str] | frozenset[str] | None = None,
) -> bool:
    """True when hitch/music or a justified skip already covers the reorder join.

    F4 3C: do not mint spoken glue (and do not fail closed) when that cover exists.
    """
    a = str(after_id or "").strip()
    b = str(before_id or "").strip()
    if not a or not b:
        return False
    skips = {str(x) for x in (justified_skip_targets or set()) if str(x).strip()}
    if b in skips:
        return True
    try:
        from interview_mux.air_script import native_handoff_segment_ids
        from interview_mux.mastering_plan_loader import load_plan_raw

        if b in native_handoff_segment_ids(load_plan_raw(ctx)):
            return True
    except Exception:
        pass
    if not ctx.artifact_exists("master/edl.json"):
        return False
    try:
        from interview_mux.assembly_ledger import hitch_covered_pairs

        edl = ctx.read_json("master/edl.json")
        clips = (
            [c for c in (edl.get("clips") or []) if isinstance(c, dict)]
            if isinstance(edl, dict)
            else []
        )
        return (a, b) in hitch_covered_pairs(clips)
    except Exception:
        return False


def default_bridge_text(
    pair: dict[str, Any],
    *,
    used_texts: set[str] | frozenset[str] | None = None,
) -> str:
    """Deterministic listener-facing hinge with no internal metadata.

    Do **not** embed the next native excerpt ("And then—{before_excerpt}").
    Prefer topic / person / place / time / causal evidence only. Relative filler
    hinges are banned — return empty when evidence cannot ground a speakable line.
    Segment IDs are edit metadata and must never be spoken.

    When ``used_texts`` is provided, refuse a grounded fallback that collides.
    """
    from interview_mux.spoken_copy_guard import (
        grounded_fallback_for_evidence,
        spoken_copy_violations,
    )

    fallback = grounded_fallback_for_evidence(bridge_guard_evidence(pair))
    if not fallback:
        return ""
    used = [str(t) for t in (used_texts or set()) if str(t or "").strip()]
    if spoken_copy_violations(fallback, evidence=bridge_guard_evidence(pair), seen_texts=used):
        return ""
    return fallback


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
    gap_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append pair-bound transition entries for every missing reorder seam.

    Returns the updated transitions document (also written to disk).

    ``gap_report`` must be the same document used for ``missing_reorder_bridges`` /
    ``assert_bridges_complete``. Re-reading disk alone can disagree with an
    in-memory repair (e.g. ``skipped_optional`` overlap marks) and suppress
    minting while completeness still sees the seam as uncovered.
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
    if isinstance(gap_report, dict):
        gr_early = gap_report
    elif ctx.artifact_exists("understanding/gap_report.json"):
        loaded_gap = ctx.read_json("understanding/gap_report.json")
        gr_early = loaded_gap if isinstance(loaded_gap, dict) else None
    else:
        gr_early = None
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
    if isinstance(synthetic_plan, dict):
        for ln in synthetic_plan.get("lines") or []:
            if not isinstance(ln, dict):
                continue
            txt = str(ln.get("text") or "").strip()
            if txt:
                used_bridge_texts.add(txt)
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
    if not isinstance(gap_report, dict):
        gap_report = (
            ctx.read_json("understanding/gap_report.json")
            if ctx.artifact_exists("understanding/gap_report.json")
            else None
        )
    from interview_mux.gap_framing import transition_redundant_with_framing
    from interview_mux.nugget_layup import (
        PLAN_REL,
        gap_has_layup_before,
        is_justified_skip_row,
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
    justified_skip_targets: set[str] = set()
    if ban_canned_air:
        plan = ctx.read_json(PLAN_REL)
        if isinstance(plan, dict):
            # A deliberate typed skip may omit spoken layup; unjustified skips still
            # must not accept canned hinge air under authority.
            for row in plan.get("layups") or []:
                if not isinstance(row, dict):
                    continue
                tid = str(row.get("target_segment_id") or "")
                if not tid:
                    continue
                if row.get("skip") and is_justified_skip_row(row, soft_migrate=True):
                    justified_skip_targets.add(tid)
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
        if not a or not b or a == b or (a, b) in existing:
            continue
        try:
            gap = pair.get("source_gap_ms")
            if gap is None:
                from interview_mux.air_order_integrity import (
                    pair_source_gap_ms,
                    resolved_segment_starts,
                    reverse_jump_margin_ms,
                )

                starts = resolved_segment_starts(ctx)
                gap = pair_source_gap_ms(a, b, starts)
            if gap is not None and int(gap) < -reverse_jump_margin_ms(ctx=ctx):
                continue
        except Exception:
            pass
        if transition_redundant_with_framing(gap_report, a, b):
            continue
        # Contentful lay-up before the next native already covers the seam.
        if suppress_when_layup and gap_has_layup_before(gap_report if isinstance(gap_report, dict) else None, b):
            existing.add((a, b))
            continue
        # Justified omit / opening ownership: do not mint canned hinge.
        if b in justified_skip_targets:
            existing.add((a, b))
            continue
        planned = planned_transition_for_pair(synthetic_plan, a, b)
        if not planned and ctx.artifact_exists("master/transitions.json"):
            try:
                tr_doc = ctx.read_json("master/transitions.json")
                for row in (tr_doc or {}).get("transitions") or []:
                    if not isinstance(row, dict):
                        continue
                    if (
                        str(row.get("after_segment_id") or "") == a
                        and str(row.get("before_segment_id") or "") == b
                    ):
                        planned = row
                        break
            except Exception:
                planned = None
        if not planned:
            if ban_canned_air and b in layup_targets:
                # Pair-aware hinge from excerpts — do not abort EDL to recompose
                # layup forever when the seam is already known.
                text = default_bridge_text(pair, used_texts=used_bridge_texts)
                if not str(text or "").strip():
                    # Strip internal tag topics and retry from native transcripts
                    # (topic_tags like chapter_close_hitch must not empty the seam).
                    pair_retry = dict(pair)
                    for key in ("after_topic", "before_topic"):
                        if _is_internal_topic_label(pair_retry.get(key)):
                            pair_retry.pop(key, None)
                    for sid, key in ((a, "after_topic"), (b, "before_topic")):
                        if pair_retry.get(key) or not sid:
                            continue
                        seg = segments_by_id.get(sid) or {}
                        if not isinstance(seg, dict):
                            continue
                        derived = _topic_from_transcript(
                            seg.get("text") or seg.get("text_excerpt") or ""
                        )
                        if derived:
                            pair_retry[key] = derived
                    text = default_bridge_text(
                        pair_retry, used_texts=used_bridge_texts
                    )
                canned = False
                unplanned.append(f"{a}->{b}")
                if not str(text or "").strip():
                    if pair_covered_without_spoken_glue(
                        ctx, a, b, justified_skip_targets=justified_skip_targets
                    ):
                        existing.add((a, b))
                        continue
                    _log_unglued_seam(ctx, a, b, "no grounded bridge text")
                    existing.add((a, b))
                    continue
                # fall through to append using text below — skip canned raise
                planned = {"text": text, "_minted_seam": True}
            # Prefer pair-aware default glue over aborting remaster. The canned
            # phrase is only used when explicitly allowed; otherwise mint a
            # deterministic hinge from default_bridge_text so mix can proceed.
            elif allow_canned:
                text = CANNED_BRIDGE_TEXT
                canned = True
            else:
                text = default_bridge_text(pair, used_texts=used_bridge_texts)
                canned = False
                unplanned.append(f"{a}->{b}")
            if not str(text or "").strip():
                if pair_covered_without_spoken_glue(
                    ctx, a, b, justified_skip_targets=justified_skip_targets
                ):
                    existing.add((a, b))
                    continue
                _log_unglued_seam(ctx, a, b, "no topic/person/place evidence for speakable VO")
                existing.add((a, b))
                continue
            try:
                decision = assert_guarded_spoken_copy(
                    text,
                    evidence=bridge_guard_evidence(pair),
                    purpose=f"transition[{a}->{b}]",
                    seen_texts=sorted(used_bridge_texts),
                    ctx=ctx,
                )
            except ValueError as exc:
                _log_unglued_seam(ctx, a, b, str(exc))
                existing.add((a, b))
                continue
            text = str(decision["text"])
            if not text.strip():
                # Guard omitted duplicate/stock — do not append empty self-echo.
                existing.add((a, b))
                continue
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
        # Materializing the plan row into transitions is one air owner, not a
        # duplicate — exclude this planned string from the collision corpus.
        seen_for_planned = sorted(
            t for t in used_bridge_texts if t.casefold() != text.casefold()
        )
        try:
            decision = assert_guarded_spoken_copy(
                text,
                evidence=bridge_guard_evidence(pair),
                purpose=f"transition[{a}->{b}]",
                seen_texts=seen_for_planned,
                ctx=ctx,
            )
        except ValueError as exc:
            _log_unglued_seam(ctx, a, b, str(exc))
            existing.add((a, b))
            continue
        text = str(decision["text"])
        if not text.strip():
            existing.add((a, b))
            continue
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
        from interview_mux.transition_vo import persist_transitions_doc

        # End-A: fill uncovered reorder seams under hard VO freeze (layup waive
        # leaves pair-specific hinge text; never invent hosted seats).
        ctx_doc = persist_transitions_doc(
            ctx,
            doc,
            stage_key="transitions",
            reason="bridge_completeness_mint",
        )
        doc = ctx_doc if isinstance(ctx_doc, dict) else doc
        ctx.log(
            f"seam_glue: materialized {minted} planned spoken transition(s) for reorder joins",
            level="info",
            stage="transitions",
            detail={"minted": minted, "reason": "bridge_completeness_mint"},
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
    from interview_mux.nugget_layup import (
        PLAN_REL,
        is_justified_skip_row,
        nugget_layup_enabled,
    )

    justified_skip_before: set[str] = set()
    if nugget_layup_enabled() and ctx.artifact_exists(PLAN_REL):
        plan = ctx.read_json(PLAN_REL)
        if isinstance(plan, dict):
            for row in plan.get("layups") or []:
                if not isinstance(row, dict) or not row.get("skip"):
                    continue
                tid = str(row.get("target_segment_id") or "").strip()
                if tid and is_justified_skip_row(row, soft_migrate=True):
                    justified_skip_before.add(tid)
    try:
        from interview_mux.air_script import native_handoff_segment_ids
        from interview_mux.mastering_plan_loader import load_plan_raw

        justified_skip_before |= native_handoff_segment_ids(load_plan_raw(ctx))
    except Exception:
        pass

    bridges = rebuild_reorder_bridges(ctx, ordered, segments_by_id)
    edl = (
        ctx.read_json("master/edl.json")
        if ctx.artifact_exists("master/edl.json")
        else None
    )
    missing = missing_reorder_bridges(
        bridges,
        gap_report=gap_report,
        transitions=transitions,
        justified_skip_before_ids=justified_skip_before,
        edl=edl if isinstance(edl, dict) else None,
    )
    from interview_mux.bridge_completeness import forbidden_bridge_pairs

    forbidden = forbidden_bridge_pairs(ctx, missing)
    missing = [
        m for m in missing if (m.get("after_segment_id"), m.get("before_segment_id")) not in forbidden
    ]
    transitions_doc = transitions if isinstance(transitions, dict) else {"transitions": []}
    if missing:
        transitions_doc = mint_missing_transitions(
            ctx,
            missing,
            transitions=transitions_doc,
            gap_report=gap_report if isinstance(gap_report, dict) else None,
        )
    completeness = assert_bridges_complete(
        bridges,
        gap_report=gap_report,
        transitions=transitions_doc,
        justified_skip_before_ids=justified_skip_before,
        edl=edl if isinstance(edl, dict) else None,
        soft=soft,
    )
    ctx.write_json("master/bridge_completeness.json", completeness)
    return bridges, transitions_doc, completeness



def _log_unglued_seam(ctx: Any, a: str, b: str, why: str) -> None:
    """A seam with no speakable grounded bridge plays without spoken glue.

    It used to raise a loud failure (canned_air_under_layup_authority /
    ungrounded_seam_bridge) or a guard ValueError; the evidence is fixed, so
    every retry refused the same seam (ISSUES 185; 151, 182).
    """
    try:
        ctx.log(
            f"seam glue: {a}->{b} left without spoken glue (advisory): {why[:200]}",
            level="warning",
            stage="transitions",
        )
    except Exception:
        pass
