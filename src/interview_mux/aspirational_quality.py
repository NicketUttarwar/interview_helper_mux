"""Aspirational quality policy — rubric gates as recommendations, best-of-N masters.

When enabled, listen-delight / PMQ / listenability rubric failures do not hard-stop
the pipeline. After max attempts per family, register candidates, pick the best
scored master, record advisories, and continue to master.wav.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

CANDIDATES_REL = "master/quality_candidates.json"
ADVISORIES_META_KEY = "quality_advisories"

# PMQ checks that remain hard: the master is missing or not the one the EDL
# describes. Everything else (speakable-copy re-lint, omit-ledger paperwork,
# duration floor, junction residual judgements) is advisory (ISSUES 185); each
# has its own producer earlier in the walk and nothing at finalize can heal it.
STRUCTURAL_PMQ_CHECKS: frozenset[str] = frozenset(
    {
        "master_exists_nonempty",
        "seam_commitment",
        "audible_script_hash_agreement",
    }
)

# Rubric gate ids that become advisory when aspirational is enabled.
RUBRIC_GATE_IDS: frozenset[str] = frozenset(
    {
        "scorecard_overall_floor",
        "scorecard_dimension_floors",
        "listenability_contract",
        "no_critical_junction_residuals",
        "feel_audit_available",
        "planned_music_preserved",
        "episode_close_outro_present",
        "opening_music_preserved",
        "opening_music_quality",
        "opening_orientation_contract",
        "air_order_integrity",
        "no_open_ship_bar_defects",
        "stage_output_semantics",
        "ship_reachability_analysis",
        "verify_master_lufs",
        "homunculus_delight_reject",
    }
)

# Air-script story_clarity hard errors (structural narrative contract).
AIR_SCRIPT_STRUCTURAL_ERRORS: frozenset[str] = frozenset(
    {"unpaid_cold_open", "multiple_orientation"}
)

_DEFAULT_WEIGHTS: dict[str, float] = {
    "listen_delight_overall": 0.5,
    "cut_integrity": 0.2,
    "nugget_retention": 0.15,
    "conversation_fit": 0.075,
    "story_followability": 0.075,
}

_DEFAULT_CATASTROPHIC: dict[str, float] = {
    "cut_integrity": 0.70,
    "listen_delight_overall": 0.70,
    "conversation_fit": 0.60,
    "story_followability": 0.60,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def aspirational_quality_cfg() -> dict[str, Any]:
    root = merged_config()
    mastering = root.get("mastering") if isinstance(root, dict) else {}
    raw = (mastering or {}).get("aspirational_quality") if isinstance(mastering, dict) else {}
    return dict(raw) if isinstance(raw, dict) else {}


def is_aspirational_enabled(ctx: RunContext | None = None) -> bool:
    cfg = aspirational_quality_cfg()
    if not bool(cfg.get("enabled", True)):
        return False
    if ctx is not None and ctx.artifact_exists("run_meta.json"):
        try:
            meta = ctx.read_json("run_meta.json")
            if isinstance(meta, dict) and meta.get("aspirational_quality_disabled"):
                return False
        except Exception:
            pass
    return True


def max_attempts_per_family() -> int:
    try:
        return max(1, int(aspirational_quality_cfg().get("max_attempts_per_family") or 3))
    except (TypeError, ValueError):
        return 3


def require_operator_publish_when_advisory() -> bool:
    return bool(aspirational_quality_cfg().get("require_operator_publish_when_advisory", True))


def pick_best_weights() -> dict[str, float]:
    raw = aspirational_quality_cfg().get("pick_best_weights")
    if isinstance(raw, dict):
        out = dict(_DEFAULT_WEIGHTS)
        for k, v in raw.items():
            try:
                out[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
        return out
    return dict(_DEFAULT_WEIGHTS)


def catastrophic_floors() -> dict[str, float]:
    raw = aspirational_quality_cfg().get("catastrophic_floors")
    if isinstance(raw, dict):
        out = dict(_DEFAULT_CATASTROPHIC)
        for k, v in raw.items():
            try:
                out[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
        return out
    return dict(_DEFAULT_CATASTROPHIC)


def is_rubric_gate(gate_id: str) -> bool:
    return str(gate_id or "").strip() in RUBRIC_GATE_IDS


RUBRIC_PMQ_CHECKS: frozenset[str] = frozenset(
    {
        "scorecard_overall_floor",
        "scorecard_dimension_floors",
        "feel_audit_available",
        "planned_music_preserved",
        "episode_close_outro_present",
        "opening_music_preserved",
        "opening_music_quality",
        "opening_orientation_contract",
        "air_order_integrity",
        "no_open_ship_bar_defects",
        "stage_output_semantics",
        "ship_reachability_analysis",
        "spoken_native_intro_duplicate",
        "mastering_plan_present_when_complete",
        "render_ledger_exists",
        # Advisory since ISSUES 185.
        "spoken_vo_speakable",
        "omit_ledger_air_contract",
        "selection_duration_floor",
    }
)


def is_structural_pmq_check(check_id: str) -> bool:
    return str(check_id or "").strip() in STRUCTURAL_PMQ_CHECKS


def is_rubric_pmq_check(check_id: str) -> bool:
    cid = str(check_id or "").strip()
    if is_structural_pmq_check(cid) or cid == "master_exists_nonempty":
        return False
    if cid == "no_critical_junction_residuals":
        return True
    return cid in RUBRIC_PMQ_CHECKS or is_rubric_gate(cid)


def rubric_gate_blocks(gate_id: str, ctx: RunContext | None = None) -> bool:
    """True when this rubric gate should still hard-stop (aspirational off)."""
    if is_aspirational_enabled(ctx):
        return False
    return is_rubric_gate(gate_id)


def load_candidates_doc(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists(CANDIDATES_REL):
        return {"version": 1, "families": {}, "candidates": []}
    try:
        doc = ctx.read_json(CANDIDATES_REL)
        return doc if isinstance(doc, dict) else {"version": 1, "families": {}, "candidates": []}
    except Exception:
        return {"version": 1, "families": {}, "candidates": []}


def _family_attempt_count(doc: dict[str, Any], family: str) -> int:
    fam = (doc.get("families") or {}).get(family) if isinstance(doc.get("families"), dict) else None
    if isinstance(fam, dict):
        return int(fam.get("attempts") or 0)
    return 0


def increment_family_attempt(ctx: RunContext, family: str) -> int:
    doc = load_candidates_doc(ctx)
    families = dict(doc.get("families") or {}) if isinstance(doc.get("families"), dict) else {}
    fam = dict(families.get(family) or {}) if isinstance(families.get(family), dict) else {}
    n = int(fam.get("attempts") or 0) + 1
    fam["attempts"] = n
    fam["last_at"] = _now()
    families[family] = fam
    doc["families"] = families
    ctx.write_json(CANDIDATES_REL, doc)
    return n


def family_attempts_exhausted(ctx: RunContext, family: str) -> bool:
    doc = load_candidates_doc(ctx)
    return _family_attempt_count(doc, family) >= max_attempts_per_family()


def _candidate_score(scores: dict[str, Any]) -> float:
    weights = pick_best_weights()
    total_w = 0.0
    total = 0.0
    delight = scores.get("listen_delight") if isinstance(scores.get("listen_delight"), dict) else {}
    dims = delight.get("dimensions") if isinstance(delight.get("dimensions"), dict) else {}
    mapping = {
        "listen_delight_overall": float(delight.get("overall") or 0.0),
        "cut_integrity": float(dims.get("cut_integrity") or 0.0),
        "nugget_retention": float(dims.get("nugget_retention") or 0.0),
        "conversation_fit": float(dims.get("conversation_fit") or 0.0),
        "story_followability": float(dims.get("story_followability") or 0.0),
    }
    for key, weight in weights.items():
        val = mapping.get(key, 0.0)
        total += weight * val
        total_w += weight
    if total_w <= 0:
        return float(delight.get("overall") or 0.0)
    return round(total / total_w, 6)


def passes_catastrophic_floors(ctx: RunContext, scores: dict[str, Any] | None = None) -> tuple[bool, list[str]]:
    """Return (ok, reasons). Fails when below catastrophic floors or missing master."""
    reasons: list[str] = []
    floors = catastrophic_floors()
    master = ctx.final_path("master", "master.wav")
    master_ok = master.is_file() and master.stat().st_size >= 1000
    if not master_ok:
        # During master_finalize the loudnorm promote may still be pending —
        # assembly.wav (or a non-trivial pending master) stands in so aspirational
        # soft-path is not blocked by missing_or_empty_master (exec_5404).
        asm = ctx.final_path("master", "assembly.wav")
        pending = (
            ctx.run_dir
            / ".pending_writes"
            / "master_finalize"
            / "master"
            / "master.wav"
        )
        asm_ok = asm.is_file() and asm.stat().st_size >= 1000
        pend_ok = pending.is_file() and pending.stat().st_size >= 1000
        if not (asm_ok or pend_ok):
            reasons.append("missing_or_empty_master")
    delight = scores or {}
    if isinstance(scores, dict) and "listen_delight" in scores:
        delight = scores.get("listen_delight") or {}
    elif ctx.artifact_exists("mastering/listen_delight_audit.json"):
        try:
            delight = ctx.read_json("mastering/listen_delight_audit.json") or {}
        except Exception:
            delight = {}
    if isinstance(delight, dict):
        overall = float(delight.get("overall") or 0.0)
        min_overall = float(floors.get("listen_delight_overall") or 0.0)
        if min_overall > 0 and overall < min_overall:
            reasons.append(f"listen_delight_overall {overall} < catastrophic {min_overall}")
        dims = delight.get("dimensions") if isinstance(delight.get("dimensions"), dict) else {}
        for dim_key, floor_key in (
            ("cut_integrity", "cut_integrity"),
            ("conversation_fit", "conversation_fit"),
            ("story_followability", "story_followability"),
        ):
            val = float(dims.get(dim_key) or 0.0)
            min_val = float(floors.get(floor_key) or 0.0)
            if min_val > 0 and val < min_val:
                reasons.append(f"{dim_key} {val} < catastrophic {min_val}")
    if not air_script_structural_ok(ctx):
        reasons.append("air_script_story_clarity_errors")
    return (not reasons, reasons)


def air_script_structural_ok(ctx: RunContext) -> bool:
    try:
        from interview_mux.mastering_plan_loader import load_plan_raw
        from interview_mux.air_script import load_air_script

        plan = load_plan_raw(ctx) or {}
        script = load_air_script(plan) or {}
        lint = script.get("story_clarity") if isinstance(script.get("story_clarity"), dict) else {}
        if lint.get("ok") is False:
            return False
        errors = [str(e) for e in (lint.get("errors") or []) if e]
        for err in errors:
            if err in AIR_SCRIPT_STRUCTURAL_ERRORS:
                return False
        return True
    except Exception:
        return True


def collect_current_scores(ctx: RunContext) -> dict[str, Any]:
    scores: dict[str, Any] = {}
    if ctx.artifact_exists("mastering/listen_delight_audit.json"):
        try:
            scores["listen_delight"] = ctx.read_json("mastering/listen_delight_audit.json")
        except Exception:
            pass
    if ctx.artifact_exists("master/listenability_contract.json"):
        try:
            scores["listenability"] = ctx.read_json("master/listenability_contract.json")
        except Exception:
            pass
    if ctx.artifact_exists("master/post_master_quality.json"):
        try:
            scores["post_master_quality"] = ctx.read_json("master/post_master_quality.json")
        except Exception:
            pass
    return scores


def register_quality_candidate(
    ctx: RunContext,
    *,
    family: str,
    scores: dict[str, Any] | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Archive master/assembly snapshot and append to candidate ledger."""
    doc = load_candidates_doc(ctx)
    candidates = list(doc.get("candidates") or []) if isinstance(doc.get("candidates"), list) else []
    attempt_id = f"{family}_{len(candidates) + 1}_{datetime.now(timezone.utc).strftime('%H%M%S')}"
    score_doc = scores if isinstance(scores, dict) else collect_current_scores(ctx)
    rank_score = _candidate_score(score_doc)
    archive_rel = f".archived/quality_candidates/{attempt_id}"
    archive_dir = Path(ctx.run_dir) / archive_rel
    archive_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for rel in ("master/master.wav", "master/assembly.wav", "mastering/listen_delight_audit.json"):
        src = ctx.final_path(rel)
        if src.is_file():
            dest = archive_dir / Path(rel).name
            if rel.startswith("mastering/"):
                dest = archive_dir / "listen_delight_audit.json"
            shutil.copy2(src, dest)
            copied.append(str(dest.name))
    entry = {
        "attempt_id": attempt_id,
        "family": family,
        "label": label or family,
        "registered_at": _now(),
        "rank_score": rank_score,
        "scores": score_doc,
        "archive_rel": archive_rel,
        "artifacts": copied,
        "catastrophic_ok": passes_catastrophic_floors(ctx, score_doc)[0],
    }
    candidates.append(entry)
    doc["candidates"] = candidates[-12:]
    ctx.write_json(CANDIDATES_REL, doc)
    return entry


def select_best_quality_candidate(
    ctx: RunContext,
    *,
    family: str | None = None,
) -> dict[str, Any] | None:
    doc = load_candidates_doc(ctx)
    candidates = [c for c in (doc.get("candidates") or []) if isinstance(c, dict)]
    if family:
        candidates = [c for c in candidates if str(c.get("family") or "") == family]
    viable = [c for c in candidates if c.get("catastrophic_ok")]
    if not viable:
        viable = candidates
    if not viable:
        return None
    return max(viable, key=lambda c: float(c.get("rank_score") or 0.0))


def apply_best_quality_candidate(ctx: RunContext, *, family: str | None = None) -> dict[str, Any]:
    best = select_best_quality_candidate(ctx, family=family)
    if not best:
        return {"ok": False, "reason": "no_candidates"}
    archive_rel = str(best.get("archive_rel") or "")
    archive_dir = Path(ctx.run_dir) / archive_rel
    if not archive_dir.is_dir():
        return {"ok": False, "reason": "archive_missing", "attempt_id": best.get("attempt_id")}
    restored: list[str] = []
    for name in ("master.wav", "assembly.wav", "listen_delight_audit.json"):
        src = archive_dir / name
        if not src.is_file():
            continue
        if name == "master.wav":
            dest = ctx.final_path("master", "master.wav")
        elif name == "assembly.wav":
            dest = ctx.final_path("master", "assembly.wav")
        else:
            dest = ctx.final_path("mastering", "listen_delight_audit.json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        restored.append(name)
    record_quality_advisories(
        ctx,
        gate_id="aspirational_pick_best",
        failed_checks=[],
        detail={
            "picked_attempt_id": best.get("attempt_id"),
            "rank_score": best.get("rank_score"),
            "family": best.get("family"),
            "restored": restored,
        },
        aspirational_proceeded=True,
    )
    ctx.log(
        f"aspirational quality: applied best candidate {best.get('attempt_id')} "
        f"score={best.get('rank_score')}",
        level="warning",
        stage="master_finalize",
    )
    return {"ok": True, "candidate": best, "restored": restored}


def record_quality_advisories(
    ctx: RunContext,
    *,
    gate_id: str,
    failed_checks: list[str],
    detail: dict[str, Any] | None = None,
    aspirational_proceeded: bool = False,
) -> None:
    entry = {
        "gate_id": gate_id,
        "failed_checks": list(failed_checks or []),
        "detail": dict(detail or {}),
        "at": _now(),
        "aspirational_proceeded": bool(aspirational_proceeded),
    }
    scores = collect_current_scores(ctx)
    if scores.get("listen_delight"):
        entry["listen_delight_overall"] = (scores.get("listen_delight") or {}).get("overall")

    def patch(meta: dict[str, Any]) -> None:
        advisories = list(meta.get(ADVISORIES_META_KEY) or [])
        advisories.append(entry)
        meta[ADVISORIES_META_KEY] = advisories[-20:]
        if aspirational_proceeded:
            meta["aspirational_proceeded"] = True
        qc = meta.get("qc_summaries") if isinstance(meta.get("qc_summaries"), dict) else {}
        qc["aspirational_quality"] = {
            "enabled": is_aspirational_enabled(ctx),
            "aspirational_proceeded": bool(meta.get("aspirational_proceeded")),
            "advisory_count": len(advisories),
        }
        meta["qc_summaries"] = qc

    ctx.mutate_run_meta(patch)


def has_quality_advisories(ctx: RunContext) -> bool:
    if not ctx.artifact_exists("run_meta.json"):
        return False
    try:
        meta = ctx.read_json("run_meta.json")
        adv = meta.get(ADVISORIES_META_KEY) if isinstance(meta, dict) else None
        if bool(adv) if isinstance(adv, list) else bool(meta.get("aspirational_proceeded")):
            return True
        # Progress floors mirror into quality_advisories; also honor floor_advisories.
        try:
            from interview_mux.floor_progress import has_floor_advisories

            if has_floor_advisories(ctx):
                return True
        except Exception:
            pass
        return False
    except Exception:
        return False


def publish_blocked_by_advisories(ctx: RunContext) -> bool:
    """True when S3/RSS sync must wait for operator consent.

    Local encode/package is never blocked by advisories (see
    ``require_publishable``). Consent for sync when advisories exist:
    Prepare (``g_publish_cleared``), Skip, or explicit Upload
    (``g_publish_advisory_consent`` — set when the operator clicks Upload).
    """
    if not require_operator_publish_when_advisory():
        return False
    if not has_quality_advisories(ctx):
        return False
    try:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        if isinstance(meta, dict) and (
            meta.get("g_publish_cleared")
            or meta.get("g_publish_skipped")
            or meta.get("g_publish_advisory_consent")
        ):
            return False
    except Exception:
        pass
    return True


def consent_g_publish_advisories(ctx: RunContext) -> None:
    """Record operator Upload as consent to sync despite quality advisories.

    Does not clear ``g_publish_pending`` — that stays until upload succeeds or Skip.
    """
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if not isinstance(meta, dict):
        meta = {}
    meta["g_publish_advisory_consent"] = True
    meta.pop("g_publish_remote_refused", None)
    meta.pop("g_publish_remote_refuse_reason", None)
    ctx.write_json("run_meta.json", meta, skip_handoff=True)


def note_remote_publish_refused(ctx: RunContext, *, reason: str) -> None:
    """Clinic PPUB-B2: local package may be ready; remote sync refused honestly.

    Never sets ``g_publish_advisory_consent``. On Full-auto, clears
    ``g_publish_pending`` so the journey does not hang waiting for consent that
    will not be auto-granted. Partial/manual keep pending (operator must Upload
    or Skip).
    """
    reason_s = str(reason or "remote_publish_refused")[:240]

    def _patch(meta: dict[str, Any]) -> None:
        meta["g_publish_remote_refused"] = True
        meta["g_publish_remote_refuse_reason"] = reason_s
        try:
            from interview_mux.automation_run import is_full_auto_run

            if is_full_auto_run(meta):
                # Local DONE; refuse-remote — do not wait forever for consent.
                meta["g_publish_pending"] = False
        except Exception:
            pass

    try:
        ctx.mutate_run_meta(_patch)
    except Exception:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        if not isinstance(meta, dict):
            meta = {}
        _patch(meta)
        ctx.write_json("run_meta.json", meta, skip_handoff=True)

    try:
        if ctx.artifact_exists("publish/publish_result.json"):
            pr = ctx.read_json("publish/publish_result.json")
            if isinstance(pr, dict):
                pr["uploaded"] = False
                pr["remote_refused"] = True
                pr["remote_refuse_reason"] = reason_s
                pr["hint"] = (
                    "Local package ready; S3 sync refused — quality advisories "
                    "require explicit Upload consent (or Skip). No silent hang."
                )
                ctx.write_json("publish/publish_result.json", pr, skip_handoff=True)
    except Exception:
        pass
