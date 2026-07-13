"""Source readiness score for first-try preclean decisions.

Writes ``understanding/source_readiness.json`` with band green|yellow|red.
Never auto-accepts DeepFilter; green may auto-dismiss the offer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.run_context import RunContext

READY_REL = "understanding/source_readiness.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _wav_stats(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"path": str(path), "exists": path.is_file()}
    if not path.is_file():
        return out
    try:
        out["bytes"] = path.stat().st_size
        from pydub import AudioSegment

        seg = AudioSegment.from_file(path)
        out["duration_ms"] = len(seg)
        out["channels"] = seg.channels
        out["frame_rate"] = seg.frame_rate
        out["max_dBFS"] = float(seg.max_dBFS) if seg.max_dBFS is not None else None
        out["dBFS"] = float(seg.dBFS) if seg.dBFS is not None else None
    except Exception as exc:  # noqa: BLE001 — readiness is fail-open
        out["probe_error"] = str(exc)[:200]
    return out


def _sap_noise_hints(ctx: RunContext) -> dict[str, Any]:
    rel = "understanding/source_acoustic_profile.json"
    if not ctx.artifact_exists(rel):
        return {}
    doc = ctx.read_json(rel)
    if not isinstance(doc, dict):
        return {}
    hints: dict[str, Any] = {}
    for key in ("noise_floor_db", "snr_estimate", "room_tone", "recommended_preclean", "quality_flags"):
        if key in doc:
            hints[key] = doc.get(key)
    summary = doc.get("summary") if isinstance(doc.get("summary"), dict) else {}
    if summary.get("noise_score") is not None:
        hints["noise_score"] = summary.get("noise_score")
    if summary.get("clipping") is not None:
        hints["clipping"] = summary.get("clipping")
    return hints


def compute_source_readiness(ctx: RunContext) -> dict[str, Any]:
    """Score source audio into green / yellow / red."""
    reasons: list[str] = []
    score = 1.0
    wav_rel = "ingest/normalized.wav"
    path = ctx.final_path(*wav_rel.split("/"))
    if not path.is_file():
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        src = str((meta or {}).get("source_audio_path") or "")
        path = Path(src) if src else path
        wav_rel = src or wav_rel

    stats = _wav_stats(path)
    if not stats.get("exists"):
        return {
            "version": 1,
            "band": "yellow",
            "score": 0.5,
            "reasons": ["Source audio not yet available for readiness probe"],
            "recommended": {"preclean": True},
            "updated_at": _now(),
            "stats": stats,
        }

    dur = int(stats.get("duration_ms") or 0)
    if dur > 0 and dur < 60_000:
        score -= 0.15
        reasons.append("Very short source (<60s)")
    if dur > 4 * 3600_000:
        score -= 0.1
        reasons.append("Very long source (>4h) — chunking/context pressure")

    dbfs = stats.get("dBFS")
    if isinstance(dbfs, (int, float)):
        if dbfs < -35:
            score -= 0.25
            reasons.append(f"Quiet overall level ({dbfs:.1f} dBFS)")
        elif dbfs > -6:
            score -= 0.2
            reasons.append(f"Hot overall level ({dbfs:.1f} dBFS)")

    max_db = stats.get("max_dBFS")
    if isinstance(max_db, (int, float)) and max_db > -0.5:
        score -= 0.25
        reasons.append("Possible clipping (peak near 0 dBFS)")

    sap = _sap_noise_hints(ctx)
    if sap.get("recommended_preclean") is True:
        score -= 0.3
        reasons.append("SAP recommends pre-clean")
    noise = sap.get("noise_score")
    if isinstance(noise, (int, float)):
        if noise >= 0.7:
            score -= 0.35
            reasons.append(f"High SAP noise_score ({noise})")
        elif noise >= 0.4:
            score -= 0.15
            reasons.append(f"Moderate SAP noise_score ({noise})")
    if sap.get("clipping") is True:
        score -= 0.2
        reasons.append("SAP reports clipping")

    score = max(0.0, min(1.0, round(score, 3)))
    if score >= 0.75:
        band = "green"
    elif score >= 0.45:
        band = "yellow"
    else:
        band = "red"

    if not reasons:
        reasons.append("Source levels look clean enough for first-try")

    return {
        "version": 1,
        "band": band,
        "score": score,
        "reasons": reasons[:12],
        "recommended": {"preclean": band in {"yellow", "red"}},
        "updated_at": _now(),
        "stats": stats,
        "sap_hints": sap,
        "wav_rel": wav_rel,
    }


def write_source_readiness(ctx: RunContext, *, stage: str = "ingest") -> dict[str, Any]:
    doc = compute_source_readiness(ctx)
    stage_key = stage if stage not in {"operator", "refresh"} else None
    ctx.write_json(READY_REL, doc, stage_key=stage_key)
    ctx.log(
        f"Source readiness: {doc['band']} (score={doc['score']})",
        level="info",
        stage=stage,
        detail={"event": "source_readiness", "band": doc["band"], "score": doc["score"]},
    )
    return doc


def load_source_readiness(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(READY_REL):
        return None
    doc = ctx.read_json(READY_REL)
    return doc if isinstance(doc, dict) else None


def maybe_auto_dismiss_preclean(ctx: RunContext, *, checkpoint: str = "before_ingest") -> bool:
    """Dismiss preclean offer when readiness is green (never auto-accept)."""
    from interview_mux.first_try import preclean_auto_dismiss_when_green
    from interview_mux.operator_quality import preclean_checkpoint_decision

    if not preclean_auto_dismiss_when_green():
        return False
    doc = load_source_readiness(ctx)
    if not doc:
        doc = write_source_readiness(ctx, stage="refresh")
    if str(doc.get("band")) != "green":
        return False
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if preclean_checkpoint_decision(meta if isinstance(meta, dict) else {}, checkpoint) in {
        "accept",
        "dismiss",
    }:
        return False

    def patch(m: dict[str, Any]) -> None:
        ap = dict(m.get("audio_preclean") or {})
        decisions = list(ap.get("decisions") or [])
        decisions.append(
            {
                "checkpoint": checkpoint,
                "action": "dismiss",
                "at": _now(),
                "reason": "auto_clean_enough",
                "by": "first_try",
            }
        )
        ap["decisions"] = decisions
        m["audio_preclean"] = ap

    ctx.mutate_run_meta(patch)
    ctx.log(
        f"Pre-clean auto-dismissed ({checkpoint}): source readiness green.",
        level="info",
        stage="audio_preclean",
        action_id="gui.preclean.dismiss",
        detail={
            "event": "preclean_auto_dismiss",
            "checkpoint": checkpoint,
            "reason": "auto_clean_enough",
        },
    )
    return True
