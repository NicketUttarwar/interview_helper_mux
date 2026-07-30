from __future__ import annotations

from interview_mux.stage_input_helpers import attach_disfluency_context
from interview_mux.acoustic_profile import compact_for_volley as acoustic_compact_for_volley, load_profile
from interview_mux.analysis_memory import default_sound_design_plan
from interview_mux.config import merged_config
from interview_mux.prompt_validation import (
    validate_sound_design_plan as _sdp_schema_errors,
    validate_stage_artifacts,
)
from interview_mux.operator_trace import logged_step
from interview_mux.production_profile import prompt_variant
from interview_mux.source_topology import attach_adaptation_to_payload
from interview_mux.artifact_writes import write_validated_artifact
from interview_mux.run_context import RunContext
from interview_mux.sonic_context import (
    align_palette_keywords_to_sonic_context,
    build_palette_keyword_catalog,
    compact_for_volley as sonic_compact_for_volley,
    load_sonic_context,
)
from interview_mux.stage_enrichment import compact_manifest_for_volley, compact_value_features_summary
from interview_mux.stages.analysis_stage import run_analysis_llm_stage, run_flow_llm_stage

_SOUND_DESIGN_PLAN_REL = "understanding/sound_design_plan.json"

def run_sound_design_palettes(ctx: RunContext) -> None:
    if not _sound_design_enabled():
        _mark_skipped(ctx, "sound_design_palettes")
        return

    def build_input(c: RunContext) -> dict:
        manifest = c.read_json("segments/manifest.json")
        payload: dict = {
            "content_brief": c.read_json("understanding/content_brief.json"),
            "segments": compact_manifest_for_volley(manifest if isinstance(manifest, dict) else {}),
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
            payload["palette_keyword_catalog"] = build_palette_keyword_catalog(sonic_context)
        vf = compact_value_features_summary(c)
        if vf:
            payload["value_features_summary"] = vf

        style = (payload["analysis_state"].get("style") or {}) if isinstance(payload["analysis_state"], dict) else {}
        notes = style.get("sound_design_notes")
        if notes:
            payload["operator_style_sound_design_notes"] = notes
        return attach_adaptation_to_payload(c, payload)

    def persist(c: RunContext, artifacts: dict) -> None:
        sdp = _load_sound_design_plan(c)
        if "coherence" in artifacts:
            sdp["coherence"] = artifacts["coherence"]
        if "palettes" in artifacts:
            palettes = artifacts["palettes"]
            palette_list = palettes if isinstance(palettes, list) else []
            sonic = load_sonic_context(c)
            if sonic and palette_list:
                palette_list = align_palette_keywords_to_sonic_context(palette_list, sonic)
            sdp["palettes"] = _attach_palette_provenance(c, palette_list)
        _validate_sound_design_plan(sdp)
        write_validated_artifact(
            c, _SOUND_DESIGN_PLAN_REL, sdp, merge_from_disk=False, stage_key="sound_design_palettes"
        )

    with logged_step("sound_design_palettes/llm_stage", ctx=ctx, stage="sound_design_palettes"):
        run_analysis_llm_stage(
            ctx,
            "sound_design_palettes",
            prompt_variant("sound_design/theme-palettes.system.txt", ctx),
            build_input,
            persist,
        )

def run_sound_design_plan(ctx: RunContext) -> None:
    if not _sound_design_enabled():
        _mark_skipped(ctx, "sound_design_plan")
        return

    def build_input(c: RunContext) -> dict:
        from interview_mux.soundscape_policy import (
            compact_for_volley as soundscape_compact,
            load_policy,
            refresh_cue_slots,
            soundscape_enabled,
        )

        if soundscape_enabled():
            try:
                refresh_cue_slots(c)
            except Exception as exc:
                c.log(
                    f"soundscape_policy cue refresh skipped: {exc}",
                    level="warning",
                    stage="sound_design_plan",
                )
        from interview_mux.episode_structure import (
            attach_episode_structure_to_payload,
            refresh_episode_structure,
            structure_enabled,
        )

        if structure_enabled():
            try:
                refresh_episode_structure(c)
            except Exception as exc:
                c.log(
                    f"episode_structure refresh skipped: {exc}",
                    level="warning",
                    stage="sound_design_plan",
                )
        manifest = c.read_json("segments/manifest.json")
        payload = {
            "sound_design_plan": _load_sound_design_plan(c),
            "selection": c.read_json("master/selection.json"),
            "narrative_plan": c.read_json("master/narrative_plan.json"),
            "transitions": c.read_json("master/transitions.json"),
            "gap_report": c.read_json("understanding/gap_report.json"),
            "segments": compact_manifest_for_volley(manifest if isinstance(manifest, dict) else {}),
        }
        from interview_mux.gap_framing import framing_vo_for_sound_design

        framing_vo = framing_vo_for_sound_design(c)
        if framing_vo:
            payload["framing_vo_lines"] = framing_vo
        profile = load_profile(c)
        if profile:
            payload["source_acoustic_profile"] = acoustic_compact_for_volley(profile)
        sonic_context = load_sonic_context(c)
        if sonic_context:
            payload["sonic_context"] = sonic_compact_for_volley(sonic_context)
        policy = load_policy(c)
        if policy:
            payload["soundscape_policy"] = soundscape_compact(policy)
        from interview_mux.music_motif import build_music_brief, default_motif_family

        brief = build_music_brief(c)
        c.write_json("understanding/music_brief.json", brief)
        payload["music_brief"] = brief
        sdp_partial = payload.get("sound_design_plan")
        if isinstance(sdp_partial, dict) and not isinstance(sdp_partial.get("motif_family"), dict):
            payload["motif_family_seed"] = default_motif_family(brief)
        return attach_disfluency_context(
            attach_episode_structure_to_payload(
                c,
                __import__("interview_mux.delivery_brief", fromlist=["attach_delivery_brief_to_payload"]).attach_delivery_brief_to_payload(
                    c, attach_adaptation_to_payload(c, payload)
                ),
            ),
            c,
        )

    def persist(c: RunContext, artifacts: dict) -> None:
        sdp = _load_sound_design_plan(c)
        assets = artifacts.get("assets")
        flow_plans = artifacts.get("flow_plans")
        if isinstance(assets, list):
            sdp["assets"] = assets
        if isinstance(flow_plans, dict):
            existing = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
            merged = dict(existing or {})
            merged.update(flow_plans)
            # Prefer podcast; drop empty flow2 scaffold
            if not merged.get("podcast") and merged.get("flow1"):
                merged["podcast"] = merged["flow1"]
            sdp["flow_plans"] = {k: v for k, v in merged.items() if k != "flow2" or v}

        _normalize_sound_design_assets(sdp)
        _normalize_chapter_stinger_reuse(sdp)
        from interview_mux.music_motif import build_music_brief, ensure_motif_on_plan

        brief = build_music_brief(c)
        c.write_json("understanding/music_brief.json", brief)
        if isinstance(artifacts.get("motif_family"), dict):
            sdp["motif_family"] = artifacts["motif_family"]
        sdp = ensure_motif_on_plan(sdp, brief)
        from interview_mux.creative_delivery import hydrate_flow_cue_segments

        actions = hydrate_flow_cue_segments(c, sdp)
        if actions:
            c.log(
                f"Hydrated {len(actions)} SDP cue segment anchor(s)",
                level="info",
                stage="sound_design_plan",
                detail={"actions": actions[:12]},
            )
        _validate_sound_design_plan(sdp)
        _validate_flow1_asset_links(sdp)
        write_validated_artifact(
            c, _SOUND_DESIGN_PLAN_REL, sdp, merge_from_disk=False, stage_key="sound_design_plan"
        )

    with logged_step("sound_design_plan/llm_stage", ctx=ctx, stage="sound_design_plan"):
        run_flow_llm_stage(
            ctx,
            "sound_design_plan",
            prompt_variant("sound_design/plan-flow1.system.txt", ctx),
            build_input,
            persist,
        )


def _repair_sdp_asset_durations(ctx: RunContext) -> bool:
    """Clamp SDP asset durations to role bands before prompt craft / generation."""
    from interview_mux.deterministic_lint import ROLE_DURATION_BANDS
    from interview_mux.mmaudio_runner import clamp_duration_seconds

    sdp = _load_sound_design_plan(ctx)
    assets = sdp.get("assets") or []
    changed = False
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        dur = asset.get("duration_seconds")
        if dur is None:
            continue
        role = str(asset.get("role") or "")
        band = ROLE_DURATION_BANDS.get(role)
        if band:
            clamped = max(float(band[0]), min(float(band[1]), float(dur)))
        else:
            clamped = clamp_duration_seconds(float(dur), role=role, ctx=ctx)
        if clamped != float(dur):
            asset["duration_seconds"] = clamped
            changed = True
    if changed:
        ctx.write_json(_SOUND_DESIGN_PLAN_REL, sdp, skip_handoff=True)
        ctx.log(
            "Repaired sound_design_plan asset durations to role bands",
            level="info",
            stage="sfx_prompt_craft",
        )
    return changed


def run_sfx_prompt_craft(ctx: RunContext) -> None:
    if not _sound_design_enabled():
        _mark_skipped(ctx, "sfx_prompt_craft")
        return

    _repair_sdp_asset_durations(ctx)

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
        from interview_mux.soundscape_policy import compact_for_volley as soundscape_compact, load_policy

        policy = load_policy(c)
        if policy:
            payload["soundscape_policy"] = soundscape_compact(policy)
        if c.artifact_exists("understanding/analysis_state.json"):
            state = c.read_json("understanding/analysis_state.json")
            style = state.get("style") if isinstance(state, dict) else None
            if isinstance(style, dict) and style.get("sound_design_notes"):
                payload["operator_style_sound_design_notes"] = style["sound_design_notes"]
        return __import__(
            "interview_mux.delivery_brief", fromlist=["attach_delivery_brief_to_payload"]
        ).attach_delivery_brief_to_payload(c, attach_adaptation_to_payload(c, payload))

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
        from interview_mux.sfx_prompt_review import maybe_auto_approve_prompt_review

        maybe_auto_approve_prompt_review(c)

    with logged_step("sfx_prompt_craft/llm_stage", ctx=ctx, stage="sfx_prompt_craft"):
        run_flow_llm_stage(
            ctx,
            "sfx_prompt_craft",
            prompt_variant("sound_design/sfx-prompt-craft.system.txt", ctx),
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
    ctx.mark_done(stage_key, force=True)

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

def _normalize_chapter_stinger_reuse(sdp: dict) -> None:
    flow_plans = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    flow1 = flow_plans.get("podcast") if isinstance(flow_plans.get("podcast"), dict) else {}
    cues = flow1.get("cues") if isinstance(flow1.get("cues"), list) else []
    chapter_cues = [
        c
        for c in cues
        if isinstance(c, dict) and str(c.get("placement") or "") in {"after_segment", "before_segment"}
    ]
    if len(chapter_cues) <= 1:
        return
    first_aid = str(chapter_cues[0].get("asset_id") or "")
    if not first_aid:
        return
    for cue in chapter_cues[1:]:
        cue["asset_id"] = first_aid


def _normalize_sound_design_assets(sdp: dict) -> None:
    palettes = sdp.get("palettes") if isinstance(sdp.get("palettes"), list) else []
    default_palette = ""
    for row in palettes:
        if isinstance(row, dict) and row.get("palette_id"):
            default_palette = str(row["palette_id"])
            break
    if not default_palette:
        default_palette = "palette_default"
    assets = sdp.get("assets")
    if not isinstance(assets, list):
        return
    for item in assets:
        if not isinstance(item, dict):
            continue
        if not item.get("palette_id"):
            item["palette_id"] = default_palette


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
    flow1 = flow_plans.get("podcast") if isinstance(flow_plans.get("podcast"), dict) else {}
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
            from interview_mux.deterministic_lint import ROLE_DURATION_BANDS
            from interview_mux.mmaudio_runner import clamp_duration_seconds

            role = str(assets_by_id[aid].get("role") or merged.get("role") or "")
            band = ROLE_DURATION_BANDS.get(role)
            if band:
                merged["duration_seconds"] = max(
                    float(band[0]), min(float(band[1]), float(plan_duration))
                )
            else:
                merged["duration_seconds"] = clamp_duration_seconds(
                    float(plan_duration),
                    role=role,
                )
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
