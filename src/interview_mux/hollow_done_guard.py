"""Hollow-done runtime / forensics guard — escalate ``.stage_done`` ∧ ¬land_honest.

Surfaces stamps that look complete but fail Land Honesty (unpaid land or
missing/incomplete outputs). Under ``MUX_FORENSICS=1`` persists
``operator/hollow_done_escalation.json`` for parent review. Never hard-raises
unless ``raise_on_find=True`` — non-forensics full-auto stays log-only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext

HOLLOW_ESCALATION_REL = "operator/hollow_done_escalation.json"


def _forensics_on() -> bool:
    try:
        from interview_mux.identical_failures import forensics_mode

        return bool(forensics_mode())
    except Exception:
        return False


def _default_stage_scope() -> list[str]:
    try:
        from interview_mux.delivery_guardrails import G3_RECONCILE_CHAIN

        return list(G3_RECONCILE_CHAIN)
    except Exception:
        pass
    try:
        from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

        return list(ANALYSIS_ORDER) + list(DELIVERY_ORDER)
    except Exception:
        return []


def scan_hollow_done(
    ctx: RunContext, stages: tuple[str, ...] | list[str] | None = None
) -> list[dict[str, Any]]:
    """Return stages with ``.stage_done`` present that are not ``land_honest``."""
    from interview_mux.done_authority import land_honest, unpaid_land_reason

    scope = list(stages) if stages is not None else _default_stage_scope()
    found: list[dict[str, Any]] = []
    for sid in scope:
        sid_s = str(sid or "").strip()
        if not sid_s:
            continue
        try:
            if not ctx.is_done(sid_s):
                continue
            if land_honest(ctx, sid_s):
                continue
        except Exception:
            continue
        unpaid: str | None = None
        incompleteness: str | None = None
        try:
            unpaid = unpaid_land_reason(ctx, sid_s)
        except Exception:
            unpaid = None
        try:
            from interview_mux.stage_completion import stage_artifact_incompleteness

            incompleteness = stage_artifact_incompleteness(ctx, sid_s)
        except Exception:
            incompleteness = None
        reason = str(unpaid or incompleteness or "").strip()
        if not reason:
            reason = f"{sid_s} hollow done — not land_honest"
        found.append(
            {
                "stage": sid_s,
                "reason": reason,
                "unpaid_land_reason": unpaid,
                "incompleteness": incompleteness,
            }
        )
    return found


def escalate_hollow_done(
    ctx: RunContext,
    *,
    stages: tuple[str, ...] | list[str] | None = None,
    raise_on_find: bool = False,
) -> list[dict[str, Any]]:
    """Log hollow stamps; under forensics write ``operator/hollow_done_escalation.json``.

    Prefer escalate+log. Unmark stays with existing G3 / demote helpers — this
    path does not demote by default. Raise only when ``raise_on_find`` is set.
    """
    found = scan_hollow_done(ctx, stages)
    if not found:
        return []
    detail: dict[str, Any] = {
        "version": 1,
        "kind": "hollow_done_escalation",
        "run_id": str(getattr(ctx, "run_id", "") or ""),
        "hollow": found,
        "ts": datetime.now(timezone.utc).isoformat(),
        "forensics": _forensics_on(),
    }
    try:
        ctx.log(
            "hollow_done_guard: "
            + ", ".join(
                f"{r['stage']} ({str(r.get('reason') or '')[:80]})" for r in found[:8]
            ),
            level="warning",
            stage="hollow_done_guard",
            detail=detail,
        )
    except Exception:
        pass
    if _forensics_on():
        try:
            ctx.write_json(HOLLOW_ESCALATION_REL, detail, skip_handoff=True)
        except Exception:
            try:
                import json

                path = ctx.final_path(*HOLLOW_ESCALATION_REL.split("/"))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(detail, indent=2), encoding="utf-8")
            except Exception:
                pass
    if raise_on_find:
        first = found[0]
        raise RuntimeError(
            f"hollow_done_escalation:{first['stage']}:{first['reason']}"
        )
    return found
