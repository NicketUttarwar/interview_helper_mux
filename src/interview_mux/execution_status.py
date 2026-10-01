"""Per-run Execution Status Recordkeeper (ESR) — honest progress SSOT for thrash halt.

Pillar A of thrash spine endgame: sticky/forensics/identical/needs_operator consult
``operator/execution_status.json`` before HARD halt. Progress is WAV/asset/mtime/
lease/heartbeat — not hollow ``.stage_done`` alone.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from interview_mux.run_context import RunContext

ESR_REL = "operator/execution_status.json"

# ---------------------------------------------------------------------------
# ESR_POST_MASTER (DP-C1–C4) — shared post-master never-thrash-wait SSOT
# ---------------------------------------------------------------------------
# After committed master + honest finalize, ESR must not thrash-wait on
# fresh:master.wav / ghost VO-MusicGen mtimes / infinite stalled keep-join.
# C5 (pipeline_complete ship-bar) is a separate family.


def pin_in_post_master_family(pin: str) -> bool:
    """C1: pins for which master.wav freshness must not ESR-stall after finalize."""
    pin_s = str(pin or "").strip()
    if not pin_s:
        return False
    try:
        from interview_mux.v2.config import SHIP_AFTER_MASTER

        ship = set(SHIP_AFTER_MASTER)
    except Exception:
        ship = set()
    pin_l = pin_s.lower()
    return pin_s in {
        "mix",
        "junction_snip_qa",
        "master_finalize",
        "listen_delight_audit",
        "listen_delight",
        *ship,
    } or "listen_delight" in pin_l


def committed_master_present(ctx: RunContext) -> bool:
    """Committed master.wav integrity (size floor) — shared C1/C2/C4 gate."""
    try:
        from interview_mux.delivery_invariants import committed_master_integrity_ok

        return bool(committed_master_integrity_ok(ctx))
    except Exception:
        try:
            mp = ctx.final_path("master", "master.wav")
            return mp.is_file() and mp.stat().st_size > 1000
        except Exception:
            return False


def post_master_finalize_honest(ctx: RunContext) -> bool:
    """Honest finalize seed-complete (Done Authority — never bare is_done)."""
    try:
        from interview_mux.done_authority import may_clear_wait

        return bool(may_clear_wait(ctx, "master_finalize"))
    except Exception:
        return False


def post_master_never_wait(ctx: RunContext, pin: str = "") -> bool:
    """C1 law: master committed ∧ finalize honest ∧ pin in post-master family.

    When True, ``should_wait_incomplete_after_conductor`` must return None
    (no ESR wait on fresh master.wav for the wrong pin).
    """
    if not committed_master_present(ctx):
        return False
    if not post_master_finalize_honest(ctx):
        return False
    pin_s = str(pin or "").strip()
    if pin_s and pin_in_post_master_family(pin_s):
        return True
    # No pin: still never-wait when pipeline ship-bar already complete.
    try:
        return bool(pipeline_complete(ctx))
    except Exception:
        return False


def skip_post_master_mtime_lease(ctx: RunContext, *, job_status: str, job_stage: str) -> bool:
    """C4 law: suppress VO/MusicGen mtime leases when stalled/idle/error post-master.

    Footgun #5: never suppress when expensive pending_writes exist or VO/music
    assets landed in the last ~90s (gui_job can lie idle while Chatterbox writes).
    """
    status = str(job_status or "").lower()
    if status not in {"stalled", "idle", "error"}:
        return False
    if not committed_master_present(ctx):
        return False
    # Hold lease if producers are still writing.
    try:
        pending_root = ctx.run_dir / ".pending_writes"
        if pending_root.is_dir():
            for sid in (
                "vo_synthesize",
                "music_palette_compose",
                "mmaudio_sfx",
                "sfx_prompt_craft",
            ):
                p = pending_root / sid
                if p.is_dir() and any(p.rglob("*")):
                    return False
    except Exception:
        pass
    try:
        import time

        now = time.time()
        synth = ctx.final_path("vo_pickup", "synthesized")
        if synth.is_dir():
            for p in synth.glob("*.wav"):
                if p.is_file() and (now - p.stat().st_mtime) < 90.0:
                    return False
        assets = ctx.final_path("sound_design", "assets")
        if assets.is_dir():
            for p in assets.rglob("*.wav"):
                if p.is_file() and (now - p.stat().st_mtime) < 90.0:
                    return False
    except Exception:
        pass
    stage = str(job_stage or "").strip()
    if pin_in_post_master_family(stage) or post_master_finalize_honest(ctx):
        return True
    return False


# Stage-class progress SLAs (seconds) — config may override via thrash_spine.progress_sla.
_DEFAULT_SLA_SEC: dict[str, float] = {
    "vo_synthesize": 180.0,
    "vo_line_adjudicate": 180.0,
    "mmaudio_sfx": 480.0,
    "music_palette_compose": 480.0,
    "sfx_prompt_craft": 480.0,
    "mix": 600.0,
    "junction_snip_qa": 360.0,
    "master_finalize": 600.0,
    "default": 300.0,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cfg_sla(stage: str) -> float:
    try:
        from interview_mux.config import merged_config

        cfg = merged_config() or {}
        spine = cfg.get("thrash_spine") if isinstance(cfg, dict) else {}
        sla = (spine or {}).get("progress_sla") if isinstance(spine, dict) else {}
        if isinstance(sla, dict):
            if stage in sla:
                return float(sla[stage])
            if "default" in sla:
                return float(sla["default"])
    except Exception:
        pass
    return float(_DEFAULT_SLA_SEC.get(stage) or _DEFAULT_SLA_SEC["default"])


def read_execution_status(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists(ESR_REL):
        return {"version": 1}
    try:
        doc = ctx.read_json(ESR_REL)
        return dict(doc) if isinstance(doc, dict) else {"version": 1}
    except Exception:
        return {"version": 1}


def _newest_mtime(paths: list[Any]) -> float:
    newest = 0.0
    for p in paths:
        try:
            if p is not None and getattr(p, "is_file", lambda: False)() and p.is_file():
                newest = max(newest, float(p.stat().st_mtime))
        except Exception:
            continue
    return newest


def _label_is_non_producer_progress(label: str) -> bool:
    """gui_job heartbeat / job_running / wasted_work are not producer progress."""
    s = str(label or "").lower()
    return (
        s.startswith("gui_heartbeat")
        or s.startswith("job_running")
        or s.startswith("wasted:")
    )


def _collect_progress_sources(
    ctx: RunContext, *, pin: str = "", include_heartbeats: bool = True
) -> tuple[list[str], float]:
    """Return (source labels, newest activity epoch seconds).

    When ``pin`` is set, only pin-relevant disk sources count toward freshness
    (plus gui/wasted heartbeats). Unrelated VO/SFX mtimes must not suppress HARD.
    """
    # (label, mtime_epoch) — mtime 0 means heartbeat/busy without a clock
    tagged: list[tuple[str, float]] = []
    pin_s = str(pin or "").strip()

    # VO wavs
    try:
        synth_dir = ctx.final_path("vo_pickup", "synthesized")
        if synth_dir.is_dir():
            wavs = [p for p in synth_dir.glob("*.wav") if p.is_file() and p.stat().st_size > 0]
            if wavs:
                tagged.append(
                    (f"vo_wavs={len(wavs)}", max(p.stat().st_mtime for p in wavs))
                )
    except Exception:
        pass

    # Sound-design / MusicGen / MMAudio assets
    try:
        assets = ctx.final_path("sound_design", "assets")
        if assets.is_dir():
            files = [
                p
                for p in assets.rglob("*")
                if p.is_file()
                and p.suffix.lower() in {".wav", ".json", ".gen.json"}
                or (p.is_file() and p.name.endswith(".gen.json"))
            ]
            # also candidates
            cand = ctx.final_path("sound_design", "assets", "_candidates")
            if cand.is_dir():
                files.extend([p for p in cand.rglob("*.wav") if p.is_file()])
            n = len([p for p in files if p.is_file()])
            if n:
                tagged.append((f"sfx_assets={n}", _newest_mtime(files)))
    except Exception:
        pass

    # Mix / assembly
    for rel in (
        ("master", "assembly.wav"),
        ("master", "assembly_preview.wav"),
        ("master", "master.wav"),
    ):
        try:
            p = ctx.final_path(*rel)
            if p.is_file() and p.stat().st_size > 0:
                tagged.append((rel[-1], p.stat().st_mtime))
        except Exception:
            pass

    # Junction / seam
    for rel in (
        ("master", "seam_autopsy.json"),
        ("operator", "nle_edits.json"),
        ("master", "edl.json"),
    ):
        try:
            p = ctx.run_dir.joinpath(*rel)
            if p.is_file():
                tagged.append((rel[-1], p.stat().st_mtime))
        except Exception:
            pass

    # gui_job heartbeat / wasted_work — telemetry only; never producer progress for HARD halt.
    if include_heartbeats:
        try:
            from interview_mux.write_staging import read_gui_job

            job = read_gui_job(ctx) or {}
            if isinstance(job, dict):
                for key in ("updated_at", "heartbeat_at", "progress_at", "ts"):
                    raw = job.get(key)
                    if not raw:
                        continue
                    try:
                        # ISO or epoch
                        if isinstance(raw, (int, float)):
                            tagged.append(("gui_heartbeat", float(raw)))
                            break
                        s = str(raw).replace("Z", "+00:00")
                        dt = datetime.fromisoformat(s)
                        tagged.append(("gui_heartbeat", dt.timestamp()))
                        break
                    except Exception:
                        continue
                status = str(job.get("status") or "").lower()
                stage = str(job.get("current_stage") or job.get("stage") or "").strip()
                if status in {"running", "starting"} and stage:
                    tagged.append((f"job_running:{stage}", 0.0))
        except Exception:
            pass

        try:
            ww_rel = "operator/wasted_work.json"
            if ctx.artifact_exists(ww_rel):
                ww = ctx.read_json(ww_rel)
                events = list((ww or {}).get("events") or []) if isinstance(ww, dict) else []
                for ev in reversed(events[-8:]):
                    if not isinstance(ev, dict):
                        continue
                    kind = str(ev.get("event") or "")
                    if kind in {
                        "expensive_start",
                        "music_deferred",
                        "orphan_complete",
                        "progress_stall",
                    }:
                        mt = 0.0
                        at = ev.get("at") or ev.get("ts")
                        if at:
                            try:
                                s = str(at).replace("Z", "+00:00")
                                mt = datetime.fromisoformat(s).timestamp()
                            except Exception:
                                pass
                        tagged.append((f"wasted:{kind}", mt))
                        break
        except Exception:
            pass

    # e2e_soft is NOT producer progress — deliberately ignored here

    # Exact pin → freshness family (B2 / C3): never substring ``"vo_" in pin``.
    _VO_WAV_PINS = frozenset(
        {
            "vo_synthesize",
            "vo_line_adjudicate",
            "nugget_layup_compose",
            "nugget_intro_compose",
            "gap_framing_compose",
            "gap_framing_recompose",
            "missing_framing",
            "transitions",
        }
    )
    _SFX_PINS = frozenset(
        {
            "sound_design_plan",
            "sound_design_vo_finalize",
            "sfx_prompt_craft",
            "mmaudio_sfx",
            "music_palette_compose",
            "musicgen_theme",
        }
    )
    _MIX_PINS = frozenset({"mix", "master_finalize", "assembly_preview"})
    _JUNCTION_PINS = frozenset({"junction_snip_qa"})
    _DELIGHT_PINS = frozenset({"listen_delight_audit", "listen_delight"})
    _EDL_NARRATIVE_PINS = frozenset({"edl_narrative_audit", "edl_narrative_remutate"})
    _EDL_PINS = frozenset({"edl", "stages/assembly"})

    def _pin_keeps(label: str) -> bool:
        if not pin_s:
            return True
        if _label_is_non_producer_progress(label):
            # Heartbeats are telemetry; never the sole freshness for a pin.
            return False
        pin_l = pin_s.lower().strip()
        s = label.lower()
        if pin_l in _SFX_PINS or pin_l.startswith("sound_design"):
            return s.startswith("sfx_assets")
        if pin_l in _VO_WAV_PINS:
            return s.startswith("vo_wavs")
        if pin_l in _MIX_PINS:
            return s in {"assembly.wav", "assembly_preview.wav", "master.wav"}
        if pin_l in _DELIGHT_PINS or pin_l.endswith("delight"):
            return s in {
                "assembly.wav",
                "assembly_preview.wav",
                "master.wav",
                "edl.json",
            }
        if pin_l in _JUNCTION_PINS:
            return s in {"seam_autopsy.json", "nle_edits.json", "edl.json"}
        if pin_l in _EDL_PINS:
            return s in {"edl.json", "seam_autopsy.json", "assembly.wav"}
        if pin_l in _EDL_NARRATIVE_PINS or pin_l.startswith("edl_narrative"):
            return s in {"edl_narrative_audit.json", "edl.json"}
        # Unknown pin: artifact sources except VO wavs (VO freshness is VO-pin only).
        return not _label_is_non_producer_progress(label) and not s.startswith("vo_wavs")

    if pin_s:
        kept = [(lab, mt) for lab, mt in tagged if _pin_keeps(lab)]
        if not kept:
            return [], 0.0
        sources = [lab for lab, _ in kept]
        newest = max((mt for _, mt in kept if mt > 0), default=0.0)
        return sources, newest

    if not include_heartbeats:
        tagged = [(lab, mt) for lab, mt in tagged if not _label_is_non_producer_progress(lab)]
    sources = [lab for lab, _ in tagged]
    newest = max((mt for _, mt in tagged if mt > 0), default=0.0)
    return sources, newest


def progress_stale(
    ctx: RunContext,
    *,
    pin: str = "",
    lease_active: bool | None = None,
    predicate_token: str = "",
    prior_token: str = "",
) -> tuple[bool, str]:
    """True when HARD halt/count is allowed (no fresh producer progress)."""
    pin_s = str(pin or "").strip()
    if lease_active is None:
        try:
            from interview_mux.thrash_hardening import expensive_stage_lease_active

            lease_active, lease_stage = expensive_stage_lease_active(ctx)
            if lease_active:
                return False, f"lease:{lease_stage}"
        except Exception:
            lease_active = False
    elif lease_active:
        return False, "lease"

    tok = str(predicate_token or "").strip()
    prior = str(prior_token or "").strip()
    if tok and prior and tok != prior:
        return False, "predicate_flipped"

    # Halt honesty: ignore gui_heartbeat / job_running / wasted_* (retry loops
    # stamp gui_job and look "fresh" forever — exec_11559 EDL thrash).
    sources, newest = _collect_progress_sources(
        ctx, pin=pin_s, include_heartbeats=False
    )
    sla = _cfg_sla(pin_s or "default")
    now = time.time()
    if newest and (now - newest) < sla:
        return False, f"fresh:{','.join(sources[:4])}"

    # Hollow done: incompleteness still present → treat as not progress
    if pin_s:
        try:
            from interview_mux.stage_completion import stage_artifact_incompleteness

            inc = stage_artifact_incompleteness(ctx, pin_s)
            if inc:
                # incomplete + no fresh disk → stale (allow halt)
                return True, f"incomplete:{inc[:80]}"
        except Exception:
            pass
        # Seed-complete pin + committed master → not producer progress (WS5).
        try:
            from interview_mux.delivery_guardrails import seed_stage_complete

            if seed_stage_complete(ctx, pin_s) and ctx.final_path(
                "master", "master.wav"
            ).is_file():
                return True, "done_pin_committed_master"
        except Exception:
            pass

    if not sources and not newest:
        return True, "no_progress_sources"
    return True, f"stale_after_{int(sla)}s"


def wait_vs_halt(
    ctx: RunContext,
    *,
    pin: str = "",
    intent: str = "",
    reason: str = "",
    predicate_token: str = "",
    prior_token: str = "",
) -> dict[str, Any]:
    """Shared decision: wait (producer active) vs allow HARD halt/count.

    Used by driver, pipeline, agenda, and web runner.
    """
    from interview_mux.thrash_hardening import (
        expensive_stage_lease_active,
        stage_predicate_token,
    )

    pin_s = str(pin or "").strip()
    lease_on, lease_stage = expensive_stage_lease_active(ctx)
    tok = predicate_token or (stage_predicate_token(ctx, pin_s) if pin_s else "")
    stale, why = progress_stale(
        ctx,
        pin=pin_s,
        lease_active=lease_on,
        predicate_token=tok,
        prior_token=prior_token,
    )
    decision = "halt" if stale else "wait"
    row = {
        "decision": decision,
        "pin": pin_s,
        "intent": str(intent or "")[:80],
        "reason": str(reason or "")[:200],
        "lease_active": bool(lease_on),
        "lease_stage": lease_stage or "",
        "progress_stale": bool(stale),
        "why": why,
        "predicate_token": tok[:240],
    }
    try:
        sync_execution_status(
            ctx,
            pin=pin_s,
            intent=intent,
            predicate_token=tok,
            extra={"wait_vs_halt": row},
        )
    except Exception:
        pass
    return row


def may_hard_halt(
    ctx: RunContext,
    *,
    pin: str = "",
    predicate_token: str = "",
    prior_token: str = "",
) -> bool:
    """False while ESR says progress is fresh — do not escalate HARD.

    Fail-closed for HARD: on ESR errors return False (wait) rather than halt.
    """
    try:
        decision = wait_vs_halt(
            ctx,
            pin=pin,
            predicate_token=predicate_token,
            prior_token=prior_token,
        )
        return decision.get("decision") == "halt"
    except Exception:
        return False


def sync_execution_status(
    ctx: RunContext,
    *,
    pin: str = "",
    intent: str = "",
    remaining_head: list[str] | None = None,
    predicate_token: str = "",
    sticky: dict[str, Any] | None = None,
    forensics: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write/update ``operator/execution_status.json`` and fold into execution_health."""
    from interview_mux.thrash_hardening import (
        expensive_stage_lease_active,
        stage_predicate_token,
    )

    prev = read_execution_status(ctx)
    pin_s = str(pin or prev.get("current_pin") or "").strip()
    lease_on, lease_stage = expensive_stage_lease_active(ctx)
    tok = str(predicate_token or "").strip()
    if not tok and pin_s:
        tok = stage_predicate_token(ctx, pin_s)
    sources, newest = _collect_progress_sources(ctx, pin=pin_s)
    stale, why = progress_stale(
        ctx,
        pin=pin_s,
        lease_active=lease_on,
        predicate_token=tok,
        prior_token=str(prev.get("predicate_token") or ""),
    )

    # Seat freeze snapshot
    seat_freeze: dict[str, Any] = {}
    try:
        from interview_mux.seat_authority import read_seat_freeze

        seat_freeze = read_seat_freeze(ctx)
    except Exception:
        seat_freeze = dict(prev.get("seat_freeze") or {}) if isinstance(prev.get("seat_freeze"), dict) else {}

    job_status = ""
    job_stage = ""
    heartbeat_age_s: float | None = None
    try:
        from interview_mux.write_staging import read_gui_job

        job = read_gui_job(ctx) or {}
        if isinstance(job, dict):
            job_status = str(job.get("status") or "")
            job_stage = str(job.get("current_stage") or job.get("stage") or "")
            if newest:
                heartbeat_age_s = max(0.0, time.time() - newest)
    except Exception:
        pass

    last_progress_at = prev.get("last_progress_at") or ""
    if not stale or (tok and tok != str(prev.get("predicate_token") or "")):
        last_progress_at = _utc_now()
    elif newest and (time.time() - newest) < _cfg_sla(pin_s or "default"):
        last_progress_at = _utc_now()

    row: dict[str, Any] = {
        "version": 1,
        "run_id": getattr(ctx, "run_id", "") or "",
        "updated_at": _utc_now(),
        "current_pin": pin_s,
        "intent": str(intent or prev.get("intent") or "")[:80],
        "remaining_head": list(remaining_head)[:12]
        if remaining_head is not None
        else list(prev.get("remaining_head") or [])[:12],
        "predicate_token": tok[:240],
        "last_progress_at": last_progress_at,
        "progress_sources": sources[:16],
        "progress_stale": bool(stale),
        "progress_why": why,
        "sticky": sticky if sticky is not None else (prev.get("sticky") or {}),
        "forensics": forensics if forensics is not None else (prev.get("forensics") or {}),
        "lease": {
            "stage": lease_stage or "",
            "active": bool(lease_on),
            "reason": "gui_or_disk" if lease_on else "",
        },
        "job": {
            "status": job_status,
            "stage": job_stage,
            "heartbeat_age_s": heartbeat_age_s,
        },
        "seat_freeze": seat_freeze,
        "reopen_gate": prev.get("reopen_gate") or {},
        "blocker_class": "" if not stale else str(prev.get("blocker_class") or why)[:120],
        "blocker_human": ""
        if not stale
        else f"progress stale ({why})"[:200],
    }
    if extra:
        row.update({k: v for k, v in extra.items() if k not in row})

    try:
        ctx.write_json(ESR_REL, row, skip_handoff=True)
    except Exception:
        pass

    # Fold summary into execution_health for GUI resilience
    try:
        from interview_mux.remediation_framework import update_execution_health

        update_execution_health(
            ctx,
            consumer_stage=pin_s or job_stage,
            error_class=str((forensics or {}).get("class") or "")[:80],
            remediation_in_progress=bool(lease_on) and not stale,
            automated_blocker="" if not stale else why[:120],
            esr_summary={
                "progress_stale": bool(stale),
                "lease_active": bool(lease_on),
                "predicate_token": tok[:120],
                "progress_sources": sources[:8],
            },
        )
    except TypeError:
        # Older signature without esr_summary
        try:
            from interview_mux.remediation_framework import update_execution_health

            update_execution_health(
                ctx,
                consumer_stage=pin_s or job_stage,
                remediation_in_progress=bool(lease_on) and not stale,
                automated_blocker="" if not stale else why[:120],
            )
        except Exception:
            pass
    except Exception:
        pass

    return row


def note_reopen_gate_decision(ctx: RunContext, decision: dict[str, Any]) -> None:
    """Stamp last timeline/seat reopen gate decision onto ESR."""
    prev = read_execution_status(ctx)
    prev["reopen_gate"] = {
        "at": _utc_now(),
        "allow": bool(decision.get("allow")),
        "intent": str(decision.get("intent") or "")[:80],
        "expected_gain": decision.get("expected_gain"),
        "refuse_reason": str(decision.get("refuse_reason") or "")[:200],
        "decision_id": str(decision.get("decision_id") or "")[:64],
    }
    try:
        ctx.write_json(ESR_REL, prev, skip_handoff=True)
    except Exception:
        pass


def _package_ready_envelope(ctx: RunContext) -> bool:
    """HPUB-2 package envelope for *stage* seed — ready:true or honest skipped:true."""
    if not ctx.artifact_exists("publish/package_ready.json"):
        return False
    try:
        doc = ctx.read_json("publish/package_ready.json")
    except Exception:
        return False
    if not isinstance(doc, dict):
        return False
    if doc.get("ready") is True:
        return True
    return doc.get("skipped") is True


def _package_ready_for_ship_bar(ctx: RunContext) -> bool:
    """C5 footgun #2: Partial DONE requires ready:true — Skip alone is not DONE."""
    if not ctx.artifact_exists("publish/package_ready.json"):
        return False
    try:
        doc = ctx.read_json("publish/package_ready.json")
    except Exception:
        return False
    if not isinstance(doc, dict):
        return False
    return doc.get("ready") is True


def pipeline_complete(ctx: RunContext) -> bool:
    """C5 ship-bar SSOT — local package DONE for Partial / unattended close.

    Required on disk:
    - committed ``master/master.wav`` (integrity floor)
    - ``publish/cover.jpg|png`` + ``publish/audio.mp3``
    - ``publish/package_ready.json`` with ``ready:true``

    ``skipped:true`` may seed-complete ``podcast_publish`` (HPUB) but is **not**
    Partial DONE — operator intentionally declined a local package.

    Stage markers alone are not enough (hollow ``.stage_done`` refused).

    **Not** this bar (separate operator surfaces):
    - G-Publish / S3 upload consent
    - ``g_publish_cleared`` / remote sync success
    - ESR wait rows / agenda remaining lists (those *consult* this bar)
    """
    if not committed_master_present(ctx):
        return False
    try:
        pub = ctx.final_path("publish")
    except Exception:
        return False
    cover_ok = (pub / "cover.jpg").is_file() or (pub / "cover.png").is_file()
    mp3_ok = (pub / "audio.mp3").is_file()
    if not cover_ok or not mp3_ok:
        return False
    if not _package_ready_for_ship_bar(ctx):
        return False
    return package_bound_to_current_master(ctx)


def package_bound_to_current_master(ctx: RunContext) -> bool:
    """The package on disk is podcast_publish's product for *this* master.

    A completed run that is re-entered at an earlier stage keeps its publish
    files; they are DONE only while the stage that made them is still done and
    the master they were cut from is still the master on disk. Otherwise the
    engine would skip the final sign-off and report a stale package as the
    run's result (ISSUES 111: every rewind case in the resume harness).
    """
    try:
        if not ctx.is_done("podcast_publish"):
            return False
        pkg = ctx.final_path("publish", "package_ready.json")
        master = ctx.final_path("master", "master.wav")
        return pkg.stat().st_mtime >= master.stat().st_mtime
    except Exception:
        return False


def ship_bar_complete(ctx: RunContext) -> bool:
    """Alias for Partial DONE vocabulary — same SSOT as ``pipeline_complete``."""
    return pipeline_complete(ctx)


def ship_bar_incomplete_reasons(ctx: RunContext) -> list[str]:
    """Operator-facing holes when ``pipeline_complete`` is False (C5 vocabulary)."""
    reasons: list[str] = []
    if not committed_master_present(ctx):
        reasons.append("master_missing_or_thin")
    try:
        pub = ctx.final_path("publish")
    except Exception:
        reasons.append("publish_dir_unavailable")
        return reasons
    if not ((pub / "cover.jpg").is_file() or (pub / "cover.png").is_file()):
        reasons.append("cover_missing")
    if not (pub / "audio.mp3").is_file():
        reasons.append("audio_mp3_missing")
    if not _package_ready_for_ship_bar(ctx):
        reasons.append("package_ready_missing_or_false")
    elif not ctx.is_done("podcast_publish"):
        reasons.append("podcast_publish_not_done")
    elif not package_bound_to_current_master(ctx):
        reasons.append("package_older_than_master")
    return reasons


def g_publish_consent_is_not_ship_bar() -> bool:
    """C5 law: G-Publish / S3 consent must never be folded into ``pipeline_complete``."""
    return True


# Five predicates operators may confuse — only pipeline_complete is Partial DONE.
SHIP_BAR_VOCABULARY: dict[str, str] = {
    "pipeline_complete": "Local ship-bar SSOT (Partial DONE)",
    "ship_after_master_remaining": "Agenda holes after master — work list, not DONE",
    "should_wait / ESR": "Wait-vs-halt; short-circuits when pipeline_complete",
    "runner batch complete": "Job batch finished a slice — not episode DONE",
    "g_publish / S3": "Operator consent / remote sync — never part of ship bar",
}


def stalled_expensive_can_advance(ctx: RunContext, stage: str) -> bool:
    """C2: stalled expensive producer may advance toward ship (never infinite keep-join).

    Pre-master: a done stage that is ESR-stalled must *not* leapfrog into
    ``SHIP_AFTER_MASTER`` (exec_13167: sound_design_vo_finalize → master_transcript_build
    while edl/mix still pending). Ship-after-master advance requires a committed master.

    Done Authority: prefer honest seed-complete over bare ``is_done``.
    """
    from interview_mux.v2.config import SHIP_AFTER_MASTER

    stage_s = str(stage or "").strip()
    master_ok = committed_master_present(ctx)
    left: list[str] = []
    try:
        from interview_mux.homunculus.agenda import ship_after_master_remaining

        left = list(ship_after_master_remaining(ctx) or [])
    except Exception:
        left = []
    done = False
    try:
        from interview_mux.done_authority import may_clear_wait

        done = bool(may_clear_wait(ctx, stage_s)) if stage_s else False
    except Exception:
        # Bare is_done never clears wait / advances (Done Authority).
        done = False
    if done and not master_ok:
        return False
    return done or bool(master_ok and (stage_s in SHIP_AFTER_MASTER or bool(left)))


def stalled_expensive_advance_stage(ctx: RunContext, stage: str) -> str:
    """First ship hole when C2 can advance — but mix seating before ship (footgun #3)."""
    if not stalled_expensive_can_advance(ctx, stage):
        return ""
    # After master: unseated mix must heal before SHIP_AFTER_MASTER leapfrog.
    if committed_master_present(ctx):
        try:
            from interview_mux.air_order import mix_outputs_seated

            if not mix_outputs_seated(ctx):
                return "mix"
        except Exception:
            pass
    try:
        from interview_mux.homunculus.agenda import ship_after_master_remaining

        left = list(ship_after_master_remaining(ctx) or [])
        return str(left[0] or "").strip() if left else ""
    except Exception:
        return ""


def should_wait_incomplete_after_conductor(
    ctx: RunContext,
    *,
    pin: str = "",
    remaining: list[str] | None = None,
) -> dict[str, Any] | None:
    """Shared wait-vs-halt for pipeline / agenda / runner incomplete-after-conductor.

    Returns the wait_vs_halt row when decision is ``wait`` (caller must not HARD
    raise / sticky-halt). Returns None when HARD escalate is allowed.

    ESR_POST_MASTER (C1): when finalize is honestly done and ``master/master.wav``
    is committed, post-family pins (mix/delight/junction/ship) must not ESR-wait
    on fresh master/assembly mtimes — remaining work is ship, not remaster
    (exec_13165). C3: all callers use this helper (never raw wait_vs_halt alone).
    """
    try:
        master_ok = committed_master_present(ctx)
    except Exception:
        master_ok = False
    try:
        if master_ok and pipeline_complete(ctx):
            return None
    except Exception:
        pass
    pin_s = str(pin or "").strip()
    if not pin_s and remaining:
        pin_s = str(remaining[0] or "").strip()
    # Self-lease: incomplete-after-conductor raised while gui_job still says
    # ``running`` for this same pin (homunculus seed-front pin → immediate
    # incomplete). ESR-wait then freezes forever with no chatterbox work
    # (exec_13183 vo_synthesize stall loop).
    try:
        from interview_mux.thrash_hardening import expensive_stage_lease_active

        lease_on, lease_stage = expensive_stage_lease_active(ctx)
        if lease_on and pin_s and lease_stage == pin_s:
            return None
    except Exception:
        pass
    # Don't ESR-wait on sealed consumers that seed-order cannot run yet —
    # mix stalled ≥10m while listen_delight_audit was rem[0] (exec_13181).
    if pin_s in {"mix", "edl", "vo_synthesize", "assembly_preview", "junction_snip_qa"}:
        try:
            from interview_mux.homunculus.agenda import remaining_stages

            rem = [str(s) for s in (remaining_stages(ctx, "delivery") or []) if s]
            if rem and pin_s in rem and rem[0] != pin_s:
                return None
        except Exception:
            pass
    # Done Authority (B5): only honest seed-complete clears wait — never bare is_done.
    if pin_s:
        try:
            from interview_mux.done_authority import may_clear_wait

            if may_clear_wait(ctx, pin_s):
                return None
        except Exception:
            pass
    # C1: post-master family never-wait (shared SSOT).
    if pin_s and post_master_never_wait(ctx, pin_s):
        return None
    if pin_s and master_ok:
        try:
            from interview_mux.done_authority import may_clear_wait

            if may_clear_wait(ctx, pin_s):
                return None
        except Exception:
            pass
    try:
        sync_execution_status(
            ctx,
            pin=pin_s or "delivery",
            intent="incomplete_after_conductor",
            remaining_head=list(remaining or [])[:12],
        )
    except Exception:
        pass
    try:
        row = wait_vs_halt(
            ctx,
            pin=pin_s or "delivery",
            intent="incomplete_after_conductor",
            reason="incomplete_after_conductor",
        )
    except Exception:
        return None
    if row.get("decision") == "wait":
        return row
    return None
