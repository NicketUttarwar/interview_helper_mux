"""Mix–Junction Seat Authority — single lifecycle SSOT for build seating.

HAU (Heard-Assembly Unification):
one state, many thin facades. Callers must not keep private assembly / precede /
music-admit shortcuts (preview OR assembly dual admit is forbidden).

Derived answers:
- ``heard_assembly`` — one heard-assembly SSOT (preview = light mode)
- ``junction_precedes_mix`` / ``who_runs_next``
- ``may_admit_music`` / ``music_admit_block_reason`` (federal: seated or preview_music)
- ``must_verify_commitment`` (A5: when assembly.wav exists)
- ``remaster_session`` / ``begin_remaster`` / ``clear_remaster`` / ``remaster_in_flight``
- ``note_speech_first_mix`` / ``maybe_remaster_after_music_epoch``
- ``speech_first_remaster_owed`` / ``ensure_speech_first_remaster`` — block ship skip
- ``clear_mix_epoch_for_speech_first`` — sole mix_epoch_block speech-first clear (FG2)
- ``optional_beds_until_remaster`` via ``allow_speech_first_mix`` (all modes)
- ``beds_deferred_for_mix`` — soft theme/SFX gates while stamp set + music incomplete
- ``next_delivery_seat`` — sole mix-vs-music resume/heal/filter pin (F1/F10/F11)

Allowed production callers of seating choice: ``next_delivery_seat`` (or
``beds_deferred_for_mix`` soft-gates only). Do not add resume/heal branches on
raw ``allow_speech_first_mix`` outside this module. Guardrails ``mix_epoch_block``
must use ``clear_mix_epoch_for_speech_first`` / remaster-owed helpers — never import
``allow_speech_first_mix`` directly.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Literal

from interview_mux.run_context import RunContext

SEAT_EPOCH_KEY = "mix_junction_seat"
WhoRuns = Literal["mix", "junction_snip_qa"]

# HAU beds policy (DP-BUILD-ASSEMBLY-FRESHNESS): mix may seat speech-first;
# MusicGen/SFX admit after seated (or explicit preview_music); remaster after beds.
BEDS_POLICY = "optional_beds_until_remaster"
# Sources that must never auto-open preview_music (operator-only).
_PREVIEW_MUSIC_AUTO_SOURCES = frozenset(
    {"auto", "full_auto", "full-auto", "driver", "homunculus", "daemon", "automation"}
)
# Only the GUI route may open preview_music (FG6: refuse forgeable "operator").
_PREVIEW_MUSIC_ALLOWED_SOURCES = frozenset({"gui"})

# Producers that may land ship-blocking omit under End-A (no silent default).
SHIP_OMIT_PRODUCER_ACTIONS: dict[str, str] = {
    "edl_overlap_repair": "edl_overlap_repair_omit",
    "segment_id_remap": "segment_id_remap_omit",
    "junction_snip_qa": "junction_incomplete_cut_omit",
    "junction": "junction_incomplete_cut_omit",
    # Host CTA prune (End-A packaging — soft freeze only). S7: ranking/sanitize,
    # not nugget_layup_compose.
    "media_ip_cta": "media_ip_cta",
    "full_master_ranking": "media_ip_cta",
    "selection_order_sanitize": "media_ip_cta",
    "media_ip_cta.heal_on_air_cta_residue": "heal_on_air_cta",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_epoch_row(ctx: RunContext) -> dict[str, Any]:
    try:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    except Exception:
        meta = {}
    if not isinstance(meta, dict):
        return {}
    epoch = meta.get("delivery_epoch") if isinstance(meta.get("delivery_epoch"), dict) else {}
    row = epoch.get(SEAT_EPOCH_KEY)
    return dict(row) if isinstance(row, dict) else {}


def _write_epoch_row(ctx: RunContext, row: dict[str, Any]) -> None:
    def _mut(meta: dict[str, Any]) -> None:
        epoch = dict(meta.get("delivery_epoch") or {})
        epoch[SEAT_EPOCH_KEY] = dict(row)
        meta["delivery_epoch"] = epoch

    try:
        ctx.mutate_run_meta(_mut)
    except Exception as exc:
        raise RuntimeError(f"mix_junction_seat_epoch_write_failed:{exc}") from exc


def remaster_owner(ctx: RunContext) -> str:
    """Active remaster owner (``junction`` / ``music_epoch`` / …) or empty."""
    return str(_read_epoch_row(ctx).get("remaster_owner") or "").strip()


def remaster_in_flight(ctx: RunContext) -> bool:
    return bool(remaster_owner(ctx))


def music_epoch_pre_beds_seat(ctx: RunContext) -> bool:
    """True when music_epoch remaster is in flight and assembly predates that stamp.

    Orphan promote can restamp ``.stage_done/mix`` from the speech-first seat
    without ``clear_remaster`` (exec_13183). A remaster land rewrites assembly
    after ``remaster_started_at`` — that seat is allowed to mark_done + clear.
    """
    if remaster_owner(ctx) != "music_epoch":
        return False
    prev = _read_epoch_row(ctx)
    started = str(
        prev.get("remaster_started_at") or prev.get("music_epoch_remaster_at") or ""
    ).strip()
    if not started:
        return True
    try:
        asm = ctx.final_path("master", "assembly.wav")
        if not asm.is_file() or asm.stat().st_size <= 0:
            return True
        asm_ts = datetime.fromtimestamp(asm.stat().st_mtime, tz=timezone.utc)
        # ISO stamps from ``_utc_now`` are timezone-aware.
        start_ts = datetime.fromisoformat(started.replace("Z", "+00:00"))
        if start_ts.tzinfo is None:
            start_ts = start_ts.replace(tzinfo=timezone.utc)
        return asm_ts < start_ts
    except Exception:
        return True


def begin_remaster(ctx: RunContext, *, owner: str = "junction") -> None:
    """Stamp explicit remaster ownership (replaces bare unmarked-mix heuristic)."""
    own = str(owner or "junction").strip() or "junction"
    prev = _read_epoch_row(ctx)
    _write_epoch_row(
        ctx,
        {
            **prev,
            "remaster_owner": own,
            "remaster_started_at": _utc_now(),
            "remaster_cleared_at": "",
            "remaster_failed_at": "",
        },
    )


def clear_remaster(ctx: RunContext) -> None:
    """Clear remaster ownership after a seated mix lands or abandoned remaster."""
    prev = _read_epoch_row(ctx)
    if not prev.get("remaster_owner") and not prev.get("remaster_failed_at"):
        return
    _write_epoch_row(
        ctx,
        {
            **prev,
            "remaster_owner": "",
            "remaster_cleared_at": _utc_now(),
        },
    )


def abandon_remaster(ctx: RunContext, *, reason: str = "") -> None:
    """Clear sticky remaster on budget exhaust / hard abort (no seated land)."""
    prev = _read_epoch_row(ctx)
    _write_epoch_row(
        ctx,
        {
            **prev,
            "remaster_owner": "",
            "remaster_failed_at": _utc_now(),
            "remaster_fail_reason": str(reason or "")[:160],
            "remaster_cleared_at": _utc_now(),
        },
    )


@contextmanager
def remaster_session(ctx: RunContext, *, owner: str = "junction") -> Iterator[None]:
    """Sole remaster entry protocol: stamp owner; clear on seat; keep on soft fail.

    Hard failures (exception): keep owner so junction can retry the same flight.
    Successful return without seating: keep owner + log (caller must reseat).
    Seated mix: clear owner.
    """
    begin_remaster(ctx, owner=owner)
    try:
        yield
    except Exception:
        # Keep remaster_owner for retry; do not zombie-clear mid-ladder.
        raise
    finally:
        try:
            from interview_mux.air_order import mix_outputs_seated

            if mix_outputs_seated(ctx):
                clear_remaster(ctx)
                close_preview_music_gate(ctx)
        except Exception:
            pass


def note_speech_first_mix(ctx: RunContext) -> None:
    """Record that Partial allowed mix before music epoch (beds come later)."""
    prev = _read_epoch_row(ctx)
    if prev.get("speech_first_mix_at"):
        return
    _write_epoch_row(ctx, {**prev, "speech_first_mix_at": _utc_now()})


def beds_deferred_for_mix(ctx: RunContext) -> bool:
    """True while beds may be soft-skipped for first-seat mix (F2).

    Use this for theme/SFX/completeness soft gates — not live
    ``allow_speech_first_mix`` alone (false after seat while stamp remains).
    False once music epoch is complete (remaster must hard-require beds).
    """
    try:
        from interview_mux.delivery_guardrails import music_epoch_complete

        if music_epoch_complete(ctx):
            return False
    except Exception:
        pass
    prev = _read_epoch_row(ctx)
    if prev.get("speech_first_mix_at"):
        return True
    return allow_speech_first_mix(ctx)


def next_delivery_seat(ctx: RunContext) -> str:
    """Always-HAU seating-order SSOT — sole mix-vs-music resume pin (F1/F10/F11).

    Order:
    1. Phase-A / EDL holes
    2. Junction-first when authority requires
    3. Music-complete + speech-first stamp → remaster mix (never speech-first again)
    4. ``allow_speech_first_mix`` → mix
    5. Earliest incomplete music-epoch producer
    6. Mix / junction / finalize
    """
    try:
        from interview_mux.delivery_guardrails import (
            MUSIC_BEFORE_MIX,
            PHASE_A_STAGES,
            music_epoch_complete,
            seed_stage_complete,
        )
    except Exception:
        MUSIC_BEFORE_MIX = (
            "music_palette_compose",
            "sfx_prompt_craft",
            "mmaudio_sfx",
        )
        PHASE_A_STAGES = ()
        music_epoch_complete = lambda _c: False  # noqa: E731
        seed_stage_complete = lambda _c, _s: False  # noqa: E731

    # When Phase A is sealed, do not rewind to hollow audit/producer holes —
    # seating law owns mix↔music from here (path_to_master / premature_cap).
    phase_a_open = True
    try:
        from interview_mux.delivery_guardrails import phase_a_sealed

        phase_a_open = not bool(phase_a_sealed(ctx))
    except Exception:
        phase_a_open = True
    if phase_a_open:
        for sid in PHASE_A_STAGES:
            try:
                if not seed_stage_complete(ctx, sid):
                    return str(sid)
            except Exception:
                continue

    try:
        if not seed_stage_complete(ctx, "edl"):
            return "edl"
    except Exception:
        pass

    demote_hollow_mix_done(ctx)

    try:
        if junction_precedes_mix(ctx):
            return "junction_snip_qa"
    except Exception:
        pass

    prev = _read_epoch_row(ctx)
    speech_stamp = bool(prev.get("speech_first_mix_at"))
    try:
        music_done = bool(music_epoch_complete(ctx))
    except Exception:
        music_done = False

    # F1 / remaster-owed: after music, never jump to junction while beds remaster pending.
    if music_done and (
        speech_stamp or bool(prev.get("preview_era_music_at"))
    ):
        if speech_first_remaster_owed(ctx):
            ensure_speech_first_remaster(ctx)
            return "mix"
        if remaster_owner(ctx) == "music_epoch" or not mix_is_seed_complete(ctx):
            return "mix"
        try:
            if not seed_stage_complete(ctx, "junction_snip_qa"):
                return "junction_snip_qa"
        except Exception:
            return "junction_snip_qa"
        return "master_finalize"

    if allow_speech_first_mix(ctx):
        return "mix"

    for sid in MUSIC_BEFORE_MIX:
        try:
            if not seed_stage_complete(ctx, sid):
                return str(sid)
        except Exception:
            return str(sid)

    if not mix_is_seed_complete(ctx):
        return "mix"
    try:
        if not seed_stage_complete(ctx, "junction_snip_qa"):
            return "junction_snip_qa"
    except Exception:
        return "junction_snip_qa"
    return "master_finalize"


def maybe_remaster_after_music_epoch(ctx: RunContext) -> bool:
    """After music completes post speech-first / preview-era seat, force a bed remaster.

    Returns True when ``begin_remaster(music_epoch)`` was stamped.
    FG4: ``music_epoch`` does **not** force junction-first (see ``junction_precedes_mix``);
    demotes ``.stage_done/mix`` so mix re-lands with beds.
    FG5: also triggers when preview-era music spent before a durable seat update.
    """
    prev = _read_epoch_row(ctx)
    speech_first = bool(prev.get("speech_first_mix_at"))
    preview_era = bool(prev.get("preview_era_music_at"))
    if not speech_first and not preview_era:
        return False
    if remaster_in_flight(ctx):
        return False
    if prev.get("music_epoch_remaster_at"):
        return False
    # Remaster only when a seat already exists that predated beds; otherwise the
    # upcoming first mix folds beds in (no sticky remaster stamp).
    kind = assembly_kind(ctx)
    if kind not in {"seated", "unseated"} and not speech_first:
        return False
    begin_remaster(ctx, owner="music_epoch")
    cur = _read_epoch_row(ctx)
    _write_epoch_row(ctx, {**cur, "music_epoch_remaster_at": _utc_now()})
    # FG4 land path: unmark mix so seed/dispatch re-runs mix with beds.
    try:
        if ctx.is_done("mix"):
            marker = ctx.final_path(".stage_done", "mix")
            if marker.is_file():
                marker.unlink()
    except Exception:
        pass
    try:
        ctx.log(
            "seat_authority: music epoch complete after speech-first/preview-era — "
            "remaster_owner=music_epoch (mix re-land)",
            level="info",
            stage="mix",
        )
    except Exception:
        pass
    return True


def speech_first_remaster_owed(ctx: RunContext) -> bool:
    """True when speech-first/preview-era beds remaster has not finished after music.

    Prevents junction/finalize from clearing ``mix_epoch_block`` while the
    speech-only seat still needs a bed remaster land.
    """
    prev = _read_epoch_row(ctx)
    speech_first = bool(prev.get("speech_first_mix_at"))
    preview_era = bool(prev.get("preview_era_music_at"))
    if not speech_first and not preview_era:
        return False
    try:
        from interview_mux.delivery_guardrails import music_epoch_complete

        if not music_epoch_complete(ctx):
            return False
    except Exception:
        return False
    if remaster_owner(ctx) == "music_epoch":
        return True
    if not prev.get("music_epoch_remaster_at"):
        if speech_first:
            return True
        return assembly_kind(ctx) in {"seated", "unseated"}
    return False


def ensure_speech_first_remaster(ctx: RunContext) -> bool:
    """Stamp music-epoch remaster when owed; return True if remaster still owed."""
    if not speech_first_remaster_owed(ctx):
        return False
    prev = _read_epoch_row(ctx)
    if remaster_owner(ctx) != "music_epoch" and not prev.get("music_epoch_remaster_at"):
        maybe_remaster_after_music_epoch(ctx)
    # Land Honesty: demote hollow mix whenever remaster is still owed (not only
    # pre-beds mtime) so orphan promote cannot restamp without clear_remaster.
    if remaster_in_flight(ctx) or speech_first_remaster_owed(ctx):
        demote_hollow_mix_done(ctx)
    return speech_first_remaster_owed(ctx)


def clear_mix_epoch_for_speech_first(ctx: RunContext) -> bool:
    """FG2-safe clear for ``mix_epoch_block(stage=\"mix\")`` only.

    Sole guardrails entry for speech-first mix epoch clear — do not import
    ``allow_speech_first_mix`` into delivery_guardrails for this path.
    """
    if not allow_speech_first_mix(ctx):
        return False
    note_speech_first_mix(ctx)
    return True


def note_preview_era_music(ctx: RunContext) -> None:
    """FG5: stamp that music spent while heard-assembly was still light/preview."""
    if assembly_kind(ctx) == "seated":
        return
    if not preview_music_gate_open(ctx):
        return
    prev = _read_epoch_row(ctx)
    if prev.get("preview_era_music_at"):
        return
    _write_epoch_row(ctx, {**prev, "preview_era_music_at": _utc_now()})


def assembly_kind(ctx: RunContext) -> Literal["none", "preview", "seated", "unseated"]:
    """Classify what assembly audio exists relative to the live EDL."""
    has_final = False
    try:
        has_final = ctx.artifact_exists("master/assembly.wav")
    except Exception:
        has_final = False
    has_preview = False
    try:
        has_preview = ctx.artifact_exists("master/assembly_preview.wav")
    except Exception:
        has_preview = False
    if not has_final and not has_preview:
        return "none"
    if has_final:
        try:
            from interview_mux.air_order import mix_outputs_seated

            if mix_outputs_seated(ctx):
                return "seated"
        except Exception:
            pass
        return "unseated"
    return "preview"


def live_incomplete_cuts(ctx: RunContext) -> bool:
    try:
        from interview_mux.junction_snip_qa import live_incomplete_cut_critical_findings

        return bool(live_incomplete_cut_critical_findings(ctx))
    except Exception:
        return False


def assembly_stale(ctx: RunContext) -> bool:
    try:
        from interview_mux.air_order import mix_stale_versus_live

        return bool(mix_stale_versus_live(ctx))
    except Exception:
        try:
            return assembly_kind(ctx) in {"none", "preview"} or (
                ctx.artifact_exists("master/assembly_preview.wav")
                and not ctx.artifact_exists("master/assembly.wav")
            )
        except Exception:
            return False


def must_verify_commitment(ctx: RunContext) -> bool:
    """A5 law: require commitment checks whenever final assembly.wav exists."""
    try:
        return bool(ctx.artifact_exists("master/assembly.wav"))
    except Exception:
        return False


def preview_music_gate_open(ctx: RunContext) -> bool:
    """True when the operator explicitly opened HAU preview_music spend.

    FG1: openness is the boolean ``preview_music`` flag only — cleared stamps
    must not leave a sticky ``preview_music_at`` that re-opens the gate.
    """
    row = _read_epoch_row(ctx)
    return bool(row.get("preview_music"))


def open_preview_music_gate(
    ctx: RunContext, *, source: str = ""
) -> bool:
    """Open preview_music so music may admit against a light/preview heard-assembly.

    FG6: only ``source="gui"`` (GUI milestone route) may open. Auto / forged
    ``operator`` labels are refused in every mode.
    Returns True when the gate is open after this call.
    """
    src = str(source or "").strip().lower()
    if src in _PREVIEW_MUSIC_AUTO_SOURCES or src not in _PREVIEW_MUSIC_ALLOWED_SOURCES:
        try:
            ctx.log(
                f"hau: refuse preview_music open (source={src or 'missing'})",
                level="warning",
                stage="mix",
            )
        except Exception:
            pass
        return preview_music_gate_open(ctx)
    if preview_music_gate_open(ctx):
        return True
    prev = _read_epoch_row(ctx)
    _write_epoch_row(
        ctx,
        {
            **prev,
            "preview_music": True,
            "preview_music_at": _utc_now(),
            "preview_music_source": src,
            "preview_music_cleared_at": "",
        },
    )
    note_preview_era_music(ctx)
    try:
        ctx.log(
            f"hau: preview_music gate opened (source={src})",
            level="info",
            stage="mix",
        )
    except Exception:
        pass
    return True


def close_preview_music_gate(ctx: RunContext) -> None:
    """Clear preview_music after a seated mix lands (FG1: clear at + flag)."""
    prev = _read_epoch_row(ctx)
    if not prev.get("preview_music") and not prev.get("preview_music_at"):
        return
    _write_epoch_row(
        ctx,
        {
            **prev,
            "preview_music": False,
            "preview_music_at": "",
            "preview_music_cleared_at": _utc_now(),
        },
    )


def may_admit_music(ctx: RunContext) -> bool:
    """Whether MusicGen / SFX / MMAudio may spend against heard-assembly.

    HAU federal (Partial + Full-auto): seated ``assembly.wav`` **or** explicit
    GUI ``preview_music`` gate. Preview WAV alone never admits.
    """
    if assembly_kind(ctx) == "seated":
        return True
    if not preview_music_gate_open(ctx):
        return False
    note_preview_era_music(ctx)
    return True


def music_admit_block_reason(ctx: RunContext) -> str:
    """Empty when music may admit; else a stable pin reason for defer/logs."""
    if may_admit_music(ctx):
        return ""
    kind = assembly_kind(ctx)
    if kind == "none":
        return "assembly_missing"
    if kind == "preview":
        return "assembly_preview_only"
    if kind == "unseated":
        return "assembly_not_seated_for_music"
    return "assembly_not_ready_for_music"


def allow_speech_first_mix(ctx: RunContext) -> bool:
    """HAU ``optional_beds_until_remaster``: mix may seat before music admits.

    Federal for Partial + Full-auto so seated-only music admit cannot deadlock
    mix. FG3: requires preview or unseated assembly — never ``none``.
    When preview_music is open, music may run first — no speech-first bypass.
    """
    if may_admit_music(ctx):
        return False
    return assembly_kind(ctx) in {"preview", "unseated"}


def hold_speech_first_mix(ctx: RunContext, resume: str) -> bool:
    """True when a mix resume must hold speech-first (not yank to MusicGen).

    Sole resume/heal hold API — callers must not use raw ``allow_speech_first_mix``.
    Soft theme/SFX gates use ``beds_deferred_for_mix`` instead.
    """
    return str(resume or "").strip() == "mix" and allow_speech_first_mix(ctx)


def heard_assembly(ctx: RunContext) -> dict[str, Any]:
    """One heard-assembly SSOT — preview is light mode of the same seating system.

    Music / mix / junction / finalize should consult this (or ``assembly_kind`` /
    ``mix_outputs_seated``) rather than private ``preview OR assembly`` ORs.
    """
    kind = assembly_kind(ctx)
    path = ""
    if kind in {"seated", "unseated"}:
        path = "master/assembly.wav"
    elif kind == "preview":
        path = "master/assembly_preview.wav"
    return {
        "kind": kind,
        "path": path,
        "light": kind == "preview",
        "seated": kind == "seated",
        "may_admit_music": may_admit_music(ctx),
        "music_admit_block_reason": music_admit_block_reason(ctx),
        "preview_music_gate": preview_music_gate_open(ctx),
        "beds_policy": BEDS_POLICY,
        "must_verify_commitment": must_verify_commitment(ctx),
    }


def junction_precedes_mix(ctx: RunContext) -> bool:
    """True when junction_snip_qa must run ahead of mix (authority SSOT).

    Junction first when:
    - live incomplete-cut criticals exist, or
    - final assembly exists but is stale vs live EDL, or
    - explicit ``remaster_owner`` is set (except ``music_epoch`` — FG4: mix
      re-lands beds; junction must not steal the remaster flight).

    Missing assembly alone does **not** precede — mix mints the first seat.
    Remaster writers must use ``remaster_session`` / ``begin_remaster``.
    """
    try:
        if live_incomplete_cuts(ctx):
            return True
        if remaster_in_flight(ctx):
            if remaster_owner(ctx) == "music_epoch":
                return False
            return True
        if ctx.artifact_exists("master/assembly.wav") and assembly_stale(ctx):
            return True
        return False
    except Exception:
        return False


def who_runs_next(ctx: RunContext) -> WhoRuns:
    return "junction_snip_qa" if junction_precedes_mix(ctx) else "mix"


def mix_is_seed_complete(ctx: RunContext) -> bool:
    """Mix is seed-complete only when seated and remaster land is paid.

    Any remaster_in_flight / speech_first_remaster_owed is never seed-complete
    (Land Honesty — mtime bump alone must not greenwash).
    """
    try:
        if not ctx.is_done("mix"):
            return False
    except Exception:
        return False
    try:
        from interview_mux.done_authority import unpaid_land_reason

        if unpaid_land_reason(ctx, "mix") is not None:
            return False
    except Exception:
        if remaster_in_flight(ctx) or speech_first_remaster_owed(ctx):
            return False
        if music_epoch_pre_beds_seat(ctx):
            return False
    try:
        from interview_mux.air_order import mix_outputs_seated

        return bool(mix_outputs_seated(ctx))
    except Exception:
        return False


def demote_hollow_mix_done(ctx: RunContext) -> bool:
    """Unmark hollow ``.stage_done/mix`` when outputs are not seated / remaster unpaid."""
    try:
        if not ctx.is_done("mix"):
            return False
        if mix_is_seed_complete(ctx):
            return False
        marker = ctx.final_path(".stage_done", "mix")
        if marker.is_file():
            marker.unlink()
        reason = "not mix_outputs_seated"
        try:
            from interview_mux.done_authority import unpaid_land_reason

            unpaid = unpaid_land_reason(ctx, "mix")
            if unpaid:
                reason = unpaid.split(":", 1)[0].strip() or "remaster unpaid"
        except Exception:
            if music_epoch_pre_beds_seat(ctx):
                reason = "music_epoch pre-beds seat"
            elif remaster_in_flight(ctx):
                reason = "remaster in flight"
        try:
            ctx.log(
                f"seat_authority: demoted hollow mix .stage_done ({reason})",
                level="warning",
                stage="mix",
            )
        except Exception:
            pass
        return True
    except Exception:
        return False


def resume_pin(ctx: RunContext) -> str:
    """Facade over air_order.mix_seat_resume_stage (single resume vocabulary)."""
    demote_hollow_mix_done(ctx)
    # HAU: unseated assembly → always mix before music (federal).
    if assembly_kind(ctx) == "unseated":
        return "mix"
    from interview_mux.air_order import mix_seat_resume_stage

    return str(mix_seat_resume_stage(ctx) or "mix")


def read_seat_snapshot(ctx: RunContext) -> dict[str, Any]:
    """Debug / tests: current authority view."""
    hau = heard_assembly(ctx)
    return {
        "assembly_kind": assembly_kind(ctx),
        "heard_assembly": hau,
        "remaster_owner": remaster_owner(ctx),
        "remaster_in_flight": remaster_in_flight(ctx),
        "speech_first_mix_at": str(_read_epoch_row(ctx).get("speech_first_mix_at") or ""),
        "live_incomplete_cuts": live_incomplete_cuts(ctx),
        "assembly_stale": assembly_stale(ctx),
        "junction_precedes_mix": junction_precedes_mix(ctx),
        "who_runs_next": who_runs_next(ctx),
        "may_admit_music": may_admit_music(ctx),
        "music_admit_block_reason": music_admit_block_reason(ctx),
        "must_verify_commitment": must_verify_commitment(ctx),
        "allow_speech_first_mix": allow_speech_first_mix(ctx),
        "beds_deferred_for_mix": beds_deferred_for_mix(ctx),
        "next_delivery_seat": next_delivery_seat(ctx),
        "preview_music_gate": preview_music_gate_open(ctx),
        "beds_policy": BEDS_POLICY,
        "mix_is_seed_complete": mix_is_seed_complete(ctx),
    }
