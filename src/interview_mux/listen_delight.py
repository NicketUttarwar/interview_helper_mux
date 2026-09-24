"""Listen delight audit — ship aspiration rubric (config: mastering.listen_delight).

Computes per-dimension scores from on-disk artifacts at call time. With default
``mastering.aspirational_quality.enabled``, floor failures are advisory: register
candidates, remutate up to ``mastering.listen_delight.max_remutate_attempts``
(default 3), pick-best, and continue to ``master.wav`` — or refuse honestly when
authoritative floors remain unmet. Set ``aspirational_quality.enabled: false`` and
``listen_delight.mode: authoritative`` to restore hard ship blocks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.config import merged_config
from interview_mux.mastering_plan_loader import best_available_mode, load_plan_raw
from interview_mux.narrative_mode import mode_consistency_report
from interview_mux.run_context import RunContext

AUDIT_REL = "mastering/listen_delight_audit.json"

DIMENSION_KEYS: tuple[str, ...] = (
    "nugget_retention",
    "cut_integrity",
    "conversation_fit",
    "sonic_weave",
    "mode_coherence",
    "finishability",
    "recommendability",
    "story_followability",
)

_DEFAULT_DIMENSION_FLOORS: dict[str, float] = {
    "nugget_retention": 0.80,
    "cut_integrity": 0.85,
    "conversation_fit": 0.85,
    "sonic_weave": 0.85,
    "mode_coherence": 0.80,
    "finishability": 0.80,
    "recommendability": 0.75,
    "story_followability": 0.85,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def listen_delight_cfg() -> dict[str, Any]:
    raw = (merged_config().get("mastering") or {}).get("listen_delight") or {}
    return raw if isinstance(raw, dict) else {}


def _fail_early_at_audit_stage(conf: dict[str, Any] | None = None) -> bool:
    cfg = conf if conf is not None else listen_delight_cfg()
    return bool(cfg.get("fail_early_at_audit_stage", False))


def _late_opening_native_in_edl_ok(ctx: RunContext) -> bool:
    """True when EDL has no opening-tape native clips late in the timeline."""
    if not ctx.artifact_exists("master/edl.json"):
        return True
    try:
        from interview_mux.air_order_integrity import (
            opening_window_ms,
            resolved_segment_starts,
        )
        from interview_mux.edl_narrative_qc import _speech_order

        edl = ctx.read_json("master/edl.json")
        if not isinstance(edl, dict):
            return True
        speech = _speech_order(edl)
        if not speech:
            return True
        starts = resolved_segment_starts(ctx)
        window = opening_window_ms(ctx=ctx)
        opening_ids = {
            sid
            for sid in speech
            if (resolved := starts.get(sid)) is not None and int(resolved) < window
        }
        if not opening_ids:
            return True
        threshold = max(1, int(len(speech) * 0.25))
        for idx, sid in enumerate(speech):
            if sid in opening_ids and idx >= threshold:
                return False
    except Exception:
        return True
    return True


def _air_order_cut_penalty(ctx: RunContext) -> float:
    """Penalty for tape-order violations that degrade listen cut integrity."""
    penalty = 0.0
    try:
        if ctx.artifact_exists("master/selection.json"):
            from interview_mux.air_order_integrity import (
                collect_violations,
                critical_violations,
            )

            sel = ctx.read_json("master/selection.json")
            if isinstance(sel, dict):
                critical = critical_violations(collect_violations(ctx, sel))
                if critical:
                    penalty = max(penalty, min(1.0, 0.25 * len(critical)))
    except Exception:
        pass
    if not _late_opening_native_in_edl_ok(ctx):
        penalty = max(penalty, 0.5)
    return penalty


def _nugget_retention(ctx: RunContext) -> float:
    """Selected duration vs delivery_brief band (~65% of source).

    Prefer concise: in-band (brief.min → ideal) is the intended landing.
    Scoring selected/ideal linearly treated a valid min-band cut as a
    retention miss and remutated ranking after EDL was already seated.
    Over-ideal tapers because 1.5× source is a ceiling, not a goal.
    Catastrophic shorts use the same brief.min ratio envelope as
    ``selection_duration_ship_ok``.
    """
    floor = float(_DEFAULT_DIMENSION_FLOORS["nugget_retention"])
    try:
        from interview_mux.delivery_brief import (
            estimated_selection_duration_sec,
            load_delivery_brief,
            selection_duration_brief_min_ratio,
        )

        brief = load_delivery_brief(ctx)
        selected_sec = estimated_selection_duration_sec(ctx)
        if not brief or selected_sec is None:
            return 0.85
        band = brief.get("target_duration_sec") or {}
        if not isinstance(band, dict):
            band = {}
        ideal_sec = float(band.get("ideal") or 0.0)
        min_sec = float(band.get("min") or 0.0)
        if ideal_sec <= 0 or selected_sec <= 0:
            return 0.85
        ratio = selected_sec / max(ideal_sec, 1.0)
        brief_min_ratio = selection_duration_brief_min_ratio()
        brief_min_floor = min_sec * brief_min_ratio
        if selected_sec >= ideal_sec:
            score = 1.0 - min(0.25, (ratio - 1.0) * 0.2)
        elif min_sec > 0 and selected_sec >= min_sec:
            span = max(ideal_sec - min_sec, 1.0)
            t = (selected_sec - min_sec) / span
            score = floor + (1.0 - floor) * t
        elif min_sec > 0 and selected_sec >= brief_min_floor:
            score = floor
        elif min_sec > 0:
            score = floor * (selected_sec / max(brief_min_floor, 1.0))
        else:
            score = ratio
        return round(_clamp(score, 0.0, 1.0), 4)
    except Exception:
        return 0.85


def _cut_integrity(ctx: RunContext) -> float:
    """Junction critical residuals + EDL lookahead hang check — fail closed.

    Missing junction artifact is no longer a free pass when EDL + words exist:
    illegal hanging ends degrade the score the same way as critical residuals.
    Uses residual SSOT so ledger-only criticals also degrade cut integrity.
    """
    score = 1.0
    residual_n = 0
    try:
        from interview_mux.delivery_guardrails import critical_residual_view

        residual_n = int(critical_residual_view(ctx).count)
        if residual_n:
            score = _clamp(1.0 - 0.15 * residual_n)
    except Exception:
        if ctx.artifact_exists("master/junction_snip_qa.json"):
            try:
                doc = ctx.read_json("master/junction_snip_qa.json")
            except Exception:
                doc = None
            if isinstance(doc, dict):
                residual = [
                    f
                    for f in (doc.get("residual_findings") or [])
                    if isinstance(f, dict) and str(f.get("severity") or "") == "critical"
                ]
                residual_n = len(residual)
                if residual_n:
                    score = _clamp(1.0 - 0.15 * residual_n)

    # Authoritative lookahead floor even when junction is missing/soft.
    hang_hits = 0
    try:
        from interview_mux.gap_vo_prior_context import (
            clause_continues_after,
            end_is_hard_hang,
            is_legal_conceptual_hinge,
            same_answer_continues,
        )
        from interview_mux.assembly_ledger import HITCH_AIR_KINDS

        edl = (
            ctx.read_json("master/edl.json")
            if ctx.artifact_exists("master/edl.json")
            else None
        )
        tr = (
            ctx.read_json("transcript/full.json")
            if ctx.artifact_exists("transcript/full.json")
            else None
        )
        words = [
            w
            for w in ((tr or {}).get("words") or [])
            if isinstance(w, dict)
        ] if isinstance(tr, dict) else []
        clips = (edl or {}).get("clips") or [] if isinstance(edl, dict) else []
        speech_n = 0
        speech_idxs = [
            i
            for i, c in enumerate(clips)
            if isinstance(c, dict) and str(c.get("type") or "") == "speech"
        ]
        for si, clip_i in enumerate(speech_idxs):
            clip = clips[clip_i]
            speech_n += 1
            end_ms = int(clip.get("source_end_ms") or 0)
            start_ms = int(clip.get("source_start_ms") or 0)
            if end_ms <= start_ms or not words:
                continue
            end_toks = [
                str(w.get("text") or w.get("word") or "").strip()
                for w in words
                if start_ms <= int(w.get("end_ms") or 0) <= end_ms
                and str(w.get("text") or w.get("word") or "").strip()
            ]
            end_text = " ".join(end_toks[-12:]) if end_toks else ""
            if not end_text:
                continue
            if (
                end_is_hard_hang(words, end_ms)
                or clause_continues_after(words, end_ms)
                or not is_legal_conceptual_hinge(
                    end_text, words=words, end_ms=end_ms, next_pause_ms=None
                )
            ):
                hang_hits += 1
                continue
            # Soft hang: same-answer split with chapter hinge air between clips.
            if si + 1 < len(speech_idxs):
                nxt = clips[speech_idxs[si + 1]]
                between = clips[clip_i + 1 : speech_idxs[si + 1]]
                has_hinge = any(
                    isinstance(c, dict)
                    and c.get("type") == "silence"
                    and str(c.get("air_kind") or "") in HITCH_AIR_KINDS
                    and int(c.get("duration_ms") or 0) > 0
                    for c in between
                )
                right_start = int(nxt.get("source_start_ms") or 0)
                if has_hinge and same_answer_continues(words, end_ms, right_start):
                    hang_hits += 1
    except Exception:
        hang_hits = 0
        speech_n = 0
    if hang_hits:
        # Ratio, not 0.2×count — five hangs on a 150-clip tape must not zero the dim.
        hang_ratio = hang_hits / max(speech_n, hang_hits, 1)
        score = _clamp(min(score, 1.0 - 0.8 * hang_ratio))
    air_penalty = _air_order_cut_penalty(ctx)
    if air_penalty:
        score = _clamp(min(score, 1.0 - air_penalty))
    return round(score, 4)


def _conversation_fit(ctx: RunContext, *, consistency_ok: bool) -> float:
    """Bridge completeness (pair-specific glue) when present; else mode-consistency soft score."""
    base = 0.9 if consistency_ok else 0.65
    if ctx.artifact_exists("master/bridge_completeness.json"):
        try:
            doc = ctx.read_json("master/bridge_completeness.json")
        except Exception:
            doc = None
        if isinstance(doc, dict):
            missing = int(doc.get("missing_count") or 0)
            stubs = int(doc.get("stub_count") or 0)
            if missing == 0 and bool(doc.get("complete")):
                base = round(_clamp(0.95 - 0.005 * min(stubs, 20)), 4)
            else:
                base = round(_clamp(1.0 - 0.2 * missing - 0.05 * min(stubs, 6)), 4)
    try:
        from interview_mux.air_script import load_air_script, paper_edit_scores
        from interview_mux.mastering_plan_loader import load_plan_raw

        plan = load_plan_raw(ctx)
        if load_air_script(plan):
            paper = paper_edit_scores(ctx)
            paper_fit = float(paper.get("conversation_fit") or base)
            return round(_clamp(min(base, paper_fit) if paper_fit < 0.7 else (0.6 * base + 0.4 * paper_fit)), 4)
    except Exception:
        pass
    return base


def _sonic_weave(ctx: RunContext) -> float:
    """Seam autopsy music_completeness / hard-edge counts when present; else soft default.

    When air-script sonic_scenes exist, reward motif/scene-bed/outro architecture and
    penalize an empty or every-Nth-only score.

    Clinic MSFX-B2: omit-all reserved themes under creative_delivery fails delight
    (score 0) — not ship-legal hollow sonic weave.
    """
    try:
        from interview_mux.theme_slot_integrity import reserved_themes_all_omitted

        if reserved_themes_all_omitted(ctx):
            return 0.0
    except Exception:
        pass
    base = 0.9
    if ctx.artifact_exists("master/seam_autopsy.json"):
        try:
            doc = ctx.read_json("master/seam_autopsy.json")
        except Exception:
            doc = None
        if isinstance(doc, dict):
            scores = doc.get("scores") if isinstance(doc.get("scores"), dict) else {}
            music = scores.get("music_completeness") if isinstance(scores, dict) else None
            if isinstance(music, (int, float)):
                base = round(_clamp(float(music)), 4)
            else:
                seams = doc.get("seams") if isinstance(doc.get("seams"), list) else []
                hard_edges = sum(
                    1
                    for s in seams
                    if isinstance(s, dict) and "music_hard_edge" in (s.get("risk_codes") or [])
                )
                if hard_edges:
                    base = round(_clamp(1.0 - 0.1 * hard_edges), 4)
    try:
        from interview_mux.air_script import load_air_script, paper_edit_scores
        from interview_mux.mastering_plan_loader import load_plan_raw

        plan = load_plan_raw(ctx)
        if load_air_script(plan) and (
            plan.get("sonic_scenes") or plan.get("sonic_opportunities")
        ):
            paper = paper_edit_scores(ctx)
            arch = float(paper.get("sonic_weave") or 0.85)
            return round(_clamp(0.45 * base + 0.55 * arch), 4)
    except Exception:
        pass
    return base


def _story_followability(ctx: RunContext) -> float:
    """Paper-edit story contract. Soft-default high when air_script is absent."""
    try:
        from interview_mux.air_script import load_air_script, paper_edit_scores
        from interview_mux.mastering_plan_loader import load_plan_raw

        plan = load_plan_raw(ctx)
        if not load_air_script(plan):
            return 0.88
        paper = paper_edit_scores(ctx)
        return round(_clamp(float(paper.get("story_followability") or 0.85)), 4)
    except Exception:
        return 0.88


def _mode_coherence(consistency_ok: bool) -> float:
    return 1.0 if consistency_ok else 0.5


def _finishability(*, consistency_ok: bool, has_gap_lines: bool, cut_integrity: float) -> float:
    base = 0.88 if consistency_ok else 0.55
    if has_gap_lines:
        base += 0.05
    base = base * (0.7 + 0.3 * cut_integrity)
    return round(_clamp(base), 4)


def _recommendability(
    *,
    finishability: float,
    conversation_fit: float,
    story_followability: float,
    mode_coherence: float,
    cut_integrity: float,
) -> float:
    """NORTH_STAR rubric 6 — would a first-time listener recommend this cut.

    Do not proxy this off gap-VO presence. Conversational_host with no
    interviewer_lines used to score 0.65 against a 0.75 floor while every
    other dim cleared — remutating ranking/EDL/mix cannot invent VO lines,
    so the audit looped forever.
    """
    score = (
        0.25 * finishability
        + 0.25 * conversation_fit
        + 0.20 * story_followability
        + 0.15 * mode_coherence
        + 0.15 * cut_integrity
    )
    return round(_clamp(score), 4)


def _dimension_floors(cfg: dict[str, Any]) -> dict[str, float]:
    raw = cfg.get("dimension_floors")
    floors = dict(_DEFAULT_DIMENSION_FLOORS)
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                floors[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
    return floors


def evaluate_listen_delight(
    ctx: RunContext,
    *,
    cfg: dict[str, Any] | None = None,
    pass_phase: str = "pre_mix",
) -> dict[str, Any]:
    """Compute dimensions + overall + pass/fail without writing or raising.

    LD1: at ``post_master``, missing evidence fails closed (score ≤ floor−ε).
    ``pre_mix`` keeps soft defaults so early audits stay non-blocking.
    """
    conf = cfg if cfg is not None else listen_delight_cfg()
    mode_str = str(conf.get("mode") or "authoritative")
    plan = load_plan_raw(ctx) or {}
    narrative_mode = best_available_mode(plan) if plan else "sparse_source"
    lines: list[dict[str, Any]] = []
    if ctx.artifact_exists("understanding/gap_report.json"):
        gr = ctx.read_json("understanding/gap_report.json")
        if isinstance(gr, dict):
            raw = gr.get("interviewer_lines") or []
            if isinstance(raw, list):
                lines = [x for x in raw if isinstance(x, dict)]
    consistency = mode_consistency_report(mode=narrative_mode, interviewer_lines=lines, plan=plan or None)
    require_mode_consistency = bool(conf.get("require_mode_consistency", True))
    consistency_ok = bool(consistency.get("ok")) if require_mode_consistency else True

    cut_integrity = _cut_integrity(ctx)
    conversation_fit = _conversation_fit(ctx, consistency_ok=consistency_ok)
    mode_coherence = _mode_coherence(consistency_ok)
    finishability = _finishability(
        consistency_ok=consistency_ok, has_gap_lines=bool(lines), cut_integrity=cut_integrity
    )
    story_followability = _story_followability(ctx)
    dims: dict[str, float] = {
        "nugget_retention": _nugget_retention(ctx),
        "cut_integrity": cut_integrity,
        "conversation_fit": conversation_fit,
        "sonic_weave": _sonic_weave(ctx),
        "mode_coherence": mode_coherence,
        "finishability": finishability,
        "story_followability": story_followability,
        "recommendability": _recommendability(
            finishability=finishability,
            conversation_fit=conversation_fit,
            story_followability=story_followability,
            mode_coherence=mode_coherence,
            cut_integrity=cut_integrity,
        ),
    }
    floors = _dimension_floors(conf)
    # LD1: post_master fail-closed when evidence for a dim is missing.
    missing_evidence: list[str] = []
    if str(pass_phase or "") == "post_master":
        evidence = {
            "nugget_retention": bool(
                ctx.artifact_exists("master/selection.json")
                and ctx.artifact_exists("understanding/delivery_brief.json")
            ),
            "cut_integrity": bool(
                ctx.artifact_exists("master/junction_snip_qa.json")
                or (
                    ctx.artifact_exists("master/edl.json")
                    and ctx.artifact_exists("transcript/full.json")
                )
            ),
            "conversation_fit": bool(
                ctx.artifact_exists("master/bridge_completeness.json")
            ),
            "sonic_weave": bool(
                ctx.artifact_exists("master/seam_autopsy.json")
                or (isinstance(plan, dict) and (plan.get("sonic_scenes") or plan.get("sonic_opportunities")))
            ),
            "story_followability": False,
        }
        try:
            from interview_mux.air_script import load_air_script

            has_air = bool(load_air_script(plan))
            evidence["story_followability"] = has_air
            evidence["conversation_fit"] = bool(evidence["conversation_fit"] or has_air)
        except Exception:
            pass
        eps = 0.01
        for dim, present in evidence.items():
            if present or dim not in floors:
                continue
            floor = float(floors.get(dim) or 0.0)
            if floor <= 0:
                continue
            capped = max(0.0, round(floor - eps, 4))
            if float(dims.get(dim) or 0.0) > capped:
                dims[dim] = capped
            missing_evidence.append(dim)
        # Recompute recommendability after clamps.
        dims["recommendability"] = _recommendability(
            finishability=float(dims.get("finishability") or 0.0),
            conversation_fit=float(dims.get("conversation_fit") or 0.0),
            story_followability=float(dims.get("story_followability") or 0.0),
            mode_coherence=float(dims.get("mode_coherence") or 0.0),
            cut_integrity=float(dims.get("cut_integrity") or 0.0),
        )

    overall = round(sum(dims.values()) / len(dims), 4)

    overall_min = float(conf.get("overall_min") or 0.90)
    failed_dims = sorted(dim for dim, floor in floors.items() if dims.get(dim, 0.0) < floor)
    overall_ok = overall >= overall_min
    # Dimension floors are the hard gate. When every dim clears its floor, do not
    # fail solely on overall — soft defaults for unfinished downstream artifacts
    # (pre-mix) would otherwise make overall_min unreachable even on a clean cut.
    if failed_dims:
        passed = False
    elif overall_ok:
        passed = True
    else:
        passed = overall >= (sum(floors.values()) / max(len(floors), 1))

    authoritative = mode_str == "authoritative"
    return {
        "mode": mode_str,
        "authoritative": authoritative,
        "narrative_mode": narrative_mode,
        "consistency": consistency,
        "dimensions": dims,
        "overall": overall,
        "overall_min": overall_min,
        "dimension_floors": floors,
        "failed_dimensions": failed_dims,
        "passed": passed,
        "has_gap_lines": bool(lines),
        "pass_phase": pass_phase,
        "missing_evidence_dims": missing_evidence,
    }


def _build_audit_doc(
    result: dict[str, Any],
    dims: dict[str, float],
    *,
    pass_phase: str,
    blocking: bool,
    advisory: bool,
    extra_notes: list[str] | None = None,
) -> dict[str, Any]:
    notes: list[str] = list(extra_notes or [])
    if result["passed"]:
        notes.append("listen_delight floors satisfied")
    else:
        notes.append(
            f"listen_delight floors failed: overall={result['overall']} "
            f"(min {result['overall_min']}); dims_below_floor={result['failed_dimensions'] or 'none'}"
        )
    if pass_phase == "pre_mix":
        notes.append(
            "listen_delight pre-mix pass (non-blocking); authoritative ship gate at master_finalize"
        )
    elif pass_phase == "post_master":
        notes.append(
            "listen_delight authoritative post-master pass (ship gate)"
            if blocking
            else "listen_delight post-master pass (advisory)"
        )
    elif pass_phase == "post_mix":
        notes.append("listen_delight dual-pass after mix (non-blocking)")
    return {
        "version": 1,
        "mode": result["mode"],
        "pass": pass_phase,
        "advisory": advisory,
        "blocking": blocking,
        "narrative_mode": result["narrative_mode"],
        "dimensions": dims,
        "overall": result["overall"],
        "overall_min": result["overall_min"],
        "dimension_floors": result["dimension_floors"],
        "failed_dimensions": result["failed_dimensions"],
        "passed": result["passed"],
        "finishability": dims["finishability"],
        "fatigue_risk": round(_clamp(1.0 - dims["finishability"]), 4),
        "mode_audible": True,
        "recommendability": dims["recommendability"],
        "mode_consistency": result["consistency"],
        "notes": notes,
        "human_rubric_ref": "NORTH_STAR.md#human-listen-rubric-ship-checklist",
        "generated_at": _now(),
    }


def _write_listen_delight_qc_meta(ctx: RunContext, result: dict[str, Any], dims: dict[str, float], *, blocking: bool, advisory: bool) -> None:
    meta: dict[str, Any]
    if ctx.artifact_exists("run_meta.json"):
        doc = ctx.read_json("run_meta.json")
        meta = doc if isinstance(doc, dict) else {}
    else:
        meta = {}
    qc = meta.get("qc_summaries") if isinstance(meta.get("qc_summaries"), dict) else {}
    qc["listen_delight"] = {
        "mode": result["mode"],
        "advisory": advisory,
        "blocking": blocking,
        "passed": result["passed"],
        "overall": result["overall"],
        "failed_dimensions": result["failed_dimensions"],
        "finishability": dims["finishability"],
        "recommendability": dims["recommendability"],
        "mode_consistency_ok": result["consistency"].get("ok"),
    }
    qc["mode_consistency"] = {
        "advisory": True,
        "blocking": False,
        "ok": result["consistency"].get("ok"),
        "violations": result["consistency"].get("violations"),
    }
    meta["qc_summaries"] = qc
    ctx.write_json("run_meta.json", meta)


def _handle_listen_delight_failure(
    ctx: RunContext,
    result: dict[str, Any],
    dims: dict[str, float],
    *,
    pass_phase: str,
    stage_id: str,
) -> bool:
    """Aspirational remutate path. Returns True only when soft-proceed is allowed.

    F7 1C: at post_master, aspirational + above catastrophic floors is advisory
    (local package continues). Catastrophic misses and aspirational-off still
    return False so callers hard-block.
    """
    from interview_mux.aspirational_quality import (
        apply_best_quality_candidate,
        family_attempts_exhausted,
        increment_family_attempt,
        is_aspirational_enabled,
        passes_catastrophic_floors,
        record_quality_advisories,
        register_quality_candidate,
    )
    from interview_mux.listen_delight_remutate import (
        apply_listen_delight_remutate,
        plan_listen_delight_remutate,
    )

    if not is_aspirational_enabled(ctx):
        return False
    authoritative = str(listen_delight_cfg().get("mode") or "").strip() == "authoritative"
    cata_ok, cata_reasons = passes_catastrophic_floors(ctx)
    cata_as_adv = False
    try:
        from interview_mux.floor_progress import catastrophic_as_advisory

        cata_as_adv = catastrophic_as_advisory(ctx)
    except Exception:
        cata_as_adv = False
    if not cata_ok and not cata_as_adv:
        return False
    if not cata_ok and cata_as_adv:
        try:
            from interview_mux.floor_progress import record_floor_advisory

            record_floor_advisory(
                ctx,
                "catastrophic_floors",
                {"reasons": list(cata_reasons or [])[:8], "pass": pass_phase},
                aspirational_proceeded=True,
            )
        except Exception:
            pass
    register_quality_candidate(ctx, family="listen_delight")
    increment_family_attempt(ctx, "listen_delight")
    remutate = plan_listen_delight_remutate(
        ctx, failed_dimensions=list(result.get("failed_dimensions") or [])
    )
    audit_patch: dict[str, Any] = {
        "aspirational_fail": True,
        "blocking": bool(authoritative and remutate.get("exhausted") and not cata_as_adv),
        "advisory": not (authoritative and remutate.get("exhausted") and not cata_as_adv),
        "remutate": remutate,
        "catastrophic_as_advisory": bool(cata_as_adv and not cata_ok),
        "catastrophic_reasons": list(cata_reasons or []) if not cata_ok else [],
    }
    # Post-master ship gate: never rewind to mix/seams — that thrashes finalize
    # after loudnorm (exec_5404). Record advisory / pick-best only.
    soft_proceed = True
    if pass_phase == "post_master":
        remutate = {
            **(remutate if isinstance(remutate, dict) else {}),
            "exhausted": True,
            "skipped_at_ship": True,
            "from_stage": None,
        }
        audit_patch["remutate"] = remutate
        audit_patch["pick_best"] = apply_best_quality_candidate(
            ctx, family="listen_delight"
        )
        # F7 1C: do not loud-fail ship on aspiration misses; catastrophic
        # becomes advisory under progress_floors.catastrophic_as_advisory.
        audit_patch["blocking"] = False
        audit_patch["advisory"] = True
    elif not remutate.get("exhausted"):
        applied = apply_listen_delight_remutate(ctx, remutate)
        audit_patch["remutate_applied"] = applied
    else:
        # Cap reached: ship best candidate; under catastrophic_as_advisory always soft-proceed.
        audit_patch["pick_best"] = apply_best_quality_candidate(
            ctx, family="listen_delight"
        )
        audit_patch["remutate_terminate"] = remutate.get("terminate") or (
            "remutate_budget_exhausted"
        )
        if authoritative and not cata_as_adv:
            soft_proceed = False
            audit_patch["blocking"] = True
            audit_patch["advisory"] = False
            audit_patch["needs_operator_reason"] = "listen_delight_floors_exhausted"
        else:
            soft_proceed = True
            audit_patch["blocking"] = False
            audit_patch["advisory"] = True
            if cata_as_adv and authoritative:
                audit_patch["needs_operator_reason"] = None
                audit_patch["progress_floors_ship_best"] = True
    if ctx.artifact_exists(AUDIT_REL):
        try:
            loaded = ctx.read_json(AUDIT_REL)
            if isinstance(loaded, dict):
                loaded.update(audit_patch)
                ctx.write_json(AUDIT_REL, loaded, stage_key="listen_delight_audit")
        except Exception:
            pass
    record_quality_advisories(
        ctx,
        gate_id="listen_delight_floors",
        failed_checks=list(result.get("failed_dimensions") or []),
        detail={
            "overall": result.get("overall"),
            "pass": pass_phase,
            "remutate": remutate,
            "authoritative_hard_block": not soft_proceed,
            "catastrophic_as_advisory": bool(cata_as_adv and not cata_ok),
            "catastrophic_reasons": list(cata_reasons or []) if not cata_ok else [],
        },
        aspirational_proceeded=soft_proceed
        and bool(audit_patch.get("pick_best", {}).get("ok")),
    )
    if soft_proceed:
        ctx.log(
            "listen_delight floors below aspiration (advisory — remutate/pick-best): "
            f"overall={result.get('overall')} dims={result.get('failed_dimensions')}",
            level="warning",
            stage=stage_id,
        )
    else:
        try:
            if ctx.artifact_exists("run_meta.json"):

                def _need(meta: dict[str, Any]) -> None:
                    meta["needs_operator"] = True
                    meta["needs_operator_stage"] = stage_id
                    meta["needs_operator_reason"] = "listen_delight_floors_exhausted"

                ctx.mutate_run_meta(_need)
        except Exception:
            pass
        ctx.log(
            "listen_delight floors exhausted under authoritative mode (hard block ship): "
            f"overall={result.get('overall')} dims={result.get('failed_dimensions')}",
            level="error",
            stage=stage_id,
        )
    return soft_proceed

def run_listen_delight_audit(ctx: RunContext) -> dict[str, Any]:
    conf = listen_delight_cfg()
    from interview_mux.aspirational_quality import is_aspirational_enabled

    aspirational = is_aspirational_enabled(ctx)
    result = evaluate_listen_delight(ctx, cfg=conf)
    dims = result["dimensions"]
    authoritative = bool(result["authoritative"])
    fail_early = _fail_early_at_audit_stage(conf)
    blocking = authoritative and fail_early and not aspirational
    advisory = not blocking

    audit = _build_audit_doc(
        result,
        dims,
        pass_phase="pre_mix",
        blocking=blocking,
        advisory=advisory,
    )
    ctx.write_json(AUDIT_REL, audit, stage_key="listen_delight_audit")
    _write_listen_delight_qc_meta(ctx, result, dims, blocking=blocking, advisory=advisory)

    if blocking and not result["passed"]:
        from interview_mux.aspirational_quality import is_aspirational_enabled

        if is_aspirational_enabled(ctx) and _handle_listen_delight_failure(
            ctx, result, dims, pass_phase="pre_mix", stage_id="listen_delight_audit"
        ):
            audit = ctx.read_json(AUDIT_REL)
            return audit if isinstance(audit, dict) else {}
        try:
            from interview_mux.homunculus.issues import ingest_catch

            ingest_catch(
                ctx,
                kind="listen_delight_floors",
                source="listen_delight",
                stage_id="listen_delight_audit",
                implicated=["listen_delight_audit", "mix"],
                evidence={"failed_dimensions": result.get("failed_dimensions")},
            )
        except Exception:
            pass
        from interview_mux.listen_delight_remutate import (
            apply_listen_delight_remutate,
            plan_listen_delight_remutate,
        )
        from interview_mux.loud_fail import raise_loud_failure

        remutate = plan_listen_delight_remutate(
            ctx, failed_dimensions=list(result["failed_dimensions"] or [])
        )
        audit["remutate"] = remutate
        ctx.write_json(AUDIT_REL, audit, stage_key="listen_delight_audit")
        if not remutate.get("exhausted"):
            applied = apply_listen_delight_remutate(ctx, remutate)
            audit["remutate_applied"] = applied
            ctx.write_json(AUDIT_REL, audit, stage_key="listen_delight_audit")
        else:
            # Cap reached: ship-best then refuse (loud_fail below).
            try:
                from interview_mux.aspirational_quality import apply_best_quality_candidate

                audit["pick_best"] = apply_best_quality_candidate(
                    ctx, family="listen_delight"
                )
                audit["remutate_terminate"] = remutate.get("terminate") or (
                    "remutate_budget_exhausted"
                )
                ctx.write_json(AUDIT_REL, audit, stage_key="listen_delight_audit")
            except Exception:
                pass
        raise_loud_failure(
            ctx,
            "Listen delight floors failed: overall="
            f"{result['overall']} (min {result['overall_min']}); "
            f"dims_below_floor={result['failed_dimensions'] or 'none'}"
            + (
                f"; remutate_from={remutate.get('from_stage')}"
                if remutate.get("from_stage")
                else ""
            ),
            stage="listen_delight_audit",
            reason="listen_delight_floors_failed",
            detail={
                "overall": result["overall"],
                "overall_min": result["overall_min"],
                "failed_dimensions": result["failed_dimensions"],
                "dimensions": dims,
                "remutate": remutate,
            },
        )
    elif authoritative and not result["passed"]:
        try:
            from interview_mux.homunculus.issues import ingest_catch

            ingest_catch(
                ctx,
                kind="listen_delight_floors",
                source="listen_delight",
                stage_id="listen_delight_audit",
                implicated=["listen_delight_audit", "master_finalize"],
                evidence={
                    "failed_dimensions": result.get("failed_dimensions"),
                    "deferred_to": "master_finalize",
                },
            )
        except Exception:
            pass
    from interview_mux.stage_completion import heal_or_raise

    heal_or_raise(ctx, "listen_delight_audit")
    return audit


def run_authoritative_listen_delight_at_ship(ctx: RunContext) -> dict[str, Any]:
    """Fresh delight after master.wav — hard-stop only when not aspirational or catastrophic."""
    conf = listen_delight_cfg()
    from interview_mux.aspirational_quality import is_aspirational_enabled

    aspirational = is_aspirational_enabled(ctx)
    mode_str = str(conf.get("mode") or "authoritative")
    if mode_str != "authoritative" and not aspirational:
        if ctx.artifact_exists(AUDIT_REL):
            try:
                loaded = ctx.read_json(AUDIT_REL)
                return loaded if isinstance(loaded, dict) else {}
            except Exception:
                return {}
        return {}

    result = evaluate_listen_delight(ctx, cfg=conf, pass_phase="post_master")
    dims = result["dimensions"]
    # F7 1C: aspirational ship is advisory; hard-block only when aspirational is off.
    blocking = not aspirational
    prior: dict[str, Any] = {}
    if ctx.artifact_exists(AUDIT_REL):
        try:
            loaded = ctx.read_json(AUDIT_REL)
            if isinstance(loaded, dict):
                prior = loaded
        except Exception:
            prior = {}
    audit = _build_audit_doc(
        result,
        dims,
        pass_phase="post_master",
        blocking=blocking and not result["passed"],
        advisory=not (blocking and not result["passed"]),
    )
    ctx.write_json(AUDIT_REL, audit, stage_key="listen_delight_audit")
    _write_listen_delight_qc_meta(
        ctx,
        result,
        dims,
        blocking=blocking and not result["passed"],
        advisory=not (blocking and not result["passed"]),
    )

    if not result["passed"]:
        if aspirational and _handle_listen_delight_failure(
            ctx,
            result,
            dims,
            pass_phase="post_master",
            stage_id="master_finalize",
        ):
            audit = ctx.read_json(AUDIT_REL)
            return audit if isinstance(audit, dict) else {}
        try:
            from interview_mux.homunculus.issues import ingest_catch

            ingest_catch(
                ctx,
                kind="listen_delight_floors",
                source="listen_delight",
                stage_id="master_finalize",
                implicated=["listen_delight_audit", "master_finalize", "mix"],
                evidence={"failed_dimensions": result.get("failed_dimensions"), "pass": "post_master"},
            )
        except Exception:
            pass
        from interview_mux.loud_fail import raise_loud_failure

        raise_loud_failure(
            ctx,
            "Listen delight floors failed at ship: overall="
            f"{result['overall']} (min {result['overall_min']}); "
            f"dims_below_floor={result['failed_dimensions'] or 'none'}",
            stage="master_finalize",
            reason="listen_delight_floors_failed",
            detail={
                "overall": result["overall"],
                "overall_min": result["overall_min"],
                "failed_dimensions": result["failed_dimensions"],
                "dimensions": dims,
                "pass": "post_master",
            },
        )
    return audit


def rerun_listen_delight_after_mix(ctx: RunContext) -> dict[str, Any]:
    """Second pass after mix so sonic_weave sees composed cues / seam autopsy.

    Writes the same audit path; does not Loud-fail (ship gate is master_finalize).
    """
    conf = listen_delight_cfg()
    result = evaluate_listen_delight(ctx, cfg=conf)
    dims = result["dimensions"]
    prior: dict[str, Any] = {}
    if ctx.artifact_exists(AUDIT_REL):
        try:
            loaded = ctx.read_json(AUDIT_REL)
            if isinstance(loaded, dict):
                prior = loaded
        except Exception:
            prior = {}
    audit = dict(prior)
    audit.update(
        _build_audit_doc(
            result,
            dims,
            pass_phase="post_mix",
            blocking=False,
            advisory=True,
        )
    )
    ctx.write_json(AUDIT_REL, audit, stage_key="listen_delight_audit")
    return audit


__all__ = [
    "AUDIT_REL",
    "DIMENSION_KEYS",
    "evaluate_listen_delight",
    "listen_delight_cfg",
    "rerun_listen_delight_after_mix",
    "run_authoritative_listen_delight_at_ship",
    "run_listen_delight_audit",
]
