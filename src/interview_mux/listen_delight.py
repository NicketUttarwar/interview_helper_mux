"""Listen delight audit — authoritative ship gate (config: mastering.listen_delight).

Computes real per-dimension scores from whatever artifacts are already on
disk at call time (delivery_brief/selection, bridge_completeness, seam
autopsy, junction_snip_qa, mode_consistency). Missing artifacts fall back to
sane soft defaults rather than failing the audit outright. When
``mastering.listen_delight.mode`` is ``authoritative`` (the default), floor
failures are a hard ship blocker for `master_finalize` / publish — see
NORTH_STAR.md and docs/cross-cutting/mastering-process.md.
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


def _nugget_retention(ctx: RunContext) -> float:
    """Selected duration vs delivery_brief ideal — a soft pack target, not a hard % floor."""
    try:
        from interview_mux.delivery_brief import (
            estimated_selection_duration_sec,
            load_delivery_brief,
        )

        brief = load_delivery_brief(ctx)
        selected_sec = estimated_selection_duration_sec(ctx)
        if not brief or selected_sec is None:
            return 0.85
        ideal_sec = float((brief.get("target_duration_sec") or {}).get("ideal") or 0.0)
        if ideal_sec <= 0 or selected_sec <= 0:
            return 0.85
        ratio = selected_sec / max(ideal_sec, 1.0)
        if ratio >= 1.0:
            # Landed at/above the ideal pack — full credit, mild taper if wildly over.
            score = 1.0 - min(0.15, (ratio - 1.0) * 0.1)
        else:
            score = ratio
        return round(_clamp(score, 0.0, 1.0), 4)
    except Exception:
        return 0.85


def _cut_integrity(ctx: RunContext) -> float:
    """Junction critical residuals + EDL lookahead hang check — fail closed.

    Missing junction artifact is no longer a free pass when EDL + words exist:
    illegal hanging ends degrade the score the same way as critical residuals.
    """
    score = 1.0
    residual_n = 0
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
            is_legal_conceptual_hinge,
        )

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
        for clip in clips:
            if not isinstance(clip, dict) or str(clip.get("type") or "") != "speech":
                continue
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
            if clause_continues_after(words, end_ms) or not is_legal_conceptual_hinge(
                end_text, words=words, end_ms=end_ms, next_pause_ms=None
            ):
                hang_hits += 1
    except Exception:
        hang_hits = 0
        speech_n = 0
    if hang_hits:
        # Ratio, not 0.2×count — five hangs on a 150-clip tape must not zero the dim.
        hang_ratio = hang_hits / max(speech_n, hang_hits, 1)
        score = _clamp(min(score, 1.0 - 0.8 * hang_ratio))
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
    """
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


def _recommendability(*, consistency_ok: bool, has_gap_lines: bool, mode: str) -> float:
    base = 0.82 if (has_gap_lines or mode == "sparse_source") else 0.6
    if consistency_ok:
        base += 0.05
    return round(_clamp(base), 4)


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


def evaluate_listen_delight(ctx: RunContext, *, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compute dimensions + overall + pass/fail without writing or raising."""
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
    dims: dict[str, float] = {
        "nugget_retention": _nugget_retention(ctx),
        "cut_integrity": cut_integrity,
        "conversation_fit": _conversation_fit(ctx, consistency_ok=consistency_ok),
        "sonic_weave": _sonic_weave(ctx),
        "mode_coherence": _mode_coherence(consistency_ok),
        "finishability": _finishability(
            consistency_ok=consistency_ok, has_gap_lines=bool(lines), cut_integrity=cut_integrity
        ),
        "recommendability": _recommendability(
            consistency_ok=consistency_ok, has_gap_lines=bool(lines), mode=narrative_mode
        ),
        "story_followability": _story_followability(ctx),
    }
    overall = round(sum(dims.values()) / len(dims), 4)

    floors = _dimension_floors(conf)
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
    }


def run_listen_delight_audit(ctx: RunContext) -> dict[str, Any]:
    conf = listen_delight_cfg()
    result = evaluate_listen_delight(ctx, cfg=conf)
    dims = result["dimensions"]
    authoritative = bool(result["authoritative"])
    blocking = authoritative
    advisory = not authoritative

    notes: list[str] = []
    if result["passed"]:
        notes.append("listen_delight floors satisfied")
    else:
        notes.append(
            f"listen_delight floors failed: overall={result['overall']} "
            f"(min {result['overall_min']}); dims_below_floor={result['failed_dimensions'] or 'none'}"
        )
    notes.append(
        "listen_delight mode=authoritative: floors are a hard ship blocker"
        if authoritative
        else "listen_delight mode=advisory: floors are observational only"
    )

    audit = {
        "version": 1,
        "mode": result["mode"],
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
    ctx.write_json(AUDIT_REL, audit)

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

    if blocking and not result["passed"] and bool(conf.get("fail_early_at_audit_stage", True)):
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
        ctx.write_json(AUDIT_REL, audit)
        if not remutate.get("exhausted"):
            applied = apply_listen_delight_remutate(ctx, remutate)
            audit["remutate_applied"] = applied
            ctx.write_json(AUDIT_REL, audit)
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
    return audit


def rerun_listen_delight_after_mix(ctx: RunContext) -> dict[str, Any]:
    """Second pass after mix so sonic_weave sees composed cues / seam autopsy.

    Writes the same audit path; does not Loud-fail (ship gate is master_finalize).
    """
    conf = listen_delight_cfg()
    result = evaluate_listen_delight(ctx, cfg=conf)
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
        {
            "version": 1,
            "mode": result["mode"],
            "pass": "post_mix",
            "dimensions": result["dimensions"],
            "overall": result["overall"],
            "overall_min": result["overall_min"],
            "dimension_floors": result["dimension_floors"],
            "failed_dimensions": result["failed_dimensions"],
            "passed": result["passed"],
            "generated_at": _now(),
        }
    )
    notes = list(audit.get("notes") or [])
    notes.append("listen_delight dual-pass after mix")
    audit["notes"] = notes
    ctx.write_json(AUDIT_REL, audit)
    return audit


__all__ = [
    "AUDIT_REL",
    "DIMENSION_KEYS",
    "evaluate_listen_delight",
    "listen_delight_cfg",
    "rerun_listen_delight_after_mix",
    "run_listen_delight_audit",
]
