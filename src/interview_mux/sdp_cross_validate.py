"""Sound design plan cross-artifact validators."""

from __future__ import annotations

from typing import Any

from interview_mux.config import merged_config
from interview_mux.run_context import RunContext


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


def _selection_ids_flow1(ctx: RunContext) -> set[str]:
    if not ctx.artifact_exists("flow_1_master/selection.json"):
        return set()
    sel = ctx.read_json("flow_1_master/selection.json")
    return {str(x) for x in (sel.get("ordered_segment_ids") or [])}


def _highlight_ranks_flow2(ctx: RunContext) -> set[int]:
    if not ctx.artifact_exists("flow_2_highlights/selection.json"):
        return set()
    sel = ctx.read_json("flow_2_highlights/selection.json")
    ranks: set[int] = set()
    for clip in sel.get("clips") or sel.get("highlights") or []:
        if isinstance(clip, dict) and clip.get("rank") is not None:
            ranks.add(int(clip["rank"]))
    return ranks


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


def validate_post_sound_plan_flow1(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    sdp = _sdp(ctx)
    cfg = merged_config()
    cap = int((cfg.get("sound_design") or {}).get("max_assets_flow1", 6))
    assets = sdp.get("assets") or []
    asset_ids = {str(a.get("asset_id")) for a in assets if isinstance(a, dict) and a.get("asset_id")}
    if len(asset_ids) > cap:
        errors.append(f"flow1 asset count {len(asset_ids)} > cap {cap}")
    selection_ids = _selection_ids_flow1(ctx)
    palette_seg_ids: set[str] = set()
    for pal in sdp.get("palettes") or []:
        if isinstance(pal, dict):
            palette_seg_ids.update(str(x) for x in (pal.get("segment_ids") or []))
    cues = ((sdp.get("flow_plans") or {}).get("flow1") or {}).get("cues") or []
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        for key in ("segment_id", "after_segment_id", "before_segment_id"):
            sid = cue.get(key)
            if sid and selection_ids and str(sid) not in selection_ids:
                errors.append(f"flow1 cue {cue.get('cue_id')}: {key}={sid} not in selection")
        if cue.get("placement") == "under_segment" and palette_seg_ids:
            seg = cue.get("segment_id")
            if seg and str(seg) not in palette_seg_ids:
                errors.append(f"bed cue segment {seg} outside palettes")
    return errors


def validate_post_sound_plan_flow2(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    sdp = _sdp(ctx)
    cfg = merged_config()
    cap = int((cfg.get("sound_design") or {}).get("max_assets_flow2", 4))
    assets = sdp.get("assets") or []
    if len(assets) > cap:
        errors.append(f"flow2 asset count {len(assets)} > cap {cap}")
    ranks = _highlight_ranks_flow2(ctx)
    cues = ((sdp.get("flow_plans") or {}).get("flow2") or {}).get("cues") or []
    clip_count = len(ranks)
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        for key in ("from_clip_rank", "to_clip_rank"):
            r = cue.get(key)
            if r is not None and ranks and int(r) not in ranks:
                errors.append(f"flow2 cue rank {key}={r} not in selection")
    if clip_count < 2:
        between = [c for c in cues if isinstance(c, dict) and c.get("placement") == "between_clips"]
        if between:
            errors.append("between_clips cues present but fewer than 2 highlight clips")
    return errors


def validate_pre_elevenlabs_spend(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    sdp = _sdp(ctx)
    assets = sdp.get("assets") or []
    if not assets:
        errors.append("SDP assets[] empty before ElevenLabs craft")
    if not ctx.artifact_exists("sound_design/elevenlabs_prompts.json"):
        errors.append("elevenlabs_prompts.json missing")
    else:
        prompts = ctx.read_json("sound_design/elevenlabs_prompts.json")
        rows = prompts.get("prompts") if isinstance(prompts, dict) else prompts
        if not rows:
            errors.append("no crafted prompts on disk")
        elif len(rows) < len(assets):
            errors.append("fewer prompts than SDP assets")
    return errors


def validate_pre_mix(ctx: RunContext, flow: str) -> list[str]:
    errors: list[str] = []
    sdp = _sdp(ctx)
    for asset in sdp.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        aid = str(asset.get("asset_id", ""))
        if not aid:
            continue
        wav = ctx.path("sound_design", "assets", f"{aid}.wav")
        if not wav.is_file():
            errors.append(f"missing WAV for asset_id {aid}")
    return errors
