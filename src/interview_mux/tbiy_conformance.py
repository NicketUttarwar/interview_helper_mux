"""Graduated TBIY narrative conformance — inventory tape elements and pick strategies.

When ``production_style`` is ``tbiy_narrative``, the system stays on TBIY even when
classic dual-host Wondery ingredients are weak or missing. Missing *frame* pieces
become VO bridges (operator record); sparse narrative collapses acts; weak moat
stays soft — never invent guest evidence and never flip to documentary.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.config import merged_config
from interview_mux.production_profile import TBIY_STYLE, adaptation_defaults, is_tbiy
from interview_mux.run_context import RunContext

# Presence labels (what the tape / artifacts support)
PRESENCE_PRESENT = "present"
PRESENCE_WEAK = "weak"
PRESENCE_MISSING = "missing"
PRESENCE_SPARSE = "sparse"
PRESENCE_UNKNOWN = "unknown"

# Strategy actions (how pipeline + prompts should behave)
ACTION_APPLY = "apply"
ACTION_SOFT = "soft"
ACTION_VO_BRIDGE = "vo_bridge"
ACTION_COLLAPSE = "collapse"
ACTION_DEFER = "defer"
ACTION_OPERATOR = "operator_only"

ELEMENT_IDS = (
    "dual_voice_reactor",
    "storyteller_dominance",
    "reaction_texture",
    "act_bridge_capacity",
    "five_act_scaffolding",
    "strategic_moat",
    "era_texture",
    "punctuator_anchors",
    "pickup_frame_voice",
)


def _role_is_content(role: str) -> bool:
    from interview_mux.conversation_context import role_is_content

    return role_is_content(role)


def _role_is_frame(role: str) -> bool:
    from interview_mux.conversation_context import role_is_frame

    return role_is_frame(role)


def _narrative_function_hint(role: str, narrative_function: str | None) -> str:
    nf = (narrative_function or "").lower()
    if nf in ("storyteller", "reactor", "frame", "analytical_lens"):
        return nf
    r = (role or "").lower()
    if r in ("interviewee", "panelist", "guest"):
        return "storyteller"
    if r in ("interviewer", "moderator", "co_host", "host"):
        return "frame"
    return "unknown"


def _conformance_cfg() -> dict[str, Any]:
    profiles = merged_config().get("production_profiles") or {}
    tbiy = profiles.get(TBIY_STYLE) or {}
    return dict(tbiy.get("conformance") or {})


def _thresholds() -> dict[str, float]:
    cfg = _conformance_cfg()
    th = dict(cfg.get("thresholds") or {})
    return {
        "frame_talk_present": float(th.get("frame_talk_present", 0.18)),
        "frame_talk_weak": float(th.get("frame_talk_weak", 0.08)),
        "content_dominance": float(th.get("content_dominance", 0.55)),
        "reaction_turns_present": float(th.get("reaction_turns_present", 6)),
        "reaction_questions_present": float(th.get("reaction_questions_present", 3)),
        "duration_ms_full_acts": float(th.get("duration_ms_full_acts", 1_800_000)),
        "duration_ms_soft_acts": float(th.get("duration_ms_soft_acts", 600_000)),
        "topic_era_present": float(th.get("topic_era_present", 2)),
    }


def _element(
    element_id: str,
    *,
    presence: str,
    action: str,
    rationale: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": element_id,
        "presence": presence,
        "action": action,
        "rationale": rationale,
        "evidence": evidence or {},
    }


def _partition_speakers(stats: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    content = [s for s in stats if _role_is_content(str(s.get("role_hint")))]
    frame = [s for s in stats if _role_is_frame(str(s.get("role_hint")))]
    return content, frame


def _duration_ms_from_stats(stats: list[dict[str, Any]]) -> int:
    return int(sum(float(s.get("talk_ms") or 0) for s in stats))


def inventory_from_topology(
    *,
    topology_class: str,
    stats: list[dict[str, Any]],
    role_map: dict[str, Any] | None = None,
    pickup_id: str | None = None,
    topic_count: int = 0,
    defaults: dict[str, Any] | None = None,
    ctx: RunContext | None = None,
    gap_fill_skipped: bool | None = None,
) -> list[dict[str, Any]]:
    """Build element inventory + strategies from topology-time signals only."""
    th = _thresholds()
    profile_defaults = defaults if isinstance(defaults, dict) else {}
    if not profile_defaults:
        # Prefer TBIY profile keys even when global production_style is documentary
        profiles = merged_config().get("production_profiles") or {}
        profile_defaults = dict((profiles.get(TBIY_STYLE) or {}).get("adaptation_defaults") or {})
    require_moat = bool(profile_defaults.get("require_moat", True))
    require_five = bool(profile_defaults.get("require_five_act_coverage", True))
    content, frame = _partition_speakers(stats)
    frame_talk = sum(float(s.get("talk_ratio") or 0) for s in frame)
    content_talk = sum(float(s.get("talk_ratio") or 0) for s in content) or (
        float(stats[0].get("talk_ratio") or 0) if stats else 0.0
    )
    frame_turns = sum(int(s.get("turn_count") or 0) for s in frame)
    frame_questions = sum(int(s.get("question_count") or 0) for s in frame)
    reactors = list((role_map or {}).get("reactor_speaker_ids") or [])
    duration_ms = _duration_ms_from_stats(stats)
    elements: list[dict[str, Any]] = []
    if gap_fill_skipped is None and ctx is not None:
        from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

        gap_fill_skipped = gap_fill_was_skipped(ctx)
    gap_fill_skipped = bool(gap_fill_skipped)

    # dual_voice_reactor
    if frame and frame_talk >= th["frame_talk_present"] and reactors:
        elements.append(
            _element(
                "dual_voice_reactor",
                presence=PRESENCE_PRESENT,
                action=ACTION_APPLY,
                rationale="Frame/reactor voice present on tape — prefer trim/reorder over invented banter.",
                evidence={"frame_talk_ratio": round(frame_talk, 4), "reactor_ids": reactors},
            )
        )
    elif frame and frame_talk >= th["frame_talk_weak"]:
        elements.append(
            _element(
                "dual_voice_reactor",
                presence=PRESENCE_WEAK,
                action=ACTION_SOFT,
                rationale="Sparse reactor turns — soft dual-voice bias; bridge gaps via pickup VO.",
                evidence={"frame_talk_ratio": round(frame_talk, 4), "reactor_ids": reactors},
            )
        )
    else:
        elements.append(
            _element(
                "dual_voice_reactor",
                presence=PRESENCE_MISSING,
                action=ACTION_VO_BRIDGE,
                rationale="No usable dual-voice texture — VO reaction/bridge lines toward TBIY frame.",
                evidence={"frame_talk_ratio": round(frame_talk, 4)},
            )
        )

    # storyteller_dominance
    if content_talk >= th["content_dominance"]:
        elements.append(
            _element(
                "storyteller_dominance",
                presence=PRESENCE_PRESENT,
                action=ACTION_APPLY,
                rationale="Content/storyteller dominates talk time — guest audio is trim/reorder only.",
                evidence={"content_talk_ratio": round(content_talk, 4)},
            )
        )
    else:
        elements.append(
            _element(
                "storyteller_dominance",
                presence=PRESENCE_WEAK,
                action=ACTION_SOFT,
                rationale="Balanced or unclear storyteller dominance — soft claim-impact ranking.",
                evidence={"content_talk_ratio": round(content_talk, 4)},
            )
        )

    # reaction_texture
    if frame_turns >= th["reaction_turns_present"] or frame_questions >= th["reaction_questions_present"]:
        elements.append(
            _element(
                "reaction_texture",
                presence=PRESENCE_PRESENT,
                action=ACTION_APPLY,
                rationale="Enough host questions/turns for on-tape reactions and punctuator anchors.",
                evidence={"frame_turns": frame_turns, "frame_questions": frame_questions},
            )
        )
    elif frame_turns > 0 or frame_questions > 0:
        elements.append(
            _element(
                "reaction_texture",
                presence=PRESENCE_WEAK,
                action=ACTION_VO_BRIDGE,
                rationale="Thin reaction texture — prioritize short pickup reaction_line / chapter_hook.",
                evidence={"frame_turns": frame_turns, "frame_questions": frame_questions},
            )
        )
    else:
        elements.append(
            _element(
                "reaction_texture",
                presence=PRESENCE_MISSING,
                action=ACTION_VO_BRIDGE,
                rationale="No host reaction turns — VO bridges carry TBIY frame energy.",
                evidence={"frame_turns": 0, "frame_questions": 0},
            )
        )

    # act_bridge_capacity — monologue / sparse host needs bridges
    if topology_class in ("monologue_heavy", "multi_idea_sparse_host"):
        elements.append(
            _element(
                "act_bridge_capacity",
                presence=PRESENCE_SPARSE,
                action=ACTION_VO_BRIDGE,
                rationale=f"{topology_class}: act bridges via pickup VO, not fabricated guest transitions.",
                evidence={"topology_class": topology_class},
            )
        )
    elif topology_class in ("panel_multi_guest", "co_host_frame"):
        elements.append(
            _element(
                "act_bridge_capacity",
                presence=PRESENCE_PRESENT,
                action=ACTION_SOFT,
                rationale="Multi-voice source — soft bridges between guest slots; prefer tape turns.",
                evidence={"topology_class": topology_class},
            )
        )
    else:
        elements.append(
            _element(
                "act_bridge_capacity",
                presence=PRESENCE_PRESENT if frame_talk >= th["frame_talk_weak"] else PRESENCE_WEAK,
                action=ACTION_SOFT if frame_talk >= th["frame_talk_weak"] else ACTION_VO_BRIDGE,
                rationale="1:1 sources use soft act bridges; VO when frame is thin.",
                evidence={"topology_class": topology_class, "frame_talk_ratio": round(frame_talk, 4)},
            )
        )

    # five_act_scaffolding
    if topology_class == "monologue_heavy" or duration_ms < th["duration_ms_soft_acts"]:
        elements.append(
            _element(
                "five_act_scaffolding",
                presence=PRESENCE_SPARSE,
                action=ACTION_COLLAPSE,
                rationale="Collapse acts II–III when sparse; soft act hints only — do not pad empty acts.",
                evidence={"topology_class": topology_class, "duration_ms": duration_ms},
            )
        )
    elif duration_ms >= th["duration_ms_full_acts"] and require_five:
        elements.append(
            _element(
                "five_act_scaffolding",
                presence=PRESENCE_PRESENT,
                action=ACTION_APPLY,
                rationale="Duration and topology support full five-act TBIY compass.",
                evidence={"duration_ms": duration_ms, "require_five_act_coverage": require_five},
            )
        )
    else:
        elements.append(
            _element(
                "five_act_scaffolding",
                presence=PRESENCE_WEAK,
                action=ACTION_SOFT,
                rationale="Soft five-act coverage — assign act_hint when evidence fits; skip empty acts.",
                evidence={"duration_ms": duration_ms, "require_five_act_coverage": require_five},
            )
        )

    # strategic_moat — topology-time unknown; enriched later from content_brief
    if require_moat:
        elements.append(
            _element(
                "strategic_moat",
                presence=PRESENCE_UNKNOWN,
                action=ACTION_SOFT,
                rationale="Moat required by profile but not yet evidenced — soft name from claims later; never invent.",
                evidence={"require_moat": True},
            )
        )
    else:
        elements.append(
            _element(
                "strategic_moat",
                presence=PRESENCE_UNKNOWN,
                action=ACTION_DEFER,
                rationale="Moat not required — defer until brief claims support a named concept.",
                evidence={"require_moat": False},
            )
        )

    # era_texture
    if topic_count >= int(th["topic_era_present"]):
        elements.append(
            _element(
                "era_texture",
                presence=PRESENCE_WEAK,
                action=ACTION_SOFT,
                rationale="Topic hints available — soft era tags only with transcript support.",
                evidence={"topic_count": topic_count},
            )
        )
    else:
        elements.append(
            _element(
                "era_texture",
                presence=PRESENCE_UNKNOWN,
                action=ACTION_DEFER,
                rationale="Sparse topics — defer era texture; do not invent eras.",
                evidence={"topic_count": topic_count},
            )
        )

    # punctuator_anchors
    if topology_class in ("one_on_one_asymmetric", "one_on_one_balanced", "multi_idea_sparse_host"):
        elements.append(
            _element(
                "punctuator_anchors",
                presence=PRESENCE_PRESENT if frame_talk >= th["frame_talk_weak"] else PRESENCE_WEAK,
                action=ACTION_APPLY if frame_talk >= th["frame_talk_weak"] else ACTION_SOFT,
                rationale="Favor punctuators on claim pivots; density follows topology caps.",
                evidence={"topology_class": topology_class},
            )
        )
    elif topology_class == "monologue_heavy":
        elements.append(
            _element(
                "punctuator_anchors",
                presence=PRESENCE_SPARSE,
                action=ACTION_SOFT,
                rationale="Monologue — beds over punctuators; soft punctuator anchors only.",
                evidence={"topology_class": topology_class},
            )
        )
    else:
        elements.append(
            _element(
                "punctuator_anchors",
                presence=PRESENCE_WEAK,
                action=ACTION_SOFT,
                rationale="Moderate punctuator bias for panel/co-host topologies.",
                evidence={"topology_class": topology_class},
            )
        )

    # pickup_frame_voice
    if gap_fill_skipped:
        elements.append(
            _element(
                "pickup_frame_voice",
                presence=PRESENCE_MISSING,
                action=ACTION_DEFER,
                rationale="Gap-fill VO path skipped — no pickup frame voice required for this source.",
                evidence={"gap_fill_mode": "skipped"},
            )
        )
    else:
        least = min(stats, key=lambda s: float(s.get("talk_ms") or 0))["speaker_id"] if stats else None
        pickup = pickup_id or least
        pickup_row = next((s for s in stats if str(s.get("speaker_id")) == str(pickup)), None)
        pickup_is_frame = bool(pickup_row and _role_is_frame(str(pickup_row.get("role_hint"))))
        if pickup and pickup_is_frame:
            elements.append(
                _element(
                    "pickup_frame_voice",
                    presence=PRESENCE_PRESENT,
                    action=ACTION_APPLY,
                    rationale="Gap pickup voice is a frame/host speaker (least-spoken default).",
                    evidence={"pickup_eligible_speaker_id": pickup},
                )
            )
        elif pickup:
            elements.append(
                _element(
                    "pickup_frame_voice",
                    presence=PRESENCE_WEAK,
                    action=ACTION_OPERATOR,
                    rationale="Pickup defaults to least-spoken; confirm in GUI if that speaker is not the intended host frame.",
                    evidence={"pickup_eligible_speaker_id": pickup, "least_spoken_speaker_id": least},
                )
            )
        else:
            elements.append(
                _element(
                    "pickup_frame_voice",
                    presence=PRESENCE_MISSING,
                    action=ACTION_OPERATOR,
                    rationale="No speakers yet — operator must confirm pickup voice when topology exists.",
                    evidence={},
                )
            )

    return elements


def enrich_from_artifacts(ctx: RunContext, elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Refresh moat / era strategies once content_brief (and related) exist."""
    by_id = {str(e.get("id")): dict(e) for e in elements if isinstance(e, dict)}
    profiles = merged_config().get("production_profiles") or {}
    tbiy_defaults = dict((profiles.get(TBIY_STYLE) or {}).get("adaptation_defaults") or {})
    profile_defaults = {**tbiy_defaults, **adaptation_defaults(ctx)}
    require_moat = bool(profile_defaults.get("require_moat", True))

    moat_text = ""
    era_tags: list[str] = []
    claim_count = 0
    if ctx.artifact_exists("understanding/content_brief.json"):
        brief = ctx.read_json("understanding/content_brief.json")
        if isinstance(brief, dict):
            raw = brief.get("strategic_moat_concept")
            if isinstance(raw, str) and raw.strip():
                moat_text = raw.strip()
            eras = brief.get("era_tags") or []
            if isinstance(eras, list):
                era_tags = [str(x) for x in eras if x]
            claims = brief.get("key_claims") or []
            if isinstance(claims, list):
                claim_count = len([c for c in claims if isinstance(c, dict)])

    # analysis_state narrative moat (profile gate)
    if not moat_text and ctx.artifact_exists("understanding/analysis_state.json"):
        state = ctx.read_json("understanding/analysis_state.json")
        if isinstance(state, dict):
            narrative = state.get("narrative") or {}
            if isinstance(narrative, dict):
                raw = narrative.get("strategic_moat_concept")
                if isinstance(raw, str) and raw.strip():
                    moat_text = raw.strip()

    if moat_text:
        by_id["strategic_moat"] = _element(
            "strategic_moat",
            presence=PRESENCE_PRESENT,
            action=ACTION_APPLY,
            rationale="Named strategic moat present — echo in Act IV / is_moat_chapter.",
            evidence={"strategic_moat_concept": moat_text[:200]},
        )
    elif claim_count > 0 and require_moat:
        by_id["strategic_moat"] = _element(
            "strategic_moat",
            presence=PRESENCE_WEAK,
            action=ACTION_SOFT,
            rationale="Claims exist but moat unset — soft-derive from strongest claim evidence; do not invent.",
            evidence={"claim_count": claim_count, "require_moat": True},
        )
    elif require_moat:
        by_id["strategic_moat"] = _element(
            "strategic_moat",
            presence=PRESENCE_MISSING,
            action=ACTION_SOFT,
            rationale="Moat still missing after brief — keep soft target; operator may set on Story Board.",
            evidence={"require_moat": True},
        )
    else:
        by_id["strategic_moat"] = _element(
            "strategic_moat",
            presence=PRESENCE_MISSING,
            action=ACTION_DEFER,
            rationale="No moat evidence and profile does not require one.",
            evidence={"require_moat": False},
        )

    if era_tags:
        by_id["era_texture"] = _element(
            "era_texture",
            presence=PRESENCE_PRESENT,
            action=ACTION_APPLY,
            rationale="Era tags on brief — preserve segment-grounded era texture.",
            evidence={"era_tag_count": len(era_tags)},
        )
    elif claim_count > 0:
        by_id.setdefault(
            "era_texture",
            _element(
                "era_texture",
                presence=PRESENCE_WEAK,
                action=ACTION_SOFT,
                rationale="Soft era texture only when transcript eras are explicit.",
                evidence={"claim_count": claim_count},
            ),
        )

    # Preserve order
    ordered = [by_id[eid] for eid in ELEMENT_IDS if eid in by_id]
    for eid, row in by_id.items():
        if eid not in ELEMENT_IDS:
            ordered.append(row)
    return ordered


def _modes_from_elements(elements: list[dict[str, Any]]) -> dict[str, str]:
    by_id = {str(e.get("id")): e for e in elements}
    five = by_id.get("five_act_scaffolding") or {}
    moat = by_id.get("strategic_moat") or {}
    bridges = [
        e
        for e in elements
        if e.get("action") == ACTION_VO_BRIDGE
        and e.get("id") in ("dual_voice_reactor", "reaction_texture", "act_bridge_capacity")
    ]

    five_action = str(five.get("action") or ACTION_SOFT)
    if five_action == ACTION_COLLAPSE:
        five_act_mode = "collapsed"
    elif five_action == ACTION_APPLY:
        five_act_mode = "full"
    else:
        five_act_mode = "soft"

    moat_action = str(moat.get("action") or ACTION_DEFER)
    if moat_action == ACTION_APPLY:
        moat_mode = "require"
    elif moat_action == ACTION_DEFER:
        moat_mode = "defer"
    else:
        moat_mode = "soft"

    if len(bridges) >= 2:
        vo_bridge_priority = "high"
    elif bridges:
        vo_bridge_priority = "normal"
    else:
        vo_bridge_priority = "low"

    return {
        "five_act_mode": five_act_mode,
        "moat_mode": moat_mode,
        "vo_bridge_priority": vo_bridge_priority,
    }


def _score(elements: list[dict[str, Any]]) -> dict[str, Any]:
    """Informational conformance score — not a documentary fallback trigger."""
    weights = {
        ACTION_APPLY: 1.0,
        ACTION_SOFT: 0.7,
        ACTION_VO_BRIDGE: 0.65,
        ACTION_COLLAPSE: 0.55,
        ACTION_DEFER: 0.35,
        ACTION_OPERATOR: 0.4,
    }
    if not elements:
        return {"ratio": 0.0, "applied": 0, "bridged": 0, "deferred": 0, "total": 0}
    total = len(elements)
    raw = sum(weights.get(str(e.get("action")), 0.3) for e in elements) / total
    return {
        "ratio": round(raw, 3),
        "applied": sum(1 for e in elements if e.get("action") == ACTION_APPLY),
        "bridged": sum(1 for e in elements if e.get("action") == ACTION_VO_BRIDGE),
        "soft": sum(1 for e in elements if e.get("action") == ACTION_SOFT),
        "collapsed": sum(1 for e in elements if e.get("action") == ACTION_COLLAPSE),
        "deferred": sum(1 for e in elements if e.get("action") == ACTION_DEFER),
        "operator_only": sum(1 for e in elements if e.get("action") == ACTION_OPERATOR),
        "total": total,
    }


def _summary_plain(topology_class: str, elements: list[dict[str, Any]], modes: dict[str, str]) -> str:
    moves = []
    for e in elements:
        action = str(e.get("action") or "")
        eid = str(e.get("id") or "")
        if action == ACTION_VO_BRIDGE:
            moves.append(f"VO-bridge {eid}")
        elif action == ACTION_COLLAPSE:
            moves.append(f"collapse {eid}")
        elif action == ACTION_SOFT:
            moves.append(f"soft {eid}")
    score = _score(elements)
    head = (
        f"TBIY conformance {int(score['ratio'] * 100)}% on {topology_class.replace('_', ' ')} "
        f"(acts={modes.get('five_act_mode')}, moat={modes.get('moat_mode')}, "
        f"VO bridges={modes.get('vo_bridge_priority')})."
    )
    if moves:
        return head + " Moves: " + "; ".join(moves[:5]) + ("…" if len(moves) > 5 else "") + "."
    return head + " Tape supports core TBIY moves with light soft bias."


def build_conformance_plan(
    *,
    topology_class: str,
    stats: list[dict[str, Any]],
    role_map: dict[str, Any] | None = None,
    pickup_id: str | None = None,
    topic_count: int = 0,
    ctx: RunContext | None = None,
) -> dict[str, Any]:
    defaults = adaptation_defaults(ctx) if ctx is not None else {}
    if not defaults:
        profiles = merged_config().get("production_profiles") or {}
        defaults = dict((profiles.get(TBIY_STYLE) or {}).get("adaptation_defaults") or {})
    elements = inventory_from_topology(
        topology_class=topology_class,
        stats=stats,
        role_map=role_map,
        pickup_id=pickup_id,
        topic_count=topic_count,
        defaults=defaults,
        ctx=ctx,
    )
    if ctx is not None:
        elements = enrich_from_artifacts(ctx, elements)
    modes = _modes_from_elements(elements)
    score = _score(elements)
    return {
        "version": 1,
        "production_style": TBIY_STYLE,
        "active": True,
        "topology_class": topology_class,
        "elements": elements,
        "modes": modes,
        "score": score,
        "summary_plain": _summary_plain(topology_class, elements, modes),
        "guidance": {
            "never_invent_guest_evidence": True,
            "never_fallback_to_documentary": True,
            "pickup_voice_least_spoken_default": True,
            "synthesize_audio": False,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def apply_conformance_to_adaptation(
    adaptation: dict[str, Any],
    conformance: dict[str, Any],
    *,
    base_ranking: dict[str, float] | None = None,
    base_sfx: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Merge conformance into flow_adaptation — tweak weights/density by moves."""
    out = dict(adaptation)
    out["tbiy_conformance"] = conformance
    modes = conformance.get("modes") if isinstance(conformance.get("modes"), dict) else {}
    elements = conformance.get("elements") if isinstance(conformance.get("elements"), list) else []
    by_id = {str(e.get("id")): e for e in elements if isinstance(e, dict)}

    ranking = dict(base_ranking or out.get("ranking_weights") or {})
    if by_id.get("reaction_texture", {}).get("action") == ACTION_VO_BRIDGE:
        ranking["reaction_opportunity"] = round(min(0.35, float(ranking.get("reaction_opportunity", 0.2)) + 0.08), 3)
    if by_id.get("five_act_scaffolding", {}).get("action") == ACTION_COLLAPSE:
        ranking["narrative_arc_fit"] = round(min(0.45, float(ranking.get("narrative_arc_fit", 0.3)) + 0.05), 3)
    if by_id.get("storyteller_dominance", {}).get("action") == ACTION_APPLY:
        ranking["claim_impact"] = round(min(0.4, float(ranking.get("claim_impact", 0.25)) + 0.05), 3)
    out["ranking_weights"] = ranking

    sfx = dict(base_sfx or out.get("sfx_density") or {})
    punct = by_id.get("punctuator_anchors", {})
    if punct.get("action") == ACTION_SOFT and modes.get("five_act_mode") == "collapsed":
        if "max_punctuators" in sfx:
            sfx["max_punctuators"] = max(1, int(sfx["max_punctuators"]) - 1)
        if "max_beds" in sfx:
            sfx["max_beds"] = max(1, int(sfx.get("max_beds", 1)) + 1)
    out["sfx_density"] = sfx

    # Prefer conformance summary when present (keeps operator-facing copy graduated)
    conf_summary = conformance.get("summary_plain")
    if isinstance(conf_summary, str) and conf_summary.strip():
        pickup = out.get("pickup_eligible_speaker_id")
        pickup_note = f" Gap pickup voice: {pickup}." if pickup else ""
        out["summary_plain"] = conf_summary.strip() + pickup_note

    out["five_act_mode"] = modes.get("five_act_mode", "soft")
    out["moat_mode"] = modes.get("moat_mode", "soft")
    out["vo_bridge_priority"] = modes.get("vo_bridge_priority", "normal")
    return out


def compact_conformance_for_volley(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(plan, dict) or not plan.get("active"):
        return None
    elements = plan.get("elements") or []
    compact_els = []
    for e in elements:
        if not isinstance(e, dict):
            continue
        compact_els.append(
            {
                "id": e.get("id"),
                "presence": e.get("presence"),
                "action": e.get("action"),
                "rationale": e.get("rationale"),
            }
        )
    return {
        "modes": plan.get("modes"),
        "score": plan.get("score"),
        "summary_plain": plan.get("summary_plain"),
        "elements": compact_els,
        "guidance": plan.get("guidance"),
    }


def load_conformance(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists("understanding/flow_adaptation.json"):
        return None
    adapt = ctx.read_json("understanding/flow_adaptation.json")
    if not isinstance(adapt, dict):
        return None
    plan = adapt.get("tbiy_conformance")
    return plan if isinstance(plan, dict) else None


def refresh_conformance(ctx: RunContext) -> dict[str, Any] | None:
    """Recompute conformance from topology + later artifacts; persist on flow_adaptation."""
    if not is_tbiy(ctx):
        return None
    if not ctx.artifact_exists("understanding/source_topology.json"):
        return None
    topo = ctx.read_json("understanding/source_topology.json")
    if not isinstance(topo, dict):
        return None
    adapt: dict[str, Any] = {}
    if ctx.artifact_exists("understanding/flow_adaptation.json"):
        prev = ctx.read_json("understanding/flow_adaptation.json")
        if isinstance(prev, dict):
            adapt = dict(prev)

    stats = list(topo.get("speaker_stats") or [])
    topic_count = 0
    if ctx.artifact_exists("understanding/speakers.json"):
        speakers_doc = ctx.read_json("understanding/speakers.json")
        if isinstance(speakers_doc, dict):
            topic_count = len(speakers_doc.get("topics") or [])
    if ctx.artifact_exists("understanding/content_brief.json"):
        brief = ctx.read_json("understanding/content_brief.json")
        if isinstance(brief, dict):
            topics = brief.get("topics") or []
            if isinstance(topics, list) and topics:
                topic_count = max(topic_count, len(topics))

    plan = build_conformance_plan(
        topology_class=str(topo.get("topology_class") or adapt.get("topology_class") or "one_on_one_asymmetric"),
        stats=stats if isinstance(stats, list) else [],
        role_map=topo.get("tbiy_role_map") if isinstance(topo.get("tbiy_role_map"), dict) else None,
        pickup_id=str(
            adapt.get("pickup_eligible_speaker_id")
            or topo.get("pickup_eligible_speaker_id")
            or ""
        )
        or None,
        topic_count=topic_count,
        ctx=ctx,
    )
    adapt = apply_conformance_to_adaptation(
        adapt,
        plan,
        base_ranking=adapt.get("ranking_weights") if isinstance(adapt.get("ranking_weights"), dict) else None,
        base_sfx=adapt.get("sfx_density") if isinstance(adapt.get("sfx_density"), dict) else None,
    )
    if not adapt.get("topology_class"):
        adapt["topology_class"] = plan.get("topology_class")
    if not adapt.get("production_style"):
        adapt["production_style"] = TBIY_STYLE
    # Mirror to final path — may run during delivery_brief_build staging without trapping
    # flow_adaptation under that stage's .pending_writes/.
    from interview_mux.write_staging import write_mirrored_json

    write_mirrored_json(ctx, "understanding/flow_adaptation.json", adapt)
    return plan


def attach_conformance_to_payload(ctx: RunContext, payload: dict[str, Any]) -> dict[str, Any]:
    plan = load_conformance(ctx)
    compact = compact_conformance_for_volley(plan)
    if compact:
        payload = dict(payload)
        payload["tbiy_conformance"] = compact
    return payload


def five_act_mode(ctx: RunContext) -> str:
    plan = load_conformance(ctx)
    if isinstance(plan, dict):
        modes = plan.get("modes") or {}
        if isinstance(modes, dict) and modes.get("five_act_mode"):
            return str(modes["five_act_mode"])
    adapt = None
    if ctx.artifact_exists("understanding/flow_adaptation.json"):
        adapt = ctx.read_json("understanding/flow_adaptation.json")
    if isinstance(adapt, dict) and adapt.get("five_act_mode"):
        return str(adapt["five_act_mode"])
    return "soft"


def moat_mode(ctx: RunContext) -> str:
    plan = load_conformance(ctx)
    if isinstance(plan, dict):
        modes = plan.get("modes") or {}
        if isinstance(modes, dict) and modes.get("moat_mode"):
            return str(modes["moat_mode"])
    adapt = None
    if ctx.artifact_exists("understanding/flow_adaptation.json"):
        adapt = ctx.read_json("understanding/flow_adaptation.json")
    if isinstance(adapt, dict) and adapt.get("moat_mode"):
        return str(adapt["moat_mode"])
    return "soft"


__all__ = [
    "ACTION_APPLY",
    "ACTION_COLLAPSE",
    "ACTION_DEFER",
    "ACTION_OPERATOR",
    "ACTION_SOFT",
    "ACTION_VO_BRIDGE",
    "ELEMENT_IDS",
    "apply_conformance_to_adaptation",
    "attach_conformance_to_payload",
    "build_conformance_plan",
    "compact_conformance_for_volley",
    "enrich_from_artifacts",
    "five_act_mode",
    "inventory_from_topology",
    "load_conformance",
    "moat_mode",
    "refresh_conformance",
]
