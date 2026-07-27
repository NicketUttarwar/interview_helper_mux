"""Evidence packets — the read-only bundle a refinement pass reasons over."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from interview_mux.refinement_flow_integrity import DRAFT_REL, FINAL_REL
from interview_mux.refinement_policy import resolve_policy_pack
from interview_mux.run_context import RunContext

EVIDENCE_DIR = "understanding/refinement_evidence"


def build_evidence_packet(ctx: RunContext, pass_id: str) -> dict[str, Any]:
    """Assemble the deterministic evidence bundle for a refinement pass.

    For ``gap_framing_recompose`` this includes: kept-order selection ids,
    the draft gap_report, narrative plan, coverage audit, comprehension
    risks filtered down to kept segments, the resolved policy pack, and
    (optionally) the mastering plan's cold_open notes.
    """
    pack = resolve_policy_pack(ctx)
    packet: dict[str, Any] = {
        "pass_id": pass_id,
        "at": datetime.now(timezone.utc).isoformat(),
        "policy_pack": pack,
        "artifacts": {},
    }
    paths = {
        "draft_gap_report": DRAFT_REL if ctx.artifact_exists(DRAFT_REL) else FINAL_REL,
        "selection": "master/selection.json",
        "narrative_plan": "master/narrative_plan.json",
        "coverage_audit": "master/coverage_audit.json",
        "episode_structure": "understanding/episode_structure.json",
        "content_brief": "understanding/content_brief.json",
        "gap_evaluations": "understanding/gap_evaluations.json",
        "mastering_plan": "mastering/mastering_plan.json",
    }
    for key, rel in paths.items():
        if not ctx.artifact_exists(rel):
            continue
        try:
            packet["artifacts"][key] = ctx.read_json(rel)
        except Exception:
            packet["artifacts"][key] = {"_error": "read_failed", "rel": rel}

    ordered: list[str] = []
    selection = packet["artifacts"].get("selection")
    if isinstance(selection, dict):
        ordered = [str(x) for x in (selection.get("ordered_segment_ids") or [])]

    if ordered and ctx.artifact_exists("understanding/comprehension_risks.json"):
        risks = ctx.read_json("understanding/comprehension_risks.json")
        if isinstance(risks, dict):
            items = risks.get("risks") or risks.get("segments") or []
            kept = set(ordered)
            packet["artifacts"]["comprehension_risks_kept"] = [
                row
                for row in items
                if isinstance(row, dict) and str(row.get("segment_id") or "") in kept
            ]

    mastering_plan = packet["artifacts"].get("mastering_plan")
    if isinstance(mastering_plan, dict):
        packet["artifacts"]["mastering_cold_open"] = mastering_plan.get("cold_open")

    ctx.write_json(f"{EVIDENCE_DIR}/{pass_id}.json", packet)
    return packet


def load_evidence_packet(ctx: RunContext, pass_id: str) -> dict[str, Any] | None:
    rel = f"{EVIDENCE_DIR}/{pass_id}.json"
    if not ctx.artifact_exists(rel):
        return None
    doc = ctx.read_json(rel)
    return doc if isinstance(doc, dict) else None
