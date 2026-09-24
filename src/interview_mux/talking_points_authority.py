"""Talking-points-first deterministic coverage + narrative (skip redundant LLMs).

When ideal cuts materialized with segment_id bindings, coverage and narrative
arc are derived from talking points rather than inventing a second keep/order
story via LLM.
"""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config
from interview_mux.ideal_cuts import MATERIALIZED_REL, TALKING_POINTS_REL, ideal_cuts_cfg
from interview_mux.run_context import RunContext


def talking_points_authority_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = ((cfg or merged_config()).get("analysis") or {}).get("talking_points_authority") or {}
    defaults = {
        # When talking points + materialized cuts exist, skip coverage LLM.
        "deterministic_coverage": True,
        # When talking points + cuts (and optional mastering_plan) exist, skip narrative LLM.
        "deterministic_narrative": True,
        # When ideal-cut boundaries are bound, skip classification LLM.
        "deterministic_classification": True,
    }
    if isinstance(raw, dict):
        return {**defaults, **raw}
    return defaults


def _cuts_by_tp(materialized: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for cut in materialized.get("cuts") or []:
        if not isinstance(cut, dict):
            continue
        tp = str(cut.get("talking_point_id") or "").strip()
        if not tp:
            continue
        out.setdefault(tp, []).append(cut)
    return out


def coverage_from_talking_points(
    talking_points: dict[str, Any],
    materialized: dict[str, Any],
    *,
    manifest_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Build coverage_audit schema from must/should talking points → cut segment_ids."""
    by_tp = _cuts_by_tp(materialized)
    mappings: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    must_total = 0
    must_covered = 0
    covered_segs: set[str] = set()

    for tp in talking_points.get("talking_points") or []:
        if not isinstance(tp, dict):
            continue
        importance = str(tp.get("importance") or "optional").strip().lower()
        if importance not in {"must_keep", "should_keep"}:
            continue
        tid = str(tp.get("talking_point_id") or "").strip()
        title = str(tp.get("title") or tid or "talking_point").strip()
        cuts = by_tp.get(tid) or []
        seg_ids: list[str] = []
        for cut in cuts:
            sid = str(cut.get("segment_id") or "").strip()
            if not sid:
                continue
            if manifest_ids is not None and sid not in manifest_ids:
                continue
            if sid not in seg_ids:
                seg_ids.append(sid)
                covered_segs.add(sid)
        covered = bool(seg_ids)
        mappings.append(
            {
                "topic": title,
                "segment_ids": seg_ids,
                "covered": covered,
            }
        )
        if importance == "must_keep":
            must_total += 1
            if covered:
                must_covered += 1
            else:
                missing.append(
                    {
                        "item": title,
                        "suggestion": f"No ideal-cut segment bound for talking_point_id={tid}",
                    }
                )
        elif not covered:
            missing.append(
                {
                    "item": title,
                    "suggestion": f"Optional/should_keep point lacks native cut: {tid}",
                }
            )

    score = 1.0 if must_total == 0 else round(must_covered / must_total, 4)
    all_cut_segs = {
        str(c.get("segment_id"))
        for c in (materialized.get("cuts") or [])
        if isinstance(c, dict) and c.get("segment_id")
    }
    orphans = sorted(all_cut_segs - covered_segs) if all_cut_segs else []
    return {
        "topic_mappings": mappings,
        "claim_mappings": [],
        "missing_coverage": missing,
        "orphan_segment_ids": orphans,
        "coverage_score": score,
        "_meta": {
            "source": "talking_points_authority",
            "must_keep_total": must_total,
            "must_keep_covered": must_covered,
        },
    }


def narrative_from_talking_points(
    talking_points: dict[str, Any],
    materialized: dict[str, Any],
    *,
    mastering_plan: dict[str, Any] | None = None,
    coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a minimal narrative_plan from talking-point order + optional Shape plan."""
    by_tp = _cuts_by_tp(materialized)
    through = str(talking_points.get("through_line") or "").strip()
    strategy = str(talking_points.get("strategy_summary") or "").strip()
    mode = ""
    if isinstance(mastering_plan, dict):
        mode = str(
            mastering_plan.get("confirmed_mode")
            or mastering_plan.get("narrative_mode")
            or mastering_plan.get("provisional_mode")
            or ""
        ).strip()

    chapters: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []
    prev_open: str | None = None
    chapter_i = 0

    for tp in talking_points.get("talking_points") or []:
        if not isinstance(tp, dict):
            continue
        importance = str(tp.get("importance") or "optional").strip().lower()
        if importance == "optional":
            continue
        tid = str(tp.get("talking_point_id") or "").strip()
        title = str(tp.get("title") or tid or f"chapter_{chapter_i + 1}").strip()
        cuts = sorted(
            by_tp.get(tid) or [],
            key=lambda c: int(c.get("start_ms") or 0),
        )
        seg_ids: list[str] = []
        for cut in cuts:
            sid = str(cut.get("segment_id") or "").strip()
            if sid and sid not in seg_ids:
                seg_ids.append(sid)
        if not seg_ids:
            continue
        chapter_i += 1
        open_id = seg_ids[0]
        chapters.append(
            {
                "chapter_id": f"ch_{chapter_i:02d}_{tid}" if tid else f"ch_{chapter_i:02d}",
                "title": title,
                "topic_tags": [tid] if tid else [],
                "suggested_open_segment_id": open_id,
                "segment_ids": seg_ids,
            }
        )
        if prev_open and open_id and prev_open != open_id:
            constraints.append(
                {
                    "before_segment_id": prev_open,
                    "after_segment_id": open_id,
                    "reason": "talking_points_air_order",
                }
            )
        prev_open = open_id

    # Prefer Shape-declared air order when present (append as soft constraints).
    if isinstance(mastering_plan, dict):
        plan_order = [str(s) for s in (mastering_plan.get("ordered_segment_ids") or []) if s]
        for i in range(len(plan_order) - 1):
            pair = {
                "before_segment_id": plan_order[i],
                "after_segment_id": plan_order[i + 1],
                "reason": "mastering_plan_ordered_segment_ids",
            }
            if pair not in constraints:
                constraints.append(pair)

    if not chapters:
        # Fallback single chapter from all cut segment_ids in time order
        ordered_cuts = sorted(
            [c for c in (materialized.get("cuts") or []) if isinstance(c, dict) and c.get("segment_id")],
            key=lambda c: int(c.get("start_ms") or 0),
        )
        seg_ids = []
        for cut in ordered_cuts:
            sid = str(cut.get("segment_id"))
            if sid not in seg_ids:
                seg_ids.append(sid)
        if seg_ids:
            chapters.append(
                {
                    "chapter_id": "ch_01_body",
                    "title": through or "Episode body",
                    "topic_tags": [],
                    "suggested_open_segment_id": seg_ids[0],
                    "segment_ids": seg_ids,
                }
            )

    score = None
    if isinstance(coverage, dict) and coverage.get("coverage_score") is not None:
        try:
            score = float(coverage["coverage_score"])
        except (TypeError, ValueError):
            score = None

    arc_bits = [strategy or through or "Talking-points-first narrative"]
    if mode:
        arc_bits.append(f"narrative_mode={mode}")
    if score is not None:
        arc_bits.append(f"coverage_score={score}")

    return {
        "arc_summary": " · ".join(arc_bits)[:2000] or "Talking-points-first narrative",
        "chapters": chapters[:12],
        "ordering_constraints": constraints,
        "pacing_notes": (
            "Deterministic narrative from talking points + ideal cuts"
            + (f"; Shape mode {mode}" if mode else "")
        ),
        "_meta": {
            "source": "talking_points_authority",
            "narrative_mode": mode or None,
        },
    }


def _materialized_span_ok(ctx: RunContext, mat: dict[str, Any]) -> bool:
    """Reject deterministic TP authority when cuts only cover early tape."""
    from interview_mux.ideal_cuts import cut_span_coverage_ratio, ideal_cuts_cfg
    from interview_mux.interview_duration_policy import transcript_duration_ms

    floor = float(ideal_cuts_cfg().get("min_span_coverage_ratio") or 0.45)
    duration_ms = int(transcript_duration_ms(ctx) or 0)
    if duration_ms <= 0:
        return True
    ratio = cut_span_coverage_ratio(mat, duration_ms)
    return ratio >= floor


def try_deterministic_coverage(ctx: RunContext) -> dict[str, Any] | None:
    conf = talking_points_authority_cfg()
    if not conf.get("deterministic_coverage", True):
        return None
    if not ideal_cuts_cfg().get("enable", True):
        return None
    if not ctx.artifact_exists(TALKING_POINTS_REL) or not ctx.artifact_exists(MATERIALIZED_REL):
        return None
    tp = ctx.read_json(TALKING_POINTS_REL)
    mat = ctx.read_json(MATERIALIZED_REL)
    if not isinstance(tp, dict) or not isinstance(mat, dict):
        return None
    if not (tp.get("talking_points") or []) or not (mat.get("cuts") or []):
        return None
    # Provisional / early-only cuts must not claim full TP coverage.
    if mat.get("boundary_bind_skipped") or not _materialized_span_ok(ctx, mat):
        return None
    if not any(
        isinstance(c, dict) and c.get("segment_id")
        for c in (mat.get("cuts") or [])
    ):
        return None
    manifest_ids: set[str] | None = None
    if ctx.artifact_exists("segments/manifest.json"):
        man = ctx.read_json("segments/manifest.json")
        if isinstance(man, dict):
            manifest_ids = {
                str(s.get("segment_id"))
                for s in (man.get("segments") or [])
                if isinstance(s, dict) and s.get("segment_id")
            }
    return coverage_from_talking_points(tp, mat, manifest_ids=manifest_ids)


def try_deterministic_narrative(ctx: RunContext) -> dict[str, Any] | None:
    conf = talking_points_authority_cfg()
    if not conf.get("deterministic_narrative", True):
        return None
    if not ideal_cuts_cfg().get("enable", True):
        return None
    if not ctx.artifact_exists(TALKING_POINTS_REL) or not ctx.artifact_exists(MATERIALIZED_REL):
        return None
    tp = ctx.read_json(TALKING_POINTS_REL)
    mat = ctx.read_json(MATERIALIZED_REL)
    if not isinstance(tp, dict) or not isinstance(mat, dict):
        return None
    if not (mat.get("cuts") or []):
        return None
    if mat.get("boundary_bind_skipped") or not _materialized_span_ok(ctx, mat):
        return None
    if not any(
        isinstance(c, dict) and c.get("segment_id")
        for c in (mat.get("cuts") or [])
    ):
        return None
    plan = None
    if ctx.artifact_exists("mastering/mastering_plan.json"):
        raw = ctx.read_json("mastering/mastering_plan.json")
        plan = raw if isinstance(raw, dict) else None
    coverage = None
    if ctx.artifact_exists("master/coverage_audit.json"):
        cov = ctx.read_json("master/coverage_audit.json")
        coverage = cov if isinstance(cov, dict) else None
    return narrative_from_talking_points(tp, mat, mastering_plan=plan, coverage=coverage)


def synthesize_narrative_from_coverage(ctx: RunContext) -> dict[str, Any] | None:
    """Build a real narrative_plan from coverage / structure / manifest (R5 salvage).

    Never returns empty chapters. Returns None only when no segment substrate exists.
    """
    seg_ids: list[str] = []
    arc = "Coverage-derived narrative arc"
    chapters: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []
    source = "coverage_synthesize"

    coverage = None
    if ctx.artifact_exists("master/coverage_audit.json"):
        cov = ctx.read_json("master/coverage_audit.json")
        coverage = cov if isinstance(cov, dict) else None
    if ctx.artifact_exists("understanding/content_brief.json"):
        brief = ctx.read_json("understanding/content_brief.json")
        if isinstance(brief, dict):
            through = str(brief.get("through_line") or brief.get("thesis") or "").strip()
            if through:
                arc = through[:2000]

    mappings = []
    if isinstance(coverage, dict):
        mappings = [m for m in (coverage.get("topic_mappings") or []) if isinstance(m, dict)]
        score = coverage.get("coverage_score")
        if score is not None:
            arc = f"{arc} · coverage_score={score}"[:2000]

    manifest_order: list[str] = []
    if ctx.artifact_exists("segments/manifest.json"):
        man = ctx.read_json("segments/manifest.json")
        if isinstance(man, dict):
            for s in man.get("segments") or []:
                if isinstance(s, dict) and s.get("segment_id"):
                    manifest_order.append(str(s["segment_id"]))

    if ctx.artifact_exists("understanding/episode_structure.json"):
        es = ctx.read_json("understanding/episode_structure.json")
        if isinstance(es, dict):
            order = [str(x) for x in (es.get("segment_order") or []) if x]
            if order:
                manifest_order = order or manifest_order

    if mappings and manifest_order:
        man_set = set(manifest_order)
        for i, m in enumerate(mappings[:12], start=1):
            m_segs = [
                str(s)
                for s in (m.get("segment_ids") or m.get("segments") or [])
                if str(s) in man_set
            ]
            if not m_segs:
                continue
            open_id = m_segs[0]
            title = str(m.get("topic") or m.get("title") or f"Topic {i}").strip() or f"Topic {i}"
            chapters.append(
                {
                    "chapter_id": f"ch_{i:02d}_cov",
                    "title": title[:200],
                    "topic_tags": [str(m.get("topic_id") or title)][:4],
                    "suggested_open_segment_id": open_id,
                    "segment_ids": m_segs,
                }
            )
            if len(chapters) >= 2:
                prev = chapters[-2]["suggested_open_segment_id"]
                if prev != open_id:
                    constraints.append(
                        {
                            "before_segment_id": prev,
                            "after_segment_id": open_id,
                            "reason": "coverage_topic_order",
                        }
                    )
        if chapters:
            source = "coverage_topic_mappings"

    if not chapters:
        # Prefer talking-points det when available
        det = try_deterministic_narrative(ctx)
        if det is not None and (det.get("chapters") or []):
            det = dict(det)
            meta = dict(det.get("_meta") or {})
            meta["source"] = "talking_points_authority_salvage"
            det["_meta"] = meta
            return det

    if not chapters and manifest_order:
        chapters.append(
            {
                "chapter_id": "ch_01_body",
                "title": "Episode body",
                "topic_tags": [],
                "suggested_open_segment_id": manifest_order[0],
                "segment_ids": list(manifest_order),
            }
        )
        source = "manifest_order_synthesize"

    if not chapters:
        return None

    return {
        "arc_summary": arc[:2000] or "Synthesized narrative arc",
        "chapters": chapters[:12],
        "ordering_constraints": constraints,
        "pacing_notes": f"Adaptive salvage narrative ({source})",
        "_meta": {"source": source},
    }


def _speaker_role_map(ctx: RunContext) -> dict[str, str]:
    out: dict[str, str] = {}
    if not ctx.artifact_exists("understanding/speakers.json"):
        return out
    doc = ctx.read_json("understanding/speakers.json")
    if not isinstance(doc, dict):
        return out
    for row in doc.get("speakers") or []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("speaker_id") or "").strip()
        if not sid:
            continue
        role = str(row.get("role") or "unknown").strip().lower()
        if role not in {"interviewer", "interviewee", "unknown"}:
            role = "unknown"
        out[sid] = role
    return out


def _segment_type_for_role(role: str, *, priority: str) -> str:
    if role == "interviewer":
        return "interviewer_question" if priority in {"must_keep", "should_keep"} else "interviewer_reaction"
    if role == "interviewee":
        return "interviewee_answer"
    return "setup"


def manifest_from_ideal_cuts(
    ctx: RunContext,
    *,
    boundaries: dict[str, Any],
    talking_points: dict[str, Any] | None,
    materialized: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build segments/manifest.json without classification LLM when cuts are bound."""
    role_map = _speaker_role_map(ctx)
    tp_by_id: dict[str, dict[str, Any]] = {}
    for tp in (talking_points or {}).get("talking_points") or []:
        if isinstance(tp, dict) and tp.get("talking_point_id"):
            tp_by_id[str(tp["talking_point_id"])] = tp
    cut_by_seg: dict[str, dict[str, Any]] = {}
    for cut in (materialized or {}).get("cuts") or []:
        if not isinstance(cut, dict):
            continue
        sid = str(cut.get("segment_id") or "").strip()
        if sid:
            cut_by_seg[sid] = cut

    segments: list[dict[str, Any]] = []
    pri_by_id: dict[str, str] = {}
    for row in boundaries.get("boundaries") or []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("segment_id") or "").strip()
        if not sid:
            continue
        cut = cut_by_seg.get(sid) or {}
        speaker = str(
            row.get("speaker_id")
            or cut.get("speaker_id")
            or next(iter(role_map), "")
            or "spk_unknown"
        ).strip()
        role = role_map.get(speaker) or "unknown"
        tp_id = str(cut.get("talking_point_id") or "").strip()
        tp = tp_by_id.get(tp_id) or {}
        priority = str(cut.get("priority") or tp.get("importance") or "optional").strip().lower()
        title = str(tp.get("title") or cut.get("rationale") or sid).strip()
        tags = [tp_id] if tp_id else ([title[:40]] if title else [])
        seg_type = _segment_type_for_role(role, priority=priority)
        pri_by_id[sid] = priority
        segments.append(
            {
                "segment_id": sid,
                "type": seg_type,
                "speaker_id": speaker,
                "speaker_role": role,
                "topic_tags": tags,
                "flags": [],
                "start_ms": int(row.get("start_ms") or cut.get("start_ms") or 0),
                "end_ms": int(row.get("end_ms") or cut.get("end_ms") or 0),
                "notes": title[:200] if title else "",
                "_meta": {"source": "talking_points_authority"},
            }
        )
    from interview_mux.boundary_enrich import stamp_span_speakers

    transcript = (
        ctx.read_json("transcript/full.json")
        if ctx.artifact_exists("transcript/full.json")
        else None
    )
    speakers_doc = (
        ctx.read_json("understanding/speakers.json")
        if ctx.artifact_exists("understanding/speakers.json")
        else None
    )
    stamped = stamp_span_speakers(segments, transcript, speakers_doc)
    for row in stamped:
        if not isinstance(row, dict):
            continue
        speaker = str(row.get("speaker_id") or "").strip()
        role = role_map.get(speaker) or str(row.get("speaker_role") or "unknown")
        row["speaker_role"] = role
        pri = pri_by_id.get(str(row.get("segment_id") or ""), "optional")
        row["type"] = _segment_type_for_role(role, priority=pri)
    return {
        "segments": stamped,
        "_meta": {
            "source": "talking_points_authority",
            "publisher_stage": "segment_classification",
            "segment_count": len(stamped),
        },
    }


def try_deterministic_classification(ctx: RunContext) -> dict[str, Any] | None:
    conf = talking_points_authority_cfg()
    if not conf.get("deterministic_classification", True):
        return None
    ic = ideal_cuts_cfg()
    if not ic.get("enable", True) or not ic.get("skip_classification_llm_when_bound", True):
        return None
    from interview_mux.ideal_cuts import BOUNDARIES_REL, boundaries_already_from_ideal_cuts

    if not boundaries_already_from_ideal_cuts(ctx):
        return None
    boundaries = ctx.read_json(BOUNDARIES_REL)
    if not isinstance(boundaries, dict) or not (boundaries.get("boundaries") or []):
        return None
    tp = ctx.read_json(TALKING_POINTS_REL) if ctx.artifact_exists(TALKING_POINTS_REL) else {}
    mat = ctx.read_json(MATERIALIZED_REL) if ctx.artifact_exists(MATERIALIZED_REL) else {}
    return manifest_from_ideal_cuts(
        ctx,
        boundaries=boundaries,
        talking_points=tp if isinstance(tp, dict) else None,
        materialized=mat if isinstance(mat, dict) else None,
    )
