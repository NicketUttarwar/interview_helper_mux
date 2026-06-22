"""Artifact phase and outputs_view for operator UI truth."""

from __future__ import annotations

from typing import Any, Literal

from interview_mux.run_context import RunContext
from interview_mux.web.stages import STAGE_BY_ID

ArtifactPhase = Literal["missing", "generating", "staged", "committed", "partial", "skipped", "n_a"]


def _is_staged(ctx: RunContext, stage_id: str, rel: str) -> bool:
    from interview_mux.write_staging import staged_path

    p = staged_path(ctx, rel, stage_id=stage_id)
    return p.is_file()


def _is_committed(ctx: RunContext, rel: str) -> bool:
    p = ctx.final_path(*rel.split("/"))
    return p.is_file() and p.stat().st_size > 0


def artifact_phase(ctx: RunContext, stage_id: str, rel: str) -> ArtifactPhase:
    if _is_staged(ctx, stage_id, rel):
        return "staged"
    if not _is_committed(ctx, rel):
        return "missing"
    from interview_mux.artifact_completeness import artifact_status

    status = artifact_status(rel, ctx)
    if status == "partial":
        return "partial"
    return "committed"


def stage_output_mode(ctx: RunContext, stage_id: str) -> str:
    if stage_id == "audio_preclean":
        from interview_mux.stages.audio_preclean import preclean_was_skipped

        if preclean_was_skipped(ctx):
            return "optional_skipped"
        if ctx.is_done(stage_id):
            return "optional_ran"
        return "optional"
    if stage_id == "vo_ingest":
        return "on_demand"
    if stage_id in (
        "transcript_review",
        "disfluency_review",
        "analysis_profile",
        "g1_vo_pickup",
        "g2_flow_select",
    ):
        return "gate"
    return "required"


def build_outputs_view(ctx: RunContext, stage_id: str) -> list[dict[str, Any]]:
    from interview_mux.stage_guidance import _artifact_checks

    checks = _artifact_checks(ctx, stage_id)
    if checks and (
        stage_id == "audio_preclean"
        or checks[0].get("path") in ("preclean/skip.json", "(skipped)")
    ):
        rows: list[dict[str, Any]] = []
        for row in checks:
            st = row.get("status", "waiting")
            phase: ArtifactPhase = "committed" if st == "done" else "missing"
            rows.append(
                {
                    "path": row.get("path", ""),
                    "label": row.get("label", row.get("path", "")),
                    "status": "complete" if st == "done" else "pending",
                    "phase": "skipped" if row.get("path") == "(skipped)" else phase,
                    "kind": "skip" if row.get("path") == "(skipped)" else "artifact",
                }
            )
        info = STAGE_BY_ID.get(stage_id)
        if info and stage_output_mode(ctx, stage_id) == "optional_skipped":
            for spec in info.artifacts:
                if spec and not spec.endswith("/"):
                    rows.append(
                        {
                            "path": spec,
                            "label": spec.split("/")[-1].replace("_", " "),
                            "status": "n_a",
                            "phase": "n_a",
                            "kind": "n_a",
                        }
                    )
        return rows

    info = STAGE_BY_ID.get(stage_id)
    if not info:
        return []

    rows = []
    for spec in info.artifacts:
        if not spec or spec.endswith("/"):
            continue
        phase = artifact_phase(ctx, stage_id, spec)
        status_map = {
            "missing": "pending",
            "staged": "staged",
            "committed": "complete",
            "partial": "partial",
            "skipped": "skipped",
            "n_a": "n_a",
            "generating": "pending",
        }
        rows.append(
            {
                "path": spec,
                "label": spec.split("/")[-1].replace("_", " "),
                "status": status_map.get(phase, "pending"),
                "phase": phase,
                "kind": "artifact",
            }
        )
    return rows


def split_artifact_lists(
    ctx: RunContext, stage_id: str, artifacts: tuple[str, ...]
) -> tuple[list[str], list[str], dict[str, str]]:
    committed: list[str] = []
    staged: list[str] = []
    lifecycle: dict[str, str] = {}
    for rel in artifacts:
        if not rel or rel.endswith("/"):
            continue
        phase = artifact_phase(ctx, stage_id, rel)
        lifecycle[rel] = phase
        if phase == "staged":
            staged.append(rel)
        elif phase in ("committed", "partial"):
            committed.append(rel)
    return committed, staged, lifecycle
