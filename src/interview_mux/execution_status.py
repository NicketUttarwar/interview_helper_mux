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

    def _pin_keeps(label: str) -> bool:
        if not pin_s:
            return True
        if _label_is_non_producer_progress(label):
            # Heartbeats are telemetry; never the sole freshness for a pin.
            return False
        pin_l = pin_s.lower()
        s = label.lower()
        if any(k in pin_l for k in ("vo_", "synthesize", "adjudicate", "layup")):
            return s.startswith("vo_wavs")
        if any(k in pin_l for k in ("music", "mmaudio", "sfx", "sound_design", "palette")):
            return s.startswith("sfx_assets")
        if any(k in pin_l for k in ("mix", "master_finalize", "assembly")):
            return s in {"assembly.wav", "assembly_preview.wav", "master.wav"}
        if "junction" in pin_l or "snip" in pin_l:
            return s in {"seam_autopsy.json", "nle_edits.json", "edl.json"}
        if "edl" in pin_l:
            return s in {"edl.json", "seam_autopsy.json", "assembly.wav"}
        # Unknown pin: real artifact sources only (no heartbeat fallthrough)
        return not _label_is_non_producer_progress(label)

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


def should_wait_incomplete_after_conductor(
    ctx: RunContext,
    *,
    pin: str = "",
    remaining: list[str] | None = None,
) -> dict[str, Any] | None:
    """Shared wait-vs-halt for pipeline / agenda / runner incomplete-after-conductor.

    Returns the wait_vs_halt row when decision is ``wait`` (caller must not HARD
    raise / sticky-halt). Returns None when HARD escalate is allowed.
    """
    pin_s = str(pin or "").strip()
    if not pin_s and remaining:
        pin_s = str(remaining[0] or "").strip()
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
