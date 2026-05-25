from __future__ import annotations

import json
from pathlib import Path

from interview_mux.config import require_secret
from interview_mux.run_context import RunContext


def run_sfx_generation(ctx: RunContext, *, profile: str) -> None:
    """Generate SFX wav files from brief using ElevenLabs."""
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

    try:
        from elevenlabs.client import ElevenLabs
    except ImportError:
        _write_placeholder_sfx(out_dir, cues)
        ctx.mark_done(stage)
        return

    client = ElevenLabs(api_key=api_key)
    for i, cue in enumerate(cues):
        desc = cue.get("description") or cue.get("mood") or "short podcast stinger"
        out_file = out_dir / f"sfx_{i+1:03d}.wav"
        try:
            audio = client.text_to_sound_effects.convert(text=desc, duration_seconds=2.0)
            if hasattr(audio, "__iter__"):
                data = b"".join(audio)
            else:
                data = audio
            out_file.write_bytes(data)
        except Exception:
            _write_silent_wav(out_file, duration_ms=int(cue.get("duration_ms", 1500)))

    manifest = {"profile": profile, "files": [p.name for p in sorted(out_dir.glob("*.wav"))]}
    ctx.write_json(f"{out_rel}/manifest.json", manifest)
    ctx.mark_done(stage)


def _collect_cues(brief: dict, profile: str) -> list[dict]:
    cues: list[dict] = []
    if profile == "podcast":
        for item in brief.get("chapter_stingers") or []:
            cues.append({**item, "description": item.get("description", item.get("mood", "soft stinger"))})
        for item in brief.get("bridges") or []:
            cues.append({**item, "description": item.get("description", "light bridge")})
    else:
        for item in brief.get("transitions") or []:
            cues.append(item)
        if brief.get("cold_open"):
            cues.insert(0, brief["cold_open"])
    if not cues:
        cues.append({"description": "short neutral stinger", "duration_ms": 1500})
    return cues


def _write_placeholder_sfx(out_dir: Path, cues: list[dict]) -> None:
    for i, cue in enumerate(cues):
        _write_silent_wav(out_dir / f"sfx_{i+1:03d}.wav", duration_ms=int(cue.get("duration_ms", 1500)))


def _write_silent_wav(path: Path, duration_ms: int = 1500) -> None:
    import subprocess

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
