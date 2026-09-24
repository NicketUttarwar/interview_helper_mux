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
# TH1b: hollow-force + delivery producers — any force-done must pass
# assert_may_force_done / heal_or_refuse_mark (no parallel hollow list).
FORCE_DONE_GUARDED: frozenset[str] = frozenset(
    {
        "vo_synthesize",
        "vo_line_adjudicate",
        "edl",
        "edl_narrative_audit",
        "mix",
        "junction_snip_qa",
        "music_palette_compose",
        "sfx_prompt_craft",
        "mmaudio_sfx",
        "assembly_preview",
        "master_finalize",
        # A-01: key meaning producers — no hollow force-done.
        # (Not a thrash-oscillation hotspot list; SAP-B5 Q2B: SAP stays here for HU-1.)
        "content_context",
        "source_acoustic_profile",
        "sonic_context_build",
        "delivery_brief_build",
        "soundscape_policy_build",
        "episode_structure_compose",
        "source_topology_build",
        "transcript_review_build",
        "vernacular_segment_sanitize",
        "boundary_detection",
        "content_brief_reanchor",
        "gap_framing_compose",
        "missing_framing",
        "nugget_layup_compose",
        "sound_design_vo_finalize",
        "refinement_agenda",
        "gap_framing_recompose",
        "selection_framing_apply",
        "mastering_research_rollup",
        "mastering_research_routing",
        "mastering_research_waves",
        "mastering_shape_agenda",
        "mastering_shape_candidates",
        "mastering_plan_synthesize",
        "mastering_plan_confirm",
        "episode_cover_generate",
        "podcast_publish",
        "master_transcript_build",
        # Wave 5 R-scan: remaining producers may not hollow-force.
        "talking_points_compose",
        "ideal_cuts_propose",
        "ideal_cuts_materialize",
        "segment_classification",
        "interview_spine_build",
        "audio_probe_build",
        "sound_design_palettes",
        "topic_coverage_audit",
        "narrative_arc_plan",
        "nugget_corpus_mine",
        "information_package_plan",
        "transitions",
        "sound_design_plan",
        "listen_delight_audit",
        "episode_meta_build",
        "episode_cover_prompt_craft",
        "podcast_encode_mp3",
        # Hollow-pass B+ R7: sanitize / air spine MUST_PRECEDE producers
        "air_contract_sanitize",
        "air_script_seams",
        "air_script_compose",
        "selection_order_sanitize",
        "full_master_ranking",
        "gap_report_sanitize",
    }
)

_SUPPRESS_BUDGET = 3
THRASH_REPORT_REL = "operator/thrash_report.json"
STICKY_HEAL_REL = "operator/sticky_heal.json"
NARRATIVE_AUDIT_CAP = 3
THRASH_WINDOW_SEC = 15 * 60
THRASH_HIT_THRESHOLD = 6
# Same pin + unchanged predicate: hard-stop heal re-execute (exec_5409 thrash).
STICKY_HEAL_HALT_AFTER = 3
FAIL_CLASS_INCOMPLETE_AFTER_CONDUCTOR = "incomplete_after_conductor"
FAIL_CLASS_MASTERING_SHAPE_HOLLOW = "mastering_shape_llm_hollow"
MASTERING_SHAPE_LLM_STAGES = frozenset(
    {
        "mastering_shape_agenda",
        "mastering_shape_candidates",
        "mastering_plan_synthesize",
        "mastering_plan_confirm",
    }
)


def premature_fail_class(resume: str) -> str:
    """Map a resume stage to a stable thrash class for identical counting."""
    from interview_mux.delivery_guardrails import MIX_EPOCH_CONSUMERS, MUSIC_BEFORE_MIX

    r = str(resume or "").strip()
    if not r:
        return "unknown"
    if r == FAIL_CLASS_INCOMPLETE_AFTER_CONDUCTOR:
        return FAIL_CLASS_INCOMPLETE_AFTER_CONDUCTOR
    if r in MASTERING_SHAPE_LLM_STAGES:
        return FAIL_CLASS_MASTERING_SHAPE_HOLLOW
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


def resume_producer(ctx: RunContext, pin: str) -> str:
    """Return the live producer for a resume pin, never a blocked consumer."""
    candidate = str(pin or "").strip()
    if candidate == "edl":
        try:
            from interview_mux.edl_narrative_remutate import narrative_audit_blocks_edl

            # Missing audit is a hard producer gate (exec_13159 hollow EDL finish).
            if not ctx.artifact_exists("master/edl_narrative_audit.json"):
                return "edl_narrative_audit"
            if narrative_audit_blocks_edl(ctx):
                return "edl_narrative_audit"
        except Exception:
            pass
    # DP-LAYUP-ADJ A + footgun #1: clamp VO consumers and VO-downstream leapfrogs.
    try:
        from interview_mux.delivery_guardrails import (
            VO_CHAIN_DOWNSTREAM_PINS,
            VO_ORDER_CLAMP_STAGES,
            clamp_resume_through_order,
        )

        if candidate in VO_ORDER_CLAMP_STAGES or candidate in VO_CHAIN_DOWNSTREAM_PINS:
            return clamp_resume_through_order(ctx, candidate)
    except Exception:
        pass
    return candidate


def infrastructure_interrupt_resume_pin(ctx: RunContext) -> str:
    """Furthest safe producer after an infrastructure interruption."""
    try:
        from interview_mux.delivery_invariants import committed_master_integrity_ok

        if committed_master_integrity_ok(ctx):
            from interview_mux.done_authority import honest_finalize_seeded

            return (
                "podcast_publish"
                if honest_finalize_seeded(ctx)
                else "master_finalize"
            )
    except Exception:
        pass
    return path_to_master_pin(ctx)


def premature_fail_key(label: str, resume: str) -> str:
    """Identical-count key by fail class (not oscillating resume stage)."""
    cls = premature_fail_class(resume)
    return f"{label}:premature_complete:{cls}"


def _vo_synth_progress_suffix(ctx: RunContext) -> str:
    """Wav progress so long chatterbox runs flip sticky predicates (not thrash)."""
    try:
        synth_dir = ctx.final_path("vo_pickup", "synthesized")
        if not synth_dir.is_dir():
            return "wavs=0"
        n = sum(1 for p in synth_dir.glob("*.wav") if p.is_file() and p.stat().st_size > 0)
        return f"wavs={n}"
    except Exception:
        return "wavs=?"


def _disk_progress_suffix(ctx: RunContext, stage: str) -> str:
    """Music/SFX/mix/junction/gui progress so long producers flip sticky tokens."""
    import time

    sid = str(stage or "").strip()
    parts: list[str] = []
    try:
        if sid in {
            "mmaudio_sfx",
            "music_palette_compose",
            "sfx_prompt_craft",
            "sound_design_plan",
        }:
            assets = ctx.final_path("sound_design", "assets")
            n = 0
            newest = 0.0
            if assets.is_dir():
                for p in assets.rglob("*"):
                    if not p.is_file():
                        continue
                    if p.suffix.lower() in {".wav", ".json"} or p.name.endswith(".gen.json"):
                        n += 1
                        newest = max(newest, p.stat().st_mtime)
            parts.append(f"sfx={n}")
            # Bucket age (60s) — wall-clock seconds would flip the sticky token every
            # tick and perpetual-reset identical/sticky counts (Pillar A footgun).
            if newest:
                parts.append(f"sfx_age_bucket={int((time.time() - newest) // 60)}")
        if sid in {"mix", "master_finalize", "assembly_preview", "junction_snip_qa"}:
            for name in ("assembly.wav", "assembly_preview.wav", "master.wav"):
                p = ctx.final_path("master", name)
                if p.is_file() and p.stat().st_size > 0:
                    parts.append(f"{name}:{int(p.stat().st_size)}:{int(p.stat().st_mtime)}")
            seam = ctx.final_path("master", "seam_autopsy.json")
            if seam.is_file():
                parts.append(f"seam:{int(seam.stat().st_mtime)}")
            nle = ctx.run_dir / "operator" / "nle_edits.json"
            if nle.is_file():
                parts.append(f"nle:{int(nle.stat().st_mtime)}")
        # gui heartbeat age for any expensive pin
        try:
            from interview_mux.write_staging import read_gui_job

            job = read_gui_job(ctx) or {}
            if isinstance(job, dict) and str(job.get("status") or "").lower() in {
                "running",
                "starting",
            }:
                parts.append(f"job={job.get('current_stage') or job.get('stage') or sid}")
        except Exception:
            pass
    except Exception:
        return "disk=?"
    return ":".join(parts) if parts else "disk=0"


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
    # Hollow done: incompleteness wins over done=1 for progress honesty
    # DETECTION_ONLY_IS_DONE: predicate token fingerprint (not advance/skip).
    done = "1" if ctx.is_done(sid) and not inc else "0"
    seed = "1" if seed_stage_complete(ctx, sid) else "0"
    token = f"{sid}:{done}:{seed}:{inc or 'ok'}"
    # Incomplete-after-conductor pin=vo_synthesize stays "json pending" for many
    # minutes while chatterbox writes vo_pickup/synthesized/*.wav — without a
    # progress signal sticky heal treats that as unchanged thrash (×3 halt).
    if sid in {"vo_synthesize", "vo_line_adjudicate", "sound_design_vo_finalize"}:
        token = f"{token}:{_vo_synth_progress_suffix(ctx)}"
    if sid in {"gap_framing_compose", "optimal_questions"}:
        token = f"{token}:{_gap_compose_progress_suffix(ctx)}"
    if sid in {
        "mmaudio_sfx",
        "music_palette_compose",
        "sfx_prompt_craft",
        "sound_design_plan",
        "mix",
        "master_finalize",
        "assembly_preview",
        "junction_snip_qa",
    }:
        token = f"{token}:{_disk_progress_suffix(ctx, sid)}"
    return token


def _gap_compose_progress_suffix(ctx: RunContext) -> str:
    """R6: identical×3 fingerprint includes high_gap_count + line_count."""
    lines_n = 0
    high_n = 0
    auth = "0"
    try:
        if ctx.artifact_exists("understanding/gap_report.json"):
            doc = ctx.read_json("understanding/gap_report.json")
            if isinstance(doc, dict):
                lines = doc.get("interviewer_lines") or []
                lines_n = len(lines) if isinstance(lines, list) else 0
                auth = "1" if doc.get("nugget_layup_authority") else "0"
    except Exception:
        pass
    try:
        if ctx.artifact_exists("understanding/gap_evaluations.json"):
            evals = ctx.read_json("understanding/gap_evaluations.json")
            if isinstance(evals, dict):
                high_n = sum(
                    1
                    for r in (evals.get("evaluations") or [])
                    if isinstance(r, dict)
                    and str(r.get("severity") or "").lower() == "high"
                )
    except Exception:
        pass
    return f"hg={high_n}:ln={lines_n}:la={auth}"


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
    import time

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
            "assembly_preview",
        }
    )
    try:
        from interview_mux.write_staging import read_gui_job

        job = read_gui_job(ctx) or {}
    except Exception:
        job = {}
    if isinstance(job, dict):
        status = str(job.get("status") or "").lower()
        stage = str(job.get("current_stage") or job.get("stage") or "").strip()
        if status in {"running", "starting"}:
            if stage in lease_stages:
                # Sealed expensive producers must not hold the lease forever when
                # gui_job still says running (exec_13170: VO done → EDL blocked).
                try:
                    from interview_mux.delivery_guardrails import seed_stage_complete

                    if seed_stage_complete(ctx, stage):
                        stage = ""  # fall through — no active lease from sealed stage
                    else:
                        return True, stage
                except Exception:
                    return True, stage
            if stage:
                try:
                    from interview_mux.delivery_guardrails import EXPENSIVE_STAGES

                    if stage in EXPENSIVE_STAGES:
                        try:
                            from interview_mux.delivery_guardrails import (
                                seed_stage_complete,
                            )

                            if seed_stage_complete(ctx, stage):
                                stage = ""
                            else:
                                return True, stage
                        except Exception:
                            return True, stage
                except Exception:
                    pass
            # a10: pending_writes lease only for expensive producers. LLM stages
            # (vo_line_adjudicate) leave orphan pending after LimitExhausted —
            # treating that as an active lease deadlocks ESR wait forever.
            expensive_pending = bool(stage) and stage in lease_stages
            if not expensive_pending and stage:
                try:
                    from interview_mux.delivery_guardrails import EXPENSIVE_STAGES

                    expensive_pending = stage in EXPENSIVE_STAGES
                except Exception:
                    expensive_pending = False
            if stage and expensive_pending:
                try:
                    pending = ctx.run_dir / ".pending_writes" / stage
                    if pending.is_dir() and any(pending.rglob("*")):
                        # Pending after seed-complete is flush residue, not active work.
                        try:
                            from interview_mux.delivery_guardrails import (
                                seed_stage_complete,
                            )

                            if seed_stage_complete(ctx, stage):
                                pass
                            else:
                                return True, stage
                        except Exception:
                            return True, stage
                except Exception:
                    pass
        # WS5: seed-complete stage with idle/stalled job is not an active lease
        # (mtime-only freshness must not block ship forever).
        if stage and status not in {"running", "starting"}:
            try:
                from interview_mux.delivery_guardrails import seed_stage_complete
                from interview_mux.write_staging import pending_writes_active

                pending = False
                try:
                    pending = (ctx.run_dir / ".pending_writes" / stage).is_dir() and any(
                        (ctx.run_dir / ".pending_writes" / stage).rglob("*")
                    )
                except Exception:
                    pending = False
                if seed_stage_complete(ctx, stage) and not pending:
                    return False, ""
            except Exception:
                pass
    # C4-1: suppress VO/MusicGen mtime leases when the job is stalled/idle/error
    # and the pin/context is already post-master/ship. running/starting still holds.
    # SSOT: execution_status.skip_post_master_mtime_lease (ESR_POST_MASTER family).
    skip_mtime_lease = False
    if isinstance(job, dict):
        status_c4 = str(job.get("status") or "").lower()
        stage_c4 = str(job.get("current_stage") or job.get("stage") or "").strip()
        try:
            from interview_mux.execution_status import skip_post_master_mtime_lease

            skip_mtime_lease = bool(
                skip_post_master_mtime_lease(
                    ctx, job_status=status_c4, job_stage=stage_c4
                )
            )
        except Exception:
            skip_mtime_lease = False
    # gui_job can lag on error while chatterbox still writes wavs (forensics thrash).
    # Skip mtime lease when vo_synthesize is already seed-complete (exec_13170).
    if not skip_mtime_lease:
        try:
            from interview_mux.delivery_guardrails import seed_stage_complete

            vo_sealed = seed_stage_complete(ctx, "vo_synthesize")
        except Exception:
            vo_sealed = False
        if not vo_sealed:
            try:
                synth_dir = ctx.final_path("vo_pickup", "synthesized")
                if synth_dir.is_dir():
                    newest = 0.0
                    for p in synth_dir.glob("*.wav"):
                        if p.is_file():
                            newest = max(newest, p.stat().st_mtime)
                    if newest and (time.time() - newest) < 180.0:
                        return True, "vo_synthesize"
            except Exception:
                pass

        # a10: host_tools / MusicGen wav growth even when gui_job stage drifted
        try:
            assets = ctx.final_path("sound_design", "assets")
            newest = 0.0
            if assets.is_dir():
                for p in assets.rglob("*.wav"):
                    if p.is_file():
                        newest = max(newest, p.stat().st_mtime)
            if newest and (time.time() - newest) < 120.0:
                try:
                    from interview_mux.delivery_guardrails import seed_stage_complete

                    if seed_stage_complete(ctx, "music_palette_compose"):
                        pass  # sealed — no mtime lease (F6)
                    else:
                        return True, "music_palette_compose"
                except Exception:
                    return True, "music_palette_compose"
        except Exception:
            pass

    def _producer_may_be_active(*stages: str) -> bool:
        if isinstance(job, dict):
            status = str(job.get("status") or "").lower()
            stage = str(job.get("current_stage") or job.get("stage") or "").strip()
            if status in {"running", "starting", "error"} and stage in stages:
                return True
        for sid in stages:
            try:
                if (ctx.run_dir / ".pending_writes" / sid).is_dir():
                    return True
            except Exception:
                pass
        return False

    # MMAudio / MusicGen asset growth while gui_job lagged
    try:
        if (not skip_mtime_lease) and _producer_may_be_active(
            "mmaudio_sfx", "music_palette_compose", "sfx_prompt_craft"
        ):
            assets = ctx.final_path("sound_design", "assets")
            newest = 0.0
            if assets.is_dir():
                for p in assets.rglob("*"):
                    if p.is_file() and (
                        p.suffix.lower() == ".wav" or p.name.endswith(".gen.json")
                    ):
                        newest = max(newest, p.stat().st_mtime)
            cand = ctx.final_path("sound_design", "assets", "_candidates")
            if cand.is_dir():
                for p in cand.rglob("*.wav"):
                    if p.is_file():
                        newest = max(newest, p.stat().st_mtime)
            if newest and (time.time() - newest) < 300.0:
                try:
                    from interview_mux.delivery_guardrails import seed_stage_complete

                    if seed_stage_complete(ctx, "mmaudio_sfx") and seed_stage_complete(
                        ctx, "music_palette_compose"
                    ):
                        pass  # sealed — no mtime lease (F6)
                    elif not seed_stage_complete(ctx, "mmaudio_sfx"):
                        return True, "mmaudio_sfx"
                    elif not seed_stage_complete(ctx, "music_palette_compose"):
                        return True, "music_palette_compose"
                except Exception:
                    return True, "mmaudio_sfx"
    except Exception:
        pass
    # Mix / assembly growth
    try:
        if _producer_may_be_active("mix", "master_finalize", "assembly_preview"):
            for name in ("assembly.wav", "assembly_preview.wav"):
                p = ctx.final_path("master", name)
                if p.is_file() and (time.time() - p.stat().st_mtime) < 300.0:
                    try:
                        from interview_mux.delivery_guardrails import seed_stage_complete

                        if seed_stage_complete(ctx, "mix"):
                            break
                        return True, "mix"
                    except Exception:
                        return True, "mix"
    except Exception:
        pass
    # Junction remaster / NLE activity
    try:
        if _producer_may_be_active("junction_snip_qa"):
            nle = ctx.run_dir / "operator" / "nle_edits.json"
            if nle.is_file() and (time.time() - nle.stat().st_mtime) < 240.0:
                return True, "junction_snip_qa"
            seam = ctx.final_path("master", "seam_autopsy.json")
            if seam.is_file() and (time.time() - seam.stat().st_mtime) < 240.0:
                return True, "junction_snip_qa"
    except Exception:
        pass
    # Homunculus host_tools MusicGen / MMAudio wav growth
    try:
        if (not skip_mtime_lease) and _producer_may_be_active(
            "mmaudio_sfx", "music_palette_compose", "sfx_prompt_craft"
        ):
            host = ctx.final_path("mastering", "homunculus", "host")
            newest = 0.0
            if host.is_dir():
                for p in host.rglob("*.wav"):
                    if p.is_file():
                        newest = max(newest, p.stat().st_mtime)
            if newest and (time.time() - newest) < 300.0:
                try:
                    from interview_mux.delivery_guardrails import seed_stage_complete

                    if seed_stage_complete(ctx, "music_palette_compose"):
                        pass
                    else:
                        return True, "music_palette_compose"
                except Exception:
                    return True, "music_palette_compose"
    except Exception:
        pass
    return False, ""


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
    from interview_mux.refinement_passes import (
        RETIRED_REFINE_GHOSTS,
        remap_retired_refine_pin,
    )

    intent_l = str(intent or "").strip().lower()
    hint_s = str(hint or "").strip()
    if hint_s in RETIRED_REFINE_GHOSTS:
        return remap_retired_refine_pin(ctx, hint_s)

    if intent_l in {"music_epoch", "music", FAIL_CLASS_MUSIC_EPOCH}:
        from interview_mux.delivery_guardrails import (
            delivery_stable_for_music,
            phase_a_sealed,
        )

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
        # Hard upstream holes → never MusicGen (exec_5409 filter-empty thrash).
        # Seal-only skew (phase_a_unsealed with assembly evidence) stays on music
        # (exec_5402: must not walk back to edl_narrative_audit).
        if not phase_a_sealed(ctx):
            _stable, reason = delivery_stable_for_music(ctx)
            hard_upstream = reason in {
                "layup_incomplete",
                "g1_open",
                "vo_adjudicate_incomplete",
                "edl_incomplete",
                "assembly_missing",
                "layup_escalation_blocking",
            } or (
                isinstance(reason, str) and reason.startswith("stale_upstream:")
            )
            if hard_upstream:
                return canonical_resume_pin(
                    ctx, FAIL_CLASS_DELIVERY_BLOCKED, hint=hint_s
                )
        try:
            from interview_mux.mix_junction_seat import next_delivery_seat

            return next_delivery_seat(ctx)
        except Exception:
            return _music_epoch_producer_pin(ctx)

    if intent_l in {"mix_seat", "mix", FAIL_CLASS_MIX_SEAT}:
        return safe_mix_resume_stage(ctx)

    if intent_l in {"finalize_inputs", "finalize", "master_finalize", FAIL_CLASS_FINALIZE}:
        return finalize_input_producer_pin(ctx, message=hint_s) or "edl"

    if intent_l in {"vo_g1", "vo", FAIL_CLASS_VO_G1}:
        if not seed_stage_complete(ctx, "nugget_layup_compose"):
            try:
                from interview_mux.stage_completion import incompleteness_resume_stage

                resume = incompleteness_resume_stage(ctx, "nugget_layup_compose")
                if resume:
                    return resume
            except Exception:
                pass
            return "nugget_layup_compose"
        if _g1_open(ctx):
            block = vo_synthesize_stability_block(ctx)
            if block == "nugget_layup_compose":
                try:
                    from interview_mux.stage_completion import incompleteness_resume_stage

                    resume = incompleteness_resume_stage(ctx, "nugget_layup_compose")
                    if resume:
                        return resume
                except Exception:
                    pass
                return "nugget_layup_compose"
            if block is None:
                try:
                    from interview_mux.delivery_invariants import resolve_g1_vo_open_resume

                    return resolve_g1_vo_open_resume(ctx)
                except Exception:
                    return "vo_synthesize"
            return resolve_vo_synth_seed_resume(block, ctx) or "vo_line_adjudicate"
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
        return resume_producer(ctx, hint_s or "edl")

    if intent_l in {
        "delivery_blocked",
        FAIL_CLASS_DELIVERY_BLOCKED,
        FAIL_CLASS_INCOMPLETE_AFTER_CONDUCTOR,
    }:
        from interview_mux.delivery_guardrails import (
            delivery_stable_for_music,
            music_epoch_complete,
            phase_a_sealed,
        )

        # Gap VO gate / hollow hosted floor → layup/compose producer, never
        # leapfrog to edl_narrative_audit (exec_13183 thrash / Cluster C SSOT).
        hint_l = hint_s.lower()
        if (
            "no synthesize lines" in hint_l
            or "hollow_zero" in hint_l
            or "hosted_vo_floor" in hint_l
            or "hosted_vo_hollow" in hint_l
        ):
            try:
                from interview_mux.hosted_vo_authority import resume_producer as _hvo_resume

                pin = _hvo_resume(ctx)
                if pin:
                    return pin
            except Exception:
                pass
            try:
                from interview_mux.stage_completion import high_gap_heal_resume_stage

                pin = high_gap_heal_resume_stage(ctx)
                if pin:
                    return pin
            except Exception:
                pass
            return "nugget_layup_compose"
        # EDL narrative QC → edl producer only (exec_13183 blank-parity thrash).
        if "edl_narrative_qc" in hint_s.lower():
            return "edl"

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
        if not phase_a_sealed(ctx):
            # Hard upstream holes: pin the real hole — never music/mix.
            # Seal-only skew (phase_a_unsealed) may proceed to path_to_master /
            # music when assembly evidence exists (exec_5402).
            hard_upstream = reason in {
                "layup_incomplete",
                "g1_open",
                "vo_adjudicate_incomplete",
                "edl_incomplete",
                "assembly_missing",
                "layup_escalation_blocking",
            } or (
                isinstance(reason, str) and reason.startswith("stale_upstream:")
            )
            if hard_upstream:
                if reason == "edl_incomplete":
                    return resume_producer(ctx, "edl")
                if reason == "assembly_missing":
                    return "assembly_preview"
                if reason == "listen_delight_incomplete":
                    return "listen_delight_audit"
                if reason in {
                    "layup_incomplete",
                    "g1_open",
                    "vo_adjudicate_incomplete",
                }:
                    return canonical_resume_pin(ctx, FAIL_CLASS_VO_G1)
                if isinstance(reason, str) and reason.startswith("stale_upstream:"):
                    return canonical_resume_pin(
                        ctx, FAIL_CLASS_PHASE_A_EDL, hint=hint_s or "transitions"
                    )
                return canonical_resume_pin(
                    ctx, FAIL_CLASS_PHASE_A_EDL, hint=hint_s or reason or "edl"
                )
        # Phase A sealed, or seal-only skew → ladder to master.wav.
        try:
            return path_to_master_pin(ctx)
        except Exception:
            if music_epoch_complete(ctx):
                return "mix" if not assembly_wav_present(ctx) else "master_finalize"
            return _music_epoch_producer_pin(ctx)

    if hint_s:
        return premature_cap_via_intent(ctx, hint_s)
    return resume_producer(ctx, hint_s or "edl")


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

    # Seating consumers need a committed WAV/JSON unless *this* producer is
    # actively staging the write. Leftover pending from a crashed producer must
    # not satisfy mix/edl/finalize completeness (pending_sid alone is not enough —
    # orphan .pending_writes/<stage>/… after TypeError/abort looked "complete").
    final = ctx.final_path(*path.split("/"))
    leftover_pending = False
    try:
        from interview_mux.write_staging import staged_path as _staged_path

        ps = pending_stage_for_path(ctx, path) if callable(pending_stage_for_path) else None
        leftover_pending = bool(
            ps and _staged_path(ctx, path, stage_id=ps).is_file() and not final.is_file()
        )
    except Exception:
        leftover_pending = (not final.is_file()) and resolved is not None and (
            ".pending_writes" in str(resolved)
        )
    if leftover_pending and consumer_s in seating_consumers:
        active = None
        try:
            if callable(active_stage_id):
                active = active_stage_id()
        except Exception:
            pass
        # Producer mid-flush / mid-stage may only have pending — allow only while live.
        if active != consumer_s:
            return False, "pending_only_seating"

    if resolved is None or not resolved.is_file():
        return False, "missing"

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
    # Fingerprint mismatch (TH3: compare helper; fail-closed — no silent restamp).
    # Producer checking its own output may be mid-rewrite — skip (same as read_stale_guard).
    try:
        from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS

        if STAGE_ARTIFACT_DISK_PATHS.get(consumer_s) == path:
            pass  # own producer — fingerprint may lag the live rewrite
        else:
            meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
            fps = (meta or {}).get("artifact_fingerprints") if isinstance(meta, dict) else None
            if isinstance(fps, dict) and path in fps:
                from interview_mux.artifact_lifecycle import compare_content_fingerprint

                ok_fp, reason_fp = compare_content_fingerprint(ctx, path, fps.get(path))
                if not ok_fp:
                    return False, reason_fp or "fingerprint_mismatch"
    except Exception:
        # Fail-closed when a fingerprint was recorded but compare raised.
        try:
            from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS as _PATHS

            if _PATHS.get(consumer_s) != path:
                meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
                fps = (meta or {}).get("artifact_fingerprints") if isinstance(meta, dict) else None
                if isinstance(fps, dict) and path in fps and fps.get(path):
                    return False, "fingerprint_compare_error"
        except Exception:
            pass
    # Assembly seating: meta flag only (never recurse into mix_assembly_seated).
    # mix is the reseating *producer* — seating_stale must not block mark_done(mix)
    # after a fresh render (clear happens only after mark_done succeeds).
    if path in {"master/assembly.wav", "master/assembly_preview.wav"} and consumer_s in {
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
    """Refuse force-done for guarded stages when incompleteness is set.

    Intentional allow-stub paths (gap skip, framing posture soft-complete, music
    epoch reseat via ``_mark_done_raw``) must leave incompleteness empty before
    calling heal — this assert is the sole hollow-stamp gate for FORCE_DONE_GUARDED.
    """
    sid = str(stage or "").strip()
    if sid not in FORCE_DONE_GUARDED:
        return
    try:
        from interview_mux.stage_completion import stage_artifact_incompleteness

        reason = stage_artifact_incompleteness(ctx, sid)
    except Exception:
        return
    if reason:
        # G1 optional skip: VO stages may soft-complete without pickup WAVs.
        if sid in {"vo_synthesize", "vo_line_adjudicate"}:
            try:
                from interview_mux.gates import g1_vo_was_skipped_optional

                if g1_vo_was_skipped_optional(ctx):
                    return
            except Exception:
                pass
        raise RuntimeError(
            f"refuse force-done {sid}: incompleteness={reason}"
        )


def forensics_suppress_allowed(ctx: RunContext, fail_class: str) -> bool:
    """Per-class suppress budget for needs_operator continues in forensics."""
    return suppress_allowed(ctx, fail_class, source="forensics")


_HARD_NON_SUPPRESS_NEEDLES = (
    "sanitize_refused",
    "selection_unsanitary",
    "gap_unsanitary",
    "air_contract_unsanitary",
    "layup_unsanitary",
    "sdp_unsanitary",
    "vo_unsanitary",
    "authority_undo",
    "incomplete-after-conductor",
    "incomplete_after_conductor",
    "identical_failure_halt",
    "same_family_over_budget",
)


def is_hard_non_suppress_class(fail_class: str) -> bool:
    """Sanitary refuse / undo thrash / sticky incomplete must not auto-continue."""
    low = str(fail_class or "").strip().lower()
    if not low:
        return False
    return any(n in low for n in _HARD_NON_SUPPRESS_NEEDLES)


def suppress_allowed(
    ctx: RunContext, fail_class: str, *, source: str = "forensics"
) -> bool:
    """Per-class suppress budget for forensics or homunculus needs_operator continues."""
    cls = str(fail_class or "unknown").strip() or "unknown"
    if is_hard_non_suppress_class(cls):
        return False
    # ESR fresh progress: do not burn suppress budget (wait, not stuck).
    try:
        from interview_mux.execution_status import may_hard_halt

        if not may_hard_halt(ctx, pin=cls[:80]):
            return True
    except Exception:
        pass
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


def infer_heal_intent(*, error: str = "", stage: str = "", intent: str = "") -> str:
    """Map error/stage → fail class.

    Structural phrases (filter empty / incomplete after conductor) win over
    stage-name substrings like ``music_palette_compose`` in remaining lists —
    otherwise heal forever re-pins music while Phase A is still open (exec_5409).
    """
    intent_l = str(intent or "").strip().lower()
    if intent_l:
        return intent_l
    text = f"{error} {stage}".lower()
    # Structural / conductor phrases FIRST.
    if (
        "incomplete after conductor" in text
        or "incomplete-after-conductor" in text
        or "incomplete_after_conductor" in text
    ):
        return FAIL_CLASS_INCOMPLETE_AFTER_CONDUCTOR
    if (
        "filter empty" in text
        or "delivery blocked" in text
        or "delivery incomplete" in text
    ):
        return FAIL_CLASS_DELIVERY_BLOCKED
    if "edl_narrative_audit thrash cap" in text:
        return FAIL_CLASS_MUSIC_EPOCH
    # Gap VO missing WAV / seated coverage must not fall through to phase_a_edl
    # just because the reason string starts with "edl:" (exec_11630 #16).
    if (
        "g1" in text
        or "vo pickup" in text
        or "vo_synth" in text
        or "gap vo lines missing wav" in text
        or "vo_seated_coverage" in text
        or "seated_bind_stale" in text
        or ("seated synthesize" in text and "missing wav" in text)
    ):
        return FAIL_CLASS_VO_G1
    if "seam_autopsy" in text or "assembly_ledger" in text:
        return FAIL_CLASS_FINALIZE
    if "finalize" in text and "incomplete" not in text:
        return FAIL_CLASS_FINALIZE
    # Mix seating incompleteness must win over MIX_EPOCH_CONSUMERS (mix is both
    # a music-epoch consumer and a mix_seat producer — exec_11630 #24 / R5c).
    if (
        "unseated" in text
        or "mix_outputs_seated" in text
        or (("mix" in text or "assembly" in text) and "stale" in text)
    ):
        return FAIL_CLASS_MIX_SEAT
    # Stage-id keywords only when the *stage arg* is a music producer, or the
    # error is clearly a music/sfx failure — not when music appears in a remaining list.
    stage_l = str(stage or "").strip().lower()
    try:
        from interview_mux.delivery_guardrails import MIX_EPOCH_CONSUMERS, MUSIC_BEFORE_MIX

        if stage_l in MUSIC_BEFORE_MIX or stage_l in MIX_EPOCH_CONSUMERS:
            return FAIL_CLASS_MUSIC_EPOCH
    except Exception:
        pass
    if stage_l in {"mix", "junction_snip_qa"}:
        return FAIL_CLASS_MIX_SEAT
    if stage_l == "master_finalize" or stage_l in SHIP_AFTER_MASTER:
        return FAIL_CLASS_FINALIZE
    # Bare keyword match on error only when stage did not already classify —
    # still avoid matching remaining-stage dumps (contain "filter empty" above).
    if "mmaudio" in text or "sfx_prompt" in text or "music_palette" in text:
        return FAIL_CLASS_MUSIC_EPOCH
    if "music gen" in text or "musicgen" in text:
        return FAIL_CLASS_MUSIC_EPOCH
    if "edl" in text or "narrative" in text or "transition" in text:
        return FAIL_CLASS_PHASE_A_EDL
    if stage_l:
        return premature_fail_class(stage_l)
    return FAIL_CLASS_DELIVERY_BLOCKED


def fail_class_for_failure(*, stage: str = "", reason: str = "", resume: str = "") -> str:
    """Shared fail class for premature, execute, gate, and ranking counters."""
    if resume:
        return premature_fail_class(resume)
    inferred = infer_heal_intent(error=reason, stage=stage)
    if inferred != FAIL_CLASS_DELIVERY_BLOCKED or (
        "filter empty" in f"{reason} {stage}".lower()
        or "incomplete after conductor" in f"{reason} {stage}".lower()
    ):
        return inferred
    if stage:
        cls = premature_fail_class(stage)
        if not cls.startswith("stage:"):
            return cls
    return premature_fail_class(stage or resume or "unknown")


def stable_fail_key(label: str, *, stage: str = "", reason: str = "", resume: str = "") -> str:
    cls = fail_class_for_failure(stage=stage, reason=reason, resume=resume)
    return f"{label}:{cls}"


def sticky_pin_is_sealed(ctx: RunContext, pin: str) -> bool:
    """True when sticky pin is seed-complete (never bare is_done — F5)."""
    sid = str(pin or "").strip()
    if not sid:
        return False
    try:
        from interview_mux.delivery_guardrails import seed_stage_complete

        return bool(seed_stage_complete(ctx, sid))
    except Exception:
        return False


def remutate_resume_allowed(ctx: RunContext) -> bool:
    """False while G1 VO is open — remutate must not yank to transitions/edl/mix."""
    try:
        from interview_mux.delivery_guardrails import _g1_open

        if _g1_open(ctx):
            return False
    except Exception:
        pass
    return True


def note_sticky_heal_attempt(
    ctx: RunContext,
    *,
    kind: str,
    pin: str,
    intent: str = "",
    predicate_token: str = "",
    halt_after: int | None = None,
) -> dict[str, Any]:
    """Count same pin+predicate heal attempts; halt when budget exhausted.

    Progress (predicate token change) resets the counter. Used by the driver so
    incomplete-after-conductor / same-pin premature heals cannot spin forever.
    """
    import time

    limit = int(halt_after if halt_after is not None else STICKY_HEAL_HALT_AFTER)
    kind_s = str(kind or "heal").strip()[:80] or "heal"
    pin_s = str(pin or "").strip()[:120]
    intent_s = str(intent or "").strip()[:80]
    token_s = str(predicate_token or "").strip()[:240]
    key = f"{kind_s}|{pin_s}|{intent_s}"
    # F5: sealed pin must clear sticky, never reinforce active_halt.
    if pin_s and sticky_pin_is_sealed(ctx, pin_s):
        doc: dict[str, Any] = {"version": 1, "attempts": {}}
        if ctx.artifact_exists(STICKY_HEAL_REL):
            try:
                loaded = ctx.read_json(STICKY_HEAL_REL)
                if isinstance(loaded, dict):
                    doc = dict(loaded)
            except Exception:
                pass
        if isinstance(doc.get("active_halt"), dict):
            doc.pop("active_halt", None)
            try:
                ctx.write_json(STICKY_HEAL_REL, doc, skip_handoff=True)
            except Exception:
                pass
        return {
            "kind": kind_s,
            "pin": pin_s,
            "intent": intent_s,
            "predicate_token": token_s,
            "count": 0,
            "halt": False,
            "cleared_sealed": True,
        }
    now = time.time()
    doc: dict[str, Any] = {"version": 1, "attempts": {}}
    if ctx.artifact_exists(STICKY_HEAL_REL):
        try:
            loaded = ctx.read_json(STICKY_HEAL_REL)
            if isinstance(loaded, dict):
                doc = dict(loaded)
        except Exception:
            pass
    attempts = dict(doc.get("attempts") or {})
    prev = dict(attempts.get(key) or {})
    prev_token = str(prev.get("predicate_token") or "")
    if prev_token and token_s and prev_token != token_s:
        count = 1
    else:
        count = int(prev.get("count") or 0) + 1
    # ESR: do not count toward HARD halt while producer progress is fresh
    progress_stale = True
    progress_why = ""
    try:
        from interview_mux.execution_status import may_hard_halt, sync_execution_status

        if not may_hard_halt(
            ctx, pin=pin_s, predicate_token=token_s, prior_token=prev_token
        ):
            progress_stale = False
            progress_why = "esr_fresh"
            # Treat as wait — keep count from escalating past halt-1
            count = min(count, max(1, limit - 1))
        sync_execution_status(
            ctx,
            pin=pin_s,
            intent=intent_s,
            predicate_token=token_s,
            sticky={
                "key": key,
                "count": count,
                "halt": False,
                "progress_stale": progress_stale,
            },
        )
    except Exception:
        progress_stale = True
    row = {
        "kind": kind_s,
        "pin": pin_s,
        "intent": intent_s,
        "predicate_token": token_s,
        "count": count,
        "halt_after": limit,
        "updated_at": now,
        "progress_stale": progress_stale,
        "progress_why": progress_why,
    }
    halt = bool(progress_stale) and count >= limit
    row["halt"] = halt
    attempts[key] = row
    # Cap map size
    if len(attempts) > 40:
        ordered = sorted(
            attempts.items(),
            key=lambda kv: float((kv[1] or {}).get("updated_at") or 0),
        )
        attempts = dict(ordered[-40:])
    doc["attempts"] = attempts
    doc["updated_at"] = now
    if halt:
        doc["active_halt"] = {
            "kind": kind_s,
            "pin": pin_s,
            "intent": intent_s,
            "count": count,
            "predicate_token": token_s,
        }
        try:
            from interview_mux.delivery_guardrails import record_wasted_work

            record_wasted_work(
                ctx,
                event="sticky_heal_halt",
                stage=pin_s or "delivery",
                detail=row,
            )
        except Exception:
            pass
    try:
        ctx.write_json(STICKY_HEAL_REL, doc, skip_handoff=True)
    except Exception:
        pass
    return row


AUTHORITY_UNDO_REL = "operator/authority_undo.json"
AUTHORITY_UNDO_HALT_AFTER = 3

# Writers that update the same authority artifact under different stage_keys must
# not count as A↔B oscillation (exec_10066: edl synth_transitions vs transitions).
_AUTHORITY_ACTION_ALIASES: dict[str, dict[str, str]] = {
    "master/transitions.json": {
        "edl": "transitions",
        "vo_synthesize": "transitions",
        "mix": "transitions",
        "assemble": "transitions",
        "admit_sanitized": "transitions",
        "commit_transitions_doc": "transitions",
        "persist_transitions_doc": "transitions",
        "write_json": "transitions",
        "write_committed_json": "transitions",
        "bridge_heal": "transitions",
        "synth_transitions": "transitions",
    },
    "understanding/sound_design_plan.json": {
        "write_json": "sound_design_plan",
        "commit_sound_design_plan": "sound_design_plan",
        "commit_sound_design_plan_doc": "sound_design_plan",
        "sound_design_palettes": "sound_design_plan",
        "admit_sanitized": "sound_design_plan",
        "analysis_profile": "sound_design_plan",
        "scaffold": "sound_design_plan",
    },
}

# Empty SDP scaffold body hash (sanitary_content_hash of default_sound_design_plan).
_SDP_EMPTY_SCAFFOLD_HASHES = frozenset({"4d59a639ec9a6a95a36e9cbc"})


def _canonical_authority_action(artifact: str, action_class: str) -> str:
    art = str(artifact or "").replace("\\", "/").strip("/")
    action = str(action_class or "").strip() or "heal"
    aliases = _AUTHORITY_ACTION_ALIASES.get(art) or {}
    return aliases.get(action, action)


def note_authority_undo_attempt(
    ctx: RunContext,
    *,
    artifact: str,
    action_class: str,
    content_hash: str,
    halt_after: int | None = None,
) -> dict[str, Any]:
    """Detect A→B→A (or two-hash oscillation) with no content progress.

    Returns a row with ``halt=True`` when the same artifact oscillates without a
    sanitary/content hash flip that advances ship bar.
    """
    import time

    limit = int(halt_after if halt_after is not None else AUTHORITY_UNDO_HALT_AFTER)
    art = str(artifact or "").strip()[:120] or "unknown"
    action = _canonical_authority_action(art, action_class)[:80] or "heal"
    h = str(content_hash or "").strip()[:64] or "empty"
    now = time.time()
    doc: dict[str, Any] = {"version": 1, "artifacts": {}}
    if ctx.artifact_exists(AUTHORITY_UNDO_REL):
        try:
            loaded = ctx.read_json(AUTHORITY_UNDO_REL)
            if isinstance(loaded, dict):
                doc = dict(loaded)
        except Exception:
            pass
    artifacts = dict(doc.get("artifacts") or {})
    prev = dict(artifacts.get(art) or {})
    history = list(prev.get("history") or [])
    # Identical rewrite by the same canonical writer — not progress, not thrash.
    if (
        history
        and str(history[-1].get("action") or "") == action
        and str(history[-1].get("hash") or "") == h
    ):
        row = dict(prev.get("last") or {})
        row.update(
            {
                "artifact": art,
                "action": action,
                "hash": h,
                "count": int(row.get("count") or len(history)),
                "halt": False,
                "reason": "",
                "updated_at": now,
                "deduped": True,
            }
        )
        artifacts[art] = {"history": history, "last": row}
        doc["artifacts"] = artifacts
        doc["updated_at"] = now
        # Clear a stale active_halt on this artifact once writers coalesce.
        active = doc.get("active_halt") if isinstance(doc.get("active_halt"), dict) else {}
        if str((active or {}).get("artifact") or "") == art:
            doc.pop("active_halt", None)
        try:
            ctx.write_json(AUTHORITY_UNDO_REL, doc, skip_handoff=True)
        except Exception:
            pass
        return row
    history.append({"action": action, "hash": h, "ts": now})
    history = history[-8:]
    hashes = [str(x.get("hash") or "") for x in history]
    actions = [str(x.get("action") or "") for x in history]
    halt = False
    reason = ""
    # Oscillation between exactly two hashes across >= halt_after transitions
    uniq = []
    for x in hashes:
        if not uniq or uniq[-1] != x:
            uniq.append(x)
    if len(history) >= limit and len(set(hashes[-limit:])) <= 2:
        # Scaffold empty → hardened content is progress, not thrash (SDP admit).
        recent = hashes[-limit:]
        if art.endswith("sound_design_plan.json") and any(
            rh in _SDP_EMPTY_SCAFFOLD_HASHES for rh in recent
        ):
            nonempty = [rh for rh in recent if rh and rh not in _SDP_EMPTY_SCAFFOLD_HASHES]
            if nonempty:
                halt = False
                reason = ""
            elif len(uniq) >= 3 and uniq[-1] == uniq[-3]:
                halt = True
                reason = f"hash_oscillation:{uniq[-3]}↔{uniq[-2]}"
        # A→B→A pattern on actions or hashes
        elif len(uniq) >= 3 and uniq[-1] == uniq[-3]:
            distinct_actions = {a for a in actions[-limit:] if a}
            # Same canonical writer flipping two content hashes during unfinished
            # EDL is bridge-heal ↔ restamp refinement (exec_11130), not A↔B thrash.
            from interview_mux.delivery_guardrails import seed_stage_complete

            if (
                (
                    art.endswith("transitions.json")
                    or art.endswith("gap_report.json")
                )
                and len(distinct_actions) <= 1
                and not seed_stage_complete(ctx, "edl")
            ):
                halt = False
                reason = ""
            else:
                halt = True
                reason = f"hash_oscillation:{uniq[-3]}↔{uniq[-2]}"
        elif (
            len(actions) >= 3
            and actions[-1] == actions[-3]
            and actions[-1] != actions[-2]
            and hashes[-1] == hashes[-3]
        ):
            halt = True
            reason = f"action_oscillation:{actions[-1]}↔{actions[-2]}"
    # ESR: oscillation while producer disk/lease progress is fresh → wait, not HARD.
    if halt:
        # Workstream B: layup plan hash oscillation → pick-best archived candidate
        # instead of halt with no accepted plan (under-goal accounted stays advisory).
        if art.endswith("nugget_layup_plan.json") or art == "understanding/nugget_layup_plan.json":
            try:
                from interview_mux.nugget_layup import try_pick_best_layup_on_oscillation

                picked = try_pick_best_layup_on_oscillation(ctx)
                if picked.get("ok"):
                    halt = False
                    reason = (reason + "|layup_air_pick_best") if reason else "layup_air_pick_best"
                    row_extra = {
                        "layup_air_pick_best": True,
                        "picked_attempt_id": (picked.get("candidate") or {}).get("attempt_id"),
                    }
                else:
                    row_extra = {"layup_air_pick_best": False, "pick_reason": picked.get("reason")}
            except Exception as exc:
                row_extra = {"layup_air_pick_best": False, "pick_error": str(exc)[:120]}
        else:
            row_extra = {}
        try:
            from interview_mux.execution_status import may_hard_halt

            if halt and not may_hard_halt(ctx, pin=art.split("/")[-1].replace(".json", "")):
                halt = False
                reason = (reason + "|esr_wait") if reason else "esr_wait"
        except Exception:
            pass
    else:
        row_extra = {}
    row = {
        "artifact": art,
        "action": action,
        "hash": h,
        "count": len(history),
        "halt": halt,
        "reason": reason,
        "updated_at": now,
    }
    if row_extra:
        row.update(row_extra)
    artifacts[art] = {"history": history, "last": row}
    if len(artifacts) > 24:
        ordered = sorted(
            artifacts.items(),
            key=lambda kv: float(((kv[1] or {}).get("last") or {}).get("updated_at") or 0),
        )
        artifacts = dict(ordered[-24:])
    doc["artifacts"] = artifacts
    doc["updated_at"] = now
    if halt:
        doc["active_halt"] = {
            "artifact": art,
            "pair": reason,
            "hash": h,
            "action": action,
        }
        try:
            from interview_mux.delivery_guardrails import record_wasted_work

            record_wasted_work(
                ctx,
                event="authority_undo_thrash",
                stage=art,
                detail=row,
            )
        except Exception:
            pass
    else:
        active = doc.get("active_halt") if isinstance(doc.get("active_halt"), dict) else {}
        if str((active or {}).get("artifact") or "") == art:
            doc.pop("active_halt", None)
    try:
        ctx.write_json(AUTHORITY_UNDO_REL, doc, skip_handoff=True)
    except Exception:
        pass
    return row



def _heal_navigate_ungated(
    ctx: RunContext,
    *,
    error: str = "",
    stage: str = "",
    intent: str = "",
) -> dict[str, str]:
    """Propose a heal pin (no Option E allowlist/checklist gate).

    Callers that rewrite ``from_stage`` must use ``heal_navigate`` /
    ``resolve_heal_from_stage`` so refuse-by-default authority applies.
    """
    # A refused soft pre-EDL shortcut is itself not a producer. Route to the
    # product QC writer and let normal attempt accounting begin there.
    soft_refuse = f"{error} {stage}".lower()
    if "pre-edl delivery qc incomplete" in soft_refuse or "e2e_stub" in soft_refuse:
        pin = "nugget_layup_compose"
        return {
            "intent": "pre_edl_qc_producer",
            "from_stage": pin,
            "mode": "delivery",
        }
    # HG-4: voice-ref is G-Framing ladder — never topic_coverage / research rewind.
    try:
        from interview_mux.stage_completion import voice_ref_heal_resume_stage

        pin = voice_ref_heal_resume_stage(ctx, error=error, stage=stage)
        if pin:
            try:
                note_delivery_pin(
                    ctx,
                    from_stage=pin,
                    intent=str(intent or "voice_reference_pending"),
                    reason=str(error or stage or "")[:240],
                    source="heal_navigate_voice_ref",
                )
            except Exception:
                pass
            return {
                "intent": str(intent or "voice_reference_pending"),
                "from_stage": pin,
                "mode": "analysis",
            }
    except Exception:
        pass
    # HG-5: high_gap_unframed pins the live writer — compose no-ops under layup.
    try:
        blob_hg = f"{error} {stage}".strip().lower()
        if "high_gap_unframed" in blob_hg or (
            "high gap segment" in blob_hg and "no interviewer line" in blob_hg
        ):
            from interview_mux.stage_completion import high_gap_heal_resume_stage

            pin = high_gap_heal_resume_stage(ctx)
            try:
                note_delivery_pin(
                    ctx,
                    from_stage=pin,
                    intent=str(intent or "high_gap_unframed"),
                    reason=str(error or stage or "")[:240],
                    source="heal_navigate_high_gap",
                )
            except Exception:
                pass
            return {
                "intent": str(intent or "high_gap_unframed"),
                "from_stage": pin,
                "mode": "delivery" if pin == "nugget_layup_compose" else "analysis",
            }
    except Exception:
        pass
    # HS-4: fuse oscillation pins the fuse writer — never edl / remaster-mix.
    try:
        blob_fuse = f"{error} {stage}".strip().lower()
        fuse_named = (
            "fuse_oscillation" in blob_fuse
            or "connector_fuse_oscillation" in blob_fuse
            or (
                "oscillation_halt" in blob_fuse
                and ("fuse" in blob_fuse or "connector_fuse" in blob_fuse)
                and "junction" not in blob_fuse
            )
        )
        if fuse_named:
            from interview_mux.stage_completion import fuse_oscillation_heal_resume_stage
            from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

            pin = fuse_oscillation_heal_resume_stage(ctx, error=error, stage=stage)
            try:
                note_delivery_pin(
                    ctx,
                    from_stage=pin,
                    intent=str(intent or "fuse_oscillation"),
                    reason=str(error or stage or "")[:240],
                    source="heal_navigate_fuse_oscillation",
                )
            except Exception:
                pass
            mode = "delivery" if pin in DELIVERY_ORDER else "analysis"
            if pin not in DELIVERY_ORDER and pin not in ANALYSIS_ORDER:
                mode = "analysis"
            return {
                "intent": str(intent or "fuse_oscillation"),
                "from_stage": pin,
                "mode": mode,
            }
    except Exception:
        pass
    # HE-2: unsanitary VO/bind must not resume edl as recovered.
    try:
        blob_edl = f"{error} {stage}".strip().lower()
        if (
            "vo_audibility_drift" in blob_edl
            or "opening_orientation_inaudible" in blob_edl
            or "never_touch_zeroed_keep" in blob_edl
        ):
            from interview_mux.stage_completion import edl_heal_resume_stage

            pin = edl_heal_resume_stage(ctx)
            try:
                note_delivery_pin(
                    ctx,
                    from_stage=pin,
                    intent=str(intent or "vo_audibility_drift"),
                    reason=str(error or stage or "")[:240],
                    source="heal_navigate_edl_vo_bind",
                )
            except Exception:
                pass
            return {
                "intent": str(intent or "vo_audibility_drift"),
                "from_stage": pin,
                "mode": "delivery",
            }
    except Exception:
        pass
    # HE-3: unsourced heard glue / preview heard-WAV pins vo_synthesize, never edl.
    try:
        blob_prev = f"{error} {stage}".strip().lower()
        if (
            "heard_wav_flow" in blob_prev
            or (
                str(stage or "").strip() == "assembly_preview"
                and (
                    "missing source_path" in blob_prev
                    or "transition pairs missing wav" in blob_prev
                    or "vo coverage not rendered" in blob_prev
                )
            )
        ):
            from interview_mux.v2.config import DELIVERY_ORDER

            pin = "vo_synthesize"
            try:
                note_delivery_pin(
                    ctx,
                    from_stage=pin,
                    intent=str(intent or "heard_wav_flow"),
                    reason=str(error or stage or "")[:240],
                    source="heal_navigate_preview_heard_wav",
                )
            except Exception:
                pass
            return {
                "intent": str(intent or "heard_wav_flow"),
                "from_stage": pin,
                "mode": "delivery" if pin in DELIVERY_ORDER else "analysis",
            }
    except Exception:
        pass
    # HF-4: unsanitary air-contract pins the W3 writer, never edl / mute-done.
    try:
        blob_air = f"{error} {stage}".strip().lower()
        if "air_contract_unsanitary" in blob_air or (
            str(stage or "").strip() == "air_contract_sanitize"
            and "unsanitary" in blob_air
        ):
            from interview_mux.v2.config import DELIVERY_ORDER

            pin = "air_contract_sanitize"
            try:
                note_delivery_pin(
                    ctx,
                    from_stage=pin,
                    intent=str(intent or "air_contract_unsanitary"),
                    reason=str(error or stage or "")[:240],
                    source="heal_navigate_air_contract_unsanitary",
                )
            except Exception:
                pass
            return {
                "intent": str(intent or "air_contract_unsanitary"),
                "from_stage": pin,
                "mode": "delivery" if pin in DELIVERY_ORDER else "analysis",
            }
    except Exception:
        pass
    # HF-5: Pass-2 re-dirtied gap pins the writer, never W1 under W3 freeze.
    try:
        blob_p2 = f"{error} {stage}".strip().lower()
        sid_p2 = str(stage or "").strip()
        if "gap_unsanitary" in blob_p2 or (
            sid_p2 in {"gap_framing_recompose", "selection_framing_apply"}
            and "unsanitary" in blob_p2
        ):
            from interview_mux.stage_completion import pass2_gap_heal_resume_stage
            from interview_mux.v2.config import DELIVERY_ORDER

            pin = pass2_gap_heal_resume_stage(ctx, error=str(error or ""), stage=sid_p2)
            if pin:
                try:
                    note_delivery_pin(
                        ctx,
                        from_stage=pin,
                        intent=str(intent or "gap_unsanitary"),
                        reason=str(error or stage or "")[:240],
                        source="heal_navigate_pass2_gap_unsanitary",
                    )
                except Exception:
                    pass
                return {
                    "intent": str(intent or "gap_unsanitary"),
                    "from_stage": pin,
                    "mode": "delivery" if pin in DELIVERY_ORDER else "analysis",
                }
    except Exception:
        pass
    # HR-4: W1 ranking/gap sanitize unsanitary self-pins, never edl / Pass-2.
    # "gap_unsanitary" stays HF-5 (Pass-2 writer under freeze).
    try:
        blob_w1 = f"{error} {stage}".strip().lower()
        pin = None
        # HR-2 selection_commit_refused embeds sanitize_refused text in the refuse
        # detail — do not hijack to W1 (exec_13177 / test_hr2_layup_commit_refuse).
        if "gap_unsanitary" not in blob_w1 and "selection_commit_refused" not in blob_w1:
            from interview_mux.stage_completion import parse_resume_stage_from_reason

            parsed = parse_resume_stage_from_reason(str(error or ""))
            if parsed == "full_master_ranking" or (
                (
                    "selection still unsanitary" in blob_w1
                    or "selection_unsanitary" in blob_w1
                    or "sanitize_refused:selection" in blob_w1
                )
                and (
                    "hard_keep_" in blob_w1
                    or "air_order_integrity_critical" in blob_w1
                )
            ):
                pin = "full_master_ranking"
            elif (
                parsed == "selection_order_sanitize"
                or "selection still unsanitary" in blob_w1
                or "selection_unsanitary" in blob_w1
                or "sanitize_refused:selection" in blob_w1
            ):
                pin = "selection_order_sanitize"
            elif parsed == "gap_report_sanitize" or "gap still unsanitary" in blob_w1:
                pin = "gap_report_sanitize"
        if pin:
            from interview_mux.v2.config import DELIVERY_ORDER

            try:
                note_delivery_pin(
                    ctx,
                    from_stage=pin,
                    intent=str(intent or "w1_sanitize_unsanitary"),
                    reason=str(error or stage or "")[:240],
                    source="heal_navigate_hr4_w1_sanitize",
                )
            except Exception:
                pass
            return {
                "intent": str(intent or "w1_sanitize_unsanitary"),
                "from_stage": pin,
                "mode": "delivery" if pin in DELIVERY_ORDER else "analysis",
            }
    except Exception:
        pass
    # HR-2: off-bus selection commit refuse pins the writer, never W1 / edl.
    try:
        blob_sel = f"{error} {stage}".strip().lower()
        if "selection_commit_refused" in blob_sel:
            from interview_mux.stage_completion import parse_resume_stage_from_reason
            from interview_mux.v2.config import DELIVERY_ORDER

            pin = parse_resume_stage_from_reason(str(error or ""))
            if pin not in {"air_script_compose", "nugget_layup_compose"}:
                pin = (
                    "nugget_layup_compose"
                    if "nugget_layup" in blob_sel
                    else "air_script_compose"
                )
            try:
                note_delivery_pin(
                    ctx,
                    from_stage=pin,
                    intent=str(intent or "selection_commit_refused"),
                    reason=str(error or stage or "")[:240],
                    source="heal_navigate_selection_commit_refused",
                )
            except Exception:
                pass
            return {
                "intent": str(intent or "selection_commit_refused"),
                "from_stage": pin,
                "mode": "delivery" if pin in DELIVERY_ORDER else "analysis",
            }
    except Exception:
        pass
    # HR-1: hitch adopt failed pins layup, never hitch-complete / edl.
    try:
        blob_hitch = f"{error} {stage}".strip().lower()
        if "hitch_layup_adopt_failed" in blob_hitch:
            from interview_mux.v2.config import DELIVERY_ORDER

            pin = "nugget_layup_compose"
            try:
                note_delivery_pin(
                    ctx,
                    from_stage=pin,
                    intent=str(intent or "hitch_layup_adopt_failed"),
                    reason=str(error or stage or "")[:240],
                    source="heal_navigate_hitch_layup_adopt",
                )
            except Exception:
                pass
            return {
                "intent": str(intent or "hitch_layup_adopt_failed"),
                "from_stage": pin,
                "mode": "delivery" if pin in DELIVERY_ORDER else "analysis",
            }
    except Exception:
        pass
    # Lock 5: structured incompleteness resume / allowlisted parse before table.
    try:
        from interview_mux.stage_completion import (
            incompleteness_resume_stage,
            parse_resume_stage_from_reason,
        )

        stage_s = str(stage or "").strip()
        err_s = str(error or "")
        structured = incompleteness_resume_stage(ctx, stage_s) if stage_s else None
        parsed = parse_resume_stage_from_reason(err_s) or parse_resume_stage_from_reason(
            f"{err_s} {stage_s}"
        )
        resume = structured or parsed
        try:
            from interview_mux.stage_completion import mastering_heal_resume_stage

            mastering = mastering_heal_resume_stage(ctx, error=err_s, stage=stage_s)
        except Exception:
            mastering = None
        if mastering:
            resume = mastering
        # Self-pin (e.g. edl incompleteness "master/edl.json is pending" → edl via
        # PRODUCER_PIN_TABLE substring) must not short-circuit intent / earliest walk.
        # HM-2: mastering pins must still return (including self-pin) — never fall
        # through to edl / delivery.
        if resume and (resume != stage_s or mastering):
            try:
                from interview_mux.delivery_guardrails import (
                    VO_CHAIN_DOWNSTREAM_PINS,
                    VO_ORDER_CLAMP_STAGES,
                    clamp_resume_through_order,
                )

                if resume in VO_ORDER_CLAMP_STAGES or resume in VO_CHAIN_DOWNSTREAM_PINS:
                    resume = clamp_resume_through_order(ctx, resume)
            except Exception:
                pass
            try:
                note_delivery_pin(
                    ctx,
                    from_stage=resume,
                    intent=str(intent or "incompleteness_resume"),
                    reason=str(error or stage or "")[:240],
                    source="heal_navigate_incompleteness_resume",
                )
            except Exception:
                pass
            from interview_mux.v2.config import DELIVERY_ORDER

            return {
                "intent": str(intent or "incompleteness_resume"),
                "from_stage": resume,
                "mode": "delivery" if resume in DELIVERY_ORDER else "analysis",
            }
    except Exception:
        pass
    # HP-4: G0 tokens pin the gate (or build if the queue is missing). Analysis
    # pins are not in DELIVERY_ORDER — honor them before the delivery-only table.
    try:
        blob_g0 = f"{error} {stage} {intent}".strip().lower()
        if (
            "g0_pending" in blob_g0
            or "transcript review" in blob_g0
            or str(stage or "").strip() in {"transcript_review", "transcript_review_build"}
        ):
            from interview_mux.stage_completion import g0_heal_resume_stage

            pin = g0_heal_resume_stage(ctx)
            try:
                note_delivery_pin(
                    ctx,
                    from_stage=pin,
                    intent=str(intent or "g0_pending"),
                    reason=str(error or stage or "")[:240],
                    source="heal_navigate_g0",
                )
            except Exception:
                pass
            return {
                "intent": str(intent or "g0_pending"),
                "from_stage": pin,
                "mode": "analysis",
            }
    except Exception:
        pass
    # Durable: PRODUCER_PIN_TABLE / premature_class_pin is the only ad-hoc→pin authority.
    try:
        from interview_mux.stage_completion import (
            premature_class_pin,
            producer_pin_for_token,
        )
        from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER

        blob = f"{error} {stage} {intent}".strip().lower()
        order = tuple(ANALYSIS_ORDER) + tuple(DELIVERY_ORDER)

        def _accept_pin(pin: str, *, intent_s: str, source: str) -> dict[str, str] | None:
            if not pin or pin not in order:
                return None
            # DP-LAYUP-ADJ A: early pin returns must not leapfrog MUST_PRECEDE/G8.
            try:
                from interview_mux.delivery_guardrails import (
                    VO_CHAIN_DOWNSTREAM_PINS,
                    VO_ORDER_CLAMP_STAGES,
                    clamp_resume_through_order,
                )

                if pin in VO_ORDER_CLAMP_STAGES or pin in VO_CHAIN_DOWNSTREAM_PINS:
                    pin = clamp_resume_through_order(ctx, pin)
            except Exception:
                pass
            if not pin or pin not in order:
                return None
            mode = "analysis" if pin in ANALYSIS_ORDER else "delivery"
            try:
                note_delivery_pin(
                    ctx,
                    from_stage=pin,
                    intent=str(intent or intent_s),
                    reason=str(error or stage or "")[:240],
                    source=source,
                )
            except Exception:
                pass
            return {
                "intent": str(intent or intent_s),
                "from_stage": pin,
                "mode": mode,
            }

        # Named premature_complete:<class> before seed-order / table fall-through.
        if "premature_complete" in blob:
            pc = premature_class_pin(blob, ctx)
            if pc:
                hit = _accept_pin(
                    pc, intent_s="premature_complete", source="heal_navigate_premature_class"
                )
                if hit:
                    return hit
        # End-E: seed-order named producer always wins (before sealed fall-through).
        if "seed order" in blob or "seed_order" in blob:
            seed_pin = producer_pin_for_token(blob, default="", ctx=ctx)
            hit = _accept_pin(
                seed_pin, intent_s="seed_order_prereq", source="heal_navigate_seed_order"
            )
            if hit:
                return hit
        table_pin = producer_pin_for_token(blob, default="", ctx=ctx)
        if table_pin and table_pin in order:
            # Prefer table pin when the token explicitly names a known class.
            import re as _re_blob

            from interview_mux.stage_completion import PRODUCER_PIN_TABLE

            _blob_toks = set(
                _re_blob.findall(r"[a-z0-9_]+(?::[a-z0-9_]+)*", blob)
            )
            explicit = any(
                (
                    needle
                    and needle not in order
                    and (
                        needle == blob
                        or (" " in needle and needle in blob)
                        or needle in _blob_toks
                    )
                )
                for needle in PRODUCER_PIN_TABLE
            ) or ("premature_complete" in blob)
            if explicit:
                hit = _accept_pin(
                    table_pin,
                    intent_s="producer_pin_table",
                    source="heal_navigate_pin_table",
                )
                if hit:
                    return hit
    except Exception:
        pass
    intent_l = infer_heal_intent(error=error, stage=stage, intent=intent)
    # Once music epoch is open/complete, force path-to-master (no narrative rewind).
    # Never take this shortcut when Phase A is unsealed — path_to_master would
    # wrongly pin music while filter still empties the music slice.
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
            and phase_a_sealed(ctx)
            and (music_epoch_complete(ctx) or intent_l != FAIL_CLASS_MUSIC_EPOCH)
            and intent_l != FAIL_CLASS_VO_G1
        ):
            # Prefer ladder pin directly for post-music progress.
            if intent_l in {
                FAIL_CLASS_MIX_SEAT,
                FAIL_CLASS_FINALIZE,
                FAIL_CLASS_DELIVERY_BLOCKED,
            } or music_epoch_complete(ctx):
                pin = resume_producer(ctx, path_to_master_pin(ctx))
                return {
                    "intent": intent_l,
                    "from_stage": pin,
                    "mode": "delivery" if pin in DELIVERY_ORDER else "analysis",
                }
    except Exception:
        pass
    pin = resume_producer(ctx, canonical_resume_pin(ctx, intent_l, hint=stage))
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
                pin = resume_producer(ctx, path_to_master_pin(ctx))
        except Exception:
            pass
    try:
        from interview_mux.refinement_passes import remap_retired_refine_pin

        pin = remap_retired_refine_pin(ctx, pin)
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


def heal_navigate(
    ctx: RunContext,
    *,
    error: str = "",
    stage: str = "",
    intent: str = "",
) -> dict[str, str]:
    """Single heal navigator with Heal Clinic Option E authority gate.

    Propose via ``_heal_navigate_ungated``, then refuse-by-default unless the
    error/intent is allowlisted and the target prereq checklist is green.
    """
    from interview_mux.heal_pin_authority import resolve_heal_from_stage

    return resolve_heal_from_stage(
        ctx, error=error, stage=stage, intent=intent
    )


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
    from interview_mux.delivery_invariants import committed_master_wav

    if committed_master_wav(ctx) or ctx.artifact_exists("master/assembly.wav"):
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
        # DETECTION_ONLY_IS_DONE: already stamped → skip demote of live incomplete.
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
    # ESR: identical thrash while producer progress is fresh is not thrash_active.
    try:
        from interview_mux.execution_status import may_hard_halt

        if not may_hard_halt(ctx, pin=str(pin or stage or ""), predicate_token=token):
            same = same[: max(0, THRASH_HIT_THRESHOLD - 1)]
    except Exception:
        pass
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
    # Never mutate honesty while a *live* driver claim / expensive lease is active.
    # Sticky partial_auto / full_auto meta alone must NOT no-op honesty (O7).
    try:
        lease_on, _ = expensive_stage_lease_active(ctx)
        if lease_on:
            return job
    except Exception:
        pass
    try:
        from interview_mux.driver_singleton import read_driver_claim

        claim = read_driver_claim(ctx)
        if isinstance(claim, dict):
            import os as _os

            pid = int(claim.get("pid") or 0)
            if pid > 0:
                try:
                    _os.kill(pid, 0)
                    alive = True
                except OSError:
                    alive = False
                if alive:
                    return job
    except Exception:
        pass
    try:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    except Exception:
        meta = {}
    # Live driver claim flags only — not sticky partial_auto/full_auto alone.
    if isinstance(meta, dict) and meta.get("automation_driver_active"):
        try:
            from interview_mux.driver_singleton import read_driver_claim

            if isinstance(read_driver_claim(ctx), dict):
                return job
        except Exception:
            pass
    if job.get("driver_active"):
        try:
            from interview_mux.driver_singleton import read_driver_claim

            if isinstance(read_driver_claim(ctx), dict):
                return job
        except Exception:
            pass
    from interview_mux.delivery_invariants import committed_master_wav

    if committed_master_wav(ctx):
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

    from interview_mux.done_authority import may_skip_as_complete

    encode_done = may_skip_as_complete(ctx, "podcast_encode_mp3")
    has_mp3 = ctx.artifact_exists("publish/audio.mp3") or ctx.artifact_exists(
        "publish/master.mp3"
    )
    if not encode_done and not has_mp3:
        holes.append("publish/audio.mp3 missing")
        pin = "podcast_encode_mp3"
    elif left and not may_skip_as_complete(ctx, "podcast_publish"):
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
    pin = str(from_stage or "").strip()
    try:
        from interview_mux.refinement_passes import remap_retired_refine_pin

        pin = remap_retired_refine_pin(ctx, pin)
    except Exception:
        pass
    doc = {
        "version": 1,
        "from_stage": pin,
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
JUNCTION_REMASTER_GEN_CAP = 3
JUNCTION_REMASTER_BUDGET_REL = "operator/junction_remaster_budget.json"
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
    """Single post-Phase-A resume ladder toward master.wav — never narrative audit.

    When Phase A is still open, redirect to the Phase-A / VO hole — never the
    music producers (filter-empty thrash when from_stage was music).
    """
    from interview_mux.delivery_guardrails import (
        MUSIC_BEFORE_MIX,
        delivery_stable_for_music,
        finalize_input_producer_pin,
        music_epoch_complete,
        phase_a_sealed,
        seed_stage_complete,
    )

    if not phase_a_sealed(ctx):
        _stable, reason = delivery_stable_for_music(ctx)
        hard_upstream = reason in {
            "layup_incomplete",
            "g1_open",
            "vo_adjudicate_incomplete",
            "edl_incomplete",
            "assembly_missing",
            "layup_escalation_blocking",
            "listen_delight_incomplete",
        } or (isinstance(reason, str) and reason.startswith("stale_upstream:"))
        if hard_upstream:
            if reason == "edl_incomplete":
                return resume_producer(ctx, "edl")
            if reason == "assembly_missing":
                return "assembly_preview"
            if reason == "listen_delight_incomplete":
                return "listen_delight_audit"
            if reason in {
                "layup_incomplete",
                "g1_open",
                "vo_adjudicate_incomplete",
            }:
                return canonical_resume_pin(ctx, FAIL_CLASS_VO_G1)
            return canonical_resume_pin(
                ctx, FAIL_CLASS_PHASE_A_EDL, hint=reason or "edl"
            )
        # Expanded WS2 O7: any incomplete Phase A producer beats music, even on
        # seal-only skew (do not walk MusicGen while layup/VO/edl still hollow).
        try:
            from interview_mux.delivery_guardrails import PHASE_A_STAGES

            for sid in PHASE_A_STAGES:
                if not seed_stage_complete(ctx, sid):
                    return resume_producer(ctx, sid) if sid == "edl" else sid
        except Exception:
            pass
        # Seal-only skew with all Phase A seed-complete: fall through to music.
    # Music epoch still open → speech-first mix or music producers (Phase A
    # already handled above; do not re-enter next_delivery_seat Phase-A walk).
    if not music_epoch_complete(ctx):
        try:
            from interview_mux.mix_junction_seat import hold_speech_first_mix

            if hold_speech_first_mix(ctx, "mix"):
                return "mix"
        except Exception:
            pass
        try:
            from interview_mux.mix_junction_seat import next_delivery_seat

            return next_delivery_seat(ctx)
        except Exception:
            for sid in MUSIC_BEFORE_MIX:
                if not seed_stage_complete(ctx, sid):
                    return sid
            return "mmaudio_sfx"
    # Music sealed: never rewind to edl_narrative_audit / Phase-A consumers.
    from interview_mux.air_order import mix_seat_resume_stage

    seat_pin = mix_seat_resume_stage(ctx)
    if seat_pin == "mix":
        return "mix"
    if seat_pin == "junction_snip_qa":
        if not ctx.artifact_exists("master/seam_autopsy.json"):
            return "junction_snip_qa"
        return "junction_snip_qa"
    from interview_mux.delivery_invariants import committed_master_wav

    if not committed_master_wav(ctx):
        pin = finalize_input_producer_pin(ctx, message="path_to_master")
        if pin in PATH_TO_MASTER or pin in {"edl", "vo_synthesize"}:
            # After music, edl pin only if EDL truly missing (restore first).
            if pin == "edl" and not ctx.artifact_exists("master/edl.json"):
                ensure_finalize_inputs_present(ctx)
                if not ctx.artifact_exists("master/edl.json"):
                    return resume_producer(ctx, "edl")
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
    from interview_mux.delivery_guardrails import seed_stage_complete

    has_delight = ctx.artifact_exists(
        "mastering/listen_delight_audit.json"
    ) or seed_stage_complete(ctx, "listen_delight_audit")
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


def _junction_seating_generation(ctx: RunContext) -> int:
    try:
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        return int((meta or {}).get("assembly_seating_generation") or 0)
    except Exception:
        return 0


def _junction_edl_hash(ctx: RunContext) -> str:
    try:
        if not ctx.artifact_exists("master/edl.json"):
            return ""
        edl = ctx.read_json("master/edl.json")
        if not isinstance(edl, dict):
            return ""
        from interview_mux.seam_autopsy import _canonical_hash

        return str(_canonical_hash(edl) or "")
    except Exception:
        return ""


def _read_junction_remaster_budget(ctx: RunContext) -> dict[str, Any]:
    rel = JUNCTION_REMASTER_BUDGET_REL
    doc: dict[str, Any] = {"by_generation": {}}
    if ctx.artifact_exists(rel):
        try:
            loaded = ctx.read_json(rel)
            if isinstance(loaded, dict):
                doc = dict(loaded)
        except Exception:
            pass
    doc.setdefault("by_generation", {})
    return doc


def _write_junction_remaster_budget(ctx: RunContext, doc: dict[str, Any]) -> None:
    out = dict(doc)
    out["updated_at"] = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).isoformat()
    try:
        ctx.write_json(JUNCTION_REMASTER_BUDGET_REL, out, skip_handoff=True)
    except Exception:
        pass


def junction_oscillation_halted(ctx: RunContext) -> bool:
    """Sticky oscillation halt until seating generation or EDL hash flips."""
    doc = _read_junction_remaster_budget(ctx)
    if not doc.get("oscillation_halt"):
        return False
    gen = _junction_seating_generation(ctx)
    edl_h = _junction_edl_hash(ctx)
    sticky_gen = int(doc.get("oscillation_halt_generation") or -1)
    sticky_hash = str(doc.get("oscillation_halt_edl_hash") or "")
    if sticky_gen != gen or sticky_hash != edl_h:
        doc["oscillation_halt"] = False
        doc.pop("oscillation_halt_generation", None)
        doc.pop("oscillation_halt_edl_hash", None)
        _write_junction_remaster_budget(ctx, doc)
        return False
    return True


def _live_junction_music_critical(ctx: RunContext) -> bool:
    """True when live JSQ / incomplete-cut findings still have critical severity."""
    try:
        from interview_mux.junction_snip_qa import (
            detect_junction_findings,
            live_incomplete_cut_critical_findings,
        )

        if live_incomplete_cut_critical_findings(ctx):
            return True
        edl = (
            ctx.read_json("master/edl.json")
            if ctx.artifact_exists("master/edl.json")
            else {}
        )
        findings = detect_junction_findings(ctx, edl if isinstance(edl, dict) else {}, cfg={})
        return any(
            isinstance(f, dict) and str(f.get("severity") or "") == "critical"
            for f in findings
        )
    except Exception:
        return True


def note_junction_oscillation_halt(ctx: RunContext) -> None:
    """Persist oscillation sticky so remaster cannot re-enter until EDL/gen flips.

    Thrash-stop must not invent a ship-blocking critical residual when live
    junction findings are already observational-only (exec_13161 PMQ spin on
    ``junction_oscillation_halt`` with JSQ blocking=False).
    """
    doc = _read_junction_remaster_budget(ctx)
    doc["oscillation_halt"] = True
    doc["oscillation_halt_generation"] = _junction_seating_generation(ctx)
    doc["oscillation_halt_edl_hash"] = _junction_edl_hash(ctx)
    _write_junction_remaster_budget(ctx, doc)
    live_critical = _live_junction_music_critical(ctx)
    try:
        from interview_mux.delivery_guardrails import record_delivery_residual

        record_delivery_residual(
            ctx,
            kind="junction_oscillation_halt",
            severity="critical" if live_critical else "soft",
            stage="junction_snip_qa",
            detail={
                "generation": doc.get("oscillation_halt_generation"),
                "edl_hash": str(doc.get("oscillation_halt_edl_hash") or "")[:64],
                "live_critical_findings": live_critical,
            },
        )
    except Exception:
        pass


def note_music_placement_thrash_halt(
    ctx: RunContext,
    *,
    kind: str = "music_placement_thrash_halt",
    stage: str = "mix",
    detail: dict[str, Any] | None = None,
) -> None:
    """Sibling music/placement thrash halt — soft residual unless live criticals."""
    live_critical = _live_junction_music_critical(ctx)
    try:
        from interview_mux.delivery_guardrails import record_delivery_residual

        record_delivery_residual(
            ctx,
            kind=kind,
            severity="critical" if live_critical else "soft",
            stage=stage,
            detail={
                **(detail if isinstance(detail, dict) else {}),
                "live_critical_findings": live_critical,
            },
        )
    except Exception:
        pass


def junction_remaster_budget_ok(ctx: RunContext) -> tuple[bool, int]:
    """Per air-order generation remaster cap (beyond in-stage max_rounds).

    Also refuses when oscillation_halt is sticky for the current EDL/generation.
    """
    if junction_oscillation_halted(ctx):
        doc = _read_junction_remaster_budget(ctx)
        gen = _junction_seating_generation(ctx)
        n = int((doc.get("by_generation") or {}).get(str(gen)) or 0)
        return False, n
    gen = _junction_seating_generation(ctx)
    doc = _read_junction_remaster_budget(ctx)
    by_gen = dict(doc.get("by_generation") or {})
    n = int(by_gen.get(str(gen)) or 0)
    return n < JUNCTION_REMASTER_GEN_CAP, n


def junction_budget_exhaust_hard_pin(ctx: RunContext) -> str:
    """On budget/osc exhaust: classified refuse-terminate — never soft-pass naked seams.

    Clinic JSQ-B3 (2026-09-17 CONTINUE): do **not** stamp ``needs_operator``.
    Exhaustion is a classified remediation / refuse-terminate edge — caller
    continues to terminal ``raise_loud_failure`` when critical residuals remain,
    or completes when residuals are observational-only.

    EM2: do **not** set ``e2e_soft_junction_residuals`` here. That flag is e2e-only
    for non-naked observational residuals; budget exhaust must not greenwash
    finalize.
    """
    reason = "junction_remaster_budget_exhausted"
    try:
        if junction_oscillation_halted(ctx):
            reason = "junction_oscillation_halt"
    except Exception:
        pass

    def _stamp_classified(meta: dict[str, Any]) -> None:
        meta["junction_remaster_budget_exhausted"] = True
        meta["junction_budget_exhaust_classified"] = True
        meta["junction_budget_exhaust_reason"] = reason
        # Never soft-pass naked via e2e flag on budget exhaust.
        meta.pop("e2e_soft_junction_residuals", None)
        # JSQ-B3: clear any prior operator hang from this exhaust path.
        if str(meta.get("needs_operator_stage") or "") == "junction_snip_qa":
            reason_prev = str(meta.get("needs_operator_reason") or "").lower()
            if (
                "junction_remaster_budget" in reason_prev
                or "junction_oscillation" in reason_prev
                or not reason_prev
            ):
                meta.pop("needs_operator", None)
                meta.pop("needs_operator_stage", None)
                meta.pop("needs_operator_reason", None)

    # Always stamp classified exhaust before ESR wait/halt — flags must land even
    # when remaster disk is still advancing (may_hard_halt False).
    try:
        if not ctx.artifact_exists("run_meta.json"):
            ctx.write_json(
                "run_meta.json",
                {
                    "junction_remaster_budget_exhausted": True,
                    "junction_budget_exhaust_classified": True,
                    "junction_budget_exhaust_reason": reason,
                },
                skip_handoff=True,
            )
        else:
            ctx.mutate_run_meta(_stamp_classified)
    except Exception:
        pass

    # ESR: budget counter may fire while remaster disk still advances — wait.
    try:
        from interview_mux.execution_status import may_hard_halt, wait_vs_halt

        if not may_hard_halt(ctx, pin="junction_snip_qa"):
            wait_vs_halt(
                ctx,
                pin="junction_snip_qa",
                intent="junction_budget",
                reason=reason,
            )
            return "junction_snip_qa"
    except Exception:
        # a8 fail-closed for HARD: classified flags already stamped above
        return "junction_snip_qa"
    try:
        from interview_mux.delivery_guardrails import record_delivery_residual, record_wasted_work

        record_wasted_work(
            ctx,
            event="junction_budget_exhaust",
            stage="junction_snip_qa",
            detail={
                "pin": "junction_snip_qa",
                "soft_pass": False,
                "reason": reason,
                "needs_operator": False,
                "terminate": "classified_refuse",
            },
        )
        live_critical = _live_junction_music_critical(ctx)
        record_delivery_residual(
            ctx,
            kind="junction_budget_exhaust",
            severity="critical" if live_critical else "soft",
            stage="junction_snip_qa",
            detail={
                "pin": "junction_snip_qa",
                "soft_pass": False,
                "reason": reason,
                "needs_operator": False,
                "terminate": "classified_refuse",
                "live_critical_findings": live_critical,
            },
        )
    except Exception:
        pass
    return "junction_snip_qa"


def note_junction_remaster(ctx: RunContext) -> int:
    """Increment remaster count for current seating generation; return new count."""
    gen = _junction_seating_generation(ctx)
    doc = _read_junction_remaster_budget(ctx)
    by_gen = dict(doc.get("by_generation") or {})
    key = str(gen)
    n = int(by_gen.get(key) or 0) + 1
    by_gen[key] = n
    doc["by_generation"] = by_gen
    _write_junction_remaster_budget(ctx, doc)
    return n


def music_epoch_sealed_no_delight_rewind(ctx: RunContext) -> bool:
    """True when music epoch stamped complete — block MusicGen re-entry for delight.

    Seal only blocks music marker wipe / full MusicGen regen. Delight + junction
    + PMQ still gate ship (heal ≠ waive).
    """
    try:
        from interview_mux.delivery_guardrails import music_epoch_complete, read_delivery_epoch

        epoch = read_delivery_epoch(ctx)
        if epoch.get("music_complete_at") and music_epoch_complete(ctx):
            return True
    except Exception:
        pass
    return False


GATE_WAIT_ESCALATE_TICKS = 8



TRUE_WASTE_STICKY_HALT_AFTER = 3



def wasted_work_counts_toward_sticky_halt(
    event: str,
    detail: dict[str, Any] | None = None,
) -> bool:
    """True-waste events that should sticky-halt — excludes expected early music filters."""
    if not wasted_work_is_true_waste(event):
        return False
    ev = str(event or "").strip().lower()
    if ev == "orphan_artifact":
        # Detect-only leftovers (no demote) are shared-path / early-pipeline
        # telemetry — sticky-halting freezes Full-auto mid-delivery (exec_11165).
        if not (detail or {}).get("demoted"):
            return False
    if ev != "music_deferred":
        return True
    reason = str((detail or {}).get("reason") or "").strip().lower()
    # Candidate filtering before assembly / Phase A — not intervene-worthy spend.
    if reason in {"assembly_missing", "phase_a_unsealed"}:
        return False
    if "music_incomplete" in reason:
        return False
    return True



# --- subtraction shim (p3-subtract batch 1) ---------------------------------
# Gate-wait tick counting deleted: the dispatch door refuses on no-delta rather
# than counting how many ticks a stage waited at a gate.
def gate_wait_tick(*_args, **_kwargs):
    raise NotImplementedError(
        "gate_wait_tick removed by p3-subtract; see subtraction-holes.md"
    )


def wasted_work_is_true_waste(*_args, **_kwargs):
    """Removed by p3-subtract; no-delta refusal at the door replaces waste classification."""
    raise NotImplementedError(
        "wasted_work_is_true_waste removed by p3-subtract; see subtraction-holes.md"
    )
