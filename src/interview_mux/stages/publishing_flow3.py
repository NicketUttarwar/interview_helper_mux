from __future__ import annotations

import re

from interview_mux.analysis_memory import load_analysis_state
from interview_mux.config import merged_config
from interview_mux.show_description_qc import (
    validate_show_description,
    validate_show_description_tone_alignment,
)
from interview_mux.tone_taxonomy import tone_class_for_show_description
from interview_mux.artifact_writes import write_validated_artifact
from interview_mux.run_context import RunContext
from interview_mux.stages.analysis_stage import run_flow_llm_stage


def _warn_if_profile_unverified(ctx: RunContext) -> None:
    state = load_analysis_state(ctx)
    if not (state.get("meta") or {}).get("operator_verified"):
        ctx.log(
            "Interview profile is not operator-verified — show copy may drift from your intent. "
            "Verify the profile in the GUI before re-running if needed.",
            level="warning",
            stage="podcast_show_description",
        )


def _show_description_qc_strict_enabled() -> bool:
    sqc = merged_config().get("show_description_qc") or {}
    return bool(sqc.get("strict"))


def run_podcast_show_description(ctx: RunContext) -> None:
    _warn_if_profile_unverified(ctx)
    ctx.path("flow_3_description").mkdir(parents=True, exist_ok=True)

    def build_input(c: RunContext) -> dict:
        out: dict = {
            "content_brief": c.read_json("understanding/content_brief.json"),
            "speakers": c.read_json("understanding/speakers.json"),
            "segments": c.read_json("segments/manifest.json"),
        }
        preferred = tone_class_for_show_description(load_analysis_state(c))
        if preferred:
            out["preferred_tone_class"] = preferred
        if c.artifact_exists("understanding/gap_evaluations.json"):
            ev = c.read_json("understanding/gap_evaluations.json")
            evaluations = ev.get("evaluations") or []
            need = sum(1 for e in evaluations if not e.get("self_explanatory"))
            if need:
                out["gap_summary"] = (
                    f"{need} of {len(evaluations)} segments needed framing; "
                    "use gap report only if it affects how the episode should be pitched."
                )
        if c.artifact_exists("understanding/gap_report.json"):
            rep = c.read_json("understanding/gap_report.json")
            lines = rep.get("interviewer_lines") or []
            record = sum(1 for ln in lines if ln.get("delivery") == "record")
            if lines:
                out["interviewer_vo_summary"] = (
                    f"{len(lines)} pickup lines ({record} recorded) — mention only if relevant to the hook."
                )
        from interview_mux.coherence import attach_coherence_summary

        attach_coherence_summary(out, c, "podcast_show_description")
        return out

    def persist(c: RunContext, artifacts: dict) -> None:
        state = load_analysis_state(c)
        preferred = tone_class_for_show_description(state)
        tone_errors = validate_show_description_tone_alignment(
            artifacts, preferred_tone_class=preferred
        )
        errors = validate_show_description(c, artifacts)
        errors.extend(tone_errors)
        if errors:
            summary = "; ".join(errors[:4])
            c.log(
                f"Show description QC failed ({len(errors)} issue(s)): {summary}",
                level="error" if _show_description_qc_strict_enabled() else "warning",
                stage="podcast_show_description",
                detail="show_description_qc_fail",
            )
            if _show_description_qc_strict_enabled():
                raise RuntimeError(
                    f"show_description_qc strict: {len(errors)} issue(s). "
                    f"Run: python tools/validate_show_description.py --run-id {c.run_id}"
                )
        write_validated_artifact(
            c,
            "flow_3_description/show_description.json",
            artifacts,
            merge_from_disk=True,
            stage_key="podcast_show_description",
        )

    ctx.log(
        "Generating podcast show description (third person, ~200 words)…",
        level="info",
        stage="podcast_show_description",
    )
    run_flow_llm_stage(
        ctx,
        "podcast_show_description",
        "publishing/podcast-show-description.system.txt",
        build_input,
        persist,
    )
    ctx.log(
        "Show description JSON ready — run export or full Flow 3 for plain-text copy.",
        level="success",
        stage="podcast_show_description",
        detail=str(ctx.path("flow_3_description/show_description.json")),
    )


def _plain_export_text(doc: dict) -> str:
    """Render distribution copy without markdown formatting."""
    body = str(doc.get("description_markdown") or "")
    body = body.replace("\\n\\n", "\n\n").replace("\\n", "\n")
    body = re.sub(r"\*\*([^*]+)\*\*", r"\1", body)
    body = re.sub(r"\*([^*]+)\*", r"\1", body)
    lines: list[str] = []
    title = (doc.get("title_suggestion") or "").strip()
    if title:
        lines.append(title)
        lines.append("")
    lines.append(body.strip())
    pitch = (doc.get("audience_pitch") or "").strip()
    if pitch:
        lines.append("")
        lines.append(pitch)
    return "\n".join(lines).strip() + "\n"


def run_export_show_description(ctx: RunContext) -> None:
    json_path = ctx.path("flow_3_description/show_description.json")
    if not json_path.is_file():
        raise FileNotFoundError(
            f"Missing {json_path.relative_to(ctx.run_dir)} — run podcast_show_description first."
        )
    doc = ctx.read_json("flow_3_description/show_description.json")
    ctx.path("flow_3_description").mkdir(parents=True, exist_ok=True)
    md_path = ctx.path("flow_3_description/show_description.md")
    md_path.write_text(_plain_export_text(doc), encoding="utf-8")
    ctx.mark_done("export_show_description")
    ctx.log(
        "Exported plain-text show description for podcast directories.",
        level="success",
        stage="export_show_description",
        detail=str(md_path),
    )
