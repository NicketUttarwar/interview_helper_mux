"""Read-only Refinement Pass summary API — GUI quality surfaces.

Thin passthrough over the refinement_* artifact modules (agenda, plan,
champion, evidence, cascade, listener outcome trajectory) plus a lightweight
"bible" snapshot (thesis / chapters / host lines). Evidence packets are
listed by path only — the GUI opens the JSON via the existing file editor
(``openArtifactInEditor``) rather than round-tripping full packet content.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from interview_mux.refinement_agenda import load_agenda
from interview_mux.refinement_cascade import load_cascade
from interview_mux.refinement_champion import CHAMPION_DIR
from interview_mux.refinement_evidence import EVIDENCE_DIR
from interview_mux.refinement_gate import load_plan
from interview_mux.refinement_outcome import TRAJECTORY_REL
from interview_mux.run_context import RunContext


def _load_champion_map(ctx: RunContext) -> dict[str, Any]:
    out: dict[str, Any] = {}
    champion_dir = ctx.path(CHAMPION_DIR)
    if not champion_dir.is_dir():
        return out
    for f in sorted(champion_dir.glob("*.json")):
        rel = f"{CHAMPION_DIR}/{f.name}"
        try:
            doc = ctx.read_json(rel)
        except Exception:
            continue
        if isinstance(doc, dict):
            out[doc.get("domain") or f.stem] = doc
    return out


def _load_evidence_refs(ctx: RunContext) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    evidence_dir = ctx.path(EVIDENCE_DIR)
    if not evidence_dir.is_dir():
        return out
    for f in sorted(evidence_dir.glob("*.json")):
        rel = f"{EVIDENCE_DIR}/{f.name}"
        out.append({"pass_id": f.stem, "path": rel})
    return out


def _load_bible(ctx: RunContext) -> dict[str, Any]:
    bible: dict[str, Any] = {}
    if ctx.artifact_exists("understanding/content_brief.json"):
        brief = ctx.read_json("understanding/content_brief.json")
        if isinstance(brief, dict) and brief.get("thesis"):
            bible["thesis"] = brief.get("thesis")
    if ctx.artifact_exists("master/narrative_plan.json"):
        plan = ctx.read_json("master/narrative_plan.json")
        if isinstance(plan, dict):
            chapters = [
                c.get("title")
                for c in (plan.get("chapters") or [])
                if isinstance(c, dict) and c.get("title")
            ]
            if chapters:
                bible["chapters"] = chapters[:12]
    if ctx.artifact_exists("understanding/gap_report.json"):
        report = ctx.read_json("understanding/gap_report.json")
        if isinstance(report, dict):
            host_lines = [
                line.get("text")
                for line in (report.get("interviewer_lines") or [])
                if isinstance(line, dict) and line.get("text")
            ]
            if host_lines:
                bible["host_lines"] = host_lines[:5]
    return bible


def register_refinement_routes(router: APIRouter, *, ctx_factory: Any) -> None:
    @router.get("/api/runs/{run_id}/refinement")
    def get_refinement_summary(run_id: str) -> dict[str, Any]:
        ctx = ctx_factory(run_id)
        return {
            "agenda": load_agenda(ctx),
            "plan": load_plan(ctx),
            "champion": _load_champion_map(ctx),
            "evidence_packets": _load_evidence_refs(ctx),
            "cascade": load_cascade(ctx),
            "listener_outcome_trajectory": (
                ctx.read_json(TRAJECTORY_REL) if ctx.artifact_exists(TRAJECTORY_REL) else None
            ),
            "bible": _load_bible(ctx),
        }
