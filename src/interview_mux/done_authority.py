"""Done Authority — single lifecycle SSOT for stage completion honesty.

Partial Zero DP-DONE-AUTHORITY (operator 1A+2A+3A) + footgun harden:

- Real completion (done ∧ outputs ∧ no incompleteness) clears waits and advances.
- Hollow ``.stage_done`` / refused stamps never count as success.
- Finalize complete = committed master + well-formed PMQ + integrity.
- Stamp finalize only on successful PMQ exit (never before delight/structural raise).
"""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext

PMQ_REL = "master/post_master_quality.json"
MASTER_WAV_REL = "master/master.wav"
SHIP_GATE_META_KEY = "master_finalize_ship_gate_open"

# Minimal ship-envelope keys — existence alone is not enough (footgun #6).
_PMQ_REQUIRED_KEYS = frozenset({"version", "status", "checks", "never_skipped"})


def note_finalize_ship_gate_open(ctx: RunContext, *, reason: str) -> None:
    """Mark finalize outputs present but ship gate still open (delight/structural)."""

    def _set(meta: dict[str, Any]) -> None:
        meta[SHIP_GATE_META_KEY] = {
            "open": True,
            "reason": str(reason or "ship_fail")[:120],
        }

    try:
        ctx.mutate_run_meta(_set)
    except Exception:
        pass


def clear_finalize_ship_gate(ctx: RunContext) -> None:
    def _clear(meta: dict[str, Any]) -> None:
        meta.pop(SHIP_GATE_META_KEY, None)

    try:
        ctx.mutate_run_meta(_clear)
    except Exception:
        pass


def finalize_ship_gate_open(ctx: RunContext) -> bool:
    try:
        if not ctx.artifact_exists("run_meta.json"):
            return False
        meta = ctx.read_json("run_meta.json")
        row = meta.get(SHIP_GATE_META_KEY) if isinstance(meta, dict) else None
        return bool(isinstance(row, dict) and row.get("open"))
    except Exception:
        return False


def is_seed_complete(ctx: RunContext, stage: str) -> bool:
    """Honest stage complete — same meaning as ``seed_stage_complete``.

    Accepts true completion; rejects hollow ``is_done``-only markers.
    ImportError → False; other exceptions propagate (footgun #8).
    """
    sid = str(stage or "").strip()
    if not sid:
        return False
    try:
        from interview_mux.delivery_guardrails import seed_stage_complete
    except ImportError:
        return False
    return bool(seed_stage_complete(ctx, sid))


def may_clear_wait(ctx: RunContext, stage: str) -> bool:
    """ESR / incomplete-after-conductor may stop waiting only on seed-complete.

    Bare ``is_done`` never clears wait (DP-B5 / footgun hollow escape).
    """
    return is_seed_complete(ctx, stage)


def honest_finalize_seeded(ctx: RunContext) -> bool:
    """True when master_finalize is seed-complete (never bare is_done).

    Use this instead of ``committed_master_wav ∧ is_done(master_finalize)``.
    """
    return may_clear_wait(ctx, "master_finalize")


def pmq_well_formed(ctx: RunContext) -> bool:
    """PMQ present and shaped as a ship envelope (not empty/corrupt JSON)."""
    try:
        if not ctx.artifact_exists(PMQ_REL):
            return False
        doc = ctx.read_json(PMQ_REL)
    except Exception:
        return False
    if not isinstance(doc, dict):
        return False
    if not _PMQ_REQUIRED_KEYS.issubset(doc.keys()):
        return False
    status = str(doc.get("status") or "").strip().lower()
    if not status:
        return False
    return True


def finalize_outputs_complete(ctx: RunContext) -> bool:
    """master_finalize output predicate: integrity ∧ well-formed PMQ."""
    try:
        from interview_mux.delivery_invariants import committed_master_integrity_ok

        if not committed_master_integrity_ok(ctx):
            return False
    except Exception:
        return False
    return pmq_well_formed(ctx)


def finalize_incompleteness(ctx: RunContext) -> str | None:
    """Human-readable incompleteness for master_finalize (or None if complete)."""
    try:
        from interview_mux.delivery_invariants import committed_master_integrity_ok

        if not committed_master_integrity_ok(ctx):
            return (
                "master_finalize hollow — resume master_finalize: "
                "committed master.wav missing/truncated/pending"
            )
    except Exception:
        return (
            "master_finalize hollow — resume master_finalize: "
            "committed master.wav missing/truncated/pending"
        )
    if not pmq_well_formed(ctx):
        if not ctx.artifact_exists(PMQ_REL):
            return (
                "master_finalize hollow — resume master_finalize: "
                f"{PMQ_REL} missing"
            )
        return (
            "master_finalize hollow — resume master_finalize: "
            f"{PMQ_REL} malformed (need version/status/checks/never_skipped)"
        )
    if finalize_ship_gate_open(ctx):
        return (
            "master_finalize hollow — resume master_finalize: "
            "ship gate open (delight/structural fail after PMQ persist)"
        )
    return None


def try_mark_done(ctx: RunContext, stage: str, *, force: bool = False) -> bool:
    """Sole recommended stamp API: True if done after call; False on AuthorityDenied.

    Other exceptions propagate. Never treats refuse / silent no-op as success.
    """
    sid = str(stage or "").strip()
    if not sid:
        return False
    try:
        ctx.mark_done(sid, force=force)
    except Exception as exc:
        try:
            from interview_mux.artifact_ownership import AuthorityDenied as AD

            if isinstance(exc, AD):
                return False
        except Exception:
            pass
        name = type(exc).__name__
        if name == "AuthorityDenied" or "authority_denied" in str(exc).lower():
            return False
        raise
    try:
        return bool(ctx.is_done(sid))
    except Exception:
        return False


def stamp_finalize_on_success(ctx: RunContext) -> None:
    """Footgun #1/#2: stamp only on successful PMQ exit; refuse is loud.

    Call after delight / structural gates have been cleared (no pending raise).
    """
    clear_finalize_ship_gate(ctx)
    if not finalize_outputs_complete(ctx):
        raise RuntimeError(
            "master_finalize: refuse mark_done — outputs incomplete "
            "(need committed master integrity + well-formed PMQ)"
        )
    if not try_mark_done(ctx, "master_finalize"):
        raise RuntimeError(
            "master_finalize: mark_done refused after successful PMQ path "
            "(AuthorityDenied / hollow / pending approval)"
        )
    if not ctx.is_done("master_finalize"):
        raise RuntimeError(
            "master_finalize: mark_done did not stick after successful PMQ path"
        )


def unmark_finalize_after_ship_fail(ctx: RunContext, *, reason: str) -> None:
    """Footgun #1: never leave seed-complete finalize after delight/structural fail."""
    note_finalize_ship_gate_open(ctx, reason=reason)
    try:
        if not ctx.is_done("master_finalize"):
            return
    except Exception:
        return
    try:
        from interview_mux.homunculus.agenda import unmark_stage_only

        unmark_stage_only(ctx, "master_finalize")
        ctx.log(
            f"master_finalize: unmarked after ship-fail ({reason})",
            level="warning",
            stage="master_finalize",
        )
    except Exception as exc:
        ctx.log(
            f"master_finalize: could not unmark after ship-fail ({reason}): {exc}",
            level="warning",
            stage="master_finalize",
        )


def require_seated_before_mix_mark(ctx: RunContext) -> None:
    """BUILD-HOLLOW-MIX: never call mark_done(mix) unless seated.

    Raises RuntimeError with classified message when unseated.
    """
    try:
        from interview_mux.air_order import mix_outputs_seated

        if mix_outputs_seated(ctx):
            return
    except Exception as exc:
        raise RuntimeError(
            f"mix unseated — refuse mark_done: seat_check_failed:{type(exc).__name__}"
        ) from exc
    raise RuntimeError(
        "mix unseated — refuse mark_done: mix_outputs_seated "
        "(mtime+commitment required before .stage_done/mix)"
    )


def read_done_snapshot(ctx: RunContext, stage: str) -> dict[str, Any]:
    """Debug / tests."""
    sid = str(stage or "").strip()
    done = False
    try:
        done = bool(ctx.is_done(sid))
    except Exception:
        done = False
    return {
        "stage": sid,
        "is_done": done,
        "is_seed_complete": is_seed_complete(ctx, sid),
        "may_clear_wait": may_clear_wait(ctx, sid),
        "finalize_outputs_complete": (
            finalize_outputs_complete(ctx) if sid == "master_finalize" else None
        ),
        "pmq_well_formed": pmq_well_formed(ctx) if sid == "master_finalize" else None,
    }
