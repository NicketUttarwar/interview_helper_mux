"""Sound design plan cross-artifact validators."""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext
from interview_mux.sonic_context import load_sonic_context


def _sdp(ctx: RunContext) -> dict[str, Any]:
    if not ctx.artifact_exists("understanding/sound_design_plan.json"):
        return {}
    doc = ctx.read_json("understanding/sound_design_plan.json")
    return doc if isinstance(doc, dict) else {}


def _manifest_ids(ctx: RunContext) -> set[str]:
    if not ctx.artifact_exists("segments/manifest.json"):
        return set()
    manifest = ctx.read_json("segments/manifest.json")
    segs = manifest.get("segments") or [] if isinstance(manifest, dict) else []
    return {str(s.get("segment_id")) for s in segs if isinstance(s, dict) and s.get("segment_id")}


def _selection_ids(ctx: RunContext) -> set[str]:
    if not ctx.artifact_exists("master/selection.json"):
        return set()
    sel = ctx.read_json("master/selection.json")
    return {str(x) for x in (sel.get("ordered_segment_ids") or [])}


def validate_post_sound_palettes(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    sdp = _sdp(ctx)
    coherence = sdp.get("coherence") or {}
    if not str(coherence.get("sonic_identity", "")).strip():
        errors.append("SDP coherence.sonic_identity missing")
    manifest_ids = _manifest_ids(ctx)
    for pal in sdp.get("palettes") or []:
        if not isinstance(pal, dict):
            continue
        seg_ids = pal.get("segment_ids") or []
        if not seg_ids:
            errors.append(f"palette {pal.get('palette_id')} has no segment_ids")
        for sid in seg_ids:
            if manifest_ids and str(sid) not in manifest_ids:
                errors.append(f"palette segment {sid} not in manifest")
    return errors


def validate_post_sound_plan(ctx: RunContext) -> list[str]:
    """Validate podcast SDP assets/cues against selection and adaptive asset caps."""
    errors: list[str] = []
    sdp = _sdp(ctx)
    cfg = merged_config()
    sd = cfg.get("sound_design") or {}
    fallback = int(sd.get("max_assets", sd.get("max_assets_flow1", 6)))
    cap = _asset_cap(ctx, fallback=fallback)
    # Tighten with delivery_brief.sfx_density when present
    if ctx.artifact_exists("understanding/delivery_brief.json"):
        brief = ctx.read_json("understanding/delivery_brief.json")
        if isinstance(brief, dict):
            dens = brief.get("sfx_density") if isinstance(brief.get("sfx_density"), dict) else {}
            brief_parts = [
                int(dens.get("max_beds") or 0),
                int(dens.get("max_punctuators") or 0),
                int(dens.get("max_foley") or 0),
            ]
            brief_cap = sum(brief_parts)
            if brief_cap > 0:
                cap = min(cap, brief_cap) if cap else brief_cap
    assets = sdp.get("assets") or []
    asset_ids = {str(a.get("asset_id")) for a in assets if isinstance(a, dict) and a.get("asset_id")}
    if len(asset_ids) > cap:
        errors.append(f"asset count {len(asset_ids)} > cap {cap}")
    selection_ids = _selection_ids(ctx)
    palette_seg_ids: set[str] = set()
    for pal in sdp.get("palettes") or []:
        if isinstance(pal, dict):
            palette_seg_ids.update(str(x) for x in (pal.get("segment_ids") or []))
    flow_plans = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    flow = flow_plans.get("podcast") if isinstance(flow_plans.get("podcast"), dict) else {}
    if not flow and isinstance(flow_plans.get("flow1"), dict):
        flow = flow_plans["flow1"]
    cues = (flow.get("cues") or []) if isinstance(flow.get("cues"), list) else []
    sonic = load_sonic_context(ctx) or {}
    flags = sonic.get("segment_flags") if isinstance(sonic.get("segment_flags"), dict) else {}
    overlap_high = {str(x) for x in (flags.get("overlap_high") or [])}
    trauma_adjacent = {str(x) for x in (flags.get("trauma_adjacent") or [])}
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        for key in ("segment_id", "after_segment_id", "before_segment_id"):
            sid = cue.get(key)
            if sid and selection_ids and str(sid) not in selection_ids:
                errors.append(f"cue {cue.get('cue_id')}: {key}={sid} not in selection")
        if cue.get("placement") == "under_segment" and palette_seg_ids:
            seg = cue.get("segment_id")
            if seg and str(seg) not in palette_seg_ids:
                errors.append(f"bed cue segment {seg} outside palettes")
        if cue.get("placement") == "under_segment":
            seg = str(cue.get("segment_id") or "")
            if seg and seg in overlap_high:
                errors.append(f"bed cue segment {seg} banned for overlap_high")
            if seg and seg in trauma_adjacent:
                errors.append(f"bed cue segment {seg} banned for trauma_adjacent")
    return errors


# Backward-compat aliases
validate_post_sound_plan_flow1 = validate_post_sound_plan


def validate_pre_sfx_generation(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    sdp = _sdp(ctx)
    assets = sdp.get("assets") or []
    if not assets:
        errors.append("SDP assets[] empty before MMAudio craft")
    assets_by_id: dict[str, dict] = {
        str(a["asset_id"]): a
        for a in assets
        if isinstance(a, dict) and a.get("asset_id")
    }
    if not ctx.artifact_exists("sound_design/sfx_prompts.json"):
        errors.append("sfx_prompts.json missing")
    else:
        prompts = ctx.read_json("sound_design/sfx_prompts.json")
        rows = prompts.get("prompts") if isinstance(prompts, dict) else prompts
        if not rows:
            errors.append("no crafted prompts on disk")
        elif len(rows) < len(assets):
            errors.append("fewer prompts than SDP assets")
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            aid = str(row.get("asset_id") or "")
            if aid and aid not in assets_by_id:
                errors.append(f"crafted prompt for unknown asset_id {aid}")
            plan_asset = assets_by_id.get(aid)
            if plan_asset and row.get("duration_seconds") is not None:
                plan_d = float(plan_asset.get("duration_seconds") or 0)
                craft_d = float(row.get("duration_seconds") or 0)
                if plan_d and abs(craft_d - plan_d) > 0.25:
                    errors.append(f"duration mismatch for {aid}: craft vs plan")
    return errors


def validate_pre_mix(ctx: RunContext, flow: str = "podcast") -> list[str]:
    _ = flow  # podcast-only delivery
    errors: list[str] = list(validate_post_mmaudio_qa(ctx))
    sdp = _sdp(ctx)
    for asset in sdp.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        aid = str(asset.get("asset_id", ""))
        if not aid:
            continue
        wav = ctx.read_path("sound_design", "assets", f"{aid}.wav")
        if not wav.is_file():
            errors.append(f"missing WAV for asset_id {aid}")
    return errors


def validate_pre_master(ctx: RunContext, flow: str = "podcast") -> list[str]:
    """Cross-check assembly readiness before loudnorm (mix completeness + QC + listen gate)."""
    errors: list[str] = list(validate_pre_mix(ctx, flow))
    from interview_mux.gates import check_post_listen_gate_pending
    from interview_mux.mix_completeness import _missing_sfx_from_mmaudio_qa

    for aid in sorted(_missing_sfx_from_mmaudio_qa(ctx)):
        msg = f"mmaudio_qa placeholder/failed for {aid}"
        if msg not in errors:
            errors.append(msg)

    cfg = merged_config()
    mix_cfg = cfg.get("mix") or {}
    intel_cfg = mix_cfg.get("intelligibility_qc") if isinstance(mix_cfg.get("intelligibility_qc"), dict) else {}
    if bool(intel_cfg.get("enabled", False)):
        meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
        summaries = meta.get("qc_summaries") if isinstance(meta.get("qc_summaries"), dict) else {}
        intel = summaries.get("mix_intelligibility")
        if isinstance(intel, dict) and intel.get("passed") is False:
            errors.append("mix_intelligibility QC failed")

    failed_listen = check_post_listen_gate_pending(ctx)
    if failed_listen:
        errors.append(f"post_listen failed for: {', '.join(failed_listen[:6])}")

    return errors


def _asset_cap(ctx: RunContext, *, fallback: int) -> int:
    cfg = merged_config()
    sound = cfg.get("sound_design") or {}
    if not bool(sound.get("use_adaptive_caps", False)):
        return fallback
    sonic = load_sonic_context(ctx) or {}
    mix_policy = sonic.get("mix_policy") if isinstance(sonic.get("mix_policy"), dict) else {}
    val = mix_policy.get("adaptive_max_assets")
    if val is None:
        val = mix_policy.get("adaptive_max_assets_flow1")
    if val is None:
        return fallback
    try:
        return max(0, int(val))
    except (TypeError, ValueError):
        return fallback


def validate_post_sonic_context(ctx: RunContext) -> list[str]:
    """Cross-check sonic_context after sonic_context_build (BUILD-SFX-01)."""
    from interview_mux.prompt_validation import validate_sonic_context

    rel = "understanding/sonic_context.json"
    if not ctx.artifact_exists(rel):
        return [f"{rel} missing"]
    doc = ctx.read_json(rel)
    if not isinstance(doc, dict):
        return [f"{rel} is not an object"]
    errors = [f"sonic_context.{e}" for e in validate_sonic_context(doc)]
    if errors:
        return errors
    registry = doc.get("tag_registry") or []
    if not registry and not doc.get("sparse_mode"):
        errors.append("sonic_context.tag_registry empty without sparse_mode")
    return errors


def validate_post_mmaudio_qa(ctx: RunContext) -> list[str]:
    """Cross-check mmaudio_qa after generation (BUILD-SFX-01)."""
    from interview_mux.prompt_validation import validate_mmaudio_qa

    rel = "sound_design/mmaudio_qa.json"
    if not ctx.artifact_exists(rel):
        return []
    doc = ctx.read_json(rel)
    if not isinstance(doc, dict):
        return [f"{rel} is not an object"]
    errors = [f"mmaudio_qa.{e}" for e in validate_mmaudio_qa(doc)]
    for row in doc.get("assets") or []:
        if not isinstance(row, dict):
            continue
        status = str(row.get("generation_status") or "").lower()
        verdict = str(row.get("verdict") or "").lower()
        if status in {"failed", "placeholder"} and verdict == "pass":
            aid = row.get("asset_id", "?")
            errors.append(f"mmaudio_qa asset {aid}: generation_status={status} but verdict=pass")
        if row.get("silence_detected") is True and verdict == "pass":
            aid = row.get("asset_id", "?")
            errors.append(f"mmaudio_qa asset {aid}: silence_detected with verdict=pass")
        reasons = [str(r) for r in (row.get("reasons") or [])]
        if verdict == "pass" and any(
            r in reasons for r in ("room_timbre_mismatch", "trauma_percussive_transient", "spectral_bucket_mismatch")
        ):
            aid = row.get("asset_id", "?")
            flagged = [r for r in reasons if r in ("room_timbre_mismatch", "trauma_percussive_transient", "spectral_bucket_mismatch")]
            errors.append(f"mmaudio_qa asset {aid}: verdict=pass with reasons {flagged}")
    return errors
