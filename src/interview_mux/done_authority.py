"""Done Authority — single lifecycle SSOT for stage completion honesty.

Partial Zero DP-DONE-AUTHORITY + Heal Clinic hollow_pass B+ Done Constitution
+ Land Honesty v2 (Cluster A / XC-HOLLOW):

- Real completion (done ∧ outputs ∧ no incompleteness) clears waits and advances.
- Hollow ``.stage_done`` / refused stamps never count as success.
- Unpaid land (remaster, remutate, authority-without-plan, shared-path) blocks
  promote / seed-complete / skip until the obligation clears.
- Finalize complete = committed master + well-formed PMQ + integrity.
- Stamp finalize only on successful PMQ exit (never before delight/structural raise).
- WRITE ``.stage_done`` → ``try_mark_done`` / ``heal_or_refuse_mark`` only (raw gated).
- READ ready / advance → ``is_seed_complete`` / ``may_clear_wait`` / ``land_honest``
  (never bare ``is_done``).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from interview_mux.run_context import RunContext

PMQ_REL = "master/post_master_quality.json"
MASTER_WAV_REL = "master/master.wav"
SHIP_GATE_META_KEY = "master_finalize_ship_gate_open"

# Minimal ship-envelope keys — existence alone is not enough (footgun #6).
_PMQ_REQUIRED_KEYS = frozenset({"version", "status", "checks", "never_skipped"})

# Hollow-pass B+: operator gates allowed marker-without-primary (assert_may_mark_done).
GATE_MARKER_ONLY: frozenset[str] = frozenset(
    {
        "transcript_review",
        "g1_vo_pickup",
        "delivery_unlock",
    }
)

# Who may set ``ctx._mark_done_raw`` (reason token). Tests use ``test_fixture``.
RAW_STAMP_ALLOW: frozenset[str] = frozenset(
    {
        "heal_or_refuse_mark",
        "test_fixture",
        "post_master_backfill",  # only after outputs_present gate
    }
)

# Post-master backfill may touch these families — still requires outputs_present.
# Empty set means: any pre-master delivery stage, outputs required (see may_backfill).
POST_MASTER_BACKFILL_ALLOW_ALL_PRE_MASTER: bool = True

# Shared disk primaries: promote / seed-complete need matching _meta.producer_stage.
SHARED_PATH_PRODUCER_STAGES: frozenset[str] = frozenset(
    {
        "gap_report_sanitize",
        "air_contract_sanitize",
        "selection_order_sanitize",
        "sound_design_plan",
    }
)

# Ownership-ALLOW co-writers may leave producer_stage on the shared primary.
# Sanitize still re-runs to restamp; unpaid must not thrash when layup just
# published VO into gap_report (exec_13198).
_SHARED_PATH_LAND_CO_PRODUCERS: dict[str, frozenset[str]] = {
    "gap_report_sanitize": frozenset(
        {
            "gap_report_sanitize",
            "nugget_layup_compose",
            "gap_framing_compose",
            "gap_framing_recompose",
        }
    ),
    # Metadata align under seat freeze may rewrite chapters; order-unchanged
    # commits preserve prior producer_stage (S4) so sanitize ↔ narrative do not
    # flip ownership. Either claim remains paid land (exec_13198).
    "selection_order_sanitize": frozenset(
        {
            "selection_order_sanitize",
            "edl_narrative_audit",
            "edl_narrative_metadata_align",
            # Legacy/alias stamps from sanitize commit paths (exec_13198).
            "selection",
            "artifact_sanitize.selection",
        }
    ),
}

# Stages that must not look complete under nugget_layup_authority without a plan.
LAYUP_AUTHORITY_STAGES: frozenset[str] = frozenset(
    {
        "gap_framing_compose",
        "nugget_layup_compose",
        "optimal_questions",
    }
)


def may_skip_as_complete(ctx: RunContext, stage: str) -> bool:
    """Pipeline / walk may skip re-invoke only on land-honest seed-complete.

    Bare ``is_done`` never skips work. Unpaid land also blocks skip.
    """
    return land_honest(ctx, stage)


def primary_disk_present(ctx: RunContext, stage: str) -> bool:
    """True when stage has no disk primary mapped, or the primary exists."""
    sid = str(stage or "").strip()
    if not sid or sid in GATE_MARKER_ONLY:
        return True
    try:
        from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

        rel = STAGE_ARTIFACT_DISK_PATHS.get(sid)
        if not rel:
            return True
        return bool(ctx.artifact_exists(str(rel)))
    except Exception:
        return False


def may_post_master_backfill(ctx: RunContext, stage: str) -> bool:
    """Hollow-pass R3: backfill only when outputs are present (anti-rewind, not hollow)."""
    sid = str(stage or "").strip()
    if not sid:
        return False
    if sid in GATE_MARKER_ONLY:
        return True
    try:
        from interview_mux.homunculus.agenda import stage_outputs_present
        from interview_mux.v2.config import DELIVERY_ORDER, SHIP_AFTER_MASTER

        if sid not in DELIVERY_ORDER or sid in SHIP_AFTER_MASTER:
            return False
        if not POST_MASTER_BACKFILL_ALLOW_ALL_PRE_MASTER:
            return False
        return bool(stage_outputs_present(ctx, sid))
    except Exception:
        return False


@contextmanager
def raw_stamp_session(ctx: RunContext, reason: str) -> Iterator[None]:
    """Hollow-pass R2: gated ``_mark_done_raw`` — reason must be in RAW_STAMP_ALLOW."""
    token = str(reason or "").strip()
    if token not in RAW_STAMP_ALLOW:
        raise RuntimeError(
            f"refuse raw stamp: reason={token!r} not in RAW_STAMP_ALLOW"
        )
    prev = bool(getattr(ctx, "_mark_done_raw", False))
    ctx._mark_done_raw = True
    try:
        yield
    finally:
        ctx._mark_done_raw = prev


def honest_restamp(ctx: RunContext, stage: str) -> bool:
    """Hollow-pass R1: restamp via try_mark_done — never bare Path.touch.

    Returns True if stage is seed-complete after the call.
    """
    sid = str(stage or "").strip()
    if not sid:
        return False
    if is_seed_complete(ctx, sid):
        return True
    if not try_mark_done(ctx, sid):
        return False
    return is_seed_complete(ctx, sid)


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


def layup_authority_without_plan(ctx: RunContext) -> bool:
    """True when gap_report claims layup authority but nugget_layup_plan is missing."""
    try:
        from interview_mux.nugget_layup import PLAN_REL, nugget_layup_enabled

        if not nugget_layup_enabled():
            return False
        if ctx.artifact_exists(PLAN_REL):
            return False
        if not ctx.artifact_exists("understanding/gap_report.json"):
            return False
        gap = ctx.read_json("understanding/gap_report.json")
        return bool(isinstance(gap, dict) and gap.get("nugget_layup_authority"))
    except Exception:
        return False


def shared_path_producer_mismatch(ctx: RunContext, stage: str) -> str | None:
    """When a shared primary exists, refuse land unless _meta.producer_stage matches.

    Empty/missing producer_stage is unpaid (unclaimed shared-path land). Wrong
    producer is unpaid. Matching producer clears.
    """
    sid = str(stage or "").strip()
    if sid not in SHARED_PATH_PRODUCER_STAGES:
        return None
    try:
        from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

        rel = STAGE_ARTIFACT_DISK_PATHS.get(sid)
        if not rel or not ctx.artifact_exists(str(rel)):
            return None
        if not str(rel).endswith(".json"):
            return None
        doc = ctx.read_json(str(rel))
        if not isinstance(doc, dict):
            return None
        producer = str((doc.get("_meta") or {}).get("producer_stage") or "").strip()
        if not producer:
            return (
                f"shared-path unpaid land — resume {sid}: "
                f"{rel} missing producer_stage"
            )
        if producer == sid:
            return None
        co = _SHARED_PATH_LAND_CO_PRODUCERS.get(sid)
        if co and producer in co:
            return None
        return (
            f"shared-path unpaid land — resume {sid}: "
            f"{rel} producer_stage={producer!r} (not {sid})"
        )
    except Exception:
        return None


def unpaid_land_reason(ctx: RunContext, stage: str) -> str | None:
    """Land Honesty: human reason when an unpaid obligation blocks land, else None.

    Sole unpaid-obligation input for promote, mix/junction incompleteness, and
    ``land_honest``. Table-driven families (Cluster A + shared-path):

    1. Remaster in flight or speech_first remaster owed → mix / junction
       (S6(B): junction-owned remaster is *paid* for ``junction_snip_qa`` —
       mix stays unpaid until ``clear_remaster``)
    2. Active remutate targets
    3. Layup authority without plan
    4. Shared-path producer_stage mismatch or missing
    """
    sid = str(stage or "").strip()
    if not sid:
        return None

    # 1. Remaster / speech-first beds remaster (Cluster A / Dig #2)
    if sid in {"mix", "junction_snip_qa"}:
        try:
            from interview_mux.mix_junction_seat import (
                music_epoch_pre_beds_seat,
                remaster_in_flight,
                remaster_owner,
                speech_first_remaster_owed,
            )

            if remaster_in_flight(ctx):
                owner = remaster_owner(ctx) or "unknown"
                owner_l = str(owner).strip().lower()
                # S6(B): junction is the primary remaster producer — paid land.
                # Mix remains unpaid so orphan promote cannot hollow-complete mid-flight.
                if sid == "junction_snip_qa" and owner_l in {
                    "junction",
                    "junction_snip_qa",
                }:
                    pass
                else:
                    if music_epoch_pre_beds_seat(ctx):
                        return (
                            f"{sid} remaster owed — resume mix: "
                            f"music_epoch_pre_beds_seat remaster_owner={owner} "
                            "(assembly predates remaster; clear_remaster only on seated land)"
                        )
                    return (
                        f"{sid} remaster owed — resume mix: "
                        f"remaster_owner={owner} (clear_remaster only on seated land)"
                    )
            # Owed before owner stamp (speech-first / preview-era) — mix only.
            # Junction alone is not unpaid until an owner stamps (or music_epoch).
            if speech_first_remaster_owed(ctx) and sid == "mix":
                return (
                    f"{sid} remaster owed — resume mix: "
                    "speech_first_remaster_owed (owner may not be stamped yet)"
                )
        except Exception:
            pass

    # 2. Active remutate
    try:
        from interview_mux.delivery_invariants import active_remutate_stages

        if sid in active_remutate_stages(ctx):
            return (
                f"{sid} remutate unpaid — resume {sid}: "
                "active remutate plan cleared this producer"
            )
    except Exception:
        pass

    # 3. Layup authority stamp without plan
    if sid in LAYUP_AUTHORITY_STAGES and layup_authority_without_plan(ctx):
        return (
            f"{sid} stamp-alone — resume gap_framing_compose: "
            "nugget_layup_authority without nugget_layup_plan"
        )

    # 4. Shared-path producer mismatch
    shared = shared_path_producer_mismatch(ctx, sid)
    if shared:
        return shared

    return None


def unpaid_land_blocks_promote(ctx: RunContext, stage: str) -> bool:
    """True when orphan promote must skip ``stage`` (unpaid land)."""
    return unpaid_land_reason(ctx, stage) is not None


def land_honest(ctx: RunContext, stage: str) -> bool:
    """True when unpaid land is clear and the stage is seed-complete."""
    sid = str(stage or "").strip()
    if not sid:
        return False
    if unpaid_land_reason(ctx, sid) is not None:
        return False
    return is_seed_complete(ctx, sid)


def may_clear_wait(ctx: RunContext, stage: str) -> bool:
    """ESR / incomplete-after-conductor may stop waiting only on land-honest complete.

    Bare ``is_done`` never clears wait (DP-B5 / footgun hollow escape).
    """
    return land_honest(ctx, stage)


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
    unpaid = unpaid_land_reason(ctx, sid)
    return {
        "stage": sid,
        "is_done": done,
        "is_seed_complete": is_seed_complete(ctx, sid),
        "land_honest": land_honest(ctx, sid),
        "unpaid_land_reason": unpaid,
        "may_clear_wait": may_clear_wait(ctx, sid),
        "finalize_outputs_complete": (
            finalize_outputs_complete(ctx) if sid == "master_finalize" else None
        ),
        "pmq_well_formed": pmq_well_formed(ctx) if sid == "master_finalize" else None,
    }
