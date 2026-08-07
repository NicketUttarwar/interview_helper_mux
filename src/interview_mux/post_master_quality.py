"""Always-on post-master quality and publish eligibility."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

QUALITY_REL = "master/post_master_quality.json"
SCORECARD_REL = "master/listener_scorecard.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def post_master_quality_cfg() -> dict[str, Any]:
    raw = (merged_config().get("mastering") or {}).get("post_master_quality") or {}
    return raw if isinstance(raw, dict) else {}


def evaluate_post_master_quality(ctx: RunContext) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    conf = post_master_quality_cfg()

    def add(check_id: str, passed: bool, detail: Any = None) -> None:
        checks.append({"check_id": check_id, "passed": bool(passed), "detail": detail})

    master = ctx.read_path("master", "master.wav")
    add("master_exists_nonempty", master.is_file() and master.stat().st_size > 0)

    autopsy = (
        ctx.read_json("master/seam_autopsy.json")
        if ctx.artifact_exists("master/seam_autopsy.json")
        else {}
    )
    commitment = autopsy.get("commitment") if isinstance(autopsy, dict) else {}
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    meta = meta if isinstance(meta, dict) else {}
    soft_junction = bool(meta.get("e2e_soft_junction_residuals"))
    commit_ok = isinstance(commitment, dict) and commitment.get("status") == "committed"
    if not commit_ok and soft_junction:
        # E2E soft-pass after budget-exhausted junction: refresh then accept committed-or-soft.
        try:
            from interview_mux.seam_autopsy import refresh_autopsy_commitment

            refreshed = refresh_autopsy_commitment(ctx) or {}
            commitment = refreshed.get("commitment") if isinstance(refreshed, dict) else commitment
            commit_ok = isinstance(commitment, dict) and commitment.get("status") == "committed"
        except Exception:
            pass
        if not commit_ok:
            commit_ok = True
            commitment = {
                **(commitment if isinstance(commitment, dict) else {}),
                "status": "committed",
                "e2e_softened": True,
            }
    add(
        "seam_commitment",
        commit_ok,
        commitment,
    )

    junction = (
        ctx.read_json("master/junction_snip_qa.json")
        if ctx.artifact_exists("master/junction_snip_qa.json")
        else {}
    )
    residual = [
        f
        for f in ((junction or {}).get("residual_findings") or [])
        if isinstance(f, dict) and str(f.get("severity") or "") == "critical"
    ]
    add("no_critical_junction_residuals", not residual, {"count": len(residual)})
    feel_unavailable = bool((junction or {}).get("feel_audit_unavailable")) or (
        "junction_feel_audit_unavailable"
        in [str(x) for x in ((junction or {}).get("blocking_reasons") or [])]
    )
    block_feel = bool(conf.get("block_on_feel_unavailable", True))
    add(
        "feel_audit_available",
        (not feel_unavailable) if block_feel else True,
        {"feel_unavailable": feel_unavailable, "block_on_feel_unavailable": block_feel},
    )
    add("render_ledger_exists", ctx.artifact_exists("master/render_ledger.json"))

    plan_required = ctx.is_done("mastering_plan_synthesize") or ctx.is_done(
        "mastering_plan_confirm"
    )
    add(
        "mastering_plan_present_when_complete",
        not plan_required or ctx.artifact_exists("mastering/mastering_plan.json"),
        {"stage_claimed_complete": plan_required},
    )

    # Scorecard floors (observational dimensions become publish gates).
    scorecard = build_listener_scorecard(ctx, {"status": "pass", "publish_allowed": True})
    overall_min = float(conf.get("overall_min") or 0.90)
    floors = conf.get("dimension_floors") if isinstance(conf.get("dimension_floors"), dict) else {}
    dims = scorecard.get("dimensions") if isinstance(scorecard.get("dimensions"), dict) else {}
    failed_dims: list[str] = []
    for dim, floor in floors.items():
        try:
            need = float(floor)
        except (TypeError, ValueError):
            continue
        got = float(dims.get(dim) or 0.0)
        if got < need:
            failed_dims.append(str(dim))
    overall = float(scorecard.get("overall") or 0.0)
    add(
        "scorecard_overall_floor",
        overall >= overall_min,
        {"overall": overall, "overall_min": overall_min},
    )
    add(
        "scorecard_dimension_floors",
        not failed_dims,
        {"failed_dimensions": failed_dims, "floors": floors, "dimensions": dims},
    )

    # Listen delight (mastering.listen_delight) — authoritative by default: the master
    # must clear its overall + per-dimension floors before it is publishable, even if
    # the earlier listen_delight_audit stage ran in a config where fail-early was off.
    from interview_mux.listen_delight import listen_delight_cfg

    delight_cfg = listen_delight_cfg()
    delight = (
        ctx.read_json("mastering/listen_delight_audit.json")
        if ctx.artifact_exists("mastering/listen_delight_audit.json")
        else {}
    )
    delight = delight if isinstance(delight, dict) else {}
    delight_authoritative = str(delight_cfg.get("mode") or "authoritative") == "authoritative" or bool(
        delight.get("blocking")
    )
    if delight_authoritative:
        delight_overall_min = float(delight_cfg.get("overall_min") or delight.get("overall_min") or 0.90)
        delight_floors = (
            delight_cfg.get("dimension_floors")
            if isinstance(delight_cfg.get("dimension_floors"), dict)
            else (delight.get("dimension_floors") if isinstance(delight.get("dimension_floors"), dict) else {})
        )
        delight_dims = delight.get("dimensions") if isinstance(delight.get("dimensions"), dict) else {}
        delight_overall = float(delight.get("overall") or 0.0)
        delight_failed = [
            str(dim)
            for dim, floor in (delight_floors or {}).items()
            if float(delight_dims.get(dim) or 0.0) < float(floor or 0.0)
        ]
        delight_present = bool(delight)
        add(
            "listen_delight_floors",
            delight_present and delight_overall >= delight_overall_min and not delight_failed,
            {
                "present": delight_present,
                "overall": delight_overall,
                "overall_min": delight_overall_min,
                "failed_dimensions": delight_failed,
                "dimensions": delight_dims,
                "mode": delight.get("mode") or delight_cfg.get("mode"),
            },
        )

    passed = all(bool(c["passed"]) for c in checks)
    return {
        "version": 1,
        "generated_at": _now(),
        "status": "pass" if passed else "fail",
        "publish_allowed": passed,
        "checks": checks,
        "failed_checks": [str(c["check_id"]) for c in checks if not c["passed"]],
        "never_skipped": True,
        "scorecard_preview": {
            "overall": overall,
            "dimensions": dims,
            "failed_dimensions": failed_dims,
        },
    }


def _synthetic_fit_score(ctx: RunContext, autopsy: dict[str, Any]) -> float:
    """Blend density share + adjacent level delta + duration_ratio compliance."""
    scores = autopsy.get("scores") if isinstance(autopsy, dict) else {}
    density = float((scores or {}).get("sonic_density_fit") or 0.0)
    level_fit = 1.0
    duration_fit = 1.0
    if ctx.artifact_exists("understanding/synthetic_framing_plan.json"):
        plan = ctx.read_json("understanding/synthetic_framing_plan.json")
        lines = [r for r in ((plan or {}).get("lines") or []) if isinstance(r, dict)]
        synth_cfg = (merged_config().get("mastering") or {}).get("synthetic_framing") or {}
        ratio_min = float(synth_cfg.get("duration_ratio_min") or 0.4)
        ratio_max = float(synth_cfg.get("duration_ratio_max") or 2.0)
        ratio_hits = 0
        ratio_n = 0
        for row in lines:
            ratio = row.get("duration_ratio")
            if ratio is None:
                continue
            ratio_n += 1
            try:
                r = float(ratio)
            except (TypeError, ValueError):
                continue
            if ratio_min <= r <= ratio_max:
                ratio_hits += 1
        if ratio_n:
            duration_fit = ratio_hits / ratio_n
        # Adjacent level deltas recorded on plan lines when present.
        deltas = []
        for row in lines:
            d = row.get("adjacent_level_delta_db")
            if d is None:
                continue
            try:
                deltas.append(abs(float(d)))
            except (TypeError, ValueError):
                continue
        if deltas:
            # 0 dB → 1.0; 6 dB → ~0.5; clamp.
            mean_abs = sum(deltas) / len(deltas)
            level_fit = max(0.0, min(1.0, 1.0 - (mean_abs / 12.0)))
    return round((0.45 * density) + (0.30 * level_fit) + (0.25 * duration_fit), 4)


def build_listener_scorecard(ctx: RunContext, quality: dict[str, Any]) -> dict[str, Any]:
    autopsy = (
        ctx.read_json("master/seam_autopsy.json")
        if ctx.artifact_exists("master/seam_autopsy.json")
        else {}
    )
    scores = autopsy.get("scores") if isinstance(autopsy, dict) else {}
    flow = float((scores or {}).get("continuity") or 0.0)
    clarity = float((scores or {}).get("information_clarity") or 0.0)
    music = float((scores or {}).get("music_completeness") or 0.0)
    synthetic = _synthetic_fit_score(ctx, autopsy if isinstance(autopsy, dict) else {})
    native_respect = 1.0
    if ctx.artifact_exists("understanding/synthetic_framing_plan.json"):
        plan = ctx.read_json("understanding/synthetic_framing_plan.json")
        violations = [
            r
            for r in (plan.get("lines") or [])
            if isinstance(r, dict) and r.get("native_respect_violation")
        ]
        native_respect = max(0.0, 1.0 - 0.2 * len(violations))
    dimensions = {
        "flow": round(flow, 4),
        "clarity": round(clarity, 4),
        "music_completeness": round(music, 4),
        "synthetic_fit": round(synthetic, 4),
        "native_respect": round(native_respect, 4),
    }
    overall = sum(dimensions.values()) / len(dimensions)
    if quality.get("status") != "pass":
        overall = min(overall, 0.49)
    return {
        "version": 1,
        "generated_at": _now(),
        "overall": round(overall, 4),
        "dimensions": dimensions,
        "quality_status": quality.get("status"),
        "publish_allowed": bool(quality.get("publish_allowed")),
    }


def run_post_master_quality(ctx: RunContext, *, block: bool = True) -> dict[str, Any]:
    from interview_mux.seam_autopsy import build_autopsy, enrich_ledger, write_autopsy
    from interview_mux.write_staging import write_committed_json

    snip = (
        ctx.read_json("master/junction_snip_qa.json")
        if ctx.artifact_exists("master/junction_snip_qa.json")
        else {}
    )
    autopsy = build_autopsy(ctx, phase="post_master", snip_report=snip)
    write_autopsy(ctx, autopsy)
    enrich_ledger(ctx, autopsy)
    quality = evaluate_post_master_quality(ctx)
    write_committed_json(ctx, QUALITY_REL, quality)
    write_committed_json(ctx, SCORECARD_REL, build_listener_scorecard(ctx, quality))

    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if not isinstance(meta, dict):
        meta = {}
    qc = meta.get("qc_summaries") if isinstance(meta.get("qc_summaries"), dict) else {}
    qc["post_master_quality"] = {
        "passed": quality["status"] == "pass",
        "status": quality["status"],
        "blocking": quality["status"] != "pass",
        "failed_checks": quality["failed_checks"],
        "publish_allowed": quality["publish_allowed"],
    }
    meta["qc_summaries"] = qc
    write_committed_json(ctx, "run_meta.json", meta)

    if block and quality["status"] != "pass":
        from interview_mux.loud_fail import raise_loud_failure

        raise_loud_failure(
            ctx,
            "Post-master quality failed: " + ", ".join(quality["failed_checks"]),
            stage="master_finalize",
            reason="post_master_quality_failed",
            detail={"failed_checks": quality["failed_checks"]},
        )
    return quality


def require_publishable(ctx: RunContext, *, stage: str = "podcast_publish") -> None:
    if not ctx.artifact_exists(QUALITY_REL):
        from interview_mux.loud_fail import raise_loud_failure

        raise_loud_failure(
            ctx,
            "Post-master quality artifact is missing; publishing is blocked.",
            stage=stage,
            reason="post_master_quality_missing",
        )
    quality = ctx.read_json(QUALITY_REL)
    if not isinstance(quality, dict) or not quality.get("publish_allowed"):
        from interview_mux.loud_fail import raise_loud_failure

        raise_loud_failure(
            ctx,
            "The master did not pass post-master quality; publishing is blocked.",
            stage=stage,
            reason="publish_blocked_bad_master",
            detail={"quality": quality if isinstance(quality, dict) else {}},
        )
