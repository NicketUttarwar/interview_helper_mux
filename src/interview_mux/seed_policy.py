"""Seed policy table — freeze/epoch sticky stages for seed-order.

When a domain is sealed (hard seat freeze, Phase A, etc.), listed stages are
treated as satisfied: force-mark done and never raise seed_order_prereq for them.
"""

from __future__ import annotations

from typing import Callable

from interview_mux.run_context import RunContext

# Stages that are intentional no-ops under hard seat freeze once EDL is done.
FREEZE_STICKY_SEED_STAGES: frozenset[str] = frozenset(
    {
        "selection_framing_apply",
        "gap_framing_recompose",
    }
)


def _hard_freeze_and_edl_done(ctx: RunContext) -> bool:
    try:
        from interview_mux.seat_authority import hard_freeze_active

        return bool(hard_freeze_active(ctx) and ctx.is_done("edl"))
    except Exception:
        return False


def seed_stage_satisfied_by_policy(ctx: RunContext, stage_id: str) -> bool:
    """True when seed-order should treat ``stage_id`` as complete without work."""
    sid = str(stage_id or "").strip()
    if not sid:
        return False
    if sid in FREEZE_STICKY_SEED_STAGES and _hard_freeze_and_edl_done(ctx):
        return True
    return False


def ensure_sticky_seed_mark(ctx: RunContext, stage_id: str) -> bool:
    """Force-mark stage done when policy says satisfied. Returns True if marked/done."""
    sid = str(stage_id or "").strip()
    if not sid or not seed_stage_satisfied_by_policy(ctx, sid):
        return False
    if ctx.is_done(sid):
        return True
    try:
        from interview_mux.stage_completion import heal_or_refuse_mark

        heal_or_refuse_mark(ctx, sid, force=True)
    except Exception:
        pass
    if ctx.is_done(sid):
        return True
    # Intentional freeze no-op: raw mark when heal refuses hollow producer paths.
    try:
        prev = getattr(ctx, "_mark_done_raw", False)
        ctx._mark_done_raw = True
        try:
            ctx.mark_done(sid, force=True)
        finally:
            ctx._mark_done_raw = prev
    except Exception:
        try:
            done = ctx.run_dir / ".stage_done" / sid
            done.parent.mkdir(parents=True, exist_ok=True)
            done.write_text("", encoding="utf-8")
        except Exception:
            return False
    return bool(ctx.is_done(sid))


def seal_freeze_sticky_stages(ctx: RunContext) -> list[str]:
    """Mark all FREEZE_STICKY stages done when hard freeze + EDL sealed.

    Single law for freeze no-ops — call from seed walk and pre_mix, not only
    when a specific earlier stage is inspected.
    """
    if not _hard_freeze_and_edl_done(ctx):
        return []
    sealed: list[str] = []
    for sid in sorted(FREEZE_STICKY_SEED_STAGES):
        if ensure_sticky_seed_mark(ctx, sid):
            sealed.append(sid)
    if sealed:
        try:
            ctx.write_json(
                "operator/seed_sanitized.json",
                {
                    "reason": "hard_freeze_sticky_noop",
                    "sealed_stages": sealed,
                    "edl_done": True,
                },
                skip_handoff=True,
            )
        except Exception:
            pass
    return sealed


def apply_seed_policy_skips(
    ctx: RunContext,
    earlier: str,
    *,
    mark: Callable[[RunContext, str], bool] | None = None,
) -> bool:
    """If ``earlier`` is policy-satisfied, sticky-mark and return True (caller continue)."""
    if not seed_stage_satisfied_by_policy(ctx, earlier):
        return False
    if mark is not None:
        mark(ctx, earlier)
    else:
        ensure_sticky_seed_mark(ctx, earlier)
    return True
