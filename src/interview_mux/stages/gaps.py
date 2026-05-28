from __future__ import annotations

from interview_mux.run_context import RunContext
from interview_mux.stages.analysis_stage import run_analysis_llm_stage, sync_gaps_to_state


def run_missing_framing(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        return {
            "segments": c.read_json("segments/manifest.json"),
            "content_brief": c.read_json("understanding/content_brief.json"),
        }

    def persist(c: RunContext, artifacts: dict) -> None:
        c.write_json("understanding/gap_evaluations.json", artifacts)

    run_analysis_llm_stage(
        ctx,
        "missing_framing",
        "interviewer-gap/missing-framing.system.txt",
        build_input,
        persist,
        sync_fn=lambda c, a: sync_gaps_to_state(c, a),
    )
    ctx.mark_done("missing_framing")


def run_optimal_questions(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        return {
            "gap_evaluations": c.read_json("understanding/gap_evaluations.json"),
            "segments": c.read_json("segments/manifest.json"),
            "content_brief": c.read_json("understanding/content_brief.json"),
        }

    def persist(c: RunContext, artifacts: dict) -> None:
        lines = artifacts.get("interviewer_lines") or []
        for i, line in enumerate(lines):
            if "line_id" not in line:
                line["line_id"] = f"line_{i+1:03d}"
            if not line.get("placement"):
                line["placement"] = "before"
            if line.get("delivery") == "synthesize":
                line["delivery"] = "record"
        c.write_json("understanding/gap_report.json", artifacts)
        _write_interviewer_script(c, lines)

    run_analysis_llm_stage(
        ctx,
        "optimal_questions",
        "interviewer-gap/optimal-questions.system.txt",
        build_input,
        persist,
    )
    ctx.mark_done("optimal_questions")


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
    """Validate VO files exist; no transform in v1."""
    report = ctx.read_json("understanding/gap_report.json")
    pickup = ctx.path("vo_pickup")
    missing = []
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
        if not any(p.is_file() for p in candidates):
            missing.append(lid or seg)
    if missing:
        raise RuntimeError(
            f"Missing VO pickup files for: {missing}. "
            f"Record and place under {pickup}"
        )
    ctx.mark_done("vo_ingest")
