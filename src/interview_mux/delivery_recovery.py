"""Product delivery recovery — archive restore, G1 pickups, resume suggestion."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

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
    return restored


def heal_layup_spoken_copy(ctx: RunContext) -> int:
    """Rewrite layup lines that spoken_copy_guard would block (generic heuristics only)."""
    from interview_mux.file_store import write_json as fs_write_json
    from interview_mux.nugget_layup import PLAN_REL, publish_layup_plan_to_gap_report
    from interview_mux.spoken_copy_guard import spoken_copy_violations

    if not ctx.artifact_exists(PLAN_REL):
        return 0
    plan = ctx.read_json(PLAN_REL)
    if not isinstance(plan, dict):
        return 0
    n = 0
    for row in plan.get("layups") or []:
        if not isinstance(row, dict) or row.get("skip"):
            continue
        text = str(row.get("text") or "").strip()
        if not spoken_copy_violations(text, evidence={}):
            continue
        beat = str(row.get("target_beat") or "").strip()
        unlock = str(row.get("forward_unlock") or "").strip()
        setup = str(row.get("setup_from_nuggets") or "").strip()
        new = " ".join(p for p in (setup, beat, unlock) if p).strip() or text
        new = re.sub(r"(?i)\s*[—\-–,]?\s*stay\s+tuned\b.*$", ".", new).strip()
        new = re.sub(
            r"(?i)\b(?:pipeline\s+stage|from_stage|until_stage|stage_done|"
            r"edit\s+timeline|gap report|unaired\s+corpus|corpus\s+nugget)\b",
            "",
            new,
        )
        new = re.sub(r"\s{2,}", " ", new).strip(" ,.—–-")
        if new and not new.endswith((".", "?", "!")):
            new = new + "."
        if not new or spoken_copy_violations(new, evidence={}):
            continue
        if new != text:
            row["text"] = new
            row["word_count"] = len(new.split())
            n += 1
    if n:
        fs_write_json(ctx.final_path(PLAN_REL), plan)
        publish_layup_plan_to_gap_report(ctx, plan)
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

    report = ctx.read_json("understanding/gap_report.json")
    lines = [
        L
        for L in (report.get("interviewer_lines") or [])
        if isinstance(L, dict)
        and str(L.get("delivery") or "").lower() == "synthesize"
        and not L.get("skipped_optional")
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
        # Skip units already completed in the durable job.
        done_units = {
            str(u.get("unit_id"))
            for u in (job.get("units") or [])
            if isinstance(u, dict) and u.get("status") == "completed"
        }
        missing = [m for m in missing if m not in done_units]
        if not missing:
            break
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
            if line.get("skipped_optional"):
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


def suggest_delivery_resume(ctx: RunContext) -> str | None:
    """Furthest sensible delivery from_stage from on-disk artifacts.

    Does not soft-force junction pass or mass mark_done (quality-first).
    """
    root = Path(ctx.run_dir)
    asm = (root / "master" / "assembly.wav").is_file()
    edl = (root / "master" / "edl.json").is_file()
    master = (root / "master" / "master.wav").is_file()

    post_finalize = (
        "master_finalize",
        "episode_meta_build",
        "episode_cover_prompt_craft",
        "podcast_encode_mp3",
        "episode_cover_generate",
        "podcast_publish",
    )
    if master and ctx.is_done("master_finalize"):
        return first_pending_delivery(ctx, post_finalize)

    if _edl_ready_artifacts(ctx) and not edl:
        return "edl"

    if asm and edl:
        if not ctx.is_done("junction_snip_qa"):
            return "junction_snip_qa"
        return first_pending_delivery(ctx, ("junction_snip_qa",) + post_finalize)

    theme_wavs = list((root / "sound_design" / "assets").glob("*.wav"))
    qa_ok = (root / "sound_design" / "mmaudio_qa.json").is_file()
    if edl and qa_ok and len(theme_wavs) >= 3 and not asm:
        return "mix"
    if edl and ctx.is_done("mmaudio_sfx"):
        return "mix"
    if edl:
        return first_pending_delivery(
            ctx,
            (
                "edl",
                "assembly_preview",
                "listen_delight_audit",
                "music_palette_compose",
                "sfx_prompt_craft",
                "mmaudio_sfx",
                "mix",
                "junction_snip_qa",
            ),
        )
    return first_pending_delivery(ctx, DELIVERY_ORDER)


def ensure_mmaudio_qa_before_mix(ctx: RunContext) -> dict[str, Any]:
    """Restore or note missing MMAudio QA before mix loud-fail."""
    rel = "sound_design/mmaudio_qa.json"
    if ctx.artifact_exists(rel):
        return {"ok": True, "restored": False, "path": rel}
    restored = restore_master_artifact(ctx, rel)
    if restored is not None and restored.is_file():
        return {"ok": True, "restored": True, "path": rel}
    return {"ok": False, "restored": False, "path": rel, "error": "mmaudio_qa_missing"}
