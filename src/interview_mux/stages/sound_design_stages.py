from __future__ import annotations

from interview_mux.disfluency.context import attach_disfluency_context
from interview_mux.acoustic_profile import compact_for_volley as acoustic_compact_for_volley, load_profile
from interview_mux.analysis_memory import default_sound_design_plan
from interview_mux.config import merged_config
from interview_mux.prompt_validation import (
    validate_sound_design_plan as _sdp_schema_errors,
    validate_stage_artifacts,
)
from interview_mux.gates import require_selected_flow_flow1, require_selected_flow_flow2
from interview_mux.operator_trace import logged_step
from interview_mux.artifact_writes import write_validated_artifact
from interview_mux.run_context import RunContext
from interview_mux.sonic_context import compact_for_volley as sonic_compact_for_volley, load_sonic_context
from interview_mux.stage_enrichment import compact_value_features_summary
from interview_mux.stages.analysis_stage import run_analysis_llm_stage, run_flow_llm_stage

_SOUND_DESIGN_PLAN_REL = "understanding/sound_design_plan.json"


def run_sound_design_palettes(ctx: RunContext) -> None:
    if not _sound_design_enabled():
        _mark_skipped(ctx, "sound_design_palettes")
        return

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
        profile = load_profile(c)
        if profile:
            payload["source_acoustic_profile"] = acoustic_compact_for_volley(profile)
        sonic_context = load_sonic_context(c)
        if sonic_context:
            payload["sonic_context"] = sonic_compact_for_volley(sonic_context)
        vf = compact_value_features_summary(c)
        if vf:
            payload["value_features_summary"] = vf

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
            palettes = artifacts["palettes"]
            sdp["palettes"] = _attach_palette_provenance(c, palettes if isinstance(palettes, list) else [])
        _validate_sound_design_plan(sdp)
        write_validated_artifact(
            c, _SOUND_DESIGN_PLAN_REL, sdp, merge_from_disk=False, stage_key="sound_design_palettes"
        )

    with logged_step("sound_design_palettes/llm_stage", ctx=ctx, stage="sound_design_palettes"):
        run_analysis_llm_stage(
            ctx,
            "sound_design_palettes",
            "sound_design/theme-palettes.system.txt",
            build_input,
            persist,
        )


def run_sound_design_plan_flow1(ctx: RunContext) -> None:
    require_selected_flow_flow1(ctx)
    if not _sound_design_enabled():
        _mark_skipped(ctx, "sound_design_plan_flow1")
        return

    def build_input(c: RunContext) -> dict:
        payload = {
            "sound_design_plan": _load_sound_design_plan(c),
            "selection": c.read_json("flow_1_master/selection.json"),
            "narrative_plan": c.read_json("flow_1_master/narrative_plan.json"),
            "transitions": c.read_json("flow_1_master/transitions.json"),
            "gap_report": c.read_json("understanding/gap_report.json"),
            "segments": c.read_json("segments/manifest.json"),
        }
        profile = load_profile(c)
        if profile:
            payload["source_acoustic_profile"] = acoustic_compact_for_volley(profile)
        sonic_context = load_sonic_context(c)
        if sonic_context:
            payload["sonic_context"] = sonic_compact_for_volley(sonic_context)
        return attach_disfluency_context(payload, c)

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
        write_validated_artifact(
            c, _SOUND_DESIGN_PLAN_REL, sdp, merge_from_disk=False, stage_key="sound_design_plan_flow1"
        )

    with logged_step("sound_design_plan_flow1/llm_stage", ctx=ctx, stage="sound_design_plan_flow1"):
        run_flow_llm_stage(
            ctx,
            "sound_design_plan_flow1",
            "sound_design/plan-flow1.system.txt",
            build_input,
            persist,
        )


def run_sound_design_plan_flow2(ctx: RunContext) -> None:
    require_selected_flow_flow2(ctx)
    if not _sound_design_enabled():
        _mark_skipped(ctx, "sound_design_plan_flow2")
        return

    def build_input(c: RunContext) -> dict:
        payload = {
            "sound_design_plan": _load_sound_design_plan(c),
            "selection": c.read_json("flow_2_highlights/selection.json"),
            "content_brief": c.read_json("understanding/content_brief.json"),
        }
        profile = load_profile(c)
        if profile:
            payload["source_acoustic_profile"] = acoustic_compact_for_volley(profile)
        sonic_context = load_sonic_context(c)
        if sonic_context:
            payload["sonic_context"] = sonic_compact_for_volley(sonic_context)
        return payload

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
        write_validated_artifact(
            c, _SOUND_DESIGN_PLAN_REL, sdp, merge_from_disk=False, stage_key="sound_design_plan_flow2"
        )

    with logged_step("sound_design_plan_flow2/llm_stage", ctx=ctx, stage="sound_design_plan_flow2"):
        run_flow_llm_stage(
            ctx,
            "sound_design_plan_flow2",
            "sound_design/plan-flow2.system.txt",
            build_input,
            persist,
        )


def run_sfx_prompt_craft(ctx: RunContext) -> None:
    if not _sound_design_enabled():
        _mark_skipped(ctx, "sfx_prompt_craft")
        return

    def build_input(c: RunContext) -> dict:
        sdp = _load_sound_design_plan(c)
        payload: dict = {
            "coherence": sdp.get("coherence", {}),
            "assets": sdp.get("assets", []),
        }
        profile = load_profile(c)
        if profile:
            payload["source_acoustic_profile"] = profile
        sonic_context = load_sonic_context(c)
        if sonic_context:
            payload["sonic_context"] = sonic_compact_for_volley(sonic_context)
        if c.artifact_exists("understanding/analysis_state.json"):
            state = c.read_json("understanding/analysis_state.json")
            style = state.get("style") if isinstance(state, dict) else None
            if isinstance(style, dict) and style.get("sound_design_notes"):
                payload["operator_style_sound_design_notes"] = style["sound_design_notes"]
        return payload

    def persist(c: RunContext, artifacts: dict) -> None:
        prompts = artifacts.get("prompts")
        if not isinstance(prompts, list):
            raise ValueError("sfx_prompt_craft: missing artifacts.prompts list")
        sdp = _load_sound_design_plan(c)
        normalized = _normalize_sfx_prompts(sdp, prompts)
        payload = {"prompts": normalized}
        schema_errors = validate_stage_artifacts("sfx_prompt_craft", payload)
        if schema_errors:
            raise ValueError(f"Invalid SFX prompts artifact: {schema_errors[0]}")
        write_validated_artifact(
            c,
            "sound_design/sfx_prompts.json",
            payload,
            merge_from_disk=True,
            stage_key="sfx_prompt_craft",
        )

    with logged_step("sfx_prompt_craft/llm_stage", ctx=ctx, stage="sfx_prompt_craft"):
        run_flow_llm_stage(
            ctx,
            "sfx_prompt_craft",
            "sound_design/sfx-prompt-craft.system.txt",
            build_input,
            persist,
        )


def run_sfx_prompt_refine(ctx: RunContext, asset_ids: list[str] | None = None) -> None:
    """LLM refine pass for failed MMAudio assets — not in default FLOW order."""

    def build_input(c: RunContext) -> dict:
        sdp = _load_sound_design_plan(c)
        crafted = {}
        if c.artifact_exists("sound_design/sfx_prompts.json"):
            data = c.read_json("sound_design/sfx_prompts.json")
            rows = data.get("prompts") or []
            crafted = {str(r["asset_id"]): r for r in rows if isinstance(r, dict) and r.get("asset_id")}
        qa_rows: list[dict] = []
        if c.artifact_exists("sound_design/mmaudio_qa.json"):
            qa_doc = c.read_json("sound_design/mmaudio_qa.json")
            qa_rows = [r for r in (qa_doc.get("assets") or []) if isinstance(r, dict)]
        listen: list[dict] = []
        if c.artifact_exists("run_meta.json"):
            meta = c.read_json("run_meta.json")
            listen = [r for r in (meta.get("sfx_listen_results") or []) if isinstance(r, dict)]

        target_ids = set(asset_ids or [])
        if not target_ids:
            for row in qa_rows:
                if row.get("verdict") == "fail" and row.get("asset_id"):
                    target_ids.add(str(row["asset_id"]))
            latest_listen: dict[str, str] = {}
            for entry in listen:
                aid = str(entry.get("asset_id") or "")
                if aid:
                    latest_listen[aid] = str(entry.get("result") or "")
            for aid, res in latest_listen.items():
                if res == "fail":
                    target_ids.add(aid)

        failed_assets: list[dict] = []
        for aid in sorted(target_ids):
            failed_assets.append(
                {
                    "asset_id": aid,
                    "original_prompt_row": crafted.get(aid, {}),
                    "qa_report": next((r for r in qa_rows if str(r.get("asset_id")) == aid), {}),
                    "listen_entries": [e for e in listen if str(e.get("asset_id")) == aid],
                }
            )

        payload: dict = {
            "coherence": sdp.get("coherence", {}),
            "failed_assets": failed_assets,
            "mmaudio_qa": qa_rows,
            "listen_results": listen,
        }
        profile = load_profile(c)
        if profile:
            payload["source_acoustic_profile"] = acoustic_compact_for_volley(profile)
        sonic_context = load_sonic_context(c)
        if sonic_context:
            payload["sonic_context"] = sonic_compact_for_volley(sonic_context)
        return payload

    def persist(c: RunContext, artifacts: dict) -> None:
        updates = artifacts.get("prompts")
        if not isinstance(updates, list) or not updates:
            raise ValueError("sfx_prompt_refine: missing artifacts.prompts list")
        path = "sound_design/sfx_prompts.json"
        existing_rows: list[dict] = []
        if c.artifact_exists(path):
            data = c.read_json(path)
            existing_rows = [r for r in (data.get("prompts") or []) if isinstance(r, dict)]
        by_id = {str(r["asset_id"]): dict(r) for r in existing_rows if r.get("asset_id")}
        for row in updates:
            if not isinstance(row, dict) or not row.get("asset_id"):
                continue
            aid = str(row["asset_id"])
            merged = {**by_id.get(aid, {}), **row, "asset_id": aid}
            by_id[aid] = merged
        sdp = _load_sound_design_plan(c)
        normalized = _normalize_sfx_prompts(sdp, list(by_id.values()))
        payload = {"prompts": normalized}
        schema_errors = validate_stage_artifacts("sfx_prompt_craft", payload)
        if schema_errors:
            raise ValueError(f"Invalid refined SFX prompts: {schema_errors[0]}")
        write_validated_artifact(
            c,
            path,
            payload,
            merge_from_disk=True,
            stage_key="sfx_prompt_refine",
        )
        _increment_refine_attempts(c, [str(r["asset_id"]) for r in updates if r.get("asset_id")])
        meta = c.read_json("run_meta.json") if c.artifact_exists("run_meta.json") else {}
        review = meta.get("sfx_prompt_review") or {}
        if isinstance(review, dict):
            review["approved"] = False
            review["approved_by"] = None
            review["approved_at"] = None
            meta["sfx_prompt_review"] = review
            c.write_json("run_meta.json", meta)
        c.log(
            "sfx_prompts_refined",
            level="info",
            stage="sfx_prompt_refine",
            detail={"asset_ids": [r.get("asset_id") for r in updates]},
        )

    with logged_step("sfx_prompt_refine/llm_stage", ctx=ctx, stage="sfx_prompt_refine"):
        run_flow_llm_stage(
            ctx,
            "sfx_prompt_refine",
            "sound_design/sfx-prompt-refine.system.txt",
            build_input,
            persist,
        )


def _increment_refine_attempts(ctx: RunContext, asset_ids: list[str]) -> None:
    def patch(m: dict) -> None:
        attempts = dict(m.get("sfx_refine_attempts") or {})
        for aid in asset_ids:
            attempts[aid] = int(attempts.get(aid, 0)) + 1
        m["sfx_refine_attempts"] = attempts

    ctx.mutate_run_meta(patch)


def _load_sound_design_plan(ctx: RunContext) -> dict:
    if ctx.artifact_exists(_SOUND_DESIGN_PLAN_REL):
        doc = ctx.read_json(_SOUND_DESIGN_PLAN_REL)
        if isinstance(doc, dict):
            return doc
    return default_sound_design_plan()


def _sound_design_enabled() -> bool:
    return bool((merged_config().get("sound_design") or {}).get("enabled", True))


def _mark_skipped(ctx: RunContext, stage_key: str) -> None:
    ctx.log(
        f"{stage_key}: skipped (sound_design.enabled=false)",
        level="info",
        stage=stage_key,
    )
    ctx.mark_done(stage_key)


def _attach_palette_provenance(ctx: RunContext, palettes: list[dict]) -> list[dict]:
    sonic = load_sonic_context(ctx) or {}
    scenario = sonic.get("scenario") if isinstance(sonic.get("scenario"), dict) else {}
    bucket = str(scenario.get("atlas_bucket") or "").strip()
    tag_lineage = [
        str(row.get("tag_id"))
        for row in (sonic.get("tag_registry") or [])
        if isinstance(row, dict) and row.get("tag_id")
    ][:8]
    out: list[dict] = []
    for row in palettes:
        if not isinstance(row, dict):
            continue
        merged = dict(row)
        if bucket and not merged.get("scenario_bucket"):
            merged["scenario_bucket"] = bucket
        if tag_lineage and not merged.get("tag_lineage"):
            merged["tag_lineage"] = tag_lineage
        out.append(merged)
    return out


def _validate_sound_design_plan(plan: dict) -> None:
    errors = _sdp_schema_errors(plan)
    if not errors:
        return
    raise ValueError(f"Invalid sound design plan: {errors[0]}")


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


def _normalize_sfx_prompts(plan: dict, prompts: list[dict]) -> list[dict]:
    """One crafted row per SDP asset; duration_seconds always from the plan asset."""
    assets = plan.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError(
            "sfx_prompt_craft requires assets in understanding/sound_design_plan.json; "
            "run sound_design_plan_flow1 or sound_design_plan_flow2 first"
        )
    assets_by_id: dict[str, dict] = {
        str(item["asset_id"]): item
        for item in assets
        if isinstance(item, dict) and item.get("asset_id")
    }
    if not assets_by_id:
        raise ValueError("sfx_prompt_craft: sound design plan assets lack asset_id values")

    by_id: dict[str, dict] = {}
    for row in prompts:
        if not isinstance(row, dict):
            continue
        aid = str(row.get("asset_id") or "")
        if not aid or aid not in assets_by_id:
            continue
        merged = {**row, "asset_id": aid}
        plan_duration = assets_by_id[aid].get("duration_seconds")
        if plan_duration is not None:
            merged["duration_seconds"] = float(plan_duration)
        by_id[aid] = merged

    missing = sorted(set(assets_by_id) - set(by_id))
    if missing:
        raise ValueError(
            "sfx_prompt_craft: missing crafted prompt for asset_id(s) "
            + ", ".join(missing)
        )
    extra = sorted(set(by_id) - set(assets_by_id))
    if extra:
        raise ValueError(
            "sfx_prompt_craft: prompts reference unknown asset_id(s) "
            + ", ".join(extra)
        )
    return [by_id[aid] for aid in sorted(by_id)]


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
