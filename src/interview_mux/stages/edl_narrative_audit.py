from __future__ import annotations

from typing import Any

from interview_mux.stage_input_helpers import attach_disfluency_context
from interview_mux.operator_trace import logged_step
from interview_mux.run_context import RunContext
from interview_mux.artifact_completeness import make_stage_persist
from interview_mux.production_profile import prompt_variant
from interview_mux.source_topology import attach_adaptation_to_payload
from interview_mux.sonic_context import compact_for_volley as sonic_compact_for_volley, load_sonic_context
from interview_mux.stages.analysis_stage import run_flow_llm_stage


def _optional_json(ctx: RunContext, rel_path: str) -> dict:
    return ctx.read_json(rel_path) if ctx.artifact_exists(rel_path) else {}


def _vo_coverage_line_rank(line: dict) -> int:
    """Prefer adjudicated / guarded gap rows over legacy layup duplicates."""
    score = 0
    if line.get("required"):
        score += 4
    if line.get("spoken_copy_guard"):
        score += 4
    if str(line.get("origin") or "") == "vo_line_adjudicate":
        score += 2
    if line.get("text"):
        score += 1
    return score


def compact_vo_coverage(ctx: RunContext) -> list[dict[str, Any]]:
    """Seated/omitted/rendered status for gap VO — not pipeline exists flags."""
    from interview_mux.air_script import omitted_vo_line_ids, seated_vo_line_ids
    from interview_mux.mastering_plan_loader import load_plan_raw
    from interview_mux.vo_synthesis_audit import synthesis_entry_matches_line

    plan = load_plan_raw(ctx) if ctx.artifact_exists("mastering/mastering_plan.json") else {}
    seated = seated_vo_line_ids(plan)
    omitted = omitted_vo_line_ids(plan)
    gap = _optional_json(ctx, "understanding/gap_report.json")
    pickup = ctx.final_path("vo_pickup")
    by_line: dict[str, dict] = {}
    for line in gap.get("interviewer_lines") or []:
        if not isinstance(line, dict):
            continue
        lid = str(line.get("line_id") or "").strip()
        if not lid:
            continue
        prev = by_line.get(lid)
        if prev is None or _vo_coverage_line_rank(line) > _vo_coverage_line_rank(prev):
            by_line[lid] = line
    rows: list[dict[str, Any]] = []
    for lid, line in by_line.items():
        wav = pickup / f"{lid}.wav"
        syn = pickup / "synthesized" / f"{lid}.wav"
        present = wav.is_file() or syn.is_file()
        script_match = False
        if present:
            try:
                script_match, _reason = synthesis_entry_matches_line(ctx, line)
            except Exception:
                script_match = present
        if lid in omitted and lid not in seated:
            coverage = "omitted"
        elif present and script_match:
            coverage = "rendered"
        elif present:
            coverage = "wav_stale"
        else:
            coverage = "missing"
        rows.append(
            {
                "line_id": lid,
                "coverage": coverage,
                "required": bool(line.get("required")),
                "severity": line.get("severity"),
                "script_match": bool(script_match),
            }
        )
    return rows


def compact_air_script_vo_seats(ctx: RunContext) -> dict[str, Any]:
    from interview_mux.air_script import load_air_script
    from interview_mux.mastering_plan_loader import load_plan_raw

    plan = load_plan_raw(ctx) if ctx.artifact_exists("mastering/mastering_plan.json") else {}
    script = load_air_script(plan) or {}
    seats = script.get("vo_seats") if isinstance(script.get("vo_seats"), dict) else {}
    return {
        "seated_line_ids": list(seats.get("seated_line_ids") or []),
        "omitted_line_ids": list(seats.get("omitted_line_ids") or []),
        "orientation_id": seats.get("orientation_id"),
    }


def run_edl_narrative_audit(ctx: RunContext) -> None:
    """Flagship semantic audit before final Flow 1 EDL construction."""

    def build_input(c: RunContext) -> dict:
        payload = {
            "content_brief": c.read_json("understanding/content_brief.json"),
            "coverage_audit": c.read_json("master/coverage_audit.json"),
            "narrative_plan": c.read_json("master/narrative_plan.json"),
            "selection": c.read_json("master/selection.json"),
            "transitions": _optional_json(c, "master/transitions.json"),
            "gap_report": _optional_json(c, "understanding/gap_report.json"),
            "nle_edits": _optional_json(c, "segments/nle_edits.json"),
            "sound_design_plan": _optional_json(c, "understanding/sound_design_plan.json"),
            "air_script_vo_seats": compact_air_script_vo_seats(c),
            "vo_coverage": compact_vo_coverage(c),
            "audit_mode": "heard_wav_flow",
            "vo_synthesis_complete": c.is_done("vo_synthesize"),
        }
        sdp = payload.get("sound_design_plan")
        if isinstance(sdp, dict):
            assets = sdp.get("assets") if isinstance(sdp.get("assets"), list) else []
            payload["sound_design_asset_summary"] = {
                "asset_count": len(assets),
                "roles": sorted(
                    {
                        str(row.get("role"))
                        for row in assets
                        if isinstance(row, dict) and row.get("role")
                    }
                ),
            }
        sonic_context = load_sonic_context(c)
        if sonic_context:
            payload["sonic_context"] = sonic_compact_for_volley(sonic_context)
        return attach_disfluency_context(
            __import__("interview_mux.delivery_brief", fromlist=["attach_delivery_brief_to_payload"]).attach_delivery_brief_to_payload(
                c, attach_adaptation_to_payload(c, payload)
            ),
            c,
        )

    base_persist = make_stage_persist("master/edl_narrative_audit.json", "edl_narrative_audit")

    def persist_with_repair(c: RunContext, artifacts: dict) -> None:
        from interview_mux.audit_repair_loop import maybe_repair_after_narrative_audit

        repaired_artifacts = maybe_repair_after_narrative_audit(c, artifacts)
        base_persist(c, repaired_artifacts)

    ctx.log(
        "Running EDL narrative audit with local volley framing before flagship review.",
        level="info",
        stage="edl_narrative_audit",
    )
    with logged_step("edl_narrative_audit/llm_stage", ctx=ctx, stage="edl_narrative_audit"):
        run_flow_llm_stage(
            ctx,
            "edl_narrative_audit",
            prompt_variant("selection/edl-narrative-audit.system.txt", ctx),
            build_input,
            persist_with_repair,
        )
