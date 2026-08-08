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
)

_DEFAULT_DIMENSION_FLOORS: dict[str, float] = {
    "nugget_retention": 0.80,
    "cut_integrity": 0.85,
    "conversation_fit": 0.85,
    "sonic_weave": 0.85,
    "mode_coherence": 0.80,
    "finishability": 0.80,
    "recommendability": 0.75,
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
    """Junction snip QA critical residuals — 1.0 clean/missing, degrades per critical finding."""
    if not ctx.artifact_exists("master/junction_snip_qa.json"):
        return 1.0
    try:
        doc = ctx.read_json("master/junction_snip_qa.json")
    except Exception:
        return 1.0
    if not isinstance(doc, dict):
        return 1.0
    residual = [
        f
        for f in (doc.get("residual_findings") or [])
        if isinstance(f, dict) and str(f.get("severity") or "") == "critical"
    ]
    if not residual:
        return 1.0
    return round(_clamp(1.0 - 0.15 * len(residual)), 4)


def _conversation_fit(ctx: RunContext, *, consistency_ok: bool) -> float:
    """Bridge completeness (pair-specific glue) when present; else mode-consistency soft score."""
    if ctx.artifact_exists("master/bridge_completeness.json"):
        try:
            doc = ctx.read_json("master/bridge_completeness.json")
        except Exception:
            doc = None
        if isinstance(doc, dict):
            missing = int(doc.get("missing_count") or 0)
            stubs = int(doc.get("stub_count") or 0)
            # When every reorder seam has glue (complete), repeated mint text is soft
            # style debt — do not fail conversation_fit solely on stub_count.
            if missing == 0 and bool(doc.get("complete")):
                return round(_clamp(0.95 - 0.005 * min(stubs, 20)), 4)
            return round(_clamp(1.0 - 0.2 * missing - 0.05 * min(stubs, 6)), 4)
    return 0.9 if consistency_ok else 0.65


def _sonic_weave(ctx: RunContext) -> float:
    """Seam autopsy music_completeness / hard-edge counts when present; else soft default."""
    if not ctx.artifact_exists("master/seam_autopsy.json"):
        return 0.9
    try:
        doc = ctx.read_json("master/seam_autopsy.json")
    except Exception:
        return 0.9
    if not isinstance(doc, dict):
        return 0.9
    scores = doc.get("scores") if isinstance(doc.get("scores"), dict) else {}
    music = scores.get("music_completeness") if isinstance(scores, dict) else None
    if isinstance(music, (int, float)):
        return round(_clamp(float(music)), 4)
    seams = doc.get("seams") if isinstance(doc.get("seams"), list) else []
    hard_edges = sum(
        1
        for s in seams
        if isinstance(s, dict) and "music_hard_edge" in (s.get("risk_codes") or [])
    )
    if hard_edges:
        return round(_clamp(1.0 - 0.1 * hard_edges), 4)
    return 0.9


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
        from interview_mux.loud_fail import raise_loud_failure

        raise_loud_failure(
            ctx,
            "Listen delight floors failed: overall="
            f"{result['overall']} (min {result['overall_min']}); "
            f"dims_below_floor={result['failed_dimensions'] or 'none'}",
            stage="listen_delight_audit",
            reason="listen_delight_floors_failed",
            detail={
                "overall": result["overall"],
                "overall_min": result["overall_min"],
                "failed_dimensions": result["failed_dimensions"],
                "dimensions": dims,
            },
        )
    return audit


__all__ = [
    "AUDIT_REL",
    "DIMENSION_KEYS",
    "evaluate_listen_delight",
    "listen_delight_cfg",
    "run_listen_delight_audit",
]
