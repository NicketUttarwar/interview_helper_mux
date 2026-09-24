"""Product delivery recovery — archive restore, G1 pickups, resume suggestion."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from interview_mux.delivery_guardrails import MUSIC_BEFORE_MIX
from interview_mux.run_context import RunContext
from interview_mux.v2.config import DELIVERY_ORDER, effective_delivery_order

MASTER_RESTORE_NAMES = (
    "edl.json",
    "selection.json",
    "transitions.json",
    "coverage_audit.json",
    "narrative_plan.json",
    "edl_narrative_audit.json",
    "assembly.wav",
    "assembly_preview.wav",
    "assembly_ledger.json",
    "seam_autopsy.json",
    "render_ledger.json",
    "junction_snip_qa.json",
)

SOUND_DESIGN_RESTORE_NAMES = ("sfx_prompts.json", "mmaudio_qa.json")


def newest_archived(ctx: RunContext, rel: str) -> Path | None:
    """Newest ``.archived/*/rel`` by sorted path (timestamp dirs sort lexicographically)."""
    arch = Path(ctx.run_dir) / ".archived"
    if not arch.is_dir():
        return None
    cands = sorted(arch.glob(f"*/{rel}"))
    return cands[-1] if cands else None


def restore_master_artifact(
    ctx: RunContext,
    rel: str,
    *,
    overwrite: bool = False,
    min_bytes: int = 0,
) -> Path | None:
    """Copy newest archived file to final path. Returns dest if restored/already present."""
    dest = ctx.final_path(*rel.split("/"))
    if dest.is_file() and not overwrite:
        if min_bytes <= 0 or dest.stat().st_size > min_bytes:
            return dest
    src = newest_archived(ctx, rel)
    if src is None:
        return dest if dest.is_file() else None
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    ctx.log(
        f"Restored {rel} from archive",
        level="info",
        stage="delivery_recovery",
        detail={"archive_src": str(src.relative_to(ctx.run_dir)), "rel": rel},
    )
    return dest


def restore_master_bundle(
    ctx: RunContext,
    *,
    names: tuple[str, ...] = MASTER_RESTORE_NAMES,
    sound_design: tuple[str, ...] = SOUND_DESIGN_RESTORE_NAMES,
) -> list[str]:
    """Restore common master + sound_design companions after invalidate/archive."""
    restored: list[str] = []
    for name in names:
        rel = f"master/{name}"
        before = ctx.final_path(*rel.split("/")).is_file()
        min_b = 1000 if name.endswith((".json", ".wav")) else 0
        path = restore_master_artifact(ctx, rel, min_bytes=min_b)
        if path is not None and not before and path.is_file():
            restored.append(rel)
    for name in sound_design:
        rel = f"sound_design/{name}"
        before = ctx.final_path(*rel.split("/")).is_file()
        path = restore_master_artifact(ctx, rel)
        if path is not None and not before and path.is_file():
            restored.append(rel)
    # vo_pickup synthesis companions (C2)
    for rel_suffix in ("vo_pickup/synthesis_report.json",):
        rel = rel_suffix
        before = ctx.final_path(*rel.split("/")).is_file()
        path = restore_master_artifact(ctx, rel)
        if path is not None and not before and path.is_file():
            restored.append(rel)
    arch = Path(ctx.run_dir) / ".archived"
    if arch.is_dir():
        for pattern in ("*/vo_pickup/synthesized/*.wav", "*/master/transitions/synthesized/*.wav"):
            for src in sorted(arch.glob(pattern)):
                try:
                    parts = src.parts
                    idx = parts.index(".archived")
                    rel_parts = parts[idx + 2 :]
                    rel = "/".join(rel_parts)
                    dest = ctx.final_path(*rel.split("/"))
                    if dest.is_file():
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    restored.append(rel)
                except (ValueError, OSError):
                    continue
    return restored


def heal_layup_spoken_copy(ctx: RunContext) -> int:
    """Repair grounded layups or skip unhealable rows before G1 can deadlock."""
    from interview_mux.nugget_layup import (
        PLAN_REL,
        publish_layup_plan_to_gap_report,
        repair_or_skip_spoken_copy_layups,
    )
    from interview_mux.spoken_copy_guard import artifact_spoken_copy_errors

    if not ctx.artifact_exists(PLAN_REL):
        return 0
    plan = ctx.read_json(PLAN_REL)
    if not isinstance(plan, dict):
        return 0
    repaired, notes = repair_or_skip_spoken_copy_layups(ctx, plan)
    n = sum(
        1
        for note in notes
        if note.get("action")
        in {
            "repair_spoken_copy_layup",
            "skip_unhealable_spoken_copy_layup",
            "rewrite_meta_question_layup",
        }
    )
    if n:
        from interview_mux.vo_synthesis_audit import invalidate_synthesis_entries

        changed_ids = [
            str(note.get("line_id") or "")
            for note in notes
            if note.get("action")
            in {
                "repair_spoken_copy_layup",
                "skip_unhealable_spoken_copy_layup",
                "rewrite_meta_question_layup",
            }
            and note.get("line_id")
        ]
        invalidate_synthesis_entries(ctx, changed_ids)
        from interview_mux.artifact_sanitize.one_writer import commit_nugget_layup_plan_doc

        commit_nugget_layup_plan_doc(
            ctx,
            repaired,
            skip_handoff=True,
            reason="heal_layup_spoken_copy",
        )
        publish_layup_plan_to_gap_report(ctx, repaired)
        gap = (
            ctx.read_json("understanding/gap_report.json")
            if ctx.artifact_exists("understanding/gap_report.json")
            else None
        )
        transitions = (
            ctx.read_json("master/transitions.json")
            if ctx.artifact_exists("master/transitions.json")
            else None
        )
        remaining = artifact_spoken_copy_errors(
            gap_report=gap if isinstance(gap, dict) else None,
            transitions=transitions if isinstance(transitions, dict) else None,
        )
        hard = [
            e
            for e in remaining
            if "spoken_repeated_" in e
            or "spoken_edit_structure_ref" in e
            or "spoken_chapter" in e
            or "spoken_construction_meta" in e
            or "spoken_show_scaffold" in e
        ]
        if hard:
            ctx.log(
                "heal_layup_spoken_copy: residual spoken-copy errors remain: "
                + "; ".join(hard[:4]),
                level="warning",
                stage="delivery_recovery",
            )
    return n


def ensure_g1_pickups(
    ctx: RunContext,
    *,
    line_ids: list[str] | None = None,
    promote: bool = True,
    max_rounds: int = 1,
    heal_spoken_copy: bool = True,
) -> dict[str, Any]:
    """Synthesize missing G1 VO lines (delivery==synthesize) via s2s_runner."""
    from interview_mux import durable_jobs, s2s_runner
    from interview_mux.gates import check_g1_vo
    from interview_mux.stages.assembly import resolve_vo_pickup_path
    from interview_mux.synthesis_fallback import SynthesisFallbackToManual

    if heal_spoken_copy:
        try:
            heal_layup_spoken_copy(ctx)
        except Exception as exc:
            ctx.log(
                f"spoken-copy heal skipped: {exc}",
                level="warning",
                stage="delivery_recovery",
            )

    if not ctx.artifact_exists("understanding/gap_report.json"):
        return {
            "ok": False,
            "error": "missing_gap_report",
            "synthesized": [],
            "errors": [],
            "g1_missing": [],
        }

    try:
        from interview_mux.vo_synthesis_audit import purge_stale_vo_wavs_for_script_drift

        purged = purge_stale_vo_wavs_for_script_drift(ctx)
        if purged:
            ctx.log(
                f"ensure_g1_pickups: purged {len(purged)} stale VO take(s) before synth",
                stage="delivery_recovery",
                detail=purged[:12],
            )
    except Exception as exc:
        ctx.log(
            f"stale VO purge skipped: {exc}",
            level="warning",
            stage="delivery_recovery",
        )

    try:
        from interview_mux.source_topology import (
            confirm_pickup_speaker,
            ensure_source_topology,
            ensure_speaker_sample_clips,
            pickup_speaker_confirmed,
        )

        ensure_source_topology(ctx)
        ensure_speaker_sample_clips(ctx)
        if not pickup_speaker_confirmed(ctx):
            try:
                confirm_pickup_speaker(ctx)
            except Exception:
                pass
        from interview_mux.gap_vo_gates import maybe_auto_accept_gap_gate_defaults

        maybe_auto_accept_gap_gate_defaults(ctx)
    except Exception as exc:
        ctx.log(
            f"clone-voice prereq ensure skipped: {exc}",
            level="warning",
            stage="delivery_recovery",
        )

    from interview_mux.gap_vo_gates import gap_framing_enabled, vo_ladder_complete

    if gap_framing_enabled(ctx):
        ok, reason = vo_ladder_complete(ctx, for_synthesize=True)
        if not ok and reason != "no_synthesize_lines":
            return {
                "ok": False,
                "error": reason or "vo_ladder_incomplete",
                "reason_code": reason,
                "synthesized": [],
                "errors": [f"vo_ladder_incomplete:{reason}"],
                "g1_missing": check_g1_vo(ctx),
            }

    report = ctx.read_json("understanding/gap_report.json")
    omitted: set[str] = set()
    try:
        from interview_mux.air_script import omitted_vo_line_ids
        from interview_mux.mastering_plan_loader import load_plan_raw

        if ctx.artifact_exists("mastering/mastering_plan.json"):
            omitted = omitted_vo_line_ids(load_plan_raw(ctx))
    except Exception:
        omitted = set()
    lines = [
        L
        for L in (report.get("interviewer_lines") or [])
        if isinstance(L, dict)
        and str(L.get("delivery") or "").lower() == "synthesize"
        and not L.get("skipped_optional")
        and not L.get("air_script_omit")
        and str(L.get("line_id") or "") not in omitted
    ]
    unit_ids = [str(L.get("line_id")) for L in lines if L.get("line_id")]
    job = durable_jobs.begin_job(
        ctx,
        stage_id="g1_vo",
        job_id="ensure_pickups",
        units=unit_ids,
        input_payload={"line_ids": unit_ids},
    )

    synthesized: list[str] = []
    errors: list[dict[str, Any]] = []
    fallbacks: list[dict[str, Any]] = []

    for _ in range(max(1, max_rounds)):
        missing = check_g1_vo(ctx)
        if line_ids is not None:
            want = set(line_ids)
            missing = [m for m in missing if m in want]
        # Durable "completed" must not hide stale script-hash rejects —
        # check_g1_vo already proved resolve_vo_pickup_path failed.
        if missing:
            for lid in missing:
                try:
                    durable_jobs.reset_unit(
                        ctx,
                        "g1_vo",
                        "ensure_pickups",
                        lid,
                        reason="stale_or_missing_pickup",
                    )
                except Exception:
                    pass
        if not missing:
            break
        # Refresh job view after reopen so unit statuses are pending.
        job = durable_jobs.load_job(ctx, "g1_vo", "ensure_pickups") or job
        by_id = {
            str(L.get("line_id")): L
            for L in (report.get("interviewer_lines") or [])
            if isinstance(L, dict)
        }
        for lid in missing:
            line = by_id.get(lid)
            if not line:
                errors.append({"line_id": lid, "error": "unknown_line_id"})
                durable_jobs.fail_unit(ctx, "g1_vo", "ensure_pickups", lid, error="unknown_line_id")
                continue
            if str(line.get("delivery") or "").lower() != "synthesize":
                continue
            if line.get("skipped_optional") or line.get("air_script_omit"):
                continue
            if lid in omitted:
                continue
            existing = resolve_vo_pickup_path(ctx, line)
            if existing is not None:
                durable_jobs.complete_unit(
                    ctx,
                    "g1_vo",
                    "ensure_pickups",
                    lid,
                    output_path=str(existing),
                )
                synthesized.append(lid)
                continue
            try:
                out = s2s_runner.synthesize_line(ctx, line, mode="synthesize")
                if promote:
                    s2s_runner.promote_synthesized_vo(ctx, line_id=lid, src=Path(out))
                durable_jobs.complete_unit(
                    ctx,
                    "g1_vo",
                    "ensure_pickups",
                    lid,
                    output_path=str(out),
                )
                synthesized.append(lid)
            except SynthesisFallbackToManual as fb:
                fallbacks.append({"line_id": lid, "notice": fb.notice})
                durable_jobs.fail_unit(
                    ctx, "g1_vo", "ensure_pickups", lid, error=str(fb.notice)[:500]
                )
            except Exception as exc:
                errors.append({"line_id": lid, "error": str(exc)[:500]})
                durable_jobs.fail_unit(
                    ctx, "g1_vo", "ensure_pickups", lid, error=str(exc)[:500]
                )
        job = durable_jobs.load_job(ctx, "g1_vo", "ensure_pickups") or job
        durable_jobs.heartbeat_job(ctx, "g1_vo", "ensure_pickups")

    if promote:
        synth_dir = ctx.final_path("vo_pickup") / "synthesized"
        if synth_dir.is_dir():
            for wav in synth_dir.glob("*.wav"):
                s2s_runner.promote_synthesized_vo(ctx, line_id=wav.stem, src=wav)

    missing_final = check_g1_vo(ctx)
    if not missing_final:
        try:
            from interview_mux.homunculus.gates import try_set_gate_decision

            try_set_gate_decision(ctx, "vo_pickup", "complete")
        except Exception:
            pass
    return {
        "ok": not errors and not missing_final,
        "synthesized": synthesized,
        "errors": errors,
        "fallbacks": fallbacks,
        "g1_missing": missing_final,
        "job": durable_jobs.load_job(ctx, "g1_vo", "ensure_pickups"),
    }


def _edl_ready_artifacts(ctx: RunContext) -> bool:
    return bool(
        ctx.artifact_exists("master/selection.json")
        and ctx.artifact_exists("understanding/sound_design_plan.json")
        and ctx.artifact_exists("understanding/gap_report.json")
        and ctx.artifact_exists("understanding/nugget_layup_plan.json")
    )


def first_pending_delivery(
    ctx: RunContext,
    ids: tuple[str, ...] | list[str] | None = None,
) -> str | None:
    order = ids or effective_delivery_order()
    for sid in order:
        if not ctx.is_done(sid):
            return sid
    return None


def resume_theme_generation(ctx: RunContext) -> str:
    """Resume seating via Always-HAU SSOT (speech-first mix or music producers)."""
    from interview_mux.mix_junction_seat import next_delivery_seat

    pin = next_delivery_seat(ctx)
    # Preserve legacy unmarked-hollow behavior when SSOT says music producer.
    if pin in MUSIC_BEFORE_MIX:
        from interview_mux.sdp_cross_validate import missing_sdp_asset_wavs

        missing = missing_sdp_asset_wavs(ctx)
        if missing:
            for sid in MUSIC_BEFORE_MIX:
                if not _seed_stage_complete(ctx, sid):
                    marker = Path(ctx.run_dir) / ".stage_done" / sid
                    if marker.is_file():
                        marker.unlink()
                        try:
                            ctx.log(
                                f"unmarked {sid} — SDP theme WAVs missing; generate before mix",
                                level="warning",
                                stage=sid,
                            )
                        except Exception:
                            pass
            return pin if pin in MUSIC_BEFORE_MIX else "music_palette_compose"
    return pin


def _seed_stage_complete(ctx: RunContext, stage: str) -> bool:
    from interview_mux.delivery_guardrails import seed_stage_complete as _ssc

    return _ssc(ctx, stage)


def suggest_delivery_resume(ctx: RunContext) -> str | None:
    """Furthest sensible delivery from_stage from on-disk artifacts.

    Does not soft-force junction pass or mass mark_done (quality-first).
    Always-HAU: mid-delivery seating uses ``next_delivery_seat``.
    """
    root = Path(ctx.run_dir)
    asm = (root / "master" / "assembly.wav").is_file()
    edl = (root / "master" / "edl.json").is_file()
    master = (root / "master" / "master.wav").is_file()

    post_finalize = (
        "master_finalize",
        "master_transcript_build",
        "episode_meta_build",
        "episode_cover_prompt_craft",
        "podcast_encode_mp3",
        "episode_cover_generate",
        "podcast_publish",
    )
    try:
        from interview_mux.done_authority import honest_finalize_seeded

        honest_fin = bool(honest_finalize_seeded(ctx))
    except Exception:
        honest_fin = bool(ctx.is_done("master_finalize"))
    if master and honest_fin:
        return first_pending_delivery(ctx, post_finalize)

    if _edl_ready_artifacts(ctx) and not edl:
        return "edl"

    if asm and edl:
        try:
            from interview_mux.delivery_guardrails import music_epoch_complete
            from interview_mux.mix_junction_seat import next_delivery_seat

            # Seated assembly mid-path: SSOT chooses remaster / music / junction.
            if not music_epoch_complete(ctx) or not ctx.is_done("junction_snip_qa"):
                return next_delivery_seat(ctx)
        except Exception:
            pass
        if not ctx.is_done("junction_snip_qa"):
            return "junction_snip_qa"
        return first_pending_delivery(ctx, ("junction_snip_qa",) + post_finalize)

    preview = (root / "master" / "assembly_preview.wav").is_file()
    if edl or preview or asm:
        try:
            from interview_mux.mix_junction_seat import next_delivery_seat

            return next_delivery_seat(ctx)
        except Exception:
            return resume_theme_generation(ctx)
    return first_pending_delivery(ctx)


def ensure_mmaudio_qa_before_mix(
    ctx: RunContext, *, run_if_missing: bool = False
) -> dict[str, Any]:
    """Restore, optionally generate, or note missing MMAudio QA before mix."""
    # HAU speech-first: beds optional until remaster — do not block mix on QA.
    try:
        from interview_mux.mix_junction_seat import beds_deferred_for_mix

        if beds_deferred_for_mix(ctx):
            return {"ok": True, "speech_first": True, "path": "sound_design/mmaudio_qa.json"}
    except Exception:
        pass
    rel = "sound_design/mmaudio_qa.json"
    if ctx.artifact_exists(rel):
        try:
            from interview_mux.mmaudio_asset_qa import heal_mmaudio_qa_wav_parity

            heal_mmaudio_qa_wav_parity(ctx)
        except Exception:
            pass
        return {"ok": True, "restored": False, "path": rel}
    restored = restore_master_artifact(ctx, rel)
    if restored is not None and restored.is_file():
        return {"ok": True, "restored": True, "path": rel}
    if run_if_missing:
        try:
            from interview_mux.mmaudio_asset_qa import run_mmaudio_asset_qa

            run_mmaudio_asset_qa(ctx)
            if ctx.artifact_exists(rel):
                return {"ok": True, "restored": False, "generated": True, "path": rel}
        except Exception as exc:
            return {
                "ok": False,
                "restored": False,
                "path": rel,
                "error": f"mmaudio_qa_generate_failed:{exc}",
            }
    return {"ok": False, "restored": False, "path": rel, "error": "mmaudio_qa_missing"}
