"""Operator delivery unstick playbook — promote, seal, pin, clear thrash, optional resume."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext

UNSTICK_ATTEMPTS_REL = "operator/unstick_attempts.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_unstick_ledger(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists(UNSTICK_ATTEMPTS_REL):
        return {"attempts": []}
    try:
        doc = ctx.read_json(UNSTICK_ATTEMPTS_REL)
    except Exception:
        return {"attempts": []}
    if not isinstance(doc, dict):
        return {"attempts": []}
    attempts = doc.get("attempts")
    if not isinstance(attempts, list):
        doc = dict(doc)
        doc["attempts"] = []
    return doc


def _write_unstick_ledger(ctx: RunContext, doc: dict[str, Any]) -> None:
    ctx.write_json(UNSTICK_ATTEMPTS_REL, doc, skip_handoff=True)


def maybe_auto_unstick_once(ctx: RunContext, sticky_signature: str) -> dict[str, Any]:
    """Invoke ``run_delivery_unstick`` at most once per sticky signature.

    Ledger: ``operator/unstick_attempts.json`` list of ``{sig, at, result}``.
    Same ``sig`` → ``{invoked: False, already_attempted: True}`` without re-unstick.
    """
    sig = str(sticky_signature or "").strip()
    if not sig:
        return {"invoked": False, "already_attempted": False, "reason": "empty_sig"}
    ledger = _read_unstick_ledger(ctx)
    attempts = list(ledger.get("attempts") or [])
    for row in attempts:
        if isinstance(row, dict) and str(row.get("sig") or "") == sig:
            return {
                "invoked": False,
                "already_attempted": True,
                "sig": sig,
                "prior": row,
            }
    result = run_delivery_unstick(ctx, clear_needs_operator=True, execute_resume=False)
    entry = {
        "sig": sig,
        "at": _utc_now(),
        "result": {
            "ok": bool(result.get("ok")),
            "from_stage": result.get("from_stage"),
            "intent": result.get("intent"),
            "thrash_cleared": result.get("thrash_cleared"),
            "phase_a_sealed": result.get("phase_a_sealed"),
        },
    }
    attempts.append(entry)
    ledger["attempts"] = attempts[-50:]
    ledger["updated_at"] = _utc_now()
    try:
        _write_unstick_ledger(ctx, ledger)
    except Exception as exc:
        result["ledger_error"] = str(exc)[:200]
    out = dict(result)
    out["invoked"] = True
    out["already_attempted"] = False
    out["sig"] = sig
    return out


def run_delivery_unstick(
    ctx: RunContext,
    *,
    clear_needs_operator: bool = True,
    execute_resume: bool = False,
) -> dict[str, Any]:
    """One-shot heal for skewed delivery runs (exec_5402 class).

    Steps:
      1. Restore archived finalize inputs when live copies missing
      2. Promote complete orphan stage_done markers
      3. Seal Phase A when stable / artifact-led
      4. Clear active thrash report when predicates allow
      5. heal_navigate → canonical from_stage
      6. Optionally clear needs_operator and return execute hint

    RC6/O8: never zero ``operator/identical_failures.json`` halt rows here.
    Identical clears require ``stage_predicate_token`` flip (or forensics/force).
    """
    out: dict[str, Any] = {
        "ok": True,
        "promoted": [],
        "demoted": [],
        "restored": [],
        "phase_a_sealed": False,
        "thrash_cleared": False,
        "from_stage": "",
        "intent": "",
        "needs_operator_cleared": False,
        "execute": None,
    }
    try:
        from interview_mux.thrash_hardening import ensure_finalize_inputs_present

        out["restored"] = ensure_finalize_inputs_present(ctx, emit_ledger=True)
    except Exception as exc:
        out["restore_error"] = str(exc)[:240]

    try:
        from interview_mux.delivery_guardrails import (
            promote_complete_orphan_stage_done,
            reconcile_orphan_artifacts,
            seal_phase_a_if_stable,
        )

        out["promoted"] = promote_complete_orphan_stage_done(ctx)
        try:
            out["demoted"] = reconcile_orphan_artifacts(ctx)
        except Exception:
            out["demoted"] = []
        seal_phase_a_if_stable(ctx)
        from interview_mux.delivery_guardrails import phase_a_sealed

        out["phase_a_sealed"] = phase_a_sealed(ctx)
    except Exception as exc:
        out["promote_seal_error"] = str(exc)[:240]

    try:
        from interview_mux.thrash_hardening import (
            FAIL_CLASS_DELIVERY_BLOCKED,
            clear_thrash_on_predicate_flip,
            heal_navigate,
            thrash_summary,
        )

        active = thrash_summary(ctx)
        pin_hint = ""
        if isinstance(active, dict):
            pin_hint = str(active.get("pin") or active.get("stage") or "")
        # Operator unstick always clears thrash (intentional heal, not auto-detect).
        cleared = clear_thrash_on_predicate_flip(
            ctx,
            stage=pin_hint or "music_palette_compose",
            prior_token="__unstick__",
        )
        out["thrash_cleared"] = bool(cleared)
        nav = heal_navigate(
            ctx,
            intent=FAIL_CLASS_DELIVERY_BLOCKED,
            stage=pin_hint or "delivery",
            error="operator_delivery_unstick",
        )
        out["from_stage"] = nav.get("from_stage") or ""
        out["intent"] = nav.get("intent") or ""
        out["mode"] = nav.get("mode") or "delivery"
    except Exception as exc:
        out["navigate_error"] = str(exc)[:240]
        out["from_stage"] = out.get("from_stage") or "music_palette_compose"
        out["mode"] = "delivery"

    if clear_needs_operator:

        def _clear(meta: dict[str, Any]) -> None:
            if not meta.get("needs_operator"):
                return
            meta.pop("needs_operator", None)
            meta.pop("needs_operator_stage", None)
            meta.pop("needs_operator_reason", None)

        try:
            if ctx.artifact_exists("run_meta.json"):
                before = ctx.read_json("run_meta.json") or {}
                had = bool(isinstance(before, dict) and before.get("needs_operator"))
                ctx.mutate_run_meta(_clear)
                out["needs_operator_cleared"] = had
        except Exception as exc:
            out["needs_clear_error"] = str(exc)[:200]

    try:
        from interview_mux.delivery_guardrails import record_wasted_work

        record_wasted_work(
            ctx,
            event="delivery_unstick",
            stage=str(out.get("from_stage") or "delivery"),
            detail={
                "from_stage": out.get("from_stage"),
                "intent": out.get("intent"),
                "promoted": (out.get("promoted") or [])[:12],
                "thrash_cleared": out.get("thrash_cleared"),
            },
        )
    except Exception:
        pass

    try:
        ctx.log(
            f"delivery_unstick → {out.get('from_stage')} "
            f"(sealed={out.get('phase_a_sealed')} thrash_cleared={out.get('thrash_cleared')})",
            level="info",
            stage=str(out.get("from_stage") or None),
            detail=out,
        )
    except Exception:
        pass

    if execute_resume and out.get("from_stage"):
        out["execute"] = {
            "mode": out.get("mode") or "delivery",
            "from_stage": out["from_stage"],
        }
    return out
