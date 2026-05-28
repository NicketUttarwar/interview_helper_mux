from __future__ import annotations

import json
from pathlib import Path

from pydub import AudioSegment

from interview_mux.run_context import RunContext


def run_micro_assembly(ctx: RunContext) -> Path:
    selection = ctx.read_json("flow_2_highlights/selection.json")
    manifest = ctx.read_json("segments/manifest.json")
    by_id = {s["segment_id"]: s for s in (manifest.get("segments") or [])}
    source = _load_audio(ctx.path("ingest", "normalized.wav"))
    highlights = selection.get("highlights") or []
    if not highlights:
        raise RuntimeError("No highlight clips extracted")
    mix = AudioSegment.silent(duration=0, frame_rate=48000)
    sdp = _load_sdp(ctx)
    cue_plan = _flow2_cues_from_sdp(ctx, sdp)
    if cue_plan.get("before_timeline"):
        mix += cue_plan["before_timeline"][0].apply_gain(-14.0).fade_in(30).fade_out(80)

    sfx_dir = ctx.path("flow_2_highlights", "sfx")
    legacy_sfx = sorted(sfx_dir.glob("*.wav")) if sfx_dir.is_dir() else []
    legacy_idx = 0

    rendered = 0
    for i, hl in enumerate(highlights):
        sid = hl.get("segment_id")
        seg = by_id.get(sid) if sid else None
        start_ms = hl.get("start_ms") or (seg and seg["start_ms"])
        end_ms = hl.get("end_ms") or (seg and seg["end_ms"])
        if start_ms is None or end_ms is None:
            continue
        rendered += 1
        clip = source[int(start_ms) : int(end_ms)]
        mix += clip
        rank = int(hl.get("rank") or (i + 1))
        if i + 1 < len(highlights):
            next_rank = int((highlights[i + 1] or {}).get("rank") or (i + 2))
            trans = _resolve_between_clip_transition(cue_plan, rank, next_rank)
            if trans is not None:
                mix += trans.apply_gain(-12.0).fade_in(25).fade_out(100)
            elif legacy_idx < len(legacy_sfx):
                mix += _load_audio(legacy_sfx[legacy_idx]).apply_gain(-12.0).fade_in(25).fade_out(100)
                legacy_idx += 1

    if cue_plan.get("after_timeline"):
        mix += cue_plan["after_timeline"][0].apply_gain(-14.0).fade_in(25).fade_out(110)
    if rendered == 0:
        raise RuntimeError("No highlight clips extracted")

    ctx.log(
        (
            f"mux_flow2: mixed highlights={rendered}, "
            f"transitions={max(0, rendered - 1)}, sfx_profile=montage"
        ),
        level="info",
        stage="mux_flow2",
    )
    assembly = ctx.path("flow_2_highlights", "assembly.wav")
    mix.export(str(assembly), format="wav")
    ctx.mark_done("mux_flow2")
    return assembly


def _load_sdp(ctx: RunContext) -> dict:
    path = ctx.path("understanding", "sound_design_plan.json")
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _flow2_cues_from_sdp(ctx: RunContext, sdp: dict) -> dict[str, list[AudioSegment | dict]]:
    out: dict[str, list[AudioSegment | dict]] = {
        "before_timeline": [],
        "after_timeline": [],
        "between_clips": [],
    }
    flow_plans = sdp.get("flow_plans") if isinstance(sdp.get("flow_plans"), dict) else {}
    flow = flow_plans.get("flow2") if isinstance(flow_plans.get("flow2"), dict) else {}
    cues = flow.get("cues") if isinstance(flow.get("cues"), list) else []
    assets = sdp.get("assets") if isinstance(sdp.get("assets"), list) else []
    assets_by_id = {
        str(item.get("asset_id")): item
        for item in assets
        if isinstance(item, dict) and item.get("asset_id")
    }
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        asset_id = str(cue.get("asset_id") or "")
        if not asset_id:
            continue
        wav = _resolve_asset_path(ctx, asset_id=asset_id, generated=sdp.get("generated"))
        if wav is None:
            continue
        audio = _load_audio(wav)
        level_db = float(cue.get("level_db", -12.0))
        if level_db:
            audio = audio.apply_gain(level_db)
        placement = str(cue.get("placement") or "")
        if placement in {"before_timeline", "after_timeline"}:
            out[placement].append(audio)
        elif placement == "between_clips":
            out["between_clips"].append(
                {
                    "audio": audio,
                    "from_clip_rank": int(cue.get("from_clip_rank") or 0),
                    "to_clip_rank": int(cue.get("to_clip_rank") or 0),
                    "role": assets_by_id.get(asset_id, {}).get("role"),
                }
            )
    return out


def _resolve_between_clip_transition(cues: dict[str, list[AudioSegment | dict]], from_rank: int, to_rank: int) -> AudioSegment | None:
    between = cues.get("between_clips") or []
    default: AudioSegment | None = None
    for item in between:
        if not isinstance(item, dict):
            continue
        audio = item.get("audio")
        if not isinstance(audio, AudioSegment):
            continue
        if default is None:
            default = audio
        if int(item.get("from_clip_rank") or 0) == from_rank and int(item.get("to_clip_rank") or 0) == to_rank:
            return audio
    return default


def _resolve_asset_path(ctx: RunContext, *, asset_id: str, generated: object) -> Path | None:
    if isinstance(generated, dict):
        rel = generated.get(asset_id)
        if isinstance(rel, str):
            p = ctx.path(rel)
            if p.is_file():
                return p
    for path in (
        ctx.path("sound_design", "assets", f"{asset_id}.wav"),
        ctx.path("flow_2_highlights", "sfx", f"{asset_id}.wav"),
    ):
        if path.is_file():
            return path
    return None


def _load_audio(path: Path) -> AudioSegment:
    seg = AudioSegment.from_file(path)
    return seg.set_channels(1).set_frame_rate(48000)
