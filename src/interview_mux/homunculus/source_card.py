"""Source card — always-packable snapshot of tape circumstances."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

from interview_mux.homunculus.admit import admit
from interview_mux.run_context import RunContext

SOURCE_CARD_REL = "mastering/homunculus/source_card.json"

CIRCUMSTANCE_AXES = (
    "one_on_one",
    "panel",
    "monologue",
    "sparse_host",
    "guest_heavy",
    "short",
    "long",
    "noisy",
    "video",
    "language_islands",
    "multi_stem",
    "music_primary",
    "lecture",
    "live_room",
)


def read_source_card(ctx: RunContext) -> dict[str, Any] | None:
    if not ctx.artifact_exists(SOURCE_CARD_REL):
        return None
    raw = ctx.read_json(SOURCE_CARD_REL)
    return raw if isinstance(raw, dict) else None


def wav_duration_s(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as wf:
            rate = wf.getframerate()
            if rate:
                return wf.getnframes() / float(rate)
    except Exception:
        return None
    return None


def refresh_source_profile(
    ctx: RunContext,
    *,
    stage: str,
    is_video: bool | None = None,
    duration_s: float | None = None,
    speaker_count: int | None = None,
    noisy: bool | None = None,
) -> str:
    from interview_mux.file_store import write_json as fs_write_json
    from interview_mux.stage_families import select_source_profile, source_profile_recipe

    video = is_video
    if video is None:
        try:
            video = str(ctx.input_audio()).lower().endswith((".mp4", ".mov", ".mkv", ".webm"))
        except Exception:
            video = False
    if duration_s is None:
        wav = ctx.path("ingest/normalized.wav")
        if wav.is_file():
            duration_s = wav_duration_s(wav)
    profile = select_source_profile(
        is_video=bool(video),
        noisy=bool(noisy),
        duration_s=duration_s,
        speaker_count=speaker_count,
    )
    recipe = source_profile_recipe(profile)
    dest = ctx.run_dir / "operator" / "source_profile.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    fs_write_json(
        dest,
        {
            "version": 1,
            "profile": profile,
            "is_video": bool(video),
            "duration_s": duration_s,
            "speaker_count": speaker_count,
            "noisy": bool(noisy),
            "selected_at_stage": stage,
            "recipe": recipe,
        },
    )

    def _patch_profile(meta: dict[str, Any]) -> None:
        meta["source_profile"] = profile
        meta["source_profile_recipe"] = recipe

    try:
        ctx.mutate_run_meta(_patch_profile)
    except Exception:
        pass
    return profile


def build_source_card(ctx: RunContext) -> dict[str, Any]:
    duration_s = None
    wav = ctx.path("ingest/normalized.wav")
    if wav.is_file():
        duration_s = wav_duration_s(wav)
    if duration_s is None:
        try:
            from interview_mux.interview_duration_policy import transcript_duration_ms

            ms = transcript_duration_ms(ctx)
            if ms:
                duration_s = ms / 1000.0
        except Exception:
            duration_s = None

    speaker_count = None
    talk_share: dict[str, Any] = {}
    speakers_rel = None
    for rel in ("understanding/speakers.json", "transcript/speakers.json"):
        if ctx.artifact_exists(rel):
            speakers_rel = rel
            raw = ctx.read_json(rel)
            rows = (raw.get("speakers") if isinstance(raw, dict) else raw) or []
            if isinstance(rows, dict):
                speaker_count = len(rows)
            elif isinstance(rows, list):
                speaker_count = len(rows)
            break

    topology = None
    format_class = None
    tone = None
    pickup = None
    if ctx.artifact_exists("understanding/source_topology.json"):
        topo = ctx.read_json("understanding/source_topology.json") or {}
        if isinstance(topo, dict):
            topology = topo.get("topology_class") or topo.get("class") or topo.get("kind")
            talk_share = topo.get("talk_share") or topo.get("speaker_stats") or {}
            pickup = topo.get("pickup_eligible_speaker_id")
    if ctx.artifact_exists("understanding/conversation_profile.json"):
        prof = ctx.read_json("understanding/conversation_profile.json") or {}
        if isinstance(prof, dict):
            format_class = prof.get("format_class_candidate") or prof.get("format_class")
            tone = prof.get("tone_class_candidate") or prof.get("tone_class")

    noisy = False
    if ctx.artifact_exists("understanding/source_acoustic_profile.json"):
        ac = ctx.read_json("understanding/source_acoustic_profile.json") or {}
        if isinstance(ac, dict):
            noisy = bool(ac.get("noisy") or ac.get("noise_floor_high"))

    islands = False
    island_count = 0
    if ctx.artifact_exists("analysis/high_value_speech_islands.json"):
        hv = ctx.read_json("analysis/high_value_speech_islands.json") or {}
        rows = (hv.get("islands") if isinstance(hv, dict) else hv) or []
        if isinstance(rows, list) and rows:
            islands = True
            island_count = len(rows)
    elif ctx.artifact_exists("analysis/low_conf_must_keep.json"):
        mk = ctx.read_json("analysis/low_conf_must_keep.json") or {}
        ids = (mk.get("segment_ids") if isinstance(mk, dict) else None) or []
        if ids:
            islands = True
            island_count = len(ids)

    is_video = False
    try:
        is_video = str(ctx.input_audio()).lower().endswith((".mp4", ".mov", ".mkv", ".webm"))
    except Exception:
        is_video = False

    profile = refresh_source_profile(
        ctx,
        stage="source_card",
        is_video=is_video,
        duration_s=duration_s,
        speaker_count=speaker_count,
        noisy=noisy,
    )

    circumstances: list[str] = []
    fc = str(format_class or topology or "").lower()
    topo_l = str(topology or "").lower()
    if "panel" in fc or topo_l == "panel_multi_guest":
        circumstances.append("panel")
    elif topo_l in {"monologue_heavy", "monologue"} or (
        "monologue" in fc and "fireside" not in fc
    ):
        circumstances.append("monologue")
    elif "fireside" in fc:
        circumstances.append("one_on_one")
    elif "sparse" in fc or topo_l == "multi_idea_sparse_host":
        circumstances.append("sparse_host")
    elif "guest" in fc:
        circumstances.append("guest_heavy")
    else:
        circumstances.append("one_on_one")
    if duration_s is not None and duration_s < 180:
        circumstances.append("short")
    if duration_s is not None and duration_s > 7200:
        circumstances.append("long")
    if noisy:
        circumstances.append("noisy")
    if is_video:
        circumstances.append("video")
    if islands:
        circumstances.append("language_islands")

    recipe = "thin_source" if "short" in circumstances else ("batch_layup" if "long" in circumstances else "standard")
    framing = (
        "sparse_omit"
        if str(topology or "").lower() in {"monologue_heavy", "monologue"}
        or str(topology or "").lower().startswith("monologue_")
        else "least_spoken_host"
    )

    card = {
        "schema_version": 1,
        "profile": profile,
        "topology": topology,
        "format_class": format_class,
        "tone": tone,
        "duration_s": duration_s,
        "speaker_count": speaker_count,
        "talk_share": talk_share,
        "pickup_speaker_id": pickup,
        "language_islands": islands,
        "language_island_count": island_count,
        "noisy": noisy,
        "is_video": is_video,
        "circumstances": circumstances,
        "recipe": recipe,
        "framing_posture": framing,
        "clone_policy": "least_spoken_host",
        "speakers_rel": speakers_rel,
        "axes": list(CIRCUMSTANCE_AXES),
    }
    ctx.write_json(SOURCE_CARD_REL, card)
    admit(
        ctx,
        identity="source_card",
        action="keep",
        payload=card,
        fact_id="source_card",
    )
    return card
