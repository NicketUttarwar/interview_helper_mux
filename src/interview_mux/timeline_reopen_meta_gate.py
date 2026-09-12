"""LLM + deterministic meta-gates for timeline reopen and seat rewrite (Pillars B/C).

Fail-open on LLM error = refuse reopen (proceed; imperfect OK).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext

GATE_LOG_REL = "mastering/timeline_reopen_gate.jsonl"
SEAT_GATE_LOG_REL = "mastering/seat_rewrite_gate.jsonl"

# Intents for decide_timeline_reopen
INTENT_DELIGHT = "delight_remutate"
INTENT_NARRATIVE = "edl_narrative_remutate"
INTENT_JUNCTION = "junction_remaster"
INTENT_OPTIMIZER = "optimizer_remaster"
INTENT_PUB_HARD = "publishability_hard"
INTENT_PUB_SOFT_MIX = "publishability_soft_mix"
INTENT_FUSE = "fuse_junction_heal"
INTENT_MIX_REWALK = "mix_rewalk"
INTENT_EDL_EDGE = "edl_edge_writeback"
INTENT_HITCH_RESTAGE = "hitch_listen_restage_late"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cfg_float(key: str, default: float) -> float:
    try:
        from interview_mux.config import merged_config

        cfg = merged_config() or {}
        spine = (cfg.get("thrash_spine") or {}) if isinstance(cfg, dict) else {}
        mg = (spine.get("meta_gate") or {}) if isinstance(spine, dict) else {}
        if key in mg:
            return float(mg[key])
    except Exception:
        pass
    return default


def _append_jsonl(ctx: RunContext, rel: str, row: dict[str, Any]) -> None:
    path = ctx.run_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _decision_id(intent: str) -> str:
    return hashlib.sha256(f"{intent}:{uuid.uuid4().hex}".encode()).hexdigest()[:12]


def _deterministic_prefilter(
    ctx: RunContext,
    *,
    intent: str,
    failed_dims: list[str] | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return allow decision if must-fix; else None to continue to LLM/heuristics."""
    detail = detail or {}
    dims = [str(d) for d in (failed_dims or [])]
    intent_s = str(intent or "")

    # Cosmetic mid_word on NLE-locked ends — never allow (before any catastrophe allow).
    if intent_s == INTENT_EDL_EDGE and detail.get("cosmetic_mid_word"):
        return {
            "allow": False,
            "expected_gain": 0.0,
            "refuse_reason": "cosmetic_mid_word_nle_locked",
            "prefilter": "detect_only",
            "axes_allowed": [],
        }

    # G1 red / missing seated WAV
    try:
        from interview_mux.delivery_guardrails import _g1_open

        if _g1_open(ctx):
            return {
                "allow": True,
                "expected_gain": 1.0,
                "refuse_reason": "",
                "prefilter": "g1_open",
                "axes_allowed": ["cut", "story"],
            }
    except Exception:
        pass

    # Critical incomplete cuts
    kinds = detail.get("incomplete_kinds") or detail.get("critical_kinds") or []
    if isinstance(kinds, (list, tuple)):
        kind_s = " ".join(str(k) for k in kinds).lower()
        if any(k in kind_s for k in ("incomplete_clause", "on_a_roll", "chapter_bleed")):
            return {
                "allow": True,
                "expected_gain": 0.9,
                "refuse_reason": "",
                "prefilter": "critical_incomplete_cut",
                "axes_allowed": ["cut"],
            }

    # Catastrophic delight floors
    overall = detail.get("overall")
    try:
        if overall is not None and float(overall) < 0.70:
            return {
                "allow": True,
                "expected_gain": 0.85,
                "refuse_reason": "",
                "prefilter": "catastrophic_overall",
                "axes_allowed": dims or ["story", "cut"],
            }
    except Exception:
        pass
    for dim in ("cut_integrity", "conversation_fit", "story_followability"):
        if dim in dims:
            score = detail.get("dim_scores", {}).get(dim) if isinstance(detail.get("dim_scores"), dict) else None
            try:
                if score is not None and float(score) < 0.60:
                    return {
                        "allow": True,
                        "expected_gain": 0.8,
                        "refuse_reason": "",
                        "prefilter": f"catastrophic_{dim}",
                        "axes_allowed": [dim.split("_")[0] if "_" in dim else dim],
                    }
            except Exception:
                pass

    return None


def _heuristic_gain(
    *,
    intent: str,
    failed_dims: list[str] | None,
    detail: dict[str, Any] | None,
) -> float:
    """When LLM unavailable, estimate gain (conservative)."""
    detail = detail or {}
    dims = failed_dims or []
    overall = detail.get("overall")
    try:
        if overall is not None:
            gap = max(0.0, 0.90 - float(overall))
            return min(1.0, gap / 0.20)
    except Exception:
        pass
    if intent in {INTENT_JUNCTION, INTENT_PUB_HARD, INTENT_FUSE}:
        return 0.4
    if intent in {INTENT_DELIGHT, INTENT_NARRATIVE} and dims:
        return 0.35
    if intent in {INTENT_PUB_SOFT_MIX, INTENT_MIX_REWALK, INTENT_OPTIMIZER}:
        return 0.25
    return 0.2


def _repo_prompt_exists(prompt_rel: str) -> bool:
    try:
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        return (root / prompt_rel).is_file()
    except Exception:
        return False


def _parse_gate_envelope(envelope: Any) -> dict[str, Any] | None:
    """Normalize llm_runner / legacy envelopes to a decision dict with ``allow``."""
    if not isinstance(envelope, dict):
        return None
    candidates: list[Any] = [
        envelope.get("artifacts"),
        envelope.get("parsed"),
        envelope.get("json"),
        envelope,
    ]
    parsed: dict[str, Any] | None = None
    for cand in candidates:
        if isinstance(cand, dict) and "allow" in cand:
            parsed = cand
            break
        if isinstance(cand, dict):
            nested = cand.get("decision") or cand.get("gate")
            if isinstance(nested, dict) and "allow" in nested:
                parsed = nested
                break
    if parsed is None:
        for key in ("text", "content", "raw"):
            raw = envelope.get(key)
            if not isinstance(raw, str) or not raw.strip():
                continue
            try:
                start = raw.find("{")
                end = raw.rfind("}")
                if start >= 0 and end > start:
                    body = json.loads(raw[start : end + 1])
                    if isinstance(body, dict) and "allow" in body:
                        parsed = body
                        break
            except Exception:
                continue
    if parsed is None:
        return None
    # Require boolean allow; malformed LLM payloads fall through to refuse/heuristic.
    if not isinstance(parsed.get("allow"), bool):
        return None
    return parsed


def _invoke_prompt_envelope(*args: Any, **kwargs: Any) -> Any:
    """Indirection so tests can mock without fighting local imports."""
    from interview_mux.stages.llm_runner import run_prompt_envelope

    return run_prompt_envelope(*args, **kwargs)


def _try_llm_gain(
    ctx: RunContext,
    *,
    intent: str,
    failed_dims: list[str],
    detail: dict[str, Any],
) -> dict[str, Any] | None:
    """Structured LLM call via llm_runner; return None on failure (caller refuses)."""
    prompt_rel = "docs/prompts/timeline_reopen_meta_gate.md"
    if not _repo_prompt_exists(prompt_rel):
        return None
    packet = {
        "intent": intent,
        "failed_dims": failed_dims[:12],
        "detail": {
            k: detail.get(k)
            for k in (
                "overall",
                "dim_scores",
                "incomplete_kinds",
                "from_stage",
                "proposed_cost_stages",
            )
            if k in detail
        },
        "instruction": (
            "Decide if reopening the timeline will significantly improve final "
            "master.wav listener quality. Return allow true only for meaningful gain."
        ),
    }
    try:
        envelope = _invoke_prompt_envelope(
            "timeline_reopen_meta_gate",
            prompt_rel,
            json.dumps(packet, ensure_ascii=False),
            ctx=ctx,
            include_preamble=False,
            task_kind="advisory",
            response_format={"type": "json_object"},
            record_stage_key="timeline_reopen_meta_gate",
        )
        return _parse_gate_envelope(envelope)
    except Exception:
        return None

def decide_timeline_reopen(
    ctx: RunContext,
    *,
    intent: str,
    failed_dims: list[str] | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Single entry for Pillar C reopen decisions.

    Never raises — on internal errors returns ``allow=False`` (fail-closed refuse)
    so callers cannot ``except: pass`` into an ungated remutate.
    """
    intent_s = str(intent or "").strip() or "unknown"
    dims = [str(d) for d in (failed_dims or [])]
    detail_d = dict(detail or {})
    did = _decision_id(intent_s)
    min_gain = _cfg_float("min_expected_gain", 0.15)
    try:
        pre = _deterministic_prefilter(
            ctx, intent=intent_s, failed_dims=dims, detail=detail_d
        )
        if pre is not None:
            row = {
                "decision_id": did,
                "intent": intent_s,
                "at": _utc_now(),
                "allow": bool(pre.get("allow")),
                "expected_gain": float(pre.get("expected_gain") or 0.0),
                "min_significant": min_gain,
                "refuse_reason": str(pre.get("refuse_reason") or ""),
                "axes_allowed": list(pre.get("axes_allowed") or []),
                "path": "prefilter",
                "prefilter": pre.get("prefilter"),
            }
            _persist(ctx, row)
            return row

        llm = _try_llm_gain(ctx, intent=intent_s, failed_dims=dims, detail=detail_d)
        if isinstance(llm, dict) and "allow" in llm:
            gain = float(llm.get("expected_gain") or llm.get("gain") or 0.0)
            allow = bool(llm.get("allow")) and gain >= min_gain
            row = {
                "decision_id": did,
                "intent": intent_s,
                "at": _utc_now(),
                "allow": allow,
                "expected_gain": gain,
                "min_significant": min_gain,
                "refuse_reason": ""
                if allow
                else str(llm.get("refuse_reason") or "llm_low_gain"),
                "axes_allowed": list(llm.get("axes_allowed") or dims),
                "path": "llm",
            }
            _persist(ctx, row)
            return row

        # Heuristic when LLM missing — conservative (refuse unless clearly above bar)
        gain = _heuristic_gain(intent=intent_s, failed_dims=dims, detail=detail_d)
        allow = gain >= max(min_gain * 2.0, 0.45)
        row = {
            "decision_id": did,
            "intent": intent_s,
            "at": _utc_now(),
            "allow": allow,
            "expected_gain": gain,
            "min_significant": min_gain,
            "refuse_reason": "" if allow else "heuristic_or_llm_unavailable_refuse",
            "axes_allowed": dims if allow else [],
            "path": "heuristic_fail_open_refuse" if not allow else "heuristic_allow",
        }
        _persist(ctx, row)
        return row
    except Exception as exc:
        row = {
            "decision_id": did,
            "intent": intent_s,
            "at": _utc_now(),
            "allow": False,
            "expected_gain": 0.0,
            "min_significant": min_gain,
            "refuse_reason": f"decide_error_refuse:{type(exc).__name__}",
            "axes_allowed": [],
            "path": "exception_fail_closed_refuse",
        }
        try:
            _persist(ctx, row)
        except Exception:
            pass
        return row


def refuse_timeline_reopen(
    *,
    intent: str = "",
    reason: str = "caller_fail_closed",
) -> dict[str, Any]:
    """Canonical refuse payload for caller except-handlers (never allow on error)."""
    return {
        "decision_id": _decision_id(str(intent or "unknown")),
        "intent": str(intent or "").strip() or "unknown",
        "at": _utc_now(),
        "allow": False,
        "expected_gain": 0.0,
        "min_significant": _cfg_float("min_expected_gain", 0.15),
        "refuse_reason": str(reason or "caller_fail_closed")[:160],
        "axes_allowed": [],
        "path": "caller_fail_closed_refuse",
    }


def _persist(ctx: RunContext, row: dict[str, Any]) -> None:
    try:
        _append_jsonl(ctx, GATE_LOG_REL, row)
    except Exception:
        pass
    try:
        from interview_mux.execution_status import note_reopen_gate_decision

        note_reopen_gate_decision(ctx, row)
    except Exception:
        pass


def decide_seat_rewrite(
    ctx: RunContext,
    *,
    proposed_delta: dict[str, Any],
    reason: str = "",
    symptoms: list[str] | None = None,
) -> dict[str, Any]:
    """Pillar B seat rewrite meta-gate."""
    min_opp = _cfg_float("min_opportunity", 0.65)
    did = _decision_id("seat_rewrite")
    symptoms = list(symptoms or [])
    # Deterministic: catastrophe
    reason_l = str(reason or "").lower()
    if any(x in reason_l for x in ("g1_red", "missing_seated_wav", "operator")):
        row = {
            "decision_id": did,
            "intent": "seat_rewrite",
            "at": _utc_now(),
            "allow": True,
            "opportunity_score": 1.0,
            "expected_listener_gain": 0.9,
            "rewrite_ops": list(proposed_delta.get("ops") or []),
            "refuse_reason": "",
            "path": "catastrophe",
        }
        _append_seat(ctx, row)
        return row

    # Score opportunity from symptoms
    score = 0.3
    if any("vo_wall" in s for s in symptoms):
        score = max(score, 0.7)
    if any("omit_collateral" in s for s in symptoms):
        score = max(score, 0.75)
    if any("orientation" in s for s in symptoms):
        score = max(score, 0.8)
    if proposed_delta.get("ops"):
        score = max(score, 0.55)
    # Packaging / CTA hygiene must be able to rewrite order under soft freeze —
    # otherwise stamp is written for the sanitized order, freeze preserves the
    # prior order, and selection_sanitize_stamp_stale (or layup CTA residue)
    # spins forever.
    src = str(proposed_delta.get("source") or "").lower()
    packaging_tokens = (
        "artifact_sanitize.selection",
        "media_ip_cta",
        "heal_on_air_cta",
        "cta_omit",
        "cta_prune",
    )
    if any(t in src or t in reason_l for t in packaging_tokens):
        score = max(score, 0.7)

    # Optional LLM — fail refuse
    llm = None
    try:
        llm = _try_llm_seat(ctx, proposed_delta=proposed_delta, reason=reason, symptoms=symptoms)
    except Exception:
        llm = None
    if isinstance(llm, dict) and "allow" in llm:
        opp = float(llm.get("opportunity_score") or llm.get("opportunity") or 0.0)
        allow = bool(llm.get("allow")) and opp >= min_opp
        row = {
            "decision_id": did,
            "intent": "seat_rewrite",
            "at": _utc_now(),
            "allow": allow,
            "opportunity_score": opp,
            "expected_listener_gain": float(llm.get("expected_listener_gain") or opp),
            "rewrite_ops": list(llm.get("rewrite_ops") or proposed_delta.get("ops") or []),
            "refuse_reason": "" if allow else str(llm.get("refuse_reason") or "llm_low_opportunity"),
            "path": "llm",
        }
        _append_seat(ctx, row)
        return row

    allow = score >= min_opp
    row = {
        "decision_id": did,
        "intent": "seat_rewrite",
        "at": _utc_now(),
        "allow": allow,
        "opportunity_score": score,
        "expected_listener_gain": score,
        "rewrite_ops": list(proposed_delta.get("ops") or []) if allow else [],
        "refuse_reason": "" if allow else "opportunity_below_threshold",
        "path": "heuristic",
    }
    _append_seat(ctx, row)
    return row


def _try_llm_seat(
    ctx: RunContext,
    *,
    proposed_delta: dict[str, Any],
    reason: str,
    symptoms: list[str],
) -> dict[str, Any] | None:
    """Structured LLM seat rewrite judge via llm_runner; None → heuristic refuse path."""
    prompt_rel = "docs/prompts/seat_rewrite_meta_gate.md"
    if not _repo_prompt_exists(prompt_rel):
        return None
    packet = {
        "reason": reason,
        "symptoms": symptoms[:12],
        "proposed_delta": proposed_delta,
        "instruction": (
            "Decide if this seat/omit rewrite is high opportunity for the listener. "
            "Refuse thrashy or low-value changes. Return JSON with allow + opportunity_score."
        ),
    }
    try:
        envelope = _invoke_prompt_envelope(
            "seat_rewrite_meta_gate",
            prompt_rel,
            json.dumps(packet, ensure_ascii=False),
            ctx=ctx,
            include_preamble=False,
            task_kind="advisory",
            response_format={"type": "json_object"},
            record_stage_key="seat_rewrite_meta_gate",
        )
        return _parse_gate_envelope(envelope)
    except Exception:
        return None


def _append_seat(ctx: RunContext, row: dict[str, Any]) -> None:
    try:
        _append_jsonl(ctx, SEAT_GATE_LOG_REL, row)
    except Exception:
        pass
    try:
        from interview_mux.execution_status import note_reopen_gate_decision

        note_reopen_gate_decision(ctx, row)
    except Exception:
        pass
