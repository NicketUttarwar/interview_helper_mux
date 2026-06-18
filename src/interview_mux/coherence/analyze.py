from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from interview_mux.coherence.claim_contradiction import detect_claim_contradictions
from interview_mux.coherence.config import (
    coherence_active,
    coherence_cfg,
    threshold,
)
from interview_mux.coherence.duration_gate import build_gate, interview_duration_ms
from interview_mux.coherence.investigations import coherence_investigations
from interview_mux.coherence.memory_sync import sync_coherence_to_state
from interview_mux.coherence.missing_callback import detect_missing_callbacks
from interview_mux.coherence.novelty import compute_novelty_scores
from interview_mux.coherence.paths import COHERENCE_REPORT_PATH
from interview_mux.coherence.theme_alignment import build_theme_scores
from interview_mux.interview_spine.paths import SPINE_PATH


def maybe_run_coherence_analysis(ctx, *, phase: str) -> int:
    """Run coherence pass for hook phase; returns investigation count enqueued."""
    if not coherence_active():
        return 0
    gate = build_gate(ctx)
    if not gate.get("activated"):
        if phase == "post_content_context" and not ctx.artifact_exists(COHERENCE_REPORT_PATH):
            ctx.write_json(COHERENCE_REPORT_PATH, _inactive_report(gate, phase))
        ctx.log(
            f"coherence_phase_complete phase={phase} activated=false enqueued=0",
            level="info",
            stage="coherence",
            detail=json.dumps({"duration_ms": gate.get("duration_ms"), "min_duration_ms": gate.get("min_duration_ms")}),
        )
        return 0

    prior = ctx.read_json(COHERENCE_REPORT_PATH) if ctx.artifact_exists(COHERENCE_REPORT_PATH) else None
    if phase != "post_content_context" and _can_skip(ctx, prior, phase):
        ctx.log(
            f"coherence_phase_complete phase={phase} skipped=unchanged enqueued=0",
            level="info",
            stage="coherence",
        )
        return 0

    report = build_coherence_report(ctx, phase=phase)
    if phase in ("post_reanchor", "post_coverage"):
        from interview_mux.prompt_validation import validate_coherence_report

        errors = validate_coherence_report(report)
        if errors:
            ctx.log(
                f"Coherence report validation failed: {errors[:3]}",
                level="warning",
                stage="coherence",
            )
        ctx.write_json(COHERENCE_REPORT_PATH, report)

    sync_coherence_to_state(ctx, report)

    if phase in ("post_reanchor", "post_coverage") and report.get("gate", {}).get("activated"):
        try:
            from interview_mux.artifact_cross_validate import validate_cross_artifacts

            cross_errors = validate_cross_artifacts(ctx, "post_coherence")
            if cross_errors:
                ctx.log(
                    f"Coherence cross-validate: {cross_errors[:2]}",
                    level="warning",
                    stage="coherence",
                )
        except Exception:
            pass

    items = coherence_investigations(report)
    from interview_mux.analysis_memory import enqueue_investigations

    enqueued = enqueue_investigations(ctx, items, created_by_stage=phase.replace("post_", "")) if items else 0
    ctx.log(
        f"coherence_phase_complete phase={phase} enqueued={enqueued}",
        level="info",
        stage="coherence",
        detail=json.dumps(
            {"risk_count": len(report.get("risks") or []), "investigation_count": enqueued},
            ensure_ascii=False,
        ),
    )
    return enqueued


def build_coherence_report(ctx, *, phase: str) -> dict[str, Any]:
    cfg = coherence_cfg()
    gate = build_gate(ctx, cfg)
    duration = int(gate.get("duration_ms") or 0)

    if not gate.get("activated"):
        return _inactive_report(gate, phase)

    spine = ctx.read_json(SPINE_PATH) if ctx.artifact_exists(SPINE_PATH) else {}
    windows = spine.get("windows") or []
    brief = (
        ctx.read_json("understanding/content_brief.json")
        if ctx.artifact_exists("understanding/content_brief.json")
        else {}
    )
    manifest = (
        ctx.read_json("segments/manifest.json")
        if ctx.artifact_exists("segments/manifest.json")
        else {}
    )

    novelty = compute_novelty_scores(windows, ctx)
    theme_rows = build_theme_scores(windows, brief, duration_ms=duration)
    scores = _merge_scores(theme_rows, novelty)

    risks: list[dict[str, Any]] = []
    if phase in ("post_content_context", "post_reanchor", "post_coverage"):
        risks.extend(_topic_drift_risks(scores, cfg))

    if phase in ("post_reanchor", "post_coverage"):
        risks.extend(
            detect_claim_contradictions(
                content_brief=brief,
                windows=windows,
                duration_ms=duration,
                threshold=threshold(cfg, "claim_contradiction_threshold", 0.72),
                blocking=bool(cfg.get("blocking_claim_contradiction", True)),
            )
        )
        risks.extend(
            detect_missing_callbacks(
                content_brief=brief,
                windows=windows,
                manifest=manifest,
                duration_ms=duration,
                threshold=threshold(cfg, "missing_callback_threshold", 0.60),
            )
        )

    if phase == "post_coverage" and ctx.artifact_exists("flow_1_master/coverage_audit.json"):
        risks = _reconcile_coverage(ctx, risks)

    summary = _build_summary(risks, phase)
    return {
        "schema_version": 1,
        "derived_from": _build_derived_from(ctx, phase, duration),
        "gate": gate,
        "scores": scores,
        "risks": risks,
        "summary": summary,
    }


def _inactive_report(gate: dict[str, Any], phase: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "derived_from": {
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "phase": phase,
            "duration_ms": int(gate.get("duration_ms") or 0),
        },
        "gate": gate,
        "scores": [],
        "risks": [],
        "summary": {
            "topic_drift_count": 0,
            "claim_contradiction_count": 0,
            "missing_callback_count": 0,
            "phase": phase,
        },
    }


def _merge_scores(theme_rows: list[dict[str, Any]], novelty: dict[str, float]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in theme_rows:
        wid = str(row.get("window_id") or "")
        merged = dict(row)
        merged["novelty_score"] = novelty.get(wid, 0.0)
        out.append(merged)
    return out


def _topic_drift_risks(scores: list[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    drift_threshold = float(cfg.get("topic_drift_threshold", 0.55))
    novelty_min = float(cfg.get("novelty_min_delta", 0.18))
    require_novelty = bool(cfg.get("require_acoustic_novelty", True))
    risks: list[dict[str, Any]] = []
    for row in scores:
        drift = float(row.get("drift_score") or 0)
        novelty = float(row.get("novelty_score") or 0)
        if drift < drift_threshold:
            continue
        if require_novelty and novelty < novelty_min:
            continue
        wid = row.get("window_id")
        time_ms = int(row.get("start_ms") or 0)
        risks.append(
            {
                "risk_id": f"drift_{wid}",
                "kind": "topic_drift",
                "time_ms": time_ms,
                "window_id": wid,
                "theme_id": row.get("best_theme_id"),
                "claim_id": None,
                "confidence": round(drift, 3),
                "blocking": False,
                "evidence": {
                    "novelty_score": novelty,
                    "theme_alignment": row.get("theme_alignment"),
                    "drift_score": drift,
                },
                "suggested_action": {
                    "type": "rerun_stage",
                    "stage": "content_brief_reanchor",
                },
                "status": "open",
            }
        )
    return risks[:12]


def _reconcile_coverage(ctx, risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    audit = ctx.read_json("flow_1_master/coverage_audit.json")
    covered = set()
    for row in audit.get("topic_coverage") or audit.get("topics") or []:
        if not isinstance(row, dict):
            continue
        if row.get("covered") is True or row.get("status") == "covered":
            covered.add(str(row.get("topic") or row.get("name") or ""))

    out: list[dict[str, Any]] = []
    for risk in risks:
        if risk.get("kind") != "missing_callback":
            out.append(risk)
            continue
        topic = str((risk.get("evidence") or {}).get("topic") or risk.get("theme_id") or "")
        if topic and topic in covered:
            resolved = dict(risk)
            resolved["status"] = "resolved"
            out.append(resolved)
        else:
            out.append(risk)
    return out


def _build_summary(risks: list[dict[str, Any]], phase: str) -> dict[str, Any]:
    open_risks = [r for r in risks if r.get("status", "open") == "open"]
    return {
        "topic_drift_count": sum(1 for r in open_risks if r.get("kind") == "topic_drift"),
        "claim_contradiction_count": sum(
            1 for r in open_risks if r.get("kind") == "claim_contradiction"
        ),
        "missing_callback_count": sum(
            1 for r in open_risks if r.get("kind") == "missing_callback"
        ),
        "phase": phase,
    }


def _sha256_json(doc: dict[str, Any]) -> str:
    payload = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _build_derived_from(ctx, phase: str, duration_ms: int) -> dict[str, Any]:
    row: dict[str, Any] = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
        "duration_ms": duration_ms,
    }
    if ctx.artifact_exists(SPINE_PATH):
        row["interview_spine_sha256"] = _sha256_json(ctx.read_json(SPINE_PATH))
    if ctx.artifact_exists("understanding/content_brief.json"):
        row["content_brief_sha256"] = _sha256_json(ctx.read_json("understanding/content_brief.json"))
    if ctx.artifact_exists("segments/manifest.json"):
        row["manifest_sha256"] = _sha256_json(ctx.read_json("segments/manifest.json"))
    return row


def _can_skip(ctx, prior: dict[str, Any] | None, phase: str) -> bool:
    from interview_mux.coherence.lineage import derived_from_matches

    if not isinstance(prior, dict):
        return False
    if str((prior.get("summary") or {}).get("phase") or "") == phase:
        return derived_from_matches(ctx, prior.get("derived_from") or {}, phase)
    return False
