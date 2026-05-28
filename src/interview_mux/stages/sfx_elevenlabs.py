from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from interview_mux.config import merged_config, require_secret
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
    _require_prompt_review_if_enabled(ctx)
    cues = _load_fallback_cues(ctx=ctx, brief_path=brief_path, profile=profile)
    api_key = require_secret("ELEVENLABS_API_KEY")

    crafted = _load_crafted_prompts(ctx)
    generation_items = _collect_generation_items(ctx=ctx, profile=profile, fallback_cues=cues)
    for item in generation_items:
        asset_id = item["asset_id"]
        out_file = out_dir / f"{asset_id}.wav"
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
                f"ElevenLabs SFX generated {out_file.name}",
                stage=stage,
                detail={
                    "asset_id": asset_id,
                    "duration_seconds": duration_seconds,
                    "prompt_influence": influence,
                    "api": "rest",
                    "path": "/v1/sound-generation",
                },
            )
        except ElevenLabsApiError as exc:
            logger.warning("ElevenLabs REST failed for %s: %s", asset_id, exc)
            ctx.log(
                "warning",
                f"ElevenLabs SFX failed for {asset_id}; wrote silence placeholder",
                stage=stage,
                detail={"status": exc.status, "api": "rest"},
            )
            _write_silent_wav(out_file, duration_ms=int(duration_seconds * 1000))
        except Exception as exc:
            logger.warning("ElevenLabs generation failed for %s: %s", asset_id, exc)
            _write_silent_wav(out_file, duration_ms=int(duration_seconds * 1000))

    if generation_items:
        _write_shared_asset_mirror(ctx=ctx, source_dir=out_dir, asset_ids=[item["asset_id"] for item in generation_items])

    manifest = {"profile": profile, "files": [p.name for p in sorted(out_dir.glob("*.wav"))], "api": "rest"}
    ctx.write_json(f"{out_rel}/manifest.json", manifest)
    ctx.mark_done(stage)


def _require_prompt_review_if_enabled(ctx: RunContext) -> None:
    if not bool(merged_config().get("g1_5_require_prompt_approval", False)):
        return
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    review = meta.get("elevenlabs_prompt_review") if isinstance(meta.get("elevenlabs_prompt_review"), dict) else {}
    if review.get("approved"):
        return
    raise RuntimeError(
        "G1.5 prompt approval required before ElevenLabs generation. "
        "Review and approve sound_design/elevenlabs_prompts.json in the GUI panel."
    )


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
    if prompt_row:
        text = prompt_row.get("elevenlabs_prompt") or ""
        neg = prompt_row.get("negative_prompt")
        if neg:
            text = f"{text}\n\nAvoid: {neg}"
        duration = float(prompt_row.get("duration_seconds") or cue.get("duration_seconds") or 2.0)
        role = cue.get("role") or "chapter_stinger"
        influence = float(prompt_row["prompt_influence"]) if "prompt_influence" in prompt_row else _ROLE_INFLUENCE.get(role, 0.35)
        return text, duration, influence

    desc = cue.get("description") or cue.get("mood") or "short podcast stinger"
    if cue.get("duration_seconds") is not None:
        return desc, float(cue.get("duration_seconds") or 2.0), 0.35
    duration_ms = cue.get("duration_ms")
    duration_seconds = float(duration_ms) / 1000.0 if duration_ms else 2.0
    return desc, duration_seconds, 0.35


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


def _write_shared_asset_mirror(*, ctx: RunContext, source_dir: Path, asset_ids: list[str]) -> None:
    target_dir = ctx.path("sound_design", "assets")
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
