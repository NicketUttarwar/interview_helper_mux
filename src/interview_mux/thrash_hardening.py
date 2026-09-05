"""Thrash / usability hardening — sticky halt classes, canonical pins, artifact usable.

See plan: thrash_edge_case_hardening (T1–T8). Keeps premature/identical loops
progress-monotonic: same failure class sticks until a named predicate flips.
"""

from __future__ import annotations

from typing import Any

from interview_mux.run_context import RunContext
from interview_mux.v2.config import DELIVERY_ORDER, SHIP_AFTER_MASTER

# Stable premature / identical fail classes (not oscillating stage ids).
FAIL_CLASS_MUSIC_EPOCH = "music_epoch"
FAIL_CLASS_PHASE_A_EDL = "phase_a_edl"
FAIL_CLASS_VO_G1 = "vo_g1"
FAIL_CLASS_MIX_SEAT = "mix_seat"
FAIL_CLASS_FINALIZE = "finalize_inputs"
FAIL_CLASS_DELIVERY_BLOCKED = "delivery_blocked"

PHASE_A_AUDIT_ONLY: frozenset[str] = frozenset({"edl_narrative_audit"})
FORCE_DONE_GUARDED: frozenset[str] = frozenset(
    {
        "vo_synthesize",
        "vo_line_adjudicate",
        "edl",
        "edl_narrative_audit",
        "mix",
        "music_palette_compose",
        "sfx_prompt_craft",
        "mmaudio_sfx",
        "assembly_preview",
        "master_finalize",
    }
)

_SUPPRESS_BUDGET = 3
THRASH_REPORT_REL = "operator/thrash_report.json"
NARRATIVE_AUDIT_CAP = 3
THRASH_WINDOW_SEC = 15 * 60
THRASH_HIT_THRESHOLD = 6


def premature_fail_class(resume: str) -> str:
    """Map a resume stage to a stable thrash class for identical counting."""
    from interview_mux.delivery_guardrails import MIX_EPOCH_CONSUMERS, MUSIC_BEFORE_MIX

    r = str(resume or "").strip()
    if not r:
        return "unknown"
    if r in MUSIC_BEFORE_MIX:
        return FAIL_CLASS_MUSIC_EPOCH
    if r in {"mix", "junction_snip_qa"}:
        return FAIL_CLASS_MIX_SEAT
    if r == "master_finalize" or r in SHIP_AFTER_MASTER:
        return FAIL_CLASS_FINALIZE
    if r in MIX_EPOCH_CONSUMERS:
        return FAIL_CLASS_MUSIC_EPOCH
    if r in {"vo_synthesize", "vo_line_adjudicate", "nugget_layup_compose", "sound_design_vo_finalize"}:
        return FAIL_CLASS_VO_G1
    if r in {
        "edl",
        "edl_narrative_audit",
        "assembly_preview",
        "listen_delight_audit",
        "transitions",
        "topic_coverage_audit",
    }:
        return FAIL_CLASS_PHASE_A_EDL
    return f"stage:{r}"


def premature_fail_key(label: str, resume: str) -> str:
    """Identical-count key by fail class (not oscillating resume stage)."""
    cls = premature_fail_class(resume)
    return f"{label}:premature_complete:{cls}"


def stage_predicate_token(ctx: RunContext, stage: str) -> str:
    """Compact token for predicate-flip detection (seed complete / incompleteness)."""
    from interview_mux.delivery_guardrails import seed_stage_complete

    sid = str(stage or "").strip()
    if not sid:
        return "empty"
    try:
        from interview_mux.stage_completion import stage_artifact_incompleteness

        inc = stage_artifact_incompleteness(ctx, sid)
    except Exception:
        inc = "err"
    done = "1" if ctx.is_done(sid) else "0"
    seed = "1" if seed_stage_complete(ctx, sid) else "0"
    return f"{sid}:{done}:{seed}:{inc or 'ok'}"


def predicate_flipped(ctx: RunContext, stage: str, prior_token: str | None) -> bool:
    """True when stage completeness token changed since last halt record."""
    if not prior_token:
        return True
    return stage_predicate_token(ctx, stage) != str(prior_token)


def clear_thrash_on_predicate_flip(
    ctx: RunContext, *, stage: str = "", prior_token: str | None = None
) -> bool:
    """Clear active thrash report when the stage predicate flipped (heal progressed)."""
    sid = str(stage or "").strip()
    if not sid:
        return False
    if prior_token is not None and not predicate_flipped(ctx, sid, prior_token):
        return False
    if not ctx.artifact_exists(THRASH_REPORT_REL):
        # Still clear if we only have prior from caller and flip detected.
        if prior_token is None:
            return False
    try:
        doc: dict[str, Any] = {"version": 1, "hits": [], "active": None}
        if ctx.artifact_exists(THRASH_REPORT_REL):
            loaded = ctx.read_json(THRASH_REPORT_REL)
            if isinstance(loaded, dict):
                doc = dict(loaded)
        active = doc.get("active")
        if not (isinstance(active, dict) and active.get("active")):
            # No active thrash — optionally still wipe stale hits for this class.
            if prior_token is None:
                return False
        doc["active"] = None
        doc["hits"] = []
        doc["cleared_at"] = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat()
        doc["cleared_stage"] = sid
        ctx.write_json(THRASH_REPORT_REL, doc, skip_handoff=True)
        try:

            def _clear_soft(meta: dict[str, Any]) -> None:
                meta.pop("thrash_pause_recommended", None)
                meta.pop("thrash_pause_pin", None)
                meta.pop("thrash_pause_reason", None)

            if ctx.artifact_exists("run_meta.json"):
                ctx.mutate_run_meta(_clear_soft)
        except Exception:
            pass
        return True
    except Exception:
        return False


def expensive_stage_lease_active(ctx: RunContext) -> tuple[bool, str]:
    """True while an expensive producer is actively running (forbid premature rewrite)."""
    lease_stages = frozenset(
        {
            "mmaudio_sfx",
            "music_palette_compose",
            "sfx_prompt_craft",
            "vo_synthesize",
            "mix",
            "master_finalize",
            "transcribe",
            "audio_preclean",
            "junction_snip_qa",
        }
    )
    try:
        from interview_mux.write_staging import read_gui_job

        job = read_gui_job(ctx) or {}
    except Exception:
        job = {}
    if not isinstance(job, dict):
        return False, ""
    status = str(job.get("status") or "").lower()
    if status not in {"running", "starting"}:
        return False, ""
    stage = str(job.get("current_stage") or job.get("stage") or "").strip()
    if stage in lease_stages:
        return True, stage
    try:
        from interview_mux.delivery_guardrails import EXPENSIVE_STAGES

        if stage in EXPENSIVE_STAGES:
            return True, stage
    except Exception:
        pass
    return False, stage


def canonical_resume_pin(ctx: RunContext, intent: str, *, hint: str = "") -> str:
    """Single producer pin for premature / recovery / interrupted / gate resumes."""
    from interview_mux.delivery_guardrails import (
        MUSIC_BEFORE_MIX,
        _g1_open,
        _music_epoch_producer_pin,
        assembly_wav_present,
        finalize_input_producer_pin,
        promote_complete_orphan_stage_done,
        resolve_vo_synth_seed_resume,
        safe_mix_resume_stage,
        seal_phase_a_if_stable,
        seed_stage_complete,
        vo_synthesize_stability_block,
    )

    intent_l = str(intent or "").strip().lower()
    hint_s = str(hint or "").strip()

    if intent_l in {"music_epoch", "music", FAIL_CLASS_MUSIC_EPOCH}:
        try:
            promote_complete_orphan_stage_done(
                ctx,
                (
                    "edl",
                    "edl_narrative_audit",
                    "assembly_preview",
                    "listen_delight_audit",
                ),
            )
            seal_phase_a_if_stable(ctx)
        except Exception:
            pass
        return _music_epoch_producer_pin(ctx)

    if intent_l in {"mix_seat", "mix", FAIL_CLASS_MIX_SEAT}:
        return safe_mix_resume_stage(ctx)

    if intent_l in {"finalize_inputs", "finalize", "master_finalize", FAIL_CLASS_FINALIZE}:
        return finalize_input_producer_pin(ctx, message=hint_s) or "edl"

    if intent_l in {"vo_g1", "vo", FAIL_CLASS_VO_G1}:
        if not seed_stage_complete(ctx, "nugget_layup_compose"):
            return "nugget_layup_compose"
        if _g1_open(ctx):
            block = vo_synthesize_stability_block(ctx)
            if block == "nugget_layup_compose":
                return "nugget_layup_compose"
            return resolve_vo_synth_seed_resume(block) or "vo_line_adjudicate"
        return hint_s if hint_s in DELIVERY_ORDER else "vo_synthesize"

    if intent_l in {"phase_a", "phase_a_edl", FAIL_CLASS_PHASE_A_EDL}:
        try:
            promote_complete_orphan_stage_done(
                ctx,
                (
                    "edl",
                    "edl_narrative_audit",
                    "assembly_preview",
                    "listen_delight_audit",
                ),
            )
        except Exception:
            pass
        # Skip audit-only consumers when assembly audio already present.
        skip_audit = assembly_wav_present(ctx)
        for sid in DELIVERY_ORDER:
            if sid not in {
                "topic_coverage_audit",
                "narrative_arc_plan",
                "full_master_ranking",
                "nugget_layup_compose",
                "refinement_agenda",
                "air_script_compose",
                "air_script_seams",
                "transitions",
                "vo_line_adjudicate",
                "vo_synthesize",
                "sound_design_vo_finalize",
                "edl_narrative_audit",
                "edl",
                "assembly_preview",
                "listen_delight_audit",
            }:
                continue
            if skip_audit and sid in PHASE_A_AUDIT_ONLY:
                continue
            if not seed_stage_complete(ctx, sid):
                return sid
        return hint_s or "edl"

    if intent_l in {"delivery_blocked", FAIL_CLASS_DELIVERY_BLOCKED}:
        from interview_mux.delivery_guardrails import (
            delivery_stable_for_music,
            music_epoch_complete,
            phase_a_sealed,
        )

        try:
            ensure_phase_a_seal_deadline(ctx)
        except Exception:
            pass
        try:
            promote_complete_orphan_stage_done(ctx)
            seal_phase_a_if_stable(ctx)
        except Exception:
            pass
        if _g1_open(ctx):
            return canonical_resume_pin(ctx, FAIL_CLASS_VO_G1)
        stable, reason = delivery_stable_for_music(ctx)
        if not stable and reason in {
            "layup_incomplete",
            "g1_open",
            "vo_adjudicate_incomplete",
            "edl_incomplete",
            "assembly_missing",
        }:
            if reason == "edl_incomplete":
                return "edl"
            if reason == "assembly_missing":
                return "assembly_preview"
            return canonical_resume_pin(ctx, FAIL_CLASS_VO_G1)
        # Post Phase-A / music path: single ladder to master.wav.
        if phase_a_sealed(ctx) or music_epoch_complete(ctx) or hint_s in PATH_TO_MASTER:
            try:
                return path_to_master_pin(ctx)
            except Exception:
                pass
        if not phase_a_sealed(ctx) or not music_epoch_complete(ctx):
            if hint_s in MUSIC_BEFORE_MIX or not music_epoch_complete(ctx):
                return _music_epoch_producer_pin(ctx)
        if hint_s:
            return premature_cap_via_intent(ctx, hint_s)
        return _music_epoch_producer_pin(ctx)

    if hint_s:
        return premature_cap_via_intent(ctx, hint_s)
    return hint_s or "edl"


def premature_cap_via_intent(ctx: RunContext, resume: str) -> str:
    """Route resume through fail-class intent (no circular import to premature_cap)."""
    cls = premature_fail_class(resume)
    if cls in {
        FAIL_CLASS_MUSIC_EPOCH,
        FAIL_CLASS_MIX_SEAT,
        FAIL_CLASS_FINALIZE,
        FAIL_CLASS_VO_G1,
        FAIL_CLASS_PHASE_A_EDL,
    }:
        return canonical_resume_pin(ctx, cls, hint=resume)
    from interview_mux.delivery_guardrails import seed_stage_complete
    from interview_mux.llm_flow_hardening import _earliest_incomplete_seed_stage

    target = resume if resume in DELIVERY_ORDER else "edl"
    earliest = _earliest_incomplete_seed_stage(ctx, target)
    if earliest:
        return earliest
    if resume and not seed_stage_complete(ctx, resume):
        return resume
    return resume or "edl"


def artifact_usable(
    ctx: RunContext, rel: str, *, consumer: str | None = None
) -> tuple[bool, str]:
    """Exists ≠ usable: stale, fingerprint, VO bind, generation drift, pending-only."""
    path = str(rel or "").replace("\\", "/").lstrip("/")
    if not path:
        return False, "empty_rel"
    seating_consumers = frozenset(
        {"mix", "junction_snip_qa", "master_finalize", "edl", "assembly_preview"}
    )
    consumer_s = str(consumer or "").strip() or None

    try:
        from interview_mux.write_staging import (
            active_stage_id,
            pending_stage_for_path,
            resolve_read_path,
        )

        resolved = resolve_read_path(ctx, path)
    except Exception:
        active_stage_id = None  # type: ignore[assignment]
        pending_stage_for_path = None  # type: ignore[assignment]
        resolved = None

    if resolved is None or not resolved.is_file():
        return False, "missing"

    # Seating consumers need a committed WAV/JSON unless *this* producer is
    # actively staging the write. Leftover pending from a crashed producer must
    # not satisfy mix/edl/finalize completeness.
    final = ctx.final_path(*path.split("/"))
    pending_only = (not final.is_file()) and (".pending_writes" in str(resolved))
    if pending_only and consumer_s in seating_consumers:
        active = None
        pending_sid = None
        try:
            if callable(active_stage_id):
                active = active_stage_id()
            if callable(pending_stage_for_path):
                pending_sid = pending_stage_for_path(ctx, path)
        except Exception:
            pass
        # Producer mid-flush / mid-stage may only have pending — allow.
        if active != consumer_s and pending_sid != consumer_s:
            return False, "pending_only_seating"

    try:
        from interview_mux.artifact_lifecycle import read_stale_guard

        stale_reason = read_stale_guard(
            ctx, path, consumer_stage=str(consumer_s or "delivery")
        )
        if stale_reason:
            return False, f"stale:{stale_reason}"
    except Exception:
        pass
    # JSON _meta.stale
    if path.endswith(".json"):
        try:
            doc = ctx.read_json(path)
            meta = doc.get("_meta") if isinstance(doc, dict) else None
            if isinstance(meta, dict) and meta.get("stale"):
                return False, f"stale_meta:{meta.get('stale_reason') or 'stale'}"
        except Exception:
            pass
    # Fingerprint mismatch
    try:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        fps = (meta or {}).get("artifact_fingerprints") if isinstance(meta, dict) else None
        if isinstance(fps, dict) and path in fps:
            from interview_mux.artifact_lifecycle import content_fingerprint

            live = content_fingerprint(ctx, path)
            if live and str(fps.get(path) or "") and live != str(fps.get(path)):
                return False, "fingerprint_mismatch"
    except Exception:
        pass
    # Assembly seating: meta flag only (never recurse into mix_assembly_seated).
    if path in {"master/assembly.wav", "master/assembly_preview.wav"} and consumer_s in {
        "mix",
        "junction_snip_qa",
        "master_finalize",
    }:
        try:
            meta = (
                ctx.read_json("run_meta.json")
                if ctx.artifact_exists("run_meta.json")
                else {}
            )
            if isinstance(meta, dict) and meta.get("assembly_seating_stale"):
                return False, "assembly_seating_stale"
        except Exception:
            pass
    # Gap skip-stub
    if path == "understanding/gap_report.json":
        try:
            from interview_mux.gap_fill_eligibility import gap_fill_was_skipped

            if gap_fill_was_skipped(ctx):
                doc = ctx.read_json(path)
                lines = (doc or {}).get("interviewer_lines") if isinstance(doc, dict) else None
                if isinstance(lines, list) and not lines:
                    return True, ""  # empty skip-stub is intentional
        except Exception:
            pass
    return True, ""


def assert_may_force_done(ctx: RunContext, stage: str) -> None:
    """Refuse force-done for guarded stages when incompleteness is set."""
    sid = str(stage or "").strip()
    if sid not in FORCE_DONE_GUARDED:
        return
    try:
        from interview_mux.stage_completion import stage_artifact_incompleteness

        reason = stage_artifact_incompleteness(ctx, sid)
    except Exception:
        return
    if reason:
        raise RuntimeError(
            f"refuse force-done {sid}: incompleteness={reason}"
        )


def forensics_suppress_allowed(ctx: RunContext, fail_class: str) -> bool:
    """Per-class suppress budget for needs_operator continues in forensics."""
    return suppress_allowed(ctx, fail_class, source="forensics")


def suppress_allowed(
    ctx: RunContext, fail_class: str, *, source: str = "forensics"
) -> bool:
    """Per-class suppress budget for forensics or homunculus needs_operator continues."""
    cls = str(fail_class or "unknown").strip() or "unknown"
    src = str(source or "forensics").strip() or "forensics"
    rel = "operator/suppress_budget.json"
    doc: dict[str, Any] = {}
    if ctx.artifact_exists(rel):
        try:
            loaded = ctx.read_json(rel)
            if isinstance(loaded, dict):
                doc = dict(loaded)
        except Exception:
            doc = {}
    # Migrate legacy forensics-only file once.
    legacy = "operator/forensics_suppress_budget.json"
    if not doc and src == "forensics" and ctx.artifact_exists(legacy):
        try:
            legacy_doc = ctx.read_json(legacy)
            if isinstance(legacy_doc, dict):
                doc = dict(legacy_doc)
        except Exception:
            pass
    by_src = dict(doc.get("by_source") or {})
    counts = dict(by_src.get(src) or doc.get("classes") or {})
    n = int(counts.get(cls) or 0) + 1
    counts[cls] = n
    by_src[src] = counts
    doc["by_source"] = by_src
    doc["classes"] = counts if src == "forensics" else dict(doc.get("classes") or {})
    doc["updated_at"] = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).isoformat()
    try:
        ctx.write_json(rel, doc, skip_handoff=True)
    except Exception:
        pass
    return n <= _SUPPRESS_BUDGET


def discard_pending_shadows_for_stage(ctx: RunContext, stage: str) -> list[str]:
    """After mark_done: drop pending files that are already committed (true shadows).

    Never rmtree the whole staging tree here — ``mark_done`` often runs *before*
    ``after_stage_write_check`` flush (e.g. ingest). Wiping unflushed pending
    deletes ``ingest/normalized.wav`` and hollow-fails the stage.
    """
    from pathlib import Path

    sid = str(stage or "").strip()
    if not sid:
        return []
    pending_root = Path(ctx.run_dir) / ".pending_writes" / sid
    if not pending_root.is_dir():
        return []
    removed: list[str] = []
    try:
        for src in sorted(pending_root.rglob("*"), reverse=True):
            if not src.is_file():
                continue
            rel = str(src.relative_to(pending_root)).replace("\\", "/")
            final = ctx.final_path(*rel.split("/"))
            if not final.is_file():
                # Still the only copy — leave for flush / approval.
                continue
            try:
                if final.stat().st_size <= 0:
                    continue
            except OSError:
                continue
            try:
                src.unlink()
                removed.append(rel)
            except OSError:
                continue
        # Prune empty dirs left behind (keep root for in-flight writers).
        for dirpath in sorted(pending_root.rglob("*"), reverse=True):
            if dirpath.is_dir():
                try:
                    next(dirpath.iterdir())
                except StopIteration:
                    try:
                        dirpath.rmdir()
                    except OSError:
                        pass
                except OSError:
                    pass
    except Exception:
        pass
    return removed


def fail_class_for_failure(*, stage: str = "", reason: str = "", resume: str = "") -> str:
    """Shared fail class for premature, execute, gate, and ranking counters."""
    text = f"{stage} {reason} {resume}".lower()
    if resume:
        return premature_fail_class(resume)
    if stage:
        cls = premature_fail_class(stage)
        if not cls.startswith("stage:"):
            return cls
    if "music" in text or "mmaudio" in text or "sfx_prompt" in text:
        return FAIL_CLASS_MUSIC_EPOCH
    if "g1" in text or "vo_synth" in text or "vo_line" in text:
        return FAIL_CLASS_VO_G1
    if "finalize" in text or "seam_autopsy" in text or "assembly_ledger" in text:
        return FAIL_CLASS_FINALIZE
    if "mix" in text or "junction" in text:
        return FAIL_CLASS_MIX_SEAT
    if "edl" in text or "narrative" in text or "transition" in text:
        return FAIL_CLASS_PHASE_A_EDL
    return premature_fail_class(stage or resume or "unknown")


def stable_fail_key(label: str, *, stage: str = "", reason: str = "", resume: str = "") -> str:
    cls = fail_class_for_failure(stage=stage, reason=reason, resume=resume)
    return f"{label}:{cls}"


def heal_navigate(
    ctx: RunContext,
    *,
    error: str = "",
    stage: str = "",
    intent: str = "",
) -> dict[str, str]:
    """Single heal navigator: error/stage → intent → canonical pin."""
    text = f"{error} {stage}".lower()
    intent_l = str(intent or "").strip().lower()
    if not intent_l:
        if "music" in text or "mmaudio" in text or "palette" in text:
            intent_l = FAIL_CLASS_MUSIC_EPOCH
        elif "g1" in text or "vo pickup" in text or "vo_synth" in text:
            intent_l = FAIL_CLASS_VO_G1
        elif "seam_autopsy" in text or "assembly_ledger" in text or "finalize" in text:
            intent_l = FAIL_CLASS_FINALIZE
        elif "mix" in text or "assembly" in text and "stale" in text:
            intent_l = FAIL_CLASS_MIX_SEAT
        elif "filter empty" in text or "incomplete after conductor" in text:
            intent_l = FAIL_CLASS_DELIVERY_BLOCKED
        elif stage:
            intent_l = premature_fail_class(stage)
        else:
            intent_l = FAIL_CLASS_DELIVERY_BLOCKED
    # Once music epoch is open/complete, force path-to-master (no narrative rewind).
    try:
        from interview_mux.delivery_guardrails import music_epoch_complete, phase_a_sealed

        if (
            intent_l
            in {
                FAIL_CLASS_MUSIC_EPOCH,
                FAIL_CLASS_MIX_SEAT,
                FAIL_CLASS_FINALIZE,
                FAIL_CLASS_DELIVERY_BLOCKED,
            }
            and (phase_a_sealed(ctx) or music_epoch_complete(ctx))
            and intent_l != FAIL_CLASS_VO_G1
        ):
            # Prefer ladder pin directly for post-music progress.
            if intent_l in {
                FAIL_CLASS_MIX_SEAT,
                FAIL_CLASS_FINALIZE,
                FAIL_CLASS_DELIVERY_BLOCKED,
            } or music_epoch_complete(ctx):
                pin = path_to_master_pin(ctx)
                return {
                    "intent": intent_l,
                    "from_stage": pin,
                    "mode": "delivery" if pin in DELIVERY_ORDER else "analysis",
                }
    except Exception:
        pass
    pin = canonical_resume_pin(ctx, intent_l, hint=stage)
    # Prefer path-to-master over narrative only when narrative is already seed-complete
    # (or absent). Real incomplete/stale narrative still gets a pin.
    if pin == "edl_narrative_audit":
        try:
            from interview_mux.delivery_guardrails import (
                music_epoch_complete,
                phase_a_sealed,
                seed_stage_complete,
            )
            from interview_mux.stage_completion import stage_artifact_incompleteness

            narrative_hole = stage_artifact_incompleteness(ctx, "edl_narrative_audit")
            if (
                (phase_a_sealed(ctx) or music_epoch_complete(ctx))
                and seed_stage_complete(ctx, "edl_narrative_audit")
                and narrative_hole is None
            ):
                pin = path_to_master_pin(ctx)
        except Exception:
            pass
    out = {
        "intent": intent_l,
        "from_stage": pin,
        "mode": "delivery" if pin in DELIVERY_ORDER else "analysis",
    }
    try:
        note_delivery_pin(
            ctx,
            from_stage=pin,
            intent=intent_l,
            reason=str(error or stage or "")[:240],
            source="heal_navigate",
        )
    except Exception:
        pass
    return out

def bump_assembly_seating_generation(ctx: RunContext, reason: str) -> None:
    """Mark mix/preview seating stale so file presence is not enough."""

    def _bump(meta: dict[str, Any]) -> None:
        meta["assembly_seating_generation"] = int(
            meta.get("assembly_seating_generation") or 0
        ) + 1
        meta["assembly_seating_stale"] = True
        meta["assembly_seating_stale_reason"] = str(reason or "")[:200]

    try:
        if ctx.artifact_exists("run_meta.json"):
            ctx.mutate_run_meta(_bump)
    except Exception:
        pass


def demote_incomplete_orphans(ctx: RunContext) -> list[str]:
    """Archive only trivially-empty hard-incomplete orphans.

    Never move live authority while a job is running, an expensive lease is
    active, or downstream master/assembly already exists. Non-empty files get a
    soft ``_meta.orphan_incomplete`` stamp instead of ``shutil.move``.
    """
    import shutil
    from datetime import datetime, timezone
    from pathlib import Path

    from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
    from interview_mux.stage_completion import stage_artifact_incompleteness

    # Never demote mid-flight — destroys the heal target.
    try:
        lease_on, _lease_stage = expensive_stage_lease_active(ctx)
        if lease_on:
            return []
    except Exception:
        pass
    try:
        from interview_mux.write_staging import read_gui_job

        job = read_gui_job(ctx) or {}
        if str((job or {}).get("status") or "").lower() in {
            "running",
            "starting",
            "awaiting_write_approval",
        }:
            return []
    except Exception:
        pass
    # Downstream progress: demoting EDL/VO would thrash finalize/mix.
    if ctx.artifact_exists("master/master.wav") or ctx.artifact_exists(
        "master/assembly.wav"
    ):
        return []

    g3 = (
        "vo_synthesize",
        "edl_narrative_audit",
        "edl",
        "assembly_preview",
        "listen_delight_audit",
        "music_palette_compose",
        "sfx_prompt_craft",
        "mmaudio_sfx",
        "mix",
        "junction_snip_qa",
        "master_finalize",
    )
    demoted: list[str] = []
    stamped: list[str] = []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for sid in g3:
        rel = STAGE_ARTIFACT_DISK_PATHS.get(sid)
        if not rel or not ctx.artifact_exists(rel):
            continue
        if ctx.is_done(sid):
            continue
        try:
            reason = stage_artifact_incompleteness(ctx, sid)
        except Exception:
            reason = "incompleteness_error"
        if reason is None:
            continue
        if not hard_incompleteness_reason(reason):
            continue
        src = ctx.final_path(*rel.split("/"))
        if not src.is_file():
            continue
        if not _artifact_trivially_empty(src, rel):
            # Soft flag only — keep live copy for restore/heal.
            if rel.endswith(".json"):
                try:
                    import json as _json

                    raw = _json.loads(src.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        meta = dict(raw.get("_meta") or {})
                        meta["orphan_incomplete"] = True
                        meta["orphan_incomplete_reason"] = str(reason)[:240]
                        meta["orphan_incomplete_at"] = datetime.now(timezone.utc).isoformat()
                        raw["_meta"] = meta
                        src.write_text(
                            _json.dumps(raw, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8",
                        )
                        stamped.append(sid)
                except Exception:
                    pass
            continue
        dest_dir = (
            Path(ctx.run_dir) / ".archived" / f"incomplete_orphan_{stamp}" / Path(rel).parent
        )
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / Path(rel).name
        try:
            shutil.move(str(src), str(dest))
            demoted.append(sid)
        except Exception:
            continue
    if demoted or stamped:
        try:
            from interview_mux.delivery_guardrails import record_wasted_work

            record_wasted_work(
                ctx,
                event="incomplete_orphan_demoted",
                stage="delivery",
                detail={"stages": demoted[:12], "stamped": stamped[:12]},
            )
        except Exception:
            pass
    return demoted


def _artifact_trivially_empty(path: Any, rel: str) -> bool:
    """True when the on-disk artifact has no usable body (safe to archive)."""
    import json
    from pathlib import Path

    p = Path(path)
    try:
        size = p.stat().st_size
    except OSError:
        return False
    if size <= 64:
        return True
    if not rel.endswith(".json"):
        # Non-trivial WAV/binary — never demote by move.
        return False
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return size <= 64
    if not isinstance(doc, dict):
        return False
    clips = doc.get("clips")
    if isinstance(clips, list) and len(clips) == 0:
        ids = doc.get("ordered_segment_ids")
        if isinstance(ids, list) and len(ids) == 0:
            return True
        if ids is None:
            return True
    lines = doc.get("interviewer_lines")
    if isinstance(lines, list) and len(lines) == 0 and not doc.get("transitions"):
        return True
    transitions = doc.get("transitions")
    if isinstance(transitions, list) and len(transitions) == 0 and clips is None:
        # transitions.json with empty list only
        if set(doc.keys()) <= {"transitions", "version", "_meta"}:
            return True
    return False


def hard_incompleteness_reason(reason: str | None) -> bool:
    """True only for empty/missing hard holes — not soft-stale or fingerprint flake."""
    text = str(reason or "").lower()
    if not text:
        return False
    soft = (
        "stale",
        "fingerprint",
        "deferred_pairs",
        "seating_stale",
        "assembly_seating",
        "pending_only",
        "orphan_incomplete",
    )
    if any(tok in text for tok in soft):
        return False
    hard = (
        "pending",
        "missing",
        "empty",
        "incomplete_error",
        "incompleteness_error",
        "no clips",
        "clips=[]",
    )
    return any(tok in text for tok in hard)


def edl_content_authority_token(edl: dict[str, Any] | None) -> str:
    """Stable token for 'did EDL content change enough to invalidate seating?'."""
    if not isinstance(edl, dict):
        return ""
    order_hash = str(edl.get("order_content_hash") or "")
    ids = edl.get("ordered_segment_ids") or []
    if not isinstance(ids, list):
        ids = []
    clips = edl.get("clips") or []
    n_clips = len(clips) if isinstance(clips, list) else 0
    speech_ids: list[str] = []
    if isinstance(clips, list):
        for c in clips:
            if not isinstance(c, dict):
                continue
            if str(c.get("type") or "") != "speech":
                continue
            speech_ids.append(str(c.get("segment_id") or c.get("id") or ""))
    return f"{order_hash}|{','.join(str(x) for x in ids)}|{n_clips}|{','.join(speech_ids)}"


def maybe_bump_seating_for_edl_rewrite(
    ctx: RunContext,
    *,
    before_token: str,
    after_edl: dict[str, Any] | None,
    source: str,
) -> bool:
    """Bump seating only when EDL authority content changed."""
    after = edl_content_authority_token(after_edl)
    if not after or after == str(before_token or ""):
        return False
    bump_assembly_seating_generation(ctx, f"edl_content:{source}")
    return True


def note_narrative_audit_cycle(ctx: RunContext) -> int:
    """Count consecutive edl_narrative_audit-only delivery cycles; return new count."""
    rel = "operator/narrative_audit_cycle.json"
    doc: dict[str, Any] = {"count": 0}
    if ctx.artifact_exists(rel):
        try:
            loaded = ctx.read_json(rel)
            if isinstance(loaded, dict):
                doc = dict(loaded)
        except Exception:
            pass
    n = int(doc.get("count") or 0) + 1
    doc["count"] = n
    doc["updated_at"] = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).isoformat()
    try:
        ctx.write_json(rel, doc, skip_handoff=True)
    except Exception:
        pass
    return n


def reset_narrative_audit_cycle(ctx: RunContext) -> None:
    rel = "operator/narrative_audit_cycle.json"
    try:
        ctx.write_json(
            rel,
            {"count": 0, "updated_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat()},
            skip_handoff=True,
        )
    except Exception:
        pass


def narrative_audit_cap_exceeded(ctx: RunContext) -> bool:
    rel = "operator/narrative_audit_cycle.json"
    if not ctx.artifact_exists(rel):
        return False
    try:
        doc = ctx.read_json(rel)
        return int((doc or {}).get("count") or 0) >= NARRATIVE_AUDIT_CAP
    except Exception:
        return False


def record_thrash_hit(
    ctx: RunContext,
    *,
    fail_class: str,
    pin: str = "",
    predicate_token: str = "",
    stage: str = "",
) -> dict[str, Any] | None:
    """If same class+token fires too often in a window, write thrash_report and return it."""
    import time

    cls = str(fail_class or "unknown")
    token = str(predicate_token or "")
    now = time.time()
    rel = THRASH_REPORT_REL
    doc: dict[str, Any] = {"version": 1, "hits": []}
    if ctx.artifact_exists(rel):
        try:
            loaded = ctx.read_json(rel)
            if isinstance(loaded, dict):
                doc = dict(loaded)
        except Exception:
            pass
    hits = [h for h in (doc.get("hits") or []) if isinstance(h, dict)]
    hits = [h for h in hits if now - float(h.get("ts") or 0) <= THRASH_WINDOW_SEC]
    hits.append(
        {
            "ts": now,
            "fail_class": cls,
            "pin": pin,
            "predicate_token": token,
            "stage": stage,
        }
    )
    same = [
        h
        for h in hits
        if h.get("fail_class") == cls and str(h.get("predicate_token") or "") == token
    ]
    doc["hits"] = hits[-40:]
    thrash = None
    if len(same) >= THRASH_HIT_THRESHOLD:
        thrash = {
            "active": True,
            "fail_class": cls,
            "pin": pin or same[-1].get("pin") or "",
            "predicate_token": token,
            "hit_count": len(same),
            "window_sec": THRASH_WINDOW_SEC,
            "stage": stage,
            "detected_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
        }
        doc["active"] = thrash
        try:
            from interview_mux.delivery_guardrails import record_wasted_work

            record_wasted_work(
                ctx,
                event="thrash_detected",
                stage=stage or pin or "delivery",
                detail=thrash,
            )
        except Exception:
            pass
        # Soft only: expose thrash in operator/thrash_report.json + wasted_work.
        # Do NOT auto-stamp needs_operator — that false-paused healthy runs when
        # the same fail class retried under an active producer/driver.
        try:

            def _mark_soft(meta: dict[str, Any]) -> None:
                meta["thrash_pause_recommended"] = True
                meta["thrash_pause_pin"] = str(pin or stage or "delivery")[:80]
                meta["thrash_pause_reason"] = (
                    f"thrash:{cls} hits={len(same)} pin={pin or stage}"
                )[:400]

            if not ctx.artifact_exists("run_meta.json"):
                ctx.write_json("run_meta.json", {}, skip_handoff=True)
            ctx.mutate_run_meta(_mark_soft)
        except Exception:
            pass
    else:
        doc["active"] = None
    try:
        ctx.write_json(rel, doc, skip_handoff=True)
    except Exception:
        pass
    return thrash


def thrash_summary(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(THRASH_REPORT_REL):
        return None
    try:
        doc = ctx.read_json(THRASH_REPORT_REL)
    except Exception:
        return None
    if not isinstance(doc, dict):
        return None
    active = doc.get("active")
    return active if isinstance(active, dict) and active.get("active") else None


def wasted_work_summary(ctx: RunContext, *, limit: int = 12) -> dict[str, Any]:
    """Compact wasted_work events for GUI (thrash-relevant only)."""
    rel = "operator/wasted_work.json"
    interesting = {
        "orphan_stage_done_promoted",
        "incomplete_orphan_demoted",
        "music_deferred",
        "premature_cap_hard_pin",
        "thrash_detected",
        "orphan_artifact",
        "phase_seal",
        "refuse_vo_synthesize_rewind",
    }
    out: dict[str, Any] = {"events": [], "counts": {}}
    if not ctx.artifact_exists(rel):
        return out
    try:
        doc = ctx.read_json(rel)
    except Exception:
        return out
    events = doc.get("events") if isinstance(doc, dict) else []
    if not isinstance(events, list):
        return out
    counts: dict[str, int] = {}
    selected: list[dict[str, Any]] = []
    for ev in reversed(events):
        if not isinstance(ev, dict):
            continue
        name = str(ev.get("event") or "")
        if name not in interesting:
            continue
        counts[name] = counts.get(name, 0) + 1
        if len(selected) < limit:
            selected.append(
                {
                    "event": name,
                    "stage": ev.get("stage"),
                    "ts": ev.get("ts") or ev.get("at"),
                    "detail": ev.get("detail") if isinstance(ev.get("detail"), dict) else {},
                }
            )
    out["events"] = list(reversed(selected))
    out["counts"] = counts
    return out


def enforce_job_complete_honesty(ctx: RunContext, job: dict[str, Any]) -> dict[str, Any]:
    """API-layer: status=complete with pre-master or ship-path holes becomes incomplete/error."""
    if not isinstance(job, dict):
        return job
    if str(job.get("status") or "") != "complete":
        return job
    # Soft-complete / reuse / phase-handoff / active driver are not false finishes.
    msg_l = str(job.get("message") or job.get("error") or "").lower()
    if any(
        tok in msg_l
        for tok in (
            "soft-complete",
            "soft complete",
            "reuse",
            "needs_operator",
            "awaiting",
            "write approval",
            "gate",
            "g-publish",
            "g_publish",
            "incomplete after conductor",
            "homunculus",
            "analysis complete",
            "phase handoff",
            "phase-handoff",
        )
    ):
        return job
    # Never mutate honesty while a driver/lease is actively working.
    try:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    except Exception:
        meta = {}
    if isinstance(meta, dict) and (
        meta.get("partial_auto_driver_active")
        or meta.get("partial_auto")
        or meta.get("full_auto")
        or meta.get("automation_driver_active")
    ):
        return job
    if job.get("partial_auto") or job.get("driver_active"):
        return job
    try:
        lease_on, _ = expensive_stage_lease_active(ctx)
        if lease_on:
            return job
    except Exception:
        pass
    if ctx.artifact_exists("master/master.wav"):
        return _enforce_ship_path_honesty(ctx, job)
    # Read-only honesty: do not restore/write artifacts from get_job.
    ship = set(SHIP_AFTER_MASTER)
    try:
        from interview_mux.homunculus.agenda import remaining_stages

        left = remaining_stages(ctx, "delivery")
    except Exception:
        left = []
    # Ship-only remainder after master is a different phase — don't error.
    if left and all(s in ship for s in left):
        return job
    finalize_hole = ""
    try:
        if ctx.artifact_exists("master/assembly.wav"):
            if not ctx.artifact_exists("master/edl.json"):
                finalize_hole = "master/edl.json missing"
            elif not ctx.artifact_exists("master/assembly_ledger.json"):
                finalize_hole = "master/assembly_ledger.json missing"
            # Seam missing alone is soft — junction budget / e2e soft may continue.
    except Exception:
        pass
    pre_master = [s for s in left if s not in ship]
    if not pre_master and not finalize_hole:
        return job
    pin_hint = pre_master[0] if pre_master else "master_finalize"
    nav = heal_navigate(
        ctx,
        error=finalize_hole or "incomplete after conductor",
        stage=pin_hint,
    )
    note_delivery_pin(
        ctx,
        from_stage=nav["from_stage"],
        intent=nav["intent"],
        reason=finalize_hole or "incomplete after conductor",
        source="job_complete_honesty",
    )
    parts = []
    if pre_master:
        parts.append("remaining: " + ", ".join(pre_master[:8]))
    if finalize_hole:
        parts.append(finalize_hole)
    msg = "Delivery incomplete — " + "; ".join(parts) + f"; resume={nav['from_stage']}"
    return {
        **job,
        "status": "error",
        "error": msg,
        "message": msg,
        "stage": nav["from_stage"],
        "current_stage": nav["from_stage"],
        "resume_hint": nav["from_stage"],
        "thrash_intent": nav["intent"],
    }


def _enforce_ship_path_honesty(ctx: RunContext, job: dict[str, Any]) -> dict[str, Any]:
    """When master.wav exists, refuse false 'complete' if encode/PMQ/publish package incomplete."""
    # Operator intentionally parked at G-Publish — not a false finish.
    try:
        meta = (
            ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        )
        if isinstance(meta, dict) and (
            meta.get("g_publish_pending") or meta.get("g_publish_skipped")
        ):
            return job
    except Exception:
        pass

    holes: list[str] = []
    pin = "podcast_encode_mp3"
    try:
        from interview_mux.homunculus.agenda import remaining_stages

        left = [s for s in remaining_stages(ctx, "delivery") if s in set(SHIP_AFTER_MASTER)]
    except Exception:
        left = []

    # Hard PMQ block (publish_allowed False) — resume encode/publish walk.
    try:
        if ctx.artifact_exists("master/post_master_quality.json"):
            pmq = ctx.read_json("master/post_master_quality.json")
            if isinstance(pmq, dict) and pmq.get("publish_allowed") is False:
                holes.append("pmq_not_publishable")
                pin = left[0] if left else "podcast_encode_mp3"
    except Exception:
        pass

    encode_done = ctx.is_done("podcast_encode_mp3")
    has_mp3 = ctx.artifact_exists("publish/audio.mp3") or ctx.artifact_exists(
        "publish/master.mp3"
    )
    if not encode_done and not has_mp3:
        holes.append("publish/audio.mp3 missing")
        pin = "podcast_encode_mp3"
    elif left and not ctx.is_done("podcast_publish"):
        # Remaining ship producers with no skip — false complete.
        holes.append("ship remaining: " + ", ".join(left[:6]))
        pin = left[0]

    if not holes:
        return job

    note_delivery_pin(
        ctx,
        from_stage=pin,
        intent="ship_path",
        reason="; ".join(holes)[:240],
        source="ship_path_honesty",
    )
    msg = "Ship incomplete — " + "; ".join(holes) + f"; resume={pin}"
    return {
        **job,
        "status": "error",
        "error": msg,
        "message": msg,
        "stage": pin,
        "current_stage": pin,
        "resume_hint": pin,
        "thrash_intent": "ship_path",
    }


DELIVERY_PIN_REL = "operator/delivery_pin.json"


def note_delivery_pin(
    ctx: RunContext,
    *,
    from_stage: str,
    intent: str = "",
    reason: str = "",
    source: str = "heal_navigate",
) -> dict[str, Any]:
    """Persist last resume pin for GUI 'why pinned' line."""
    doc = {
        "version": 1,
        "from_stage": str(from_stage or "").strip(),
        "intent": str(intent or "").strip(),
        "reason": str(reason or "")[:400],
        "source": str(source or "heal_navigate"),
        "updated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
    }
    try:
        ctx.write_json(DELIVERY_PIN_REL, doc, skip_handoff=True)
    except Exception:
        pass
    return doc


def delivery_pin_summary(ctx: RunContext) -> dict[str, Any] | None:
    """Live 'why pinned' for GUI: thrash → stamped pin → needs_operator → path-to-master."""
    thrash = thrash_summary(ctx)
    if isinstance(thrash, dict) and thrash.get("active"):
        pin = str(thrash.get("pin") or thrash.get("stage") or "").strip()
        if pin:
            return {
                "from_stage": pin,
                "intent": str(thrash.get("fail_class") or ""),
                "reason": (
                    f"thrash:{thrash.get('fail_class')} "
                    f"hits={thrash.get('hit_count') or '?'}"
                ).strip(),
                "source": "thrash",
            }
    try:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        if isinstance(meta, dict) and meta.get("thrash_pause_recommended"):
            pin = str(meta.get("thrash_pause_pin") or "").strip()
            if pin:
                return {
                    "from_stage": pin,
                    "intent": "thrash",
                    "reason": str(meta.get("thrash_pause_reason") or "thrash_pause_recommended"),
                    "source": "thrash_soft",
                }
    except Exception:
        pass
    stamped: dict[str, Any] | None = None
    if ctx.artifact_exists(DELIVERY_PIN_REL):
        try:
            loaded = ctx.read_json(DELIVERY_PIN_REL)
            if isinstance(loaded, dict) and loaded.get("from_stage"):
                stamped = {
                    "from_stage": str(loaded.get("from_stage") or ""),
                    "intent": str(loaded.get("intent") or ""),
                    "reason": str(loaded.get("reason") or ""),
                    "source": str(loaded.get("source") or "delivery_pin"),
                }
        except Exception:
            stamped = None
    needs_stage = ""
    needs_reason = ""
    try:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        if isinstance(meta, dict) and meta.get("needs_operator"):
            needs_stage = str(meta.get("needs_operator_stage") or "").strip()
            needs_reason = str(meta.get("needs_operator_reason") or "").strip()
    except Exception:
        pass
    if needs_stage:
        return {
            "from_stage": needs_stage,
            "intent": (stamped or {}).get("intent") or "needs_operator",
            "reason": needs_reason or (stamped or {}).get("reason") or "needs_operator",
            "source": "needs_operator",
        }
    if stamped:
        return stamped
    try:
        from interview_mux.delivery_guardrails import music_epoch_complete, phase_a_sealed

        if phase_a_sealed(ctx) or music_epoch_complete(ctx):
            pin = path_to_master_pin(ctx)
            if pin:
                return {
                    "from_stage": pin,
                    "intent": "path_to_master",
                    "reason": "next producer on path to master.wav",
                    "source": "path_to_master",
                }
    except Exception:
        pass
    return None


def vo_done_with_deferred_pairs_ok(ctx: RunContext) -> tuple[bool, str]:
    """Freeze honesty: vo_synthesize may be done with deferred pairs only if freeze exists."""
    try:
        from interview_mux.transition_vo import (
            deferred_transition_pairs,
            read_transitions_pair_freeze,
        )

        deferred = deferred_transition_pairs(ctx)
        if not deferred:
            return True, ""
        if not read_transitions_pair_freeze(ctx):
            return False, "deferred_pairs_without_freeze"
        return True, "deferred_owned_by_mix_last_chance"
    except Exception:
        return True, ""

# --- Progress-to-master ladder (post-music → mix → junction → finalize) ---

PATH_TO_MASTER: tuple[str, ...] = (
    "music_palette_compose",
    "sfx_prompt_craft",
    "mmaudio_sfx",
    "mix",
    "junction_snip_qa",
    "master_finalize",
)
PHASE_A_SEAL_DEADLINE_ATTEMPTS = 5
PROGRESS_STALL_SEC = 20 * 60
JUNCTION_REMASTER_GEN_CAP = 5
# Stages that legitimately sit in `remaining` unchanged while work runs.
_STALL_SAFE_HEAD: frozenset[str] = frozenset(
    {
        "mmaudio_sfx",
        "music_palette_compose",
        "sfx_prompt_craft",
        "vo_synthesize",
        "mix",
        "master_finalize",
        "transcribe",
        "audio_preclean",
        "junction_snip_qa",
    }
)


def path_to_master_pin(ctx: RunContext) -> str:
    """Single post-Phase-A resume ladder toward master.wav — never narrative audit."""
    from interview_mux.delivery_guardrails import (
        MUSIC_BEFORE_MIX,
        assembly_wav_present,
        finalize_input_producer_pin,
        music_epoch_complete,
        seed_stage_complete,
    )
    from interview_mux.heal_routing import mix_assembly_seated

    # Music epoch still open → earliest music producer only.
    if not music_epoch_complete(ctx):
        for sid in MUSIC_BEFORE_MIX:
            if not seed_stage_complete(ctx, sid):
                return sid
        return "mmaudio_sfx"
    # Music sealed: never rewind to edl_narrative_audit / Phase-A consumers.
    if not assembly_wav_present(ctx) or not mix_assembly_seated(ctx):
        return "mix"
    if not seed_stage_complete(ctx, "junction_snip_qa"):
        if not ctx.artifact_exists("master/seam_autopsy.json"):
            return "junction_snip_qa"
        # Junction seed-complete but seam missing → still junction.
        return "junction_snip_qa"
    if not ctx.artifact_exists("master/master.wav"):
        pin = finalize_input_producer_pin(ctx, message="path_to_master")
        if pin in PATH_TO_MASTER or pin in {"edl", "vo_synthesize"}:
            # After music, edl pin only if EDL truly missing (restore first).
            if pin == "edl" and not ctx.artifact_exists("master/edl.json"):
                ensure_finalize_inputs_present(ctx)
                if not ctx.artifact_exists("master/edl.json"):
                    return "edl"
            if pin == "edl":
                return "junction_snip_qa"
            return pin if pin in PATH_TO_MASTER else "master_finalize"
        return "master_finalize"
    return "master_finalize"


def ensure_finalize_inputs_present(
    ctx: RunContext, *, emit_ledger: bool = True
) -> list[str]:
    """Restore archived EDL/ledger/seam/render when live copies missing."""
    restored: list[str] = []
    try:
        from interview_mux.delivery_recovery import restore_master_artifact

        targets = (
            "master/edl.json",
            "master/assembly_ledger.json",
            "master/seam_autopsy.json",
            "master/render_ledger.json",
        )
        for rel in targets:
            if ctx.artifact_exists(rel):
                continue
            try:
                path = restore_master_artifact(ctx, rel, min_bytes=32)
            except Exception:
                path = None
            if path is not None and path.is_file():
                restored.append(rel)
        # Legacy mastering/seam_autopsy → master/seam_autopsy
        if not ctx.artifact_exists("master/seam_autopsy.json"):
            try:
                path = restore_master_artifact(
                    ctx, "mastering/seam_autopsy.json", min_bytes=32
                )
            except Exception:
                path = None
            if path is not None and path.is_file():
                try:
                    import shutil

                    dest = ctx.final_path("master", "seam_autopsy.json")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if not dest.is_file():
                        shutil.copy2(path, dest)
                    restored.append("master/seam_autopsy.json")
                except Exception:
                    pass
    except Exception:
        pass
    if (
        emit_ledger
        and ctx.artifact_exists("master/edl.json")
        and not ctx.artifact_exists("master/assembly_ledger.json")
    ):
        try:
            from interview_mux.assembly_ledger import write_assembly_ledger

            edl = ctx.read_json("master/edl.json")
            write_assembly_ledger(ctx, edl=edl if isinstance(edl, dict) else None)
            if ctx.artifact_exists("master/assembly_ledger.json"):
                restored.append("master/assembly_ledger.json")
        except Exception:
            pass
    return restored


def ensure_phase_a_seal_deadline(ctx: RunContext) -> dict[str, Any]:
    """Promote/repair once toward Phase-A seal; sticky halt after repeated failure.

    Skew class (exec_5402): preview/delight present, Phase A unsealed → music deferred
    → filter empty → false complete. One promote+seal attempt per call; after N
    failed attempts stamp needs_operator with a canonical pin.
    """
    from interview_mux.delivery_guardrails import (
        assembly_wav_present,
        phase_a_sealed,
        promote_complete_orphan_stage_done,
        seal_phase_a_if_stable,
    )

    out: dict[str, Any] = {"sealed": False, "attempted": False, "halt": False, "pin": ""}
    if phase_a_sealed(ctx):
        out["sealed"] = True
        return out
    # Only act when audio evidence of Phase A work exists.
    has_preview = ctx.artifact_exists("master/assembly_preview.wav") or assembly_wav_present(
        ctx
    )
    has_delight = ctx.artifact_exists("mastering/listen_delight_audit.json") or ctx.is_done(
        "listen_delight_audit"
    )
    has_edl = ctx.artifact_exists("master/edl.json")
    if not (has_preview or has_delight or has_edl):
        return out
    rel = "operator/phase_a_seal_deadline.json"
    doc: dict[str, Any] = {"attempts": 0}
    if ctx.artifact_exists(rel):
        try:
            loaded = ctx.read_json(rel)
            if isinstance(loaded, dict):
                doc = dict(loaded)
        except Exception:
            pass
    try:
        promote_complete_orphan_stage_done(
            ctx,
            (
                "edl",
                "edl_narrative_audit",
                "assembly_preview",
                "listen_delight_audit",
            ),
        )
        seal_phase_a_if_stable(ctx)
        out["attempted"] = True
    except Exception as exc:
        out["error"] = str(exc)[:200]
    if phase_a_sealed(ctx):
        out["sealed"] = True
        doc["attempts"] = 0
        doc["sealed_at"] = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat()
        try:
            ctx.write_json(rel, doc, skip_handoff=True)
        except Exception:
            pass
        return out
    # Only count toward deadline when the sole remaining blocker is the seal itself
    # (skew class). Real upstream holes (G1/layup/EDL) must not burn the budget.
    try:
        from interview_mux.delivery_guardrails import delivery_stable_for_music

        _stable, reason = delivery_stable_for_music(ctx)
        if reason not in {"phase_a_unsealed", ""}:
            out["skipped_reason"] = reason
            return out
    except Exception:
        pass
    n = int(doc.get("attempts") or 0) + 1
    doc["attempts"] = n
    doc["updated_at"] = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).isoformat()
    pin = path_to_master_pin(ctx) if has_preview else "edl"
    try:
        from interview_mux.delivery_guardrails import delivery_stable_for_music

        stable, reason = delivery_stable_for_music(ctx)
        if not stable and reason not in {"phase_a_unsealed", ""}:
            pin = canonical_resume_pin(ctx, FAIL_CLASS_PHASE_A_EDL, hint=reason)
    except Exception:
        pass
    out["pin"] = pin
    doc["pin"] = pin
    try:
        ctx.write_json(rel, doc, skip_handoff=True)
    except Exception:
        pass
    if n >= PHASE_A_SEAL_DEADLINE_ATTEMPTS:
        # Soft: record + expose pin for resume — do NOT stamp needs_operator.
        # Hard pause here false-stopped healthy runs mid Phase-A promote.
        out["halt"] = False
        out["soft_deadline"] = True
        try:
            from interview_mux.delivery_guardrails import record_wasted_work

            record_wasted_work(
                ctx,
                event="phase_a_seal_deadline",
                stage=pin or "edl",
                detail=out,
            )
        except Exception:
            pass
    return out


def _job_activity_fresh(ctx: RunContext, *, max_idle_sec: float) -> bool:
    """True when gui_job / log / heartbeat show recent activity (not idle stall)."""
    import time
    from pathlib import Path

    now = time.time()
    try:
        from interview_mux.write_staging import read_gui_job

        job = read_gui_job(ctx) or {}
    except Exception:
        job = {}
    if isinstance(job, dict):
        status = str(job.get("status") or "").lower()
        if status in {"running", "starting", "awaiting_write_approval"}:
            return True
        for key in ("updated_at", "progress_at", "heartbeat_at"):
            raw = job.get(key)
            if not raw:
                continue
            try:
                if isinstance(raw, (int, float)):
                    ts = float(raw)
                else:
                    text = str(raw).replace("Z", "+00:00")
                    from datetime import datetime

                    ts = datetime.fromisoformat(text).timestamp()
                if now - ts < max_idle_sec:
                    return True
            except Exception:
                continue
    # Recent gui_log / operator log writes count as activity.
    for name in ("gui_log.jsonl", "operator_e2e.log"):
        try:
            p = Path(ctx.run_dir) / name
            if p.is_file() and (now - p.stat().st_mtime) < max_idle_sec:
                return True
        except Exception:
            continue
    return False


def note_progress_stall(
    ctx: RunContext,
    *,
    remaining: list[str] | None = None,
    stage: str = "",
) -> dict[str, Any] | None:
    """If remaining unchanged AND job truly idle for PROGRESS_STALL_SEC → soft signal.

    Never pauses while gui_job is running or an expensive head stage is in remaining
    with recent activity. Does not stamp needs_operator (driver/homunculus may still
    resume via returned pin); returns a report only after hard idle.
    """
    import time

    left = [str(s) for s in (remaining or []) if s]
    token = "|".join(left[:24]) or str(stage or "")
    if not token:
        return None
    head = left[0] if left else str(stage or "")
    # Long producers: remaining set often unchanged while work is healthy.
    if head in _STALL_SAFE_HEAD and _job_activity_fresh(ctx, max_idle_sec=PROGRESS_STALL_SEC):
        return None
    if _job_activity_fresh(ctx, max_idle_sec=60.0):
        # Any active/recent job — reset stall clock via token refresh below.
        pass
    rel = "operator/progress_stall.json"
    now = time.time()
    doc: dict[str, Any] = {}
    if ctx.artifact_exists(rel):
        try:
            loaded = ctx.read_json(rel)
            if isinstance(loaded, dict):
                doc = dict(loaded)
        except Exception:
            doc = {}
    prior_token = str(doc.get("token") or "")
    since = float(doc.get("since_ts") or now)
    # Reset clock whenever job is active or remaining set changes.
    if prior_token != token or _job_activity_fresh(ctx, max_idle_sec=90.0):
        doc = {
            "token": token,
            "since_ts": now,
            "stage": stage or head,
            "reset_reason": "activity" if prior_token == token else "token_change",
        }
        try:
            ctx.write_json(rel, doc, skip_handoff=True)
        except Exception:
            pass
        return None
    elapsed = now - since
    doc["updated_at"] = now
    doc["elapsed_sec"] = elapsed
    try:
        ctx.write_json(rel, doc, skip_handoff=True)
    except Exception:
        pass
    if elapsed < PROGRESS_STALL_SEC:
        return None
    # Still don't pause expensive heads without a truly idle job.
    if head in _STALL_SAFE_HEAD:
        try:
            from interview_mux.write_staging import read_gui_job

            st = str((read_gui_job(ctx) or {}).get("status") or "").lower()
            if st in {"running", "starting", "awaiting_write_approval"}:
                return None
        except Exception:
            return None
    pin = path_to_master_pin(ctx) if left else (stage or "delivery")
    stall = {
        "active": True,
        "token": token,
        "elapsed_sec": elapsed,
        "pin": pin,
        "remaining": left[:12],
        "soft": True,
    }
    # Soft only: wasted_work + return pin. No needs_operator stamp.
    try:
        from interview_mux.delivery_guardrails import record_wasted_work

        record_wasted_work(
            ctx, event="progress_stall", stage=pin, detail=stall
        )
    except Exception:
        pass
    return stall


def junction_remaster_budget_ok(ctx: RunContext) -> tuple[bool, int]:
    """Per air-order generation remaster cap (beyond in-stage max_rounds)."""
    gen = 0
    try:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        gen = int((meta or {}).get("assembly_seating_generation") or 0)
    except Exception:
        gen = 0
    rel = "operator/junction_remaster_budget.json"
    doc: dict[str, Any] = {"by_generation": {}}
    if ctx.artifact_exists(rel):
        try:
            loaded = ctx.read_json(rel)
            if isinstance(loaded, dict):
                doc = dict(loaded)
        except Exception:
            pass
    by_gen = dict(doc.get("by_generation") or {})
    key = str(gen)
    n = int(by_gen.get(key) or 0)
    return n < JUNCTION_REMASTER_GEN_CAP, n


def note_junction_remaster(ctx: RunContext) -> int:
    """Increment remaster count for current seating generation; return new count."""
    gen = 0
    try:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        gen = int((meta or {}).get("assembly_seating_generation") or 0)
    except Exception:
        gen = 0
    rel = "operator/junction_remaster_budget.json"
    doc: dict[str, Any] = {"by_generation": {}}
    if ctx.artifact_exists(rel):
        try:
            loaded = ctx.read_json(rel)
            if isinstance(loaded, dict):
                doc = dict(loaded)
        except Exception:
            pass
    by_gen = dict(doc.get("by_generation") or {})
    key = str(gen)
    n = int(by_gen.get(key) or 0) + 1
    by_gen[key] = n
    doc["by_generation"] = by_gen
    doc["updated_at"] = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).isoformat()
    try:
        ctx.write_json(rel, doc, skip_handoff=True)
    except Exception:
        pass
    return n


def music_epoch_sealed_no_delight_rewind(ctx: RunContext) -> bool:
    """True when music epoch stamped complete — do not re-enter listen_delight/music."""
    try:
        from interview_mux.delivery_guardrails import music_epoch_complete, read_delivery_epoch

        epoch = read_delivery_epoch(ctx)
        if epoch.get("music_complete_at") and music_epoch_complete(ctx):
            return True
    except Exception:
        pass
    return False

