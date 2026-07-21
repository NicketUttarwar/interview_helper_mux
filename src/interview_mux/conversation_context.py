"""Conversation context kernel — speakers artifact, gap sensitivity, hypotheses."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from interview_mux.run_context import RunContext
from interview_mux.tone_taxonomy import (
    FORMAT_CLASS_VALUES,
    TONE_CLASS_VALUES,
    validate_format_class,
    validate_tone_class,
)

FRAME_ROLES = frozenset({"interviewer", "moderator", "co_host", "host", "frame"})
CONTENT_ROLES = frozenset({"interviewee", "panelist", "guest", "content", "subject"})
GAP_TYPES = (
    "missing_question",
    "missing_setup",
    "missing_callback",
    "missing_definition",
    "missing_followup",
    "ok_with_light_bridge",
)
SEVERITY_LEVELS = ("strict", "normal", "relaxed")

_FORMAT_GAP_BASE: dict[str, dict[str, str]] = {
    "one_on_one": {
        "missing_question": "strict",
        "missing_setup": "strict",
        "missing_callback": "normal",
        "missing_definition": "normal",
        "missing_followup": "normal",
        "ok_with_light_bridge": "strict",
    },
    "panel": {
        "missing_question": "normal",
        "missing_setup": "normal",
        "missing_callback": "relaxed",
        "missing_definition": "strict",
        "missing_followup": "normal",
        "ok_with_light_bridge": "normal",
    },
    "fireside": {
        "missing_question": "normal",
        "missing_setup": "normal",
        "missing_callback": "relaxed",
        "missing_definition": "normal",
        "missing_followup": "relaxed",
        "ok_with_light_bridge": "relaxed",
    },
    "media_profile": {
        "missing_question": "normal",
        "missing_setup": "normal",
        "missing_callback": "relaxed",
        "missing_definition": "normal",
        "missing_followup": "relaxed",
        "ok_with_light_bridge": "relaxed",
    },
    "technical_deep_dive": {
        "missing_question": "normal",
        "missing_setup": "strict",
        "missing_callback": "normal",
        "missing_definition": "strict",
        "missing_followup": "normal",
        "ok_with_light_bridge": "strict",
    },
    "debate": {
        "missing_question": "normal",
        "missing_setup": "strict",
        "missing_callback": "relaxed",
        "missing_definition": "normal",
        "missing_followup": "normal",
        "ok_with_light_bridge": "normal",
    },
}

_GAP_NOTES: dict[str, str] = {
    "one_on_one": "Strict self-explanatory bar; fewer ok_with_light_bridge allowances.",
    "panel": "Relaxed missing_callback across guests; strict missing_definition for jargon.",
    "fireside": "Relaxed bridges; emotional continuity over literal self-containment.",
    "media_profile": "Relaxed bridges; polished guest answers often carry context.",
    "technical_deep_dive": "Strict missing_definition and missing_setup for acronyms.",
    "debate": "Strict missing_setup for positions; relaxed missing_callback when roles clear.",
}

_STAGES_GAP_SENSITIVITY = frozenset(
    {
        "missing_framing",
        "optimal_questions",
        "full_master_ranking",
        "highlight_selection",
        "edl_narrative_audit",
    }
)
_STAGES_FULL_SPEAKERS = frozenset(
    {
        "content_context",
        "content_brief_reanchor",
        "boundary_detection",
        "segment_classification",
        "source_topology_build",
        "speaker_roles",
    }
)
_STAGES_CONVERSATION_PROFILE = frozenset(
    {
        "content_context",
        "source_topology_build",
        "sonic_context_build",
        "episode_structure_compose",
        "delivery_brief_build",
        "soundscape_policy_build",
        "narrative_arc_plan",
        "topic_coverage_audit",
    }
)


def role_is_frame(role: str) -> bool:
    return (role or "").lower() in FRAME_ROLES


def role_is_content(role: str) -> bool:
    return (role or "").lower() in CONTENT_ROLES


def _shift_severity(level: str, *, steps: int) -> str:
    order = list(SEVERITY_LEVELS)
    try:
        idx = order.index(level)
    except ValueError:
        idx = 1
    idx = max(0, min(len(order) - 1, idx + steps))
    return order[idx]


def _question_density_from_count(question_count: int, turn_count: int) -> str:
    if turn_count <= 0:
        return "low"
    ratio = question_count / turn_count
    if ratio >= 0.25:
        return "high"
    if ratio >= 0.08:
        return "medium"
    return "low"


def _infer_format_class(speakers: list[dict[str, Any]], stats: list[dict[str, Any]]) -> str:
    panelists = [s for s in speakers if str(s.get("role", "")).lower() == "panelist"]
    content = [s for s in speakers if role_is_content(str(s.get("role", "")))]
    frame = [s for s in speakers if role_is_frame(str(s.get("role", "")))]
    if len(panelists) >= 2 or len(content) >= 2:
        return "panel"
    if len(frame) >= 2 or any(str(s.get("role", "")).lower() == "co_host" for s in speakers):
        return "debate"
    if stats and stats[0].get("talk_ratio", 0) >= 0.80:
        return "fireside"
    return "one_on_one"


def _infer_dynamics(stats: list[dict[str, Any]]) -> dict[str, str]:
    if not stats:
        return {"question_density": "medium", "turn_asymmetry": "medium", "overlap_risk": "low"}
    total_q = sum(int(s.get("question_count", 0)) for s in stats)
    total_turns = sum(max(1, int(s.get("turn_count", 0))) for s in stats)
    q_density = _question_density_from_count(total_q, total_turns)
    ratios = sorted((float(s.get("talk_ratio", 0)) for s in stats), reverse=True)
    asymmetry = "low"
    if len(ratios) >= 2:
        spread = ratios[0] - ratios[1]
        if spread >= 0.35:
            asymmetry = "high"
        elif spread >= 0.18:
            asymmetry = "medium"
    return {
        "question_density": q_density,
        "turn_asymmetry": asymmetry,
        "overlap_risk": "low",
    }


def build_gap_sensitivity(
    format_class: str,
    *,
    tone_class: str | None = None,
    dynamics: dict[str, Any] | None = None,
    speakers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Layered gap policy from format, tone, dynamics, and speaker layout."""
    fc = format_class if format_class in FORMAT_CLASS_VALUES else "one_on_one"
    hints = dict(_FORMAT_GAP_BASE.get(fc, _FORMAT_GAP_BASE["one_on_one"]))
    overlays: list[dict[str, str]] = []
    priority: list[str] = []
    deemphasize: list[str] = []
    segment_focus = "interviewee_answer"
    flow_hints = "flow1_narrative_default"

    tc = tone_class if validate_tone_class(tone_class) else None
    if tc in ("investor", "technical"):
        hints["missing_setup"] = _shift_severity(hints["missing_setup"], steps=1)
        hints["missing_definition"] = _shift_severity(hints["missing_definition"], steps=1)
        priority.append("missing_definition")
        overlays.append({"axis": f"tone_{tc}", "effect": "elevate missing_setup and missing_definition"})
    elif tc in ("human_interest", "conversational"):
        hints["ok_with_light_bridge"] = _shift_severity(hints["ok_with_light_bridge"], steps=-1)
        hints["missing_callback"] = _shift_severity(hints["missing_callback"], steps=-1)
        deemphasize.append("missing_callback")
    elif tc == "journalistic":
        hints["missing_question"] = _shift_severity(hints["missing_question"], steps=1)

    dyn = dynamics if isinstance(dynamics, dict) else {}
    if dyn.get("overlap_risk") == "high":
        hints["missing_setup"] = _shift_severity(hints["missing_setup"], steps=1)
        overlays.append({"axis": "high_overlap_risk", "effect": "elevate missing_setup"})
    if dyn.get("turn_asymmetry") == "high":
        hints["missing_question"] = _shift_severity(hints["missing_question"], steps=-1)
        deemphasize.append("missing_question")
    if dyn.get("question_density") == "low":
        hints["ok_with_light_bridge"] = _shift_severity(hints["ok_with_light_bridge"], steps=-1)

    spk = speakers or []
    panelists = [s for s in spk if str(s.get("role", "")).lower() == "panelist"]
    if len(panelists) >= 2 or fc == "panel":
        hints["missing_callback"] = "relaxed"
        priority.append("missing_definition")
        segment_focus = "interviewee_answer_per_guest"
        flow_hints = "flow2_clip_clarity_on_panel"
    if any(str(s.get("role", "")).lower() == "co_host" for s in spk):
        hints["missing_setup"] = _shift_severity(hints["missing_setup"], steps=1)
    if fc == "fireside":
        flow_hints = "flow1_narrative_continuity"
        deemphasize.append("ok_with_light_bridge")
    if fc == "technical_deep_dive":
        priority.extend(["missing_definition", "missing_setup"])
        flow_hints = "flow1_definition_heavy"

    notes = _GAP_NOTES.get(fc, "")
    if tc:
        notes = f"{notes} Tone overlay: {tc}." if notes else f"Tone overlay: {tc}."

    out: dict[str, Any] = {
        "format_class": fc,
        "severity_hints": hints,
        "priority_gap_types": list(dict.fromkeys(priority)),
        "deemphasize_gap_types": list(dict.fromkeys(deemphasize)),
        "theme_overlays": overlays,
        "segment_focus": segment_focus,
        "flow_hints": flow_hints,
        "notes": notes.strip(),
    }
    if tc:
        out["tone_class"] = tc
    return out


@dataclass
class ConversationContext:
    speakers_doc: dict[str, Any] = field(default_factory=dict)
    speakers: list[dict[str, Any]] = field(default_factory=list)
    speaker_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    frame_ids: list[str] = field(default_factory=list)
    content_ids: list[str] = field(default_factory=list)
    panelist_ids: list[str] = field(default_factory=list)
    format_class: str | None = None
    tone_class: str | None = None
    format_confidence: float | None = None
    dynamics: dict[str, Any] = field(default_factory=dict)
    gap_sensitivity: dict[str, Any] = field(default_factory=dict)
    conversation_profile: dict[str, Any] = field(default_factory=dict)
    conversation_hypotheses: list[dict[str, Any]] = field(default_factory=list)
    confirmed_hypothesis_id: str | None = None
    hypotheses_pending: bool = False
    topology_hint: str | None = None

    def profile_style(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if validate_tone_class(self.tone_class):
            out["tone_class"] = str(self.tone_class)
        if validate_format_class(self.format_class):
            out["format_class"] = str(self.format_class)
        if self.conversation_profile.get("format_notes"):
            out["format_notes"] = str(self.conversation_profile["format_notes"])[:240]
        return out

    def compact_speakers(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for sp in self.speakers:
            if not isinstance(sp, dict):
                continue
            row = {
                "speaker_id": sp.get("speaker_id"),
                "role": sp.get("role"),
                "narrative_function": sp.get("narrative_function"),
                "label": sp.get("label"),
                "confidence": sp.get("confidence"),
            }
            rows.append({k: v for k, v in row.items() if v is not None})
        return rows


def _load_speakers_doc(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists("understanding/speakers.json"):
        return {}
    doc = ctx.read_json("understanding/speakers.json")
    return doc if isinstance(doc, dict) else {}


def _resolve_format_tone(
    speakers_doc: dict[str, Any],
    state: dict[str, Any] | None,
) -> tuple[str | None, str | None, float | None]:
    style = (state or {}).get("style") if isinstance(state, dict) else {}
    if not isinstance(style, dict):
        style = {}
    profile = speakers_doc.get("conversation_profile") or {}
    if not isinstance(profile, dict):
        profile = {}

    confirmed_id = speakers_doc.get("confirmed_conversation_hypothesis_id")
    hypotheses = speakers_doc.get("conversation_hypotheses") or []
    if confirmed_id and isinstance(hypotheses, list):
        for hyp in hypotheses:
            if isinstance(hyp, dict) and hyp.get("id") == confirmed_id:
                fc = hyp.get("format_class")
                if validate_format_class(fc):
                    return str(fc), None, float(hyp.get("confidence") or 0.75)

    fc = style.get("format_class") or profile.get("format_class_candidate")
    tc = style.get("tone_class") or profile.get("tone_class_candidate")
    conf = profile.get("format_confidence")
    return (
        str(fc) if validate_format_class(fc) else None,
        str(tc) if validate_tone_class(tc) else None,
        float(conf) if isinstance(conf, (int, float)) else None,
    )


def load_conversation_context(ctx: RunContext) -> ConversationContext:
    from interview_mux.analysis_memory import load_analysis_state

    speakers_doc = _load_speakers_doc(ctx)
    state = load_analysis_state(ctx)
    speakers = speakers_doc.get("speakers") or []
    if not isinstance(speakers, list):
        speakers = []

    by_id: dict[str, dict[str, Any]] = {}
    frame_ids: list[str] = []
    content_ids: list[str] = []
    panelist_ids: list[str] = []
    for sp in speakers:
        if not isinstance(sp, dict):
            continue
        sid = str(sp.get("speaker_id") or "")
        if not sid:
            continue
        by_id[sid] = sp
        role = str(sp.get("role") or "")
        if role_is_frame(role):
            frame_ids.append(sid)
        if role_is_content(role):
            content_ids.append(sid)
        if role.lower() == "panelist":
            panelist_ids.append(sid)

    profile = speakers_doc.get("conversation_profile") or {}
    if not isinstance(profile, dict):
        profile = {}
    dynamics = profile.get("dynamics") if isinstance(profile.get("dynamics"), dict) else {}

    format_class, tone_class, format_confidence = _resolve_format_tone(speakers_doc, state)
    hypotheses = speakers_doc.get("conversation_hypotheses") or []
    if not isinstance(hypotheses, list):
        hypotheses = []
    confirmed_id = speakers_doc.get("confirmed_conversation_hypothesis_id")
    confirmed_id = str(confirmed_id) if confirmed_id else None
    hypotheses_pending = bool(hypotheses) and not confirmed_id

    gap_sensitivity = speakers_doc.get("gap_sensitivity") or state.get("gap_sensitivity") or {}
    if not isinstance(gap_sensitivity, dict) or not gap_sensitivity.get("severity_hints"):
        if format_class:
            gap_sensitivity = build_gap_sensitivity(
                format_class,
                tone_class=tone_class,
                dynamics=dynamics,
                speakers=speakers,
            )

    topology_hint = None
    if format_class == "panel" or len(panelist_ids) >= 2:
        topology_hint = "panel_multi_guest"
    elif any(str(s.get("role", "")).lower() == "co_host" for s in speakers):
        topology_hint = "co_host_frame"
    elif format_class == "fireside":
        topology_hint = "monologue_heavy"

    return ConversationContext(
        speakers_doc=speakers_doc,
        speakers=speakers,
        speaker_by_id=by_id,
        frame_ids=frame_ids,
        content_ids=content_ids,
        panelist_ids=panelist_ids,
        format_class=format_class,
        tone_class=tone_class,
        format_confidence=format_confidence,
        dynamics=dict(dynamics),
        gap_sensitivity=dict(gap_sensitivity) if isinstance(gap_sensitivity, dict) else {},
        conversation_profile=dict(profile),
        conversation_hypotheses=list(hypotheses),
        confirmed_hypothesis_id=confirmed_id,
        hypotheses_pending=hypotheses_pending,
        topology_hint=topology_hint,
    )


def enrich_speakers_artifact(ctx: RunContext, artifacts: dict[str, Any]) -> dict[str, Any]:
    from interview_mux.source_topology import _speaker_talk_stats

    out = copy.deepcopy(artifacts)
    speakers = out.get("speakers") or []
    if not isinstance(speakers, list):
        return out

    transcript = ctx.read_json("transcript/full.json")
    stats = _speaker_talk_stats(transcript, out)
    stats_by_id = {str(s["speaker_id"]): s for s in stats if s.get("speaker_id")}

    for row in speakers:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("speaker_id") or "")
        st = stats_by_id.get(sid)
        if not st:
            continue
        turns = max(1, int(st.get("turn_count", 0)))
        if row.get("question_density") is None:
            row["question_density"] = _question_density_from_count(
                int(st.get("question_count", 0)), turns
            )
        if row.get("avg_turn_length_ms") is None:
            row["avg_turn_length_ms"] = round(float(st.get("avg_turn_ms", 0)), 1)

    profile = out.get("conversation_profile")
    if not isinstance(profile, dict):
        profile = {}
        out["conversation_profile"] = profile
    if not validate_format_class(profile.get("format_class_candidate")):
        profile["format_class_candidate"] = _infer_format_class(speakers, stats)
    if profile.get("format_confidence") is None:
        profile["format_confidence"] = 0.6
    if not isinstance(profile.get("dynamics"), dict) or not profile.get("dynamics"):
        profile["dynamics"] = _infer_dynamics(stats)

    if not out.get("gap_sensitivity") or not (out.get("gap_sensitivity") or {}).get("severity_hints"):
        out["gap_sensitivity"] = build_gap_sensitivity(
            str(profile.get("format_class_candidate")),
            tone_class=profile.get("tone_class_candidate"),
            dynamics=profile.get("dynamics"),
            speakers=speakers,
        )
    return out


def apply_confirmed_hypothesis(doc: dict[str, Any], hypothesis_id: str) -> dict[str, Any]:
    out = copy.deepcopy(doc)
    hypotheses = out.get("conversation_hypotheses") or []
    chosen = None
    for hyp in hypotheses:
        if isinstance(hyp, dict) and str(hyp.get("id")) == hypothesis_id:
            chosen = hyp
            break
    if not chosen:
        raise ValueError(f"Unknown conversation hypothesis: {hypothesis_id}")

    role_map = chosen.get("speaker_role_map") or {}
    if isinstance(role_map, dict):
        for row in out.get("speakers") or []:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("speaker_id") or "")
            if sid in role_map:
                row["role"] = role_map[sid]

    profile = out.setdefault("conversation_profile", {})
    if validate_format_class(chosen.get("format_class")):
        profile["format_class_candidate"] = chosen["format_class"]
        profile["format_confidence"] = float(chosen.get("confidence") or 0.75)

    out["confirmed_conversation_hypothesis_id"] = hypothesis_id
    out["gap_sensitivity"] = build_gap_sensitivity(
        str(profile.get("format_class_candidate")),
        tone_class=profile.get("tone_class_candidate"),
        dynamics=profile.get("dynamics") if isinstance(profile.get("dynamics"), dict) else None,
        speakers=out.get("speakers") or [],
    )
    return out


def attach_conversation_context(
    ctx: RunContext,
    payload: dict[str, Any],
    stage_id: str | None = None,
) -> dict[str, Any]:
    """Inject conversation slices appropriate for the target stage."""
    from interview_mux.write_staging import active_stage

    sid = stage_id or active_stage() or ""
    if not ctx.artifact_exists("understanding/speakers.json"):
        return payload

    conv = load_conversation_context(ctx)
    out = dict(payload)

    style = conv.profile_style()
    if style:
        out["profile_style"] = {**(out.get("profile_style") or {}), **style}

    if sid in _STAGES_FULL_SPEAKERS and conv.speakers_doc:
        out["speakers"] = conv.speakers_doc
    elif conv.compact_speakers():
        out.setdefault("conversation_speakers", conv.compact_speakers())

    if sid in _STAGES_CONVERSATION_PROFILE and conv.conversation_profile:
        out["conversation_profile"] = conv.conversation_profile

    if sid in _STAGES_GAP_SENSITIVITY and conv.gap_sensitivity:
        out["gap_sensitivity"] = conv.gap_sensitivity

    if conv.topology_hint and sid in ("source_topology_build", "content_context", "narrative_arc_plan"):
        out["topology_hint"] = conv.topology_hint

    if conv.hypotheses_pending and sid in ("speaker_roles", "content_context"):
        out["conversation_hypotheses_pending"] = True

    return out


def conversation_context_volley_lines(ctx: RunContext, stage_id: str) -> str:
    conv = load_conversation_context(ctx)
    if not conv.speakers:
        return ""
    lines: list[str] = []
    if conv.format_class:
        lines.append(f"Format: {conv.format_class}")
    if conv.tone_class:
        lines.append(f"Tone: {conv.tone_class}")
    if conv.topology_hint:
        lines.append(f"Topology hint: {conv.topology_hint}")
    if conv.hypotheses_pending:
        lines.append(f"Hypotheses pending confirmation ({len(conv.conversation_hypotheses)})")
    if stage_id in _STAGES_GAP_SENSITIVITY and conv.gap_sensitivity.get("notes"):
        lines.append(f"Gap policy: {conv.gap_sensitivity['notes'][:200]}")
    role_bits = [
        f"{sp.get('speaker_id')}={sp.get('role')}" for sp in conv.compact_speakers()[:8]
    ]
    if role_bits:
        lines.append("Speakers: " + ", ".join(role_bits))
    return "\n".join(lines)


def hypotheses_require_confirmation(doc: dict[str, Any] | None) -> bool:
    if not isinstance(doc, dict):
        return False
    hypotheses = doc.get("conversation_hypotheses") or []
    if not hypotheses:
        return False
    return not bool(doc.get("confirmed_conversation_hypothesis_id"))


def sync_conversation_to_analysis_state(ctx: RunContext, speakers_doc: dict[str, Any]) -> None:
    from interview_mux.analysis_memory import load_analysis_state, save_analysis_state

    state = load_analysis_state(ctx)
    state["speakers"] = speakers_doc.get("speakers") or []
    profile = speakers_doc.get("conversation_profile")
    if isinstance(profile, dict) and profile:
        state["conversation_profile"] = profile
        state.setdefault("style", {})
        fc = profile.get("format_class_candidate")
        if validate_format_class(fc) and not state["style"].get("format_class"):
            state["style"]["format_class"] = fc
        tc = profile.get("tone_class_candidate")
        if validate_tone_class(tc) and not state["style"].get("tone_class"):
            state["style"]["tone_class"] = tc
        if not str(state["style"].get("tone") or "").strip() and validate_tone_class(tc):
            state["style"]["tone"] = str(tc).replace("_", " ")
    gs = speakers_doc.get("gap_sensitivity")
    if isinstance(gs, dict) and gs.get("severity_hints"):
        state["gap_sensitivity"] = gs
    hypotheses = speakers_doc.get("conversation_hypotheses")
    if isinstance(hypotheses, list):
        state["conversation_hypotheses"] = hypotheses
    confirmed = speakers_doc.get("confirmed_conversation_hypothesis_id")
    if confirmed:
        state["confirmed_conversation_hypothesis_id"] = confirmed
    save_analysis_state(ctx, state, stage="speaker_roles")


def confirm_conversation_hypothesis(ctx: RunContext, hypothesis_id: str) -> dict[str, Any]:
    """Apply operator-selected conversation hypothesis and invalidate downstream topology."""
    if not ctx.artifact_exists("understanding/speakers.json"):
        raise ValueError("understanding/speakers.json missing")
    doc = ctx.read_json("understanding/speakers.json")
    updated = apply_confirmed_hypothesis(doc, hypothesis_id)
    updated = enrich_speakers_artifact(ctx, updated)
    ctx.write_json("understanding/speakers.json", updated, stage_key="speaker_roles")
    sync_conversation_to_analysis_state(ctx, updated)

    from interview_mux.pipeline import ANALYSIS_ORDER

    downstream = [s for s in ANALYSIS_ORDER if s != "speaker_roles"]
    if "source_topology_build" in downstream:
        idx = downstream.index("source_topology_build")
        to_clear = downstream[idx:]
        if to_clear:
            ctx.clear_from(to_clear[0], ANALYSIS_ORDER)

    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}

    def _patch(m: dict[str, Any]) -> None:
        ack = dict(m.get("handoff_ack") or {})
        for sid in ("source_topology_build", "content_context", "boundary_detection"):
            ack.pop(sid, None)
        m["handoff_ack"] = ack

    if meta:
        ctx.mutate_run_meta(_patch)

    from interview_mux.artifact_lifecycle import invalidate_downstream_memory

    invalidate_downstream_memory(ctx, "source_topology_build")
    return updated
