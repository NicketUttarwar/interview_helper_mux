"""Gate categories. Homunculus is controller on 0.1.0; G0 still blocks."""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

CATEGORIES = (
    "transcript_integrity",
    "framing_consent",
    "vo_pickup",
    "source_preclean",
    "nle_optional",
    "listen_borderline",
    "optimizer_authority",
    "quality_ship",
    "publish_package",
    "prompt_promotion",
)

DECISIONS_REL = "mastering/homunculus/gate_decisions.json"


def recommended_framing_action(ctx: RunContext) -> str:
    """Whether framing is on. Clone speaker stays least-spoken host."""
    try:
        from interview_mux.homunculus.source_card import read_source_card

        card = read_source_card(ctx) or {}
        circ = [str(x).lower() for x in (card.get("circumstances") or [])]
        if card.get("framing_posture") == "sparse_omit" or "monologue" in circ:
            return "skip"
    except Exception:
        pass
    return "present_operator"


def category_status(ctx: RunContext) -> dict[str, Any]:
    from interview_mux.gates import check_g1_vo, check_transcript_review_pending

    g0_open = False
    try:
        g0_open = bool(check_transcript_review_pending(ctx))
    except Exception:
        g0_open = False
    g1: dict[str, Any] = {}
    try:
        raw = check_g1_vo(ctx)
        g1 = raw if isinstance(raw, dict) else {"pending": bool(raw)}
    except Exception:
        g1 = {}
    decisions = {}
    if ctx.artifact_exists(DECISIONS_REL):
        raw_d = ctx.read_json(DECISIONS_REL)
        if isinstance(raw_d, dict):
            decisions = raw_d.get("decisions") or raw_d
    framing_open = False
    try:
        from interview_mux.gap_vo_gates import check_gap_framing_decision_pending

        framing_open = bool(check_gap_framing_decision_pending(ctx))
    except Exception:
        framing_open = False
    cats = {
        "transcript_integrity": {
            "open": g0_open,
            "blocks_analysis": g0_open,
            "decision": (decisions.get("transcript_integrity") or {}).get("action")
            if isinstance(decisions.get("transcript_integrity"), dict)
            else decisions.get("transcript_integrity"),
        },
        "framing_consent": {
            "open": framing_open,
            "recommended": recommended_framing_action(ctx),
            "clone_policy": "least_spoken_host",
        },
        "vo_pickup": {"open": bool(g1.get("pending") if isinstance(g1, dict) else g1)},
        "source_preclean": {"open": False, "never_auto": True},
        "nle_optional": {"open": False},
        "listen_borderline": {"open": False},
        "optimizer_authority": {"open": False},
        "quality_ship": {"open": ctx.artifact_exists("mastering/homunculus/limit_exhausted.json")},
        "publish_package": {"open": ctx.artifact_exists("master/master.wav")},
        "prompt_promotion": {"open": False},
    }
    return {"categories": list(CATEGORIES), **cats, "decisions": decisions}


def set_gate_decision(ctx: RunContext, category: str, action: str) -> dict[str, Any]:
    """Homunculus controller: open / auto_resolve / present_operator / skip."""
    if category not in CATEGORIES:
        raise ValueError(f"unknown gate category {category}")
    if category == "transcript_integrity" and action in {"skip", "auto_resolve"}:
        raise RuntimeError("transcript_integrity cannot skip or auto-resolve word-level STT")
    if category == "framing_consent" and action == "auto_resolve":
        if recommended_framing_action(ctx) == "skip":
            raise RuntimeError(
                "framing_consent cannot auto-resolve dense gap VO when posture is sparse_omit"
            )
    doc = {"decisions": {}}
    if ctx.artifact_exists(DECISIONS_REL):
        raw = ctx.read_json(DECISIONS_REL)
        if isinstance(raw, dict):
            doc = raw
            doc.setdefault("decisions", {})
    doc["decisions"][category] = {"action": action}
    ctx.write_json(DECISIONS_REL, doc)
    from interview_mux.homunculus.ledger import append_ledger

    append_ledger(
        ctx,
        {"kind": "gate", "identity": f"gate:{category}", "action": action},
    )
    return doc
