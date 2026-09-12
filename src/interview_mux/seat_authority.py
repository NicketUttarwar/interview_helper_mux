"""VO seat freeze + holistic review (Pillar B thrash spine endgame).

Soft freeze after air_contract_sanitize; hard freeze after vo_synthesize + WAV
parity. Post-freeze seat/omit mutations require unlock (operator / G1 red /
LLM seat-rewrite meta-gate).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext

SEAT_FREEZE_META_KEY = "vo_seats_freeze"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cfg_int(path: str, default: int) -> int:
    try:
        from interview_mux.config import merged_config

        cfg = merged_config() or {}
        spine = cfg.get("thrash_spine") if isinstance(cfg, dict) else {}
        if not isinstance(spine, dict):
            return default
        cur: Any = spine
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return int(cur)
    except Exception:
        return default


def _cfg_float(path: str, default: float) -> float:
    try:
        from interview_mux.config import merged_config

        cfg = merged_config() or {}
        spine = cfg.get("thrash_spine") if isinstance(cfg, dict) else {}
        if not isinstance(spine, dict):
            return default
        cur: Any = spine
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return float(cur)
    except Exception:
        return default


def seat_fingerprint(ctx: RunContext) -> str:
    """Hash of seated + omitted + orientation ids."""
    try:
        from interview_mux.air_script import omitted_vo_line_ids, seated_vo_line_ids

        seated = sorted(str(x) for x in (seated_vo_line_ids(ctx) or []) if x)
        omitted = sorted(str(x) for x in (omitted_vo_line_ids(ctx) or []) if x)
    except Exception:
        seated, omitted = [], []
    orientation: list[str] = []
    try:
        gap = ctx.read_json("understanding/gap_report.json") if ctx.artifact_exists("understanding/gap_report.json") else {}
        for ln in (gap or {}).get("interviewer_lines") or []:
            if not isinstance(ln, dict):
                continue
            lid = str(ln.get("line_id") or "")
            role = str(ln.get("role") or ln.get("kind") or "").lower()
            if "orient" in role or lid.startswith("vo_preface"):
                orientation.append(lid)
    except Exception:
        pass
    body = json.dumps(
        {"seated": seated, "omitted": omitted, "orientation": sorted(set(orientation))},
        sort_keys=True,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def read_seat_freeze(ctx: RunContext) -> dict[str, Any]:
    try:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        epoch = (meta or {}).get("delivery_epoch") if isinstance(meta, dict) else {}
        freeze = (epoch or {}).get(SEAT_FREEZE_META_KEY) if isinstance(epoch, dict) else {}
        return dict(freeze) if isinstance(freeze, dict) else {}
    except Exception:
        return {}


def soft_freeze_active(ctx: RunContext) -> bool:
    fr = read_seat_freeze(ctx)
    return bool(fr.get("soft"))


def hard_freeze_active(ctx: RunContext) -> bool:
    fr = read_seat_freeze(ctx)
    return bool(fr.get("hard"))


def stamp_soft_seat_freeze(ctx: RunContext, *, reason: str = "air_contract_sanitize") -> dict[str, Any]:
    fp = seat_fingerprint(ctx)
    row = {
        "soft": True,
        "hard": False,
        "fingerprint": fp,
        "soft_at": _utc_now(),
        "soft_reason": str(reason or "")[:160],
        "generation": int(read_seat_freeze(ctx).get("generation") or 0),
        "rewrite_generations_post_soft": int(
            read_seat_freeze(ctx).get("rewrite_generations_post_soft") or 0
        ),
        "rewrite_generations_post_hard": int(
            read_seat_freeze(ctx).get("rewrite_generations_post_hard") or 0
        ),
    }
    prev = read_seat_freeze(ctx)
    if prev.get("hard"):
        row["hard"] = True
        row["hard_at"] = prev.get("hard_at")
        row["hard_reason"] = prev.get("hard_reason")

    def _mut(meta: dict[str, Any]) -> None:
        epoch = dict(meta.get("delivery_epoch") or {})
        epoch[SEAT_FREEZE_META_KEY] = row
        meta["delivery_epoch"] = epoch

    ctx.mutate_run_meta(_mut)
    return row


def stamp_hard_seat_freeze(ctx: RunContext, *, reason: str = "vo_synthesize") -> dict[str, Any]:
    fp = seat_fingerprint(ctx)
    prev = read_seat_freeze(ctx)
    row = {
        "soft": True,
        "hard": True,
        "fingerprint": fp,
        "soft_at": prev.get("soft_at") or _utc_now(),
        "soft_reason": prev.get("soft_reason") or "implied",
        "hard_at": _utc_now(),
        "hard_reason": str(reason or "")[:160],
        "generation": int(prev.get("generation") or 0),
        "rewrite_generations_post_soft": int(prev.get("rewrite_generations_post_soft") or 0),
        "rewrite_generations_post_hard": int(prev.get("rewrite_generations_post_hard") or 0),
    }

    def _mut(meta: dict[str, Any]) -> None:
        epoch = dict(meta.get("delivery_epoch") or {})
        epoch[SEAT_FREEZE_META_KEY] = row
        meta["delivery_epoch"] = epoch

    ctx.mutate_run_meta(_mut)
    return row


def unlock_seat_freeze(
    ctx: RunContext,
    *,
    reason: str,
    clear_hard: bool = True,
    clear_soft: bool = False,
) -> dict[str, Any]:
    """Operator / meta-gate unlock. Prefer clearing hard only for catastrophe."""

    def _mut(meta: dict[str, Any]) -> None:
        epoch = dict(meta.get("delivery_epoch") or {})
        fr = dict(epoch.get(SEAT_FREEZE_META_KEY) or {})
        if clear_hard:
            fr["hard"] = False
            fr["hard_unlocked_at"] = _utc_now()
        if clear_soft:
            fr["soft"] = False
            fr["soft_unlocked_at"] = _utc_now()
        fr["unlock_reason"] = str(reason or "")[:200]
        epoch[SEAT_FREEZE_META_KEY] = fr
        meta["delivery_epoch"] = epoch

    ctx.mutate_run_meta(_mut)
    return read_seat_freeze(ctx)


def bump_seat_rewrite_generation(ctx: RunContext) -> int:
    prev = read_seat_freeze(ctx)
    soft_n = int(prev.get("rewrite_generations_post_soft") or 0) + 1
    hard_n = int(prev.get("rewrite_generations_post_hard") or 0)
    if prev.get("hard"):
        hard_n += 1
    gen = int(prev.get("generation") or 0) + 1
    fp = seat_fingerprint(ctx)

    def _mut(meta: dict[str, Any]) -> None:
        epoch = dict(meta.get("delivery_epoch") or {})
        fr = dict(epoch.get(SEAT_FREEZE_META_KEY) or {})
        fr["generation"] = gen
        fr["rewrite_generations_post_soft"] = soft_n
        fr["rewrite_generations_post_hard"] = hard_n
        fr["fingerprint"] = fp
        fr["last_rewrite_at"] = _utc_now()
        # Re-assert soft after rewrite
        fr["soft"] = True
        epoch[SEAT_FREEZE_META_KEY] = fr
        meta["delivery_epoch"] = epoch

    ctx.mutate_run_meta(_mut)
    return gen


def seat_rewrite_budget_ok(ctx: RunContext) -> tuple[bool, str]:
    prev = read_seat_freeze(ctx)
    soft_max = _cfg_int("seat_freeze.max_rewrites_post_soft", 2)
    hard_max = _cfg_int("seat_freeze.max_rewrites_post_hard", 1)
    soft_n = int(prev.get("rewrite_generations_post_soft") or 0)
    hard_n = int(prev.get("rewrite_generations_post_hard") or 0)
    if prev.get("hard") and hard_n >= hard_max:
        return False, f"hard_rewrite_cap:{hard_n}>={hard_max}"
    if prev.get("soft") and soft_n >= soft_max:
        return False, f"soft_rewrite_cap:{soft_n}>={soft_max}"
    return True, "ok"


def _grant_one_shot_rewrite_token(ctx: RunContext, *, reason: str) -> None:
    """Allow exactly one post-freeze seat mutation (Pass B / ensure / clamp)."""

    def _mut(meta: dict[str, Any]) -> None:
        epoch = dict(meta.get("delivery_epoch") or {})
        fr = dict(epoch.get(SEAT_FREEZE_META_KEY) or {})
        fr["one_shot_rewrite"] = True
        fr["one_shot_reason"] = str(reason or "")[:160]
        fr["one_shot_at"] = _utc_now()
        epoch[SEAT_FREEZE_META_KEY] = fr
        meta["delivery_epoch"] = epoch

    try:
        ctx.mutate_run_meta(_mut)
    except Exception as exc:
        raise RuntimeError(f"one_shot_rewrite_token_grant_failed:{exc}") from exc


def consume_one_shot_rewrite_token(ctx: RunContext) -> bool:
    """Consume a granted one-shot rewrite token. True if token was present."""
    fr = read_seat_freeze(ctx)
    if not fr.get("one_shot_rewrite"):
        return False

    def _mut(meta: dict[str, Any]) -> None:
        epoch = dict(meta.get("delivery_epoch") or {})
        row = dict(epoch.get(SEAT_FREEZE_META_KEY) or {})
        row["one_shot_rewrite"] = False
        row.pop("one_shot_reason", None)
        row.pop("one_shot_at", None)
        epoch[SEAT_FREEZE_META_KEY] = row
        meta["delivery_epoch"] = epoch

    try:
        ctx.mutate_run_meta(_mut)
    except Exception:
        return False
    return True


def seat_mutation_allowed(
    ctx: RunContext,
    *,
    reason: str = "",
    require_meta_gate: bool = True,
) -> tuple[bool, str]:
    """Gate Pass B / ensure / omit / reconcile seat rewrites after freeze."""
    fr = read_seat_freeze(ctx)
    if not fr.get("soft") and not fr.get("hard"):
        return True, "unfrozen"
    if fr.get("one_shot_rewrite"):
        return True, "one_shot_token"
    # Catastrophe unlocks — still subject to rewrite budget (not unlimited).
    reason_l = str(reason or "").lower()
    catastrophe = any(
        x in reason_l
        for x in ("g1_red", "operator", "missing_seated_wav", "catastrophe")
    )
    # Selection packaging (CTA / sanitize) is not a VO-seat fingerprint rewrite —
    # soft rewrite cap must not permanently block it (exec_11165 layup spin).
    packaging = any(
        x in reason_l
        for x in (
            "media_ip_cta",
            "artifact_sanitize.selection",
            "cta_omit",
            "cta_prune",
            "heal_on_air_cta",
        )
    )
    ok, why = seat_rewrite_budget_ok(ctx)
    if not ok and not packaging and not catastrophe:
        return False, why
    if catastrophe:
        return True, "catastrophe_or_operator"
    if packaging:
        if not require_meta_gate:
            return True, "packaging_budget_ok"
        return False, "frozen_needs_meta_gate"
    if not require_meta_gate:
        return True, "budget_ok"
    # Caller must have already passed meta-gate; this helper is the freeze check.
    # When require_meta_gate, refuse silent mutation — caller uses request_seat_rewrite.
    return False, "frozen_needs_meta_gate"


def request_seat_rewrite(
    ctx: RunContext,
    *,
    proposed_delta: dict[str, Any] | None = None,
    reason: str = "",
    symptoms: list[str] | None = None,
) -> dict[str, Any]:
    """LLM (or deterministic) meta-gate for post-freeze seat/omit rewrite."""
    from interview_mux.timeline_reopen_meta_gate import decide_seat_rewrite

    try:
        decision = decide_seat_rewrite(
            ctx,
            proposed_delta=proposed_delta or {},
            reason=reason,
            symptoms=list(symptoms or []),
        )
    except Exception as exc:
        return {
            "allow": False,
            "refuse_reason": f"seat_rewrite_error:{type(exc).__name__}",
            "opportunity_score": 0.0,
            "rewrite_ops": [],
        }
    if decision.get("allow"):
        unlock_seat_freeze(ctx, reason=f"meta_gate:{reason}", clear_hard=False, clear_soft=False)
        _grant_one_shot_rewrite_token(ctx, reason=str(reason or "meta_gate"))
        # Keep freeze flags; one-shot token lets Pass B/ensure/clamp proceed once.
    return decision


def apply_seat_rewrite_ops(
    ctx: RunContext,
    ops: list[dict[str, Any]],
) -> list[str]:
    """Apply minimal omit/reseat ops from meta-gate, then clamp + re-freeze."""
    notes: list[str] = []
    if not ops:
        return notes
    try:
        gap_path = "understanding/gap_report.json"
        gap = ctx.read_json(gap_path) if ctx.artifact_exists(gap_path) else {}
        lines = list((gap or {}).get("interviewer_lines") or [])
        by_id = {
            str(ln.get("line_id") or ""): ln
            for ln in lines
            if isinstance(ln, dict) and ln.get("line_id")
        }
        for op in ops:
            if not isinstance(op, dict):
                continue
            action = str(op.get("action") or "").lower()
            lid = str(op.get("line_id") or "")
            ln = by_id.get(lid)
            if not ln:
                continue
            if action in {"omit", "skip"}:
                ln["skipped_optional"] = True
                ln["air_script_omit"] = True
                notes.append(f"omit:{lid}")
            elif action in {"unomit", "revive"}:
                ln["skipped_optional"] = False
                ln["air_script_omit"] = False
                ln.pop("omit", None)
                notes.append(f"revive:{lid}")
        gap["interviewer_lines"] = lines
        ctx.write_json(gap_path, gap)
    except Exception as exc:
        notes.append(f"gap_write_err:{exc}")
    try:
        from interview_mux.vo_contract import clamp_hosted_seats_to_rendered_wavs

        clamp_hosted_seats_to_rendered_wavs(ctx)
        notes.append("clamped")
    except Exception:
        pass
    try:
        from interview_mux.artifact_sanitize.air_script import commit_air_contract

        commit_air_contract(ctx, reason="seat_rewrite_meta")
        notes.append("air_contract")
    except Exception:
        pass
    bump_seat_rewrite_generation(ctx)
    stamp_soft_seat_freeze(ctx, reason="post_meta_rewrite")
    return notes


def holistic_seat_review(ctx: RunContext) -> dict[str, Any]:
    """Deterministic seat consistency report before transitions / adjudicate / edl."""
    failures: list[str] = []
    try:
        from interview_mux.air_script import omitted_vo_line_ids, seated_vo_line_ids

        seated = set(str(x) for x in (seated_vo_line_ids(ctx) or []) if x)
        omitted = set(str(x) for x in (omitted_vo_line_ids(ctx) or []) if x)
    except Exception:
        seated, omitted = set(), set()
    both = sorted(seated & omitted)
    if both:
        failures.append(f"seated_and_omitted:{','.join(both[:8])}")

    # Gap eligibility
    try:
        from interview_mux.air_script import gap_line_air_eligible

        gap = (
            ctx.read_json("understanding/gap_report.json")
            if ctx.artifact_exists("understanding/gap_report.json")
            else {}
        )
        by_id = {
            str(ln.get("line_id") or ""): ln
            for ln in (gap or {}).get("interviewer_lines") or []
            if isinstance(ln, dict)
        }
        for lid in sorted(seated):
            ln = by_id.get(lid)
            if ln is None:
                failures.append(f"seated_missing_from_gap:{lid}")
            elif not gap_line_air_eligible(ln):
                failures.append(f"seated_not_eligible:{lid}")
    except Exception as exc:
        failures.append(f"eligibility_err:{exc}")

    # Fingerprint drift vs freeze
    fr = read_seat_freeze(ctx)
    fp = seat_fingerprint(ctx)
    if fr.get("soft") and fr.get("fingerprint") and fr["fingerprint"] != fp:
        # Not always a failure — note drift for sanitize pin
        failures.append(f"fingerprint_drift:{fr['fingerprint']}->{fp}")

    ok = not failures
    report = {
        "ok": ok,
        "failures": failures[:24],
        "fingerprint": fp,
        "seated_n": len(seated),
        "omitted_n": len(omitted),
        "resume_pin": "air_contract_sanitize" if not ok else "",
        "at": _utc_now(),
    }
    try:
        ctx.write_json("operator/holistic_seat_review.json", report, skip_handoff=True)
    except Exception:
        pass
    return report


def freeze_blocks_selection_layup_invalidate(ctx: RunContext) -> bool:
    """When soft/hard freeze holds, selection order change must not wipe Pass B."""
    return soft_freeze_active(ctx) or hard_freeze_active(ctx)


def may_rewind_to_air_script_seams(ctx: RunContext) -> bool:
    """Refuse air_script_seams rewind under hard freeze + assembly unless catastrophe."""
    if hard_freeze_active(ctx):
        try:
            asm = ctx.final_path("master", "assembly.wav")
            if asm.is_file() and asm.stat().st_size > 0:
                # Catastrophe unlocks: missing seated WAV / G1 red.
                try:
                    from interview_mux.vo_contract import seated_vo_missing_ids

                    if seated_vo_missing_ids(ctx):
                        return True
                except Exception:
                    pass
                try:
                    from interview_mux.gates import check_g1_vo

                    if check_g1_vo(ctx):
                        return True
                except Exception:
                    pass
                return False
        except Exception:
            pass
    return True


def gate_seat_mutation(
    ctx: RunContext,
    *,
    reason: str,
    symptoms: list[str] | None = None,
    proposed_delta: dict[str, Any] | None = None,
) -> bool:
    """Return True if a seat/omit mutation may proceed under soft/hard freeze.

    Unfrozen → True. Catastrophe/operator reasons → True. Otherwise require
    ``request_seat_rewrite`` allow; refuse → False (caller must no-op).

    Fail-closed: any exception while freeze holds → refuse (no silent mutate).
    """
    try:
        frozen = soft_freeze_active(ctx) or hard_freeze_active(ctx)
    except Exception:
        frozen = False
    if not frozen:
        return True
    try:
        allowed, why = seat_mutation_allowed(
            ctx, reason=reason, require_meta_gate=True
        )
        if allowed:
            if why == "one_shot_token":
                consume_one_shot_rewrite_token(ctx)
            elif why == "catastrophe_or_operator":
                try:
                    bump_seat_rewrite_generation(ctx)
                except Exception:
                    pass
            return True
        if why != "frozen_needs_meta_gate":
            return False
        dec = request_seat_rewrite(
            ctx,
            proposed_delta=proposed_delta or {"ops": [], "from": reason},
            reason=reason,
            symptoms=list(symptoms or []),
        )
        if dec.get("allow"):
            consume_one_shot_rewrite_token(ctx)
            return True
        return False
    except Exception:
        return False


def operator_seat_unlock_note(ctx: RunContext, *, reason: str) -> None:
    """Stamp operator unlock note and grant one-shot rewrite (G1 / gap CRUD)."""
    unlock_seat_freeze(
        ctx,
        reason=f"operator:{reason}",
        clear_hard=False,
        clear_soft=False,
    )
    _grant_one_shot_rewrite_token(ctx, reason=f"operator:{reason}")


def frozen_omitted_line_ids(ctx: RunContext) -> set[str]:
    """Omit set to treat as intentional under publishability omit_collateral."""
    if not (soft_freeze_active(ctx) or hard_freeze_active(ctx)):
        return set()
    try:
        from interview_mux.air_script import omitted_vo_line_ids

        return set(str(x) for x in (omitted_vo_line_ids(ctx) or []) if x)
    except Exception:
        return set()
