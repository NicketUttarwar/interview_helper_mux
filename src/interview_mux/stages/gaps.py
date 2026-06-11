from __future__ import annotations

from pathlib import Path

from interview_mux.analysis_memory import load_analysis_state
from interview_mux.tone_taxonomy import compact_profile_style_hints
from interview_mux.llm_specialists import (
    load_comprehension_risks,
    maybe_run_pre_stage_specialists,
)
from interview_mux.run_context import RunContext
from interview_mux.stage_enrichment import compact_value_features_summary
from interview_mux.artifact_completeness import make_stage_persist
from interview_mux.stages.analysis_stage import run_analysis_llm_stage, sync_gaps_to_state


def run_missing_framing(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        payload = {
            "segments": c.read_json("segments/manifest.json"),
            "content_brief": c.read_json("understanding/content_brief.json"),
        }
        risks = load_comprehension_risks(c, "missing_framing")
        if risks:
            payload["comprehension_risks"] = risks
        vf = compact_value_features_summary(c)
        if vf:
            payload["value_features_summary"] = vf
        hints = compact_profile_style_hints(load_analysis_state(c))
        if hints:
            payload["profile_style"] = hints
        return payload

    persist = make_stage_persist("understanding/gap_evaluations.json", "missing_framing")

    maybe_run_pre_stage_specialists(ctx, "missing_framing", build_input(ctx))

    run_analysis_llm_stage(
        ctx,
        "missing_framing",
        "interviewer-gap/missing-framing.system.txt",
        build_input,
        persist,
        sync_fn=lambda c, a: sync_gaps_to_state(c, a),
    )


def run_optimal_questions(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        payload = {
            "gap_evaluations": c.read_json("understanding/gap_evaluations.json"),
            "segments": c.read_json("segments/manifest.json"),
            "content_brief": c.read_json("understanding/content_brief.json"),
        }
        vf = compact_value_features_summary(c)
        if vf:
            payload["value_features_summary"] = vf
        return payload

    def persist(c: RunContext, artifacts: dict) -> None:
        from interview_mux.artifact_writes import write_validated_artifact

        lines = artifacts.get("interviewer_lines") or []
        for i, line in enumerate(lines):
            if "line_id" not in line:
                line["line_id"] = f"line_{i+1:03d}"
            if not line.get("placement"):
                line["placement"] = "before"
            if line.get("delivery") == "synthesize":
                line["delivery"] = "record"
        write_validated_artifact(
            c,
            "understanding/gap_report.json",
            artifacts,
            merge_from_disk=True,
            stage_key="optimal_questions",
        )
        _write_interviewer_script(c, lines)

    run_analysis_llm_stage(
        ctx,
        "optimal_questions",
        "interviewer-gap/optimal-questions.system.txt",
        build_input,
        persist,
    )


def _write_interviewer_script(ctx: RunContext, lines: list[dict]) -> None:
    rows = ["# Interviewer script — record each line to vo_pickup/{line_id}.wav", ""]
    for line in lines:
        lid = line.get("line_id", "line_unknown")
        rows.append(f"## {lid} ({line.get('delivery', 'record')})")
        rows.append(f"Target: {line.get('targets_segment_id', '')} — {line.get('gap_type', '')}")
        rows.append(line.get("text", ""))
        rows.append("")
    ctx.path("understanding", "interviewer_script.txt").write_text("\n".join(rows), encoding="utf-8")


def ingest_vo_pickup(ctx: RunContext) -> None:
    """Validate VO files exist; optionally normalize loudness for mix."""
    import subprocess

    from interview_mux.config import merged_config

    report = ctx.read_json("understanding/gap_report.json")
    pickup = ctx.path("vo_pickup")
    missing = []
    normalized = 0
    mix_cfg = merged_config().get("mix") or {}
    normalize = bool(mix_cfg.get("normalize_vo_pickup", True))
    for line in report.get("interviewer_lines") or []:
        if line.get("delivery") != "record":
            continue
        lid = line.get("line_id", "")
        seg = line.get("targets_segment_id", "")
        clean = pickup / "clean"
        bases = [clean, pickup] if clean.is_dir() else [pickup]
        candidates: list[Path] = []
        for base in bases:
            candidates.extend([base / f"{lid}.wav", base / f"{seg}.wav"])
        found = next((p for p in candidates if p.is_file()), None)
        if not found:
            missing.append(lid or seg)
            continue
        if normalize and found.parent == pickup:
            norm_dir = pickup / "normalized"
            norm_dir.mkdir(parents=True, exist_ok=True)
            out = norm_dir / found.name
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(found),
                    "-af",
                    "loudnorm=I=-18:TP=-1.5:LRA=11",
                    "-ar",
                    "48000",
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    str(out),
                ],
                check=True,
                capture_output=True,
            )
            normalized += 1
    if missing:
        raise RuntimeError(
            f"Missing VO pickup files for: {missing}. "
            f"Record and place under {pickup}"
        )
    if normalized:
        ctx.log(
            f"vo_ingest: normalized {normalized} pickup WAV(s) under vo_pickup/normalized/",
            level="info",
            stage="vo_ingest",
        )
    ctx.mark_done("vo_ingest")
