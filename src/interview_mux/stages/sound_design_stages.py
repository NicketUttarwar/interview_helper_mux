from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from interview_mux.analysis_memory import default_sound_design_plan
from interview_mux.config import repo_root
from interview_mux.gates import require_selected_flow_flow1, require_selected_flow_flow2
from interview_mux.run_context import RunContext
from interview_mux.stages.analysis_stage import run_analysis_llm_stage, run_flow_llm_stage

_SOUND_DESIGN_PLAN_REL = "understanding/sound_design_plan.json"


def run_sound_design_palettes(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        payload: dict = {
            "content_brief": c.read_json("understanding/content_brief.json"),
            "segments": c.read_json("segments/manifest.json"),
            "analysis_state": c.read_json("understanding/analysis_state.json"),
        }
        sdp = _load_sound_design_plan(c)
        payload["sound_design_plan"] = {
            "version": sdp.get("version", 1),
            "coherence": sdp.get("coherence", {}),
            "palettes": sdp.get("palettes", []),
        }
        if c.artifact_exists("understanding/source_acoustic_profile.json"):
            payload["source_acoustic_profile"] = c.read_json("understanding/source_acoustic_profile.json")

        style = (payload["analysis_state"].get("style") or {}) if isinstance(payload["analysis_state"], dict) else {}
        notes = style.get("sound_design_notes")
        if notes:
            payload["operator_style_sound_design_notes"] = notes
        return payload

    def persist(c: RunContext, artifacts: dict) -> None:
        sdp = _load_sound_design_plan(c)
        if "coherence" in artifacts:
            sdp["coherence"] = artifacts["coherence"]
        if "palettes" in artifacts:
            sdp["palettes"] = artifacts["palettes"]
        _validate_sound_design_plan(sdp)
        c.write_json(_SOUND_DESIGN_PLAN_REL, sdp)

    run_analysis_llm_stage(
        ctx,
        "sound_design_palettes",
        "sound_design/theme-palettes.system.txt",
        build_input,
        persist,
    )
    ctx.mark_done("sound_design_palettes")


def run_sound_design_plan_flow1(ctx: RunContext) -> None:
    require_selected_flow_flow1(ctx)

    def build_input(c: RunContext) -> dict:
        return {
            "sound_design_plan": _load_sound_design_plan(c),
            "selection": c.read_json("flow_1_master/selection.json"),
            "narrative_plan": c.read_json("flow_1_master/narrative_plan.json"),
            "transitions": c.read_json("flow_1_master/transitions.json"),
            "gap_report": c.read_json("understanding/gap_report.json"),
            "segments": c.read_json("segments/manifest.json"),
        }

    def persist(c: RunContext, artifacts: dict) -> None:
        sdp = _load_sound_design_plan(c)
        assets = artifacts.get("assets")
        flow_plans = artifacts.get("flow_plans")
        if isinstance(assets, list):
            sdp["assets"] = assets
        if isinstance(flow_plans, dict):
            existing = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
            merged = {"flow1": (existing or {}).get("flow1"), "flow2": (existing or {}).get("flow2")}
            merged.update(flow_plans)
            sdp["flow_plans"] = merged

        _validate_sound_design_plan(sdp)
        _validate_flow1_asset_links(sdp)
        c.write_json(_SOUND_DESIGN_PLAN_REL, sdp)

    run_flow_llm_stage(
        ctx,
        "sound_design_plan_flow1",
        "sound_design/plan-flow1.system.txt",
        build_input,
        persist,
    )
    ctx.mark_done("sound_design_plan_flow1")


def run_sound_design_plan_flow2(ctx: RunContext) -> None:
    require_selected_flow_flow2(ctx)

    def build_input(c: RunContext) -> dict:
        return {
            "sound_design_plan": _load_sound_design_plan(c),
            "selection": c.read_json("flow_2_highlights/selection.json"),
            "content_brief": c.read_json("understanding/content_brief.json"),
        }

    def persist(c: RunContext, artifacts: dict) -> None:
        sdp = _load_sound_design_plan(c)
        assets = artifacts.get("assets")
        flow_plans = artifacts.get("flow_plans")
        if isinstance(assets, list):
            sdp["assets"] = assets
        if isinstance(flow_plans, dict):
            existing = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
            merged = {"flow1": (existing or {}).get("flow1"), "flow2": (existing or {}).get("flow2")}
            merged.update(flow_plans)
            sdp["flow_plans"] = merged

        _validate_sound_design_plan(sdp)
        _validate_flow2_asset_links(sdp)
        c.write_json(_SOUND_DESIGN_PLAN_REL, sdp)

    run_flow_llm_stage(
        ctx,
        "sound_design_plan_flow2",
        "sound_design/plan-flow2.system.txt",
        build_input,
        persist,
    )
    ctx.mark_done("sound_design_plan_flow2")


def run_elevenlabs_prompt_craft(ctx: RunContext) -> None:
    def build_input(c: RunContext) -> dict:
        sdp = _load_sound_design_plan(c)
        payload: dict = {
            "coherence": sdp.get("coherence", {}),
            "assets": sdp.get("assets", []),
        }
        if c.artifact_exists("understanding/source_acoustic_profile.json"):
            payload["source_acoustic_profile"] = c.read_json("understanding/source_acoustic_profile.json")
        if c.artifact_exists("understanding/analysis_state.json"):
            state = c.read_json("understanding/analysis_state.json")
            style = state.get("style") if isinstance(state, dict) else None
            if isinstance(style, dict) and style.get("sound_design_notes"):
                payload["operator_style_sound_design_notes"] = style["sound_design_notes"]
        return payload

    def persist(c: RunContext, artifacts: dict) -> None:
        prompts = artifacts.get("prompts")
        if not isinstance(prompts, list):
            return
        c.write_json("sound_design/elevenlabs_prompts.json", {"prompts": prompts})

    run_flow_llm_stage(
        ctx,
        "elevenlabs_prompt_craft",
        "sound_design/elevenlabs-prompt-craft.system.txt",
        build_input,
        persist,
    )
    ctx.mark_done("elevenlabs_prompt_craft")


def _load_sound_design_plan(ctx: RunContext) -> dict:
    if ctx.artifact_exists(_SOUND_DESIGN_PLAN_REL):
        doc = ctx.read_json(_SOUND_DESIGN_PLAN_REL)
        if isinstance(doc, dict):
            return doc
    return default_sound_design_plan()


def _validate_sound_design_plan(plan: dict) -> None:
    schema = _load_sound_design_schema()
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(plan), key=lambda e: list(e.path))
    if not errors:
        return
    first = errors[0]
    path = ".".join(str(p) for p in first.path) or "(root)"
    raise ValueError(f"Invalid sound design plan at {path}: {first.message}")


def _load_sound_design_schema() -> dict:
    path = repo_root() / "docs" / "cross-cutting" / "json-schemas" / "sound_design_plan.schema.json"
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _validate_flow1_asset_links(plan: dict) -> None:
    assets = plan.get("assets")
    flow_plans = plan.get("flow_plans")
    if not isinstance(assets, list) or not isinstance(flow_plans, dict):
        return
    flow1 = flow_plans.get("flow1") if isinstance(flow_plans.get("flow1"), dict) else {}
    cues = flow1.get("cues") if isinstance(flow1.get("cues"), list) else []
    asset_ids = {str(item.get("asset_id")) for item in assets if isinstance(item, dict) and item.get("asset_id")}
    missing = [
        str(cue.get("cue_id", ""))
        for cue in cues
        if isinstance(cue, dict) and str(cue.get("asset_id", "")) not in asset_ids
    ]
    if missing:
        raise ValueError(
            "Invalid sound design plan flow1: cues reference unknown asset_id values for "
            f"cue_id(s) {missing}"
        )


def _validate_flow2_asset_links(plan: dict) -> None:
    assets = plan.get("assets")
    flow_plans = plan.get("flow_plans")
    if not isinstance(assets, list) or not isinstance(flow_plans, dict):
        return
    flow2 = flow_plans.get("flow2") if isinstance(flow_plans.get("flow2"), dict) else {}
    cues = flow2.get("cues") if isinstance(flow2.get("cues"), list) else []
    asset_ids = {str(item.get("asset_id")) for item in assets if isinstance(item, dict) and item.get("asset_id")}
    missing = [
        str(cue.get("cue_id", ""))
        for cue in cues
        if isinstance(cue, dict) and str(cue.get("asset_id", "")) not in asset_ids
    ]
    if missing:
        raise ValueError(
            "Invalid sound design plan flow2: cues reference unknown asset_id values for "
            f"cue_id(s) {missing}"
        )
