from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from interview_mux.config import require_secret
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
    """Generate SFX wav files from brief using ElevenLabs REST API."""
    if profile == "podcast":
        brief_path = "flow_1_master/podcast_sfx_brief.json"
        out_rel = "flow_1_master/sfx"
        stage = "elevenlabs_sfx_flow1"
    else:
        brief_path = "flow_2_highlights/sfx_brief.json"
        out_rel = "flow_2_highlights/sfx"
        stage = "elevenlabs_sfx_flow2"

    brief = ctx.read_json(brief_path)
    out_dir = ctx.path(out_rel)
    out_dir.mkdir(parents=True, exist_ok=True)

    cues = _collect_cues(brief, profile)
    api_key = require_secret("ELEVENLABS_API_KEY")

    crafted = _load_crafted_prompts(ctx)
    for i, cue in enumerate(cues):
        asset_id = cue.get("asset_id") or f"sfx_{i+1:03d}"
        out_file = out_dir / f"{asset_id}.wav" if crafted else out_dir / f"sfx_{i+1:03d}.wav"
        prompt_row = crafted.get(asset_id) if crafted else None
        text, duration_seconds, influence = _resolve_generation_params(cue, prompt_row)
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

    manifest = {"profile": profile, "files": [p.name for p in sorted(out_dir.glob("*.wav"))], "api": "rest"}
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
    if prompt_row:
        text = prompt_row.get("elevenlabs_prompt") or ""
        neg = prompt_row.get("negative_prompt")
        if neg:
            text = f"{text}\n\nAvoid: {neg}"
        duration = float(prompt_row.get("duration_seconds") or 2.0)
        role = cue.get("role") or "chapter_stinger"
        influence = float(prompt_row["prompt_influence"]) if "prompt_influence" in prompt_row else _ROLE_INFLUENCE.get(role, 0.35)
        return text, duration, influence

    desc = cue.get("description") or cue.get("mood") or "short podcast stinger"
    duration_ms = cue.get("duration_ms")
    duration_seconds = float(duration_ms) / 1000.0 if duration_ms else 2.0
    return desc, duration_seconds, 0.35


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
