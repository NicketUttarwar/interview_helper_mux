from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from interview_mux.config import require_secret
from interview_mux.g15_prompt_review import require_elevenlabs_generation
from interview_mux.elevenlabs_rest import ElevenLabsApiError, generate_sound_effect
from interview_mux.run_context import RunContext

logger = logging.getLogger(__name__)

_ROLE_INFLUENCE: dict[str, float] = {
    "ambient_bed": 0.30,
    "chapter_stinger": 0.38,
    "transition_stinger": 0.40,
    "cold_open": 0.42,
    "vo_bridge": 0.32,
    "accent_foley": 0.35,
}


def run_sfx_generation(ctx: RunContext, *, profile: str) -> None:
    """Generate SFX wav files from sound design assets using ElevenLabs REST API."""
    if profile == "podcast":
        brief_path = "flow_1_master/podcast_sfx_brief.json"
        out_rel = "flow_1_master/sfx"
        stage = "elevenlabs_sfx_flow1"
    else:
        brief_path = "flow_2_highlights/sfx_brief.json"
        out_rel = "flow_2_highlights/sfx"
        stage = "elevenlabs_sfx_flow2"
    out_dir = ctx.path(out_rel)
    out_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = ctx.path("sound_design", "assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    require_elevenlabs_generation(ctx)
    cues = _load_fallback_cues(ctx=ctx, brief_path=brief_path, profile=profile)
    api_key = require_secret("ELEVENLABS_API_KEY")

    crafted = _load_crafted_prompts(ctx)
    generation_items = _collect_generation_items(ctx=ctx, profile=profile, fallback_cues=cues)
    for item in generation_items:
        asset_id = item["asset_id"]
        out_file = assets_dir / f"{asset_id}.wav"
        prompt_row = crafted.get(asset_id) if crafted else None
        text, duration_seconds, influence = _resolve_generation_params(item, prompt_row)
        try:
            audio = generate_sound_effect(
                api_key=api_key,
                text=text,
                duration_seconds=duration_seconds,
                prompt_influence=influence,
            )
            _write_audio_as_wav(out_file, audio)
            ctx.log(
                "info",
                f"ElevenLabs SFX generated {asset_id}.wav",
                stage=stage,
                detail={
                    "asset_id": asset_id,
                    "duration_seconds": duration_seconds,
                    "prompt_influence": influence,
                    "api": "rest",
                    "path": "/v1/sound-generation",
                    "artifact": f"sound_design/assets/{asset_id}.wav",
                },
            )
        except ElevenLabsApiError as exc:
            logger.warning("ElevenLabs REST failed for %s: %s", asset_id, exc)
            ctx.log(
                "warning",
                f"ElevenLabs SFX failed for {asset_id}; wrote silence placeholder",
                stage=stage,
                detail={"status": exc.status, "api": "rest", "asset_id": asset_id},
            )
            _write_silent_wav(out_file, duration_ms=int(duration_seconds * 1000))
        except Exception as exc:
            logger.warning("ElevenLabs generation failed for %s: %s", asset_id, exc)
            _write_silent_wav(out_file, duration_ms=int(duration_seconds * 1000))

    if generation_items:
        _mirror_assets_to_flow_dir(
            ctx=ctx,
            asset_ids=[item["asset_id"] for item in generation_items],
            target_dir=out_dir,
        )

    manifest = {
        "profile": profile,
        "files": [p.name for p in sorted(assets_dir.glob("*.wav"))],
        "asset_paths": [f"sound_design/assets/{p.name}" for p in sorted(assets_dir.glob("*.wav"))],
        "api": "rest",
    }
    ctx.write_json(f"{out_rel}/manifest.json", manifest)
    ctx.mark_done(stage)


def _load_crafted_prompts(ctx: RunContext) -> dict[str, dict]:
    path = ctx.path("sound_design/elevenlabs_prompts.json")
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = data.get("prompts") or data.get("artifacts", {}).get("prompts") or []
    return {row["asset_id"]: row for row in rows if row.get("asset_id")}


def _resolve_generation_params(
    cue: dict,
    prompt_row: dict | None,
) -> tuple[str, float, float | None]:
    duration_seconds = _plan_duration_seconds(cue)
    role = cue.get("role") or "chapter_stinger"
    influence = _ROLE_INFLUENCE.get(role, 0.35)

    if prompt_row:
        text = prompt_row.get("elevenlabs_prompt") or ""
        neg = prompt_row.get("negative_prompt")
        if neg:
            text = f"{text}\n\nAvoid: {neg}"
        if "prompt_influence" in prompt_row:
            influence = float(prompt_row["prompt_influence"])
        return text, duration_seconds, influence

    desc = cue.get("description") or cue.get("mood") or "short podcast stinger"
    return desc, duration_seconds, influence


def _plan_duration_seconds(cue: dict) -> float:
    if cue.get("duration_seconds") is not None:
        return float(cue["duration_seconds"])
    duration_ms = cue.get("duration_ms")
    if duration_ms is not None:
        return float(duration_ms) / 1000.0
    return 2.0


def _collect_generation_items(
    *,
    ctx: RunContext,
    profile: str,
    fallback_cues: list[dict],
) -> list[dict]:
    plan = _load_sound_design_plan(ctx)
    if not plan:
        return _dedupe_fallback_cues(fallback_cues)

    flow_key = "flow1" if profile == "podcast" else "flow2"
    flow_plans = plan.get("flow_plans") if isinstance(plan.get("flow_plans"), dict) else {}
    flow = flow_plans.get(flow_key) if isinstance(flow_plans.get(flow_key), dict) else {}
    cues = flow.get("cues") if isinstance(flow.get("cues"), list) else []
    assets = plan.get("assets") if isinstance(plan.get("assets"), list) else []
    assets_by_id = {
        str(asset.get("asset_id")): asset
        for asset in assets
        if isinstance(asset, dict) and asset.get("asset_id")
    }

    ordered_asset_ids: list[str] = []
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        aid = str(cue.get("asset_id") or "")
        if not aid or aid not in assets_by_id or aid in ordered_asset_ids:
            continue
        ordered_asset_ids.append(aid)

    if not ordered_asset_ids:
        return _dedupe_fallback_cues(fallback_cues)

    return [assets_by_id[aid] for aid in ordered_asset_ids]


def _load_sound_design_plan(ctx: RunContext) -> dict:
    path = ctx.path("understanding/sound_design_plan.json")
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _load_fallback_cues(*, ctx: RunContext, brief_path: str, profile: str) -> list[dict]:
    """Fallback cues for runs without sound design plan asset definitions."""
    if ctx.path(brief_path).is_file():
        brief = ctx.read_json(brief_path)
        return _collect_cues(brief, profile)
    return [{"description": "short neutral stinger", "duration_ms": 1500, "role": "chapter_stinger"}]


def _dedupe_fallback_cues(cues: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for i, cue in enumerate(cues):
        asset_id = str(cue.get("asset_id") or f"sfx_{i+1:03d}")
        if asset_id in seen:
            continue
        seen.add(asset_id)
        out.append({**cue, "asset_id": asset_id})
    return out


def _mirror_assets_to_flow_dir(*, ctx: RunContext, asset_ids: list[str], target_dir: Path) -> None:
    """Copy canonical sound_design/assets WAVs into flow-specific sfx/ for v1 paths."""
    source_dir = ctx.path("sound_design", "assets")
    target_dir.mkdir(parents=True, exist_ok=True)
    for asset_id in asset_ids:
        src = source_dir / f"{asset_id}.wav"
        if not src.is_file():
            continue
        dst = target_dir / f"{asset_id}.wav"
        dst.write_bytes(src.read_bytes())


def _collect_cues(brief: dict, profile: str) -> list[dict]:
    cues: list[dict] = []
    if profile == "podcast":
        for item in brief.get("chapter_stingers") or []:
            cues.append({**item, "role": "chapter_stinger", "description": item.get("description", item.get("mood", "soft stinger"))})
        for item in brief.get("bridges") or []:
            cues.append({**item, "role": "vo_bridge", "description": item.get("description", "light bridge")})
        for item in brief.get("beds") or []:
            cues.append({**item, "role": "ambient_bed", "description": item.get("description", item.get("mood", "quiet bed"))})
    else:
        for item in brief.get("transitions") or []:
            cues.append({**item, "role": "transition_stinger"})
        if brief.get("cold_open"):
            cues.insert(0, {**brief["cold_open"], "role": "cold_open"})
        if brief.get("outro"):
            cues.append({**brief["outro"], "role": "cold_open"})
    if not cues:
        cues.append({"description": "short neutral stinger", "duration_ms": 1500, "role": "chapter_stinger"})
    return cues


def _write_audio_as_wav(path: Path, data: bytes) -> None:
    if data[:4] == b"RIFF":
        path.write_bytes(data)
        return
    tmp = path.with_suffix(".el.mp3")
    tmp.write_bytes(data)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(tmp), "-ar", "48000", "-ac", "1", str(path)],
            check=True,
            capture_output=True,
        )
    finally:
        tmp.unlink(missing_ok=True)


def _write_silent_wav(path: Path, duration_ms: int = 1500) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=mono",
            "-t",
            str(duration_ms / 1000.0),
            str(path),
        ],
        check=True,
        capture_output=True,
    )
