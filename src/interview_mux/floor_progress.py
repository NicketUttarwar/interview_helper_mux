"""Progress-first floor policy — goals stretch, then advisory-continue.

Count/score floors stay as goals. After a stretch ladder (revive discarded /
skipped pools) and optional best-of-N, a miss becomes a durable advisory and the
walk continues toward master.wav. Only playability blockers hard-stop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext

FLOOR_ADVISORIES_META_KEY = "floor_advisories"
PROGRESS_FLOORS_DISABLED_META = "progress_floors_disabled"

# Still-blocking classes — playability / unreadable ship envelope only.
PLAYABILITY_BLOCKERS: frozenset[str] = frozenset(
    {
        "master_exists_nonempty",
        "spoken_vo_speakable",
        "audible_script_hash_agreement",
        "omit_ledger_air_contract",
        "selection_duration_floor",
        "opening_orientation_contract",
        "air_order_integrity",
        "no_open_ship_bar_defects",
        "stage_output_semantics",
        "ship_reachability_analysis",
        "never_touch_zeroed_keep",
        "vo_audibility_drift",
        "selection_edl_order_drift",
        "pending_write_barrier",
        "hosted_vo_wav_coverage",
        # hosted_vo_hollow_zero demoted: count-floor emptiness is advisory so a
        # short/empty hosted VO set never blocks the final master. Wav coverage
        # and other audibility blockers above remain playability.
    }
)

# Count/score floors that never block progress when progress_floors is on.
COUNT_SCORE_FLOOR_GATES: frozenset[str] = frozenset(
    {
        "hosted_vo_floor",
        "hosted_vo_floor_unmet",
        "hosted_vo_floor_unsatisfiable",
        "hosted_vo_hollow_zero",
        "min_layup_coverage",
        "nugget_air_coverage",
        "listenability_contract",
        "soundscape_density",
        "listen_delight_floors",
        "scorecard_overall_floor",
        "scorecard_dimension_floors",
        "boundary_timeline_coverage",
        "catastrophic_floors",
    }
)


@dataclass
class FloorSpec:
    gate_id: str
    goal: float | int
    catastrophic: float | int | None = None
    max_attempts: int = 3
    domain: str = ""
    stretch_fn: Callable[[RunContext], dict[str, Any]] | None = None
    score_fn: Callable[[RunContext], float] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class FloorEval:
    status: str  # "met" | "stretch_needed" | "miss_advisory"
    have: float | int
    goal: float | int
    gate_id: str
    detail: dict[str, Any] = field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def progress_floors_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    root = cfg if isinstance(cfg, dict) else merged_config()
    mastering = root.get("mastering") if isinstance(root, dict) else {}
    raw = (mastering or {}).get("progress_floors") if isinstance(mastering, dict) else {}
    defaults: dict[str, Any] = {
        "enabled": True,
        "max_attempts_per_family": 3,
        "record_advisories": True,
        "require_operator_publish_when_advisory": True,
        "hosted_vo": {"aspirational": True},
        "layup_coverage": {"aspirational": True},
        "nugget_air": {"aspirational": True},
        "listenability": {"aspirational": True},
        "soundscape_density": {"aspirational": True},
        "listen_delight": {"aspirational": True, "catastrophic_as_advisory": True},
        "boundary_coverage": {"aspirational": True},
    }
    if not isinstance(raw, dict):
        return defaults
    out = dict(defaults)
    out.update(raw)
    for key in (
        "hosted_vo",
        "layup_coverage",
        "nugget_air",
        "listenability",
        "soundscape_density",
        "listen_delight",
        "boundary_coverage",
    ):
        block = raw.get(key)
        if isinstance(block, dict):
            merged = dict(defaults.get(key) or {})
            merged.update(block)
            out[key] = merged
    return out


def is_progress_floors_enabled(ctx: RunContext | None = None) -> bool:
    cfg = progress_floors_cfg()
    if not bool(cfg.get("enabled", True)):
        return False
    if ctx is not None and ctx.artifact_exists("run_meta.json"):
        try:
            meta = ctx.read_json("run_meta.json")
            if isinstance(meta, dict) and meta.get(PROGRESS_FLOORS_DISABLED_META):
                return False
        except Exception:
            pass
    return True


def domain_aspirational(domain: str, ctx: RunContext | None = None) -> bool:
    """True when a named floor domain should advisory-continue on miss."""
    if not is_progress_floors_enabled(ctx):
        return False
    cfg = progress_floors_cfg()
    block = cfg.get(domain)
    if isinstance(block, dict):
        return bool(block.get("aspirational", True))
    return True


def hosted_vo_aspirational(ctx: RunContext | None = None) -> bool:
    return domain_aspirational("hosted_vo", ctx)


def layup_coverage_aspirational(ctx: RunContext | None = None) -> bool:
    return domain_aspirational("layup_coverage", ctx)


def nugget_air_aspirational(ctx: RunContext | None = None) -> bool:
    return domain_aspirational("nugget_air", ctx)


def listenability_aspirational(ctx: RunContext | None = None) -> bool:
    return domain_aspirational("listenability", ctx)


def soundscape_density_aspirational(ctx: RunContext | None = None) -> bool:
    return domain_aspirational("soundscape_density", ctx)


def listen_delight_aspirational(ctx: RunContext | None = None) -> bool:
    return domain_aspirational("listen_delight", ctx)


def catastrophic_as_advisory(ctx: RunContext | None = None) -> bool:
    if not listen_delight_aspirational(ctx):
        return False
    cfg = progress_floors_cfg()
    block = cfg.get("listen_delight") if isinstance(cfg.get("listen_delight"), dict) else {}
    return bool(block.get("catastrophic_as_advisory", True))


def boundary_coverage_aspirational(ctx: RunContext | None = None) -> bool:
    return domain_aspirational("boundary_coverage", ctx)


def max_attempts_per_family(ctx: RunContext | None = None) -> int:
    try:
        return max(1, int(progress_floors_cfg().get("max_attempts_per_family") or 3))
    except (TypeError, ValueError):
        return 3


def floor_miss_blocks_progress(ctx: RunContext | None, gate_id: str) -> bool:
    """Count/score floor misses never block when progress floors are on."""
    gid = str(gate_id or "").strip()
    if gid in PLAYABILITY_BLOCKERS:
        return True
    if not is_progress_floors_enabled(ctx):
        return gid in COUNT_SCORE_FLOOR_GATES or bool(gid)
    if gid in COUNT_SCORE_FLOOR_GATES:
        return False
    # Unknown count-like tokens that include "floor" stay non-blocking under policy.
    if "floor" in gid.lower() and gid not in PLAYABILITY_BLOCKERS:
        return False
    return False


def is_playability_blocker(error_class: str) -> bool:
    return str(error_class or "").strip() in PLAYABILITY_BLOCKERS


def evaluate_floor(
    ctx: RunContext,
    spec: FloorSpec,
    have: float | int,
) -> FloorEval:
    goal = spec.goal
    try:
        have_n = float(have)
        goal_n = float(goal)
    except (TypeError, ValueError):
        have_n = 0.0
        goal_n = 0.0
    detail = {"have": have, "goal": goal, "domain": spec.domain}
    if have_n + 1e-9 >= goal_n:
        return FloorEval(
            status="met",
            have=have,
            goal=goal,
            gate_id=spec.gate_id,
            detail=detail,
        )
    if domain_aspirational(spec.domain or "hosted_vo", ctx) or is_progress_floors_enabled(ctx):
        return FloorEval(
            status="stretch_needed" if spec.stretch_fn else "miss_advisory",
            have=have,
            goal=goal,
            gate_id=spec.gate_id,
            detail=detail,
        )
    return FloorEval(
        status="miss_advisory",
        have=have,
        goal=goal,
        gate_id=spec.gate_id,
        detail={**detail, "hard_legacy": True},
    )


def run_stretch_then_best_of(
    ctx: RunContext,
    spec: FloorSpec,
    *,
    have_fn: Callable[[RunContext], float | int],
) -> FloorEval:
    """Stretch once, optionally score variants via stretch_fn, then evaluate."""
    have = have_fn(ctx)
    ev = evaluate_floor(ctx, spec, have)
    if ev.status == "met":
        return ev
    stretch_notes: list[str] = []
    if callable(spec.stretch_fn):
        try:
            result = spec.stretch_fn(ctx) or {}
            if isinstance(result, dict):
                notes = result.get("notes") or result.get("revived") or []
                if isinstance(notes, list):
                    stretch_notes.extend(str(n) for n in notes)
                elif notes:
                    stretch_notes.append(str(notes))
        except Exception as exc:
            stretch_notes.append(f"stretch_error:{exc}")
    have2 = have_fn(ctx)
    ev2 = evaluate_floor(ctx, spec, have2)
    ev2.detail["stretch_notes"] = stretch_notes
    if ev2.status == "met":
        return ev2
    # Best-of-N is domain-owned (candidate ledgers); here we only re-score after stretch.
    if callable(spec.score_fn):
        try:
            ev2.detail["score"] = float(spec.score_fn(ctx))
        except Exception:
            pass
    ev2.status = "miss_advisory"
    return ev2


def record_floor_advisory(
    ctx: RunContext,
    gate_id: str,
    detail: dict[str, Any] | None = None,
    *,
    aspirational_proceeded: bool = True,
    mirror_quality: bool = True,
) -> None:
    if not bool(progress_floors_cfg().get("record_advisories", True)):
        return
    entry = {
        "gate_id": str(gate_id),
        "detail": dict(detail or {}),
        "at": _now(),
        "aspirational_proceeded": bool(aspirational_proceeded),
    }

    def patch(meta: dict[str, Any]) -> None:
        advisories = list(meta.get(FLOOR_ADVISORIES_META_KEY) or [])
        advisories.append(entry)
        meta[FLOOR_ADVISORIES_META_KEY] = advisories[-40:]
        if aspirational_proceeded:
            meta["floor_aspirational_proceeded"] = True
            # Clear thrash stamps for count floors.
            if str(gate_id).startswith("hosted_vo_floor"):
                meta.pop("hosted_vo_floor_unmet", None)
                meta.pop("hosted_vo_floor_unmet_prose", None)
                meta.pop("hosted_vo_floor_unsatisfiable", None)
                meta.pop("hosted_vo_floor_unsatisfiable_prose", None)
                meta.pop("hosted_vo_floor_wait", None)
                if meta.get("needs_operator_reason") in {
                    "hosted_vo_floor_unmet",
                    "hosted_vo_floor_unsatisfiable",
                }:
                    meta.pop("needs_operator", None)
                    meta.pop("needs_operator_reason", None)
        qc = meta.get("qc_summaries") if isinstance(meta.get("qc_summaries"), dict) else {}
        qc["progress_floors"] = {
            "enabled": is_progress_floors_enabled(ctx),
            "floor_aspirational_proceeded": bool(meta.get("floor_aspirational_proceeded")),
            "advisory_count": len(advisories),
        }
        meta["qc_summaries"] = qc

    try:
        ctx.mutate_run_meta(patch)
    except Exception:
        pass

    if mirror_quality:
        try:
            from interview_mux.aspirational_quality import record_quality_advisories

            record_quality_advisories(
                ctx,
                gate_id=str(gate_id),
                failed_checks=[str(gate_id)],
                detail=dict(detail or {}),
                aspirational_proceeded=aspirational_proceeded,
            )
        except Exception:
            pass

    try:
        ctx.log(
            f"progress_floors advisory: {gate_id} "
            f"detail={ {k: detail.get(k) for k in ('have', 'need', 'goal', 'pool_exhausted') if isinstance(detail, dict) and k in detail} }",
            level="warning",
            stage="floor_progress",
        )
    except Exception:
        pass


def has_floor_advisories(ctx: RunContext) -> bool:
    if not ctx.artifact_exists("run_meta.json"):
        return False
    try:
        meta = ctx.read_json("run_meta.json")
        if not isinstance(meta, dict):
            return False
        adv = meta.get(FLOOR_ADVISORIES_META_KEY)
        return bool(adv) if isinstance(adv, list) else bool(meta.get("floor_aspirational_proceeded"))
    except Exception:
        return False


def proceed_on_floor_miss(
    ctx: RunContext,
    *,
    gate_id: str,
    have: float | int,
    need: float | int,
    pool_exhausted: bool = True,
    extra: dict[str, Any] | None = None,
) -> None:
    """Record advisory and clear count-floor thrash stamps — walk continues.

    Hosted VO count floor (including have==0 / HOLLOW_ZERO) is advisory-only so
    the pipeline can always continue to a final master. Still stamps identity via
    callers; this records the floor advisory + aspirational_proceeded flag.
    """
    detail: dict[str, Any] = {
        "have": have,
        "need": need,
        "goal": need,
        "pool_exhausted": bool(pool_exhausted),
    }
    if extra:
        detail.update(extra)
    record_floor_advisory(
        ctx,
        gate_id=gate_id,
        detail=detail,
        aspirational_proceeded=True,
        mirror_quality=True,
    )


__all__ = [
    "COUNT_SCORE_FLOOR_GATES",
    "FLOOR_ADVISORIES_META_KEY",
    "FloorEval",
    "FloorSpec",
    "PLAYABILITY_BLOCKERS",
    "boundary_coverage_aspirational",
    "catastrophic_as_advisory",
    "domain_aspirational",
    "evaluate_floor",
    "floor_miss_blocks_progress",
    "has_floor_advisories",
    "hosted_vo_aspirational",
    "is_playability_blocker",
    "is_progress_floors_enabled",
    "layup_coverage_aspirational",
    "listen_delight_aspirational",
    "listenability_aspirational",
    "max_attempts_per_family",
    "nugget_air_aspirational",
    "proceed_on_floor_miss",
    "progress_floors_cfg",
    "record_floor_advisory",
    "run_stretch_then_best_of",
    "soundscape_density_aspirational",
]
