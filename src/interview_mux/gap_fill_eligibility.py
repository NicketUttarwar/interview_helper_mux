"""Binary gap-fill eligibility — skip missing_framing / optimal_questions / G1 when not applicable."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from interview_mux.config import merged_config
from interview_mux.conversation_context import load_conversation_context, role_is_frame
from interview_mux.run_context import RunContext

GAP_FILL_SKIP_REL = "understanding/gap_fill_skip.json"
GAP_FILL_GUI_STAGE_IDS = frozenset({"missing_framing", "gap_framing_compose", "optimal_questions", "g1_vo_pickup"})

# Skip G-Framing only for a true solo. Hosted 1:1 (including balanced talk-time)
# is always eligible. Sparse-omit is recovery_policy.vo_posture — not a skip.
_SKIP_TOPOLOGY_CLASSES = frozenset({"monologue_heavy", "monologue"})
_ELIGIBLE_TOPOLOGY_CLASSES = frozenset(
    {"one_on_one_asymmetric", "one_on_one_balanced", "balanced_1on1"}
)
_SILENT_SKIP_SIGNALS = frozenset({"forced_skipped", "true_monologue", "topology_skip_class"})
_SYNTHETIC_DELIVERIES = frozenset({"synthesize", "chatterbox", "record", "mlx_audio"})
# Authoritative VO count is post-layup. Compose is hints only — do not deadlock there.
_GAP_VO_COUNT_STAGES = frozenset({"nugget_layup_compose"})
_EDL_VO_COUNT_STAGES = frozenset(
    {"g1_vo_pickup", "vo_synthesize", "edl", "mix", "master_finalize"}
)
_SKIP_STUB_RELS = (
    "understanding/gap_report.json",
    "understanding/gap_evaluations.json",
)

_GAP_FILL_INVALIDATION_STAGES = frozenset({"speaker_roles", "source_topology_build"})


@dataclass
class GapFillDecision:
    eligible: bool
    reason: str
    signals: dict[str, Any] = field(default_factory=dict)


def gap_fill_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis = (cfg or merged_config()).get("analysis") or {}
    defaults = {
        "enabled": True,
        "auto_skip_when_ineligible": False,
        "frame_confidence_min": 0.65,
        "hide_gui_stages_when_skipped": False,
        "min_synthetic_vo_lines": 3,
    }
    raw = analysis.get("gap_fill")
    if isinstance(raw, dict):
        return {**defaults, **raw}
    return defaults


def gap_fill_enabled(cfg: dict[str, Any] | None = None) -> bool:
    return bool(gap_fill_cfg(cfg).get("enabled", True))


def gap_fill_auto_skip_enabled(cfg: dict[str, Any] | None = None) -> bool:
    cfg_block = gap_fill_cfg(cfg)
    return bool(cfg_block.get("enabled", True)) and bool(
        cfg_block.get("auto_skip_when_ineligible", False)
    )


def gap_fill_hide_gui_stages(cfg: dict[str, Any] | None = None) -> bool:
    return bool(gap_fill_cfg(cfg).get("hide_gui_stages_when_skipped", True))


def frame_confidence_min(cfg: dict[str, Any] | None = None) -> float:
    """Clone auto-approve floor — does not skip G-Framing eligibility."""
    return float(gap_fill_cfg(cfg).get("frame_confidence_min", 0.65))


def gap_fill_was_skipped(ctx: RunContext) -> bool:
    if not ctx.artifact_exists(GAP_FILL_SKIP_REL):
        return False
    doc = ctx.read_json(GAP_FILL_SKIP_REL)
    return isinstance(doc, dict) and str(doc.get("status")) == "skipped"


def gap_fill_mode(ctx: RunContext) -> Literal["active", "skipped", "pending"]:
    if gap_fill_was_skipped(ctx):
        return "skipped"
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    raw = str((meta or {}).get("gap_fill_mode") or "").lower()
    if raw == "active":
        return "active"
    if ctx.is_done("optimal_questions"):
        return "active"
    return "pending"


def _discard_skip_stub_gap_artifacts(ctx: RunContext) -> None:
    """Remove skip-producer gap_report / evaluations so framing Yes cannot inherit a stub."""
    for rel in _SKIP_STUB_RELS:
        if not ctx.artifact_exists(rel):
            continue
        try:
            doc = ctx.read_json(rel)
        except Exception:
            continue
        producer = str((doc.get("_meta") or {}).get("producer") or "") if isinstance(doc, dict) else ""
        if producer != "gap_fill_skip":
            continue
        path = ctx.final_path(*rel.split("/"))
        if path.is_file():
            path.unlink(missing_ok=True)


def clear_gap_fill_skip(ctx: RunContext, *, reason: str = "upstream_invalidation") -> None:
    """Remove skip artifact and gap stage done markers when roles/topology may have changed."""
    skip_path = ctx.final_path(*GAP_FILL_SKIP_REL.split("/"))
    if skip_path.is_file():
        skip_path.unlink(missing_ok=True)
    _discard_skip_stub_gap_artifacts(ctx)
    for stage_id in ("missing_framing", "gap_framing_compose", "optimal_questions"):
        marker = ctx.final_path(".stage_done", stage_id)
        if marker.is_file():
            marker.unlink(missing_ok=True)

    def patch(meta: dict[str, Any]) -> None:
        meta.pop("gap_fill_mode", None)
        meta.pop("gap_fill_skip_reason", None)

    if ctx.artifact_exists("run_meta.json"):
        ctx.mutate_run_meta(patch)

    if ctx.artifact_exists("understanding/flow_adaptation.json"):
        adapt = ctx.read_json("understanding/flow_adaptation.json")
        if isinstance(adapt, dict):
            overrides = dict(adapt.get("operator_overrides") or {})
            if overrides.pop("gap_fill_skipped", None) is not None:
                adapt["operator_overrides"] = overrides
                ctx.write_json("understanding/flow_adaptation.json", adapt, skip_handoff=True)

    ctx.log(
        f"Gap-fill skip cleared ({reason}) — will re-evaluate before missing_framing.",
        level="info",
        stage="missing_framing",
        action_id="gap_fill.re_evaluate",
        detail={"reason": reason},
    )


def maybe_clear_gap_fill_skip_on_invalidation(ctx: RunContext, stage_id: str) -> None:
    if stage_id in _GAP_FILL_INVALIDATION_STAGES and gap_fill_was_skipped(ctx):
        clear_gap_fill_skip(ctx, reason=f"redo_from_{stage_id}")


def silent_skip_allowed(decision: GapFillDecision) -> bool:
    """True only for operator skip / true monologue — never for hosted interviews."""
    if decision.eligible:
        return False
    return str((decision.signals or {}).get("skip_signal") or "") in _SILENT_SKIP_SIGNALS


def assess_gap_fill_eligibility(ctx: RunContext) -> GapFillDecision:
    """Fail-open: hosted / multi-speaker tapes run G-Framing. Skip only true solo."""
    try:
        from interview_mux.pipeline_mode import load_pipeline_mode
        from interview_mux.gap_vo_gates import gap_framing_enabled

        stored = load_pipeline_mode(ctx)
        if stored and str(stored.get("mode") or "") == "native_only":
            codes = list(stored.get("reason_codes") or [])
            skip_signal = codes[0] if codes else "native_only"
            return GapFillDecision(
                eligible=False,
                reason="pipeline_mode native_only — skip gap-fill VO",
                signals={"skip_signal": skip_signal, "pipeline_mode": "native_only"},
            )
        if not gap_framing_enabled(ctx):
            return GapFillDecision(
                eligible=False,
                reason="G-Framing disabled — skip gap-fill VO",
                signals={"skip_signal": "gap_framing_no", "pipeline_mode": "native_only"},
            )
    except Exception:
        pass

    if not gap_fill_enabled():
        return GapFillDecision(
            eligible=True,
            reason="gap_fill policy disabled — run gap stages",
            signals={"policy": "enabled_false"},
        )

    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    forced = str((meta or {}).get("gap_fill_mode") or "").lower()
    if forced == "skipped":
        return GapFillDecision(
            eligible=False,
            reason="run_meta.gap_fill_mode=skipped (operator escape hatch)",
            signals={"forced": "skipped", "skip_signal": "forced_skipped"},
        )
    if forced == "active":
        return GapFillDecision(
            eligible=True,
            reason="run_meta.gap_fill_mode=active (forced)",
            signals={"forced": "active"},
        )

    conv = load_conversation_context(ctx)
    speakers = [sp for sp in (conv.speakers or []) if isinstance(sp, dict)]
    n_speakers = len(speakers)
    topology_class = _topology_class(ctx)
    signals: dict[str, Any] = {
        "frame_ids": list(conv.frame_ids),
        "format_class": conv.format_class,
        "hypotheses_pending": conv.hypotheses_pending,
        "speaker_count": n_speakers,
        "topology_class": topology_class,
    }

    if topology_class in _SKIP_TOPOLOGY_CLASSES:
        return GapFillDecision(
            eligible=False,
            reason=f"Topology {topology_class} — skip gap-fill VO",
            signals={**signals, "skip_signal": "topology_skip_class"},
        )

    if topology_class in _ELIGIBLE_TOPOLOGY_CLASSES:
        return GapFillDecision(
            eligible=True,
            reason="Hosted one-on-one topology — run gap-fill evaluation",
            signals={**signals, "eligible_signal": "hosted_one_on_one"},
        )

    if n_speakers >= 2:
        return GapFillDecision(
            eligible=True,
            reason="Multi-speaker tape — run gap-fill evaluation",
            signals={**signals, "eligible_signal": "multi_speaker_fail_open"},
        )

    if n_speakers <= 1 and not _solo_frame_asks_questions(conv):
        return GapFillDecision(
            eligible=False,
            reason="True monologue — no interviewer frame for gap-fill VO",
            signals={**signals, "skip_signal": "true_monologue"},
        )

    return GapFillDecision(
        eligible=True,
        reason="Solo frame speaker asks questions — run gap-fill evaluation",
        signals={**signals, "eligible_signal": "solo_frame_questions"},
    )


def _topology_class(ctx: RunContext) -> str | None:
    if not ctx.artifact_exists("understanding/source_topology.json"):
        return None
    topo = ctx.read_json("understanding/source_topology.json")
    if isinstance(topo, dict) and topo.get("topology_class"):
        return str(topo["topology_class"])
    return None


def _solo_frame_asks_questions(conv: Any) -> bool:
    speakers = [sp for sp in (conv.speakers or []) if isinstance(sp, dict)]
    if len(speakers) != 1:
        return False
    sp = speakers[0]
    if not role_is_frame(str(sp.get("role") or "")):
        return False
    return str(sp.get("question_density") or "").lower() in {"medium", "high"}


def _native_segment_count(ctx: RunContext) -> int:
    if ctx.artifact_exists("master/selection.json"):
        sel = ctx.read_json("master/selection.json")
        if isinstance(sel, dict):
            ids = [str(x) for x in (sel.get("ordered_segment_ids") or []) if x]
            if ids:
                return len(ids)
    if ctx.artifact_exists("segments/manifest.json"):
        man = ctx.read_json("segments/manifest.json")
        rows = (man.get("segments") if isinstance(man, dict) else None) or []
        return len([r for r in rows if isinstance(r, dict)])
    return 0


def min_synthetic_vo_lines(ctx: RunContext) -> int:
    floor = max(1, int(gap_fill_cfg().get("min_synthetic_vo_lines") or 3))
    natives = _native_segment_count(ctx)
    if natives <= 0:
        return floor
    return max(1, min(floor, natives))


def count_active_gap_vo_lines(ctx: RunContext) -> int:
    if not ctx.artifact_exists("understanding/gap_report.json"):
        return 0
    doc = ctx.read_json("understanding/gap_report.json")
    if not isinstance(doc, dict):
        return 0
    n = 0
    for ln in doc.get("interviewer_lines") or []:
        if (
            not isinstance(ln, dict)
            or ln.get("skipped_optional")
            or ln.get("air_script_omit")
            or not str(ln.get("text") or "").strip()
        ):
            continue
        raw = ln.get("delivery")
        if raw is None:
            delivery = "synthesize"
        else:
            delivery = str(raw).strip().lower()
            if not delivery:
                continue
        if delivery in _SYNTHETIC_DELIVERIES:
            n += 1
    return n


def count_edl_vo_pickup(ctx: RunContext) -> int:
    if not ctx.artifact_exists("master/edl.json"):
        return 0
    edl = ctx.read_json("master/edl.json")
    if not isinstance(edl, dict):
        return 0
    return sum(
        1
        for c in (edl.get("clips") or [])
        if isinstance(c, dict) and str(c.get("type") or "") == "vo_pickup"
    )


def hosted_framing_requires_synthetic_vo(ctx: RunContext) -> bool:
    """Min-3 cloned host questions — hosted 1:1 with G-Framing Yes only.

    Panels / co-host / sparse-host stay auto-Yes but are not held to this floor.
    C-04: G1 optional skip sticky-waives this floor (XOR with seat floor).
    """
    try:
        from interview_mux.gap_vo_gates import gap_framing_enabled

        if not gap_framing_enabled(ctx):
            return False
    except Exception:
        return False
    if gap_fill_was_skipped(ctx):
        return False
    # C-04: sticky XOR — skip ⇒ floor waived.
    try:
        if ctx.artifact_exists("run_meta.json"):
            meta = ctx.read_json("run_meta.json")
            if isinstance(meta, dict) and meta.get("hosted_framing_floor_waived"):
                return False
        from interview_mux.gates import g1_vo_was_skipped_optional

        if g1_vo_was_skipped_optional(ctx):
            return False
    except Exception:
        pass
    return _topology_class(ctx) in _ELIGIBLE_TOPOLOGY_CLASSES


def synthetic_vo_incompleteness(ctx: RunContext, stage_id: str) -> str | None:
    """Ship bar: G-Framing Yes on hosted 1:1 requires cloned host questions."""
    if not hosted_framing_requires_synthetic_vo(ctx):
        return None
    need = min_synthetic_vo_lines(ctx)
    if stage_id in _GAP_VO_COUNT_STAGES:
        have = count_active_gap_vo_lines(ctx)
        if have < need:
            # One-shot reseat before declaring incomplete — air-script omit can
            # transiently wipe seats between layup publish and seed checks.
            try:
                from interview_mux.vo_contract import ensure_hosted_framing_vo_seats

                ensure_hosted_framing_vo_seats(ctx)
                have = count_active_gap_vo_lines(ctx)
            except Exception:
                pass
        if have < need:
            return (
                f"G-Framing Yes requires ≥{need} synthetic host line(s), "
                f"gap_report has {have}"
            )
        return None
    if stage_id in _EDL_VO_COUNT_STAGES:
        have = max(count_active_gap_vo_lines(ctx), count_edl_vo_pickup(ctx))
        if have < need:
            return (
                f"G-Framing Yes requires ≥{need} synthetic host VO clip(s) on the "
                f"timeline, have {have}"
            )
    return None


def persist_gap_fill_mode(ctx: RunContext, decision: GapFillDecision, *, skipped: bool) -> None:
    mode = "skipped" if skipped else "active"

    def patch(meta: dict[str, Any]) -> None:
        meta["gap_fill_mode"] = mode
        meta["gap_fill_skip_reason"] = decision.reason if skipped else None

    ctx.mutate_run_meta(patch)

    from interview_mux.analysis_memory import load_analysis_state, save_analysis_state

    state = load_analysis_state(ctx)
    state["gap_fill_decision"] = {
        "eligible": decision.eligible,
        "mode": mode,
        "reason": decision.reason,
        "signals": decision.signals,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_analysis_state(ctx, state, stage="missing_framing")


def gap_fill_stage_visibility(ctx: RunContext, stage_id: str) -> Literal["visible", "hidden"]:
    """Always visible — refinement plan removes hide path for skipped gap stages."""
    return "visible"


def visible_pipeline_stage_ids(stages: list[dict[str, Any]]) -> list[str]:
    """Stage ids shown in GUI step list (excludes hidden gap-fill stages)."""
    return [
        str(s.get("id"))
        for s in stages
        if isinstance(s, dict) and s.get("stage_visibility", "visible") != "hidden"
    ]


def filter_visible_job_stages(ctx: RunContext, stage_ids: list[str]) -> list[str]:
    """Exclude hidden gap-fill stages from batch job progress totals."""
    if not gap_fill_hide_gui_stages() or not gap_fill_was_skipped(ctx):
        return list(stage_ids)
    return [sid for sid in stage_ids if sid not in GAP_FILL_GUI_STAGE_IDS]


def gap_fill_skipped_by_operator(ctx: RunContext) -> bool:
    """True when the operator explicitly chose to skip gap speaker / VO pickup path."""
    if gap_fill_was_skipped(ctx):
        return True
    if not ctx.artifact_exists("understanding/flow_adaptation.json"):
        return False
    adapt = ctx.read_json("understanding/flow_adaptation.json")
    if not isinstance(adapt, dict):
        return False
    overrides = adapt.get("operator_overrides") or {}
    return bool(overrides.get("gap_fill_skipped"))


def operator_skip_gap_fill(
    ctx: RunContext,
    *,
    reason: str = "Operator skipped gap speaker sections — no new VO or gap analysis",
) -> None:
    """Operator escape hatch: skip missing_framing / optimal_questions / G1 VO path."""
    from interview_mux.source_topology import load_flow_adaptation
    from interview_mux.stages.gaps import ensure_gap_fill_skipped
    from interview_mux.write_staging import discard_stage_writes, has_pending_writes

    adapt = load_flow_adaptation(ctx) or {}
    overrides = dict(adapt.get("operator_overrides") or {})
    overrides["gap_fill_skipped"] = True
    overrides["gap_framing_enabled"] = False
    overrides["pickup_speaker_confirmed"] = True
    adapt["operator_overrides"] = overrides
    ctx.write_json("understanding/flow_adaptation.json", adapt, skip_handoff=True)

    def _disable_framing(meta: dict[str, Any]) -> None:
        meta["gap_framing_enabled"] = False

    if ctx.artifact_exists("run_meta.json"):
        ctx.mutate_run_meta(_disable_framing)

    for stage_id in ("missing_framing", "gap_framing_compose", "optimal_questions"):
        if has_pending_writes(ctx, stage_id):
            discard_stage_writes(ctx, stage_id)

    ensure_gap_fill_skipped(
        ctx,
        reason=reason,
        signals={"skip_signal": "operator_skip", "source": "gui"},
    )


__all__ = [
    "GAP_FILL_GUI_STAGE_IDS",
    "GAP_FILL_SKIP_REL",
    "GapFillDecision",
    "assess_gap_fill_eligibility",
    "clear_gap_fill_skip",
    "gap_fill_auto_skip_enabled",
    "gap_fill_cfg",
    "gap_fill_enabled",
    "gap_fill_hide_gui_stages",
    "gap_fill_mode",
    "gap_fill_was_skipped",
    "maybe_clear_gap_fill_skip_on_invalidation",
    "persist_gap_fill_mode",
    "gap_fill_stage_visibility",
    "visible_pipeline_stage_ids",
    "filter_visible_job_stages",
    "frame_confidence_min",
    "gap_fill_skipped_by_operator",
    "hosted_framing_requires_synthetic_vo",
    "min_synthetic_vo_lines",
    "operator_skip_gap_fill",
    "silent_skip_allowed",
    "synthetic_vo_incompleteness",
]
