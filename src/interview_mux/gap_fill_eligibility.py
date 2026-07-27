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

_SKIP_TOPOLOGY_CLASSES = frozenset(
    {"one_on_one_balanced", "monologue_heavy", "multi_idea_sparse_host"}
)
_ELIGIBLE_TOPOLOGY_CLASSES = frozenset({"one_on_one_asymmetric"})

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
        "auto_skip_when_ineligible": True,
        "frame_confidence_min": 0.65,
        "hide_gui_stages_when_skipped": False,
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
        cfg_block.get("auto_skip_when_ineligible", True)
    )


def gap_fill_hide_gui_stages(cfg: dict[str, Any] | None = None) -> bool:
    return bool(gap_fill_cfg(cfg).get("hide_gui_stages_when_skipped", True))


def _frame_confidence_min(cfg: dict[str, Any] | None = None) -> float:
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


def clear_gap_fill_skip(ctx: RunContext, *, reason: str = "upstream_invalidation") -> None:
    """Remove skip artifact and gap stage done markers when roles/topology may have changed."""
    skip_path = ctx.final_path(*GAP_FILL_SKIP_REL.split("/"))
    if skip_path.is_file():
        skip_path.unlink(missing_ok=True)
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


def assess_gap_fill_eligibility(ctx: RunContext) -> GapFillDecision:
    """Deterministic binary gate: True when classic asymmetric interview gap-fill applies."""
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
            signals={"forced": "skipped"},
        )
    if forced == "active":
        return GapFillDecision(
            eligible=True,
            reason="run_meta.gap_fill_mode=active (forced)",
            signals={"forced": "active"},
        )

    conv = load_conversation_context(ctx)
    signals: dict[str, Any] = {
        "frame_ids": list(conv.frame_ids),
        "format_class": conv.format_class,
        "hypotheses_pending": conv.hypotheses_pending,
    }

    if conv.hypotheses_pending:
        return GapFillDecision(
            eligible=False,
            reason="Conversation format hypotheses pending — skip gap-fill VO",
            signals={**signals, "skip_signal": "hypotheses_pending"},
        )

    speakers = conv.speakers or []
    if speakers and all(str(sp.get("role") or "").lower() == "unknown" for sp in speakers if isinstance(sp, dict)):
        return GapFillDecision(
            eligible=False,
            reason="All speaker roles unknown — skip gap-fill VO",
            signals={**signals, "skip_signal": "all_roles_unknown"},
        )

    if not conv.frame_ids:
        return GapFillDecision(
            eligible=False,
            reason="No frame/interviewer speaker identified — skip gap-fill VO",
            signals={**signals, "skip_signal": "zero_frame_speakers"},
        )

    min_conf = _frame_confidence_min()
    frame_speakers = [
        conv.speaker_by_id[sid]
        for sid in conv.frame_ids
        if sid in conv.speaker_by_id
    ]
    low_conf = [
        str(sp.get("speaker_id"))
        for sp in frame_speakers
        if isinstance(sp, dict)
        and float(sp.get("confidence") or 0) < min_conf
    ]
    if low_conf:
        return GapFillDecision(
            eligible=False,
            reason=f"Frame speaker confidence below {min_conf:.2f} — skip gap-fill VO",
            signals={**signals, "skip_signal": "low_frame_confidence", "low_conf_speakers": low_conf},
        )

    dynamics = conv.dynamics or {}
    turn_asymmetry = str(dynamics.get("turn_asymmetry") or "medium")
    signals["turn_asymmetry"] = turn_asymmetry

    if len(conv.frame_ids) > 1 and turn_asymmetry == "low":
        return GapFillDecision(
            eligible=False,
            reason="Multiple frame speakers with balanced turns — skip gap-fill VO",
            signals={**signals, "skip_signal": "multi_frame_low_asymmetry"},
        )

    topology_class = _topology_class(ctx)
    signals["topology_class"] = topology_class
    if topology_class in _SKIP_TOPOLOGY_CLASSES:
        return GapFillDecision(
            eligible=False,
            reason=f"Topology {topology_class} — skip gap-fill VO",
            signals={**signals, "skip_signal": "topology_skip_class"},
        )

    if conv.format_class == "fireside" and _storyteller_dominant(ctx, conv):
        return GapFillDecision(
            eligible=False,
            reason="Fireside format with dominant storyteller — skip gap-fill VO",
            signals={**signals, "skip_signal": "fireside_storyteller_dominant"},
        )

    if len(conv.frame_ids) == 1 and _frame_eligible(conv, min_conf):
        if topology_class in _ELIGIBLE_TOPOLOGY_CLASSES or turn_asymmetry in ("medium", "high"):
            return GapFillDecision(
                eligible=True,
                reason="Clear asymmetric interview frame — run gap-fill evaluation",
                signals={**signals, "eligible_signal": "asymmetric_interview"},
            )
        if _question_density_on_frame(ctx, conv):
            return GapFillDecision(
                eligible=True,
                reason="Question density concentrated on frame speaker — run gap-fill",
                signals={**signals, "eligible_signal": "frame_question_density"},
            )

    return GapFillDecision(
        eligible=False,
        reason="Interview frame not clear enough for gap-fill VO — using segments as-is",
        signals={**signals, "skip_signal": "default_not_eligible"},
    )


def _topology_class(ctx: RunContext) -> str | None:
    if not ctx.artifact_exists("understanding/source_topology.json"):
        return None
    topo = ctx.read_json("understanding/source_topology.json")
    if isinstance(topo, dict) and topo.get("topology_class"):
        return str(topo["topology_class"])
    return None


def _storyteller_dominant(ctx: RunContext, conv: Any) -> bool:
    if not ctx.artifact_exists("understanding/source_topology.json"):
        return False
    topo = ctx.read_json("understanding/source_topology.json")
    if not isinstance(topo, dict):
        return False
    stats = topo.get("speaker_stats") or []
    if not isinstance(stats, list) or len(stats) < 2:
        return False
    ratios = sorted(
        (float(row.get("talk_ratio") or 0) for row in stats if isinstance(row, dict)),
        reverse=True,
    )
    return len(ratios) >= 2 and ratios[0] >= 0.75


def _frame_eligible(conv: Any, min_conf: float) -> bool:
    if len(conv.frame_ids) != 1:
        return False
    sp = conv.speaker_by_id.get(conv.frame_ids[0]) or {}
    role = str(sp.get("role") or "")
    return role_is_frame(role) and float(sp.get("confidence") or 0) >= min_conf


def _question_density_on_frame(ctx: RunContext, conv: Any) -> bool:
    if len(conv.frame_ids) != 1:
        return False
    frame_id = conv.frame_ids[0]
    sp = conv.speaker_by_id.get(frame_id) or {}
    return str(sp.get("question_density") or "").lower() in ("medium", "high")


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
    overrides["pickup_speaker_confirmed"] = True
    adapt["operator_overrides"] = overrides
    ctx.write_json("understanding/flow_adaptation.json", adapt, skip_handoff=True)

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
    "gap_fill_skipped_by_operator",
    "operator_skip_gap_fill",
]
