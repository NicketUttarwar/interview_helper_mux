"""Theme open/outro integrity — no silent bookend duration (exec_11130)."""

from __future__ import annotations

import array
import json
import wave
from pathlib import Path

import pytest
from pydub import AudioSegment
from pydub.generators import Sine

from interview_mux.theme_slot_integrity import (
    assert_theme_bookends_ready_for_mix,
    ensure_cold_open_cue,
    refuse_silent_theme_overlay,
    reserved_theme_asset_ids,
    shrink_theme_reservations_for_omit,
    theme_asset_audible,
    wav_is_audible,
)
from run_fixtures import isolated_run_ctx


def _write_sdp(ctx, doc: dict) -> None:
    ctx.write_json("understanding/sound_design_plan.json", doc, skip_handoff=True)


def _write_edl(ctx, clips: list) -> None:
    ordered = [
        str(c.get("segment_id"))
        for c in clips
        if isinstance(c, dict) and c.get("type") == "speech" and c.get("segment_id")
    ] or ["seg_a"]
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ordered,
            "timeline_duration_ms": max(
                1, sum(int(c.get("duration_ms") or 0) for c in clips)
            ),
            "clips": clips,
        },
        skip_handoff=True,
    )


def _write_silent_wav(path: Path, *, seconds: float = 1.0, sr: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(seconds * sr)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(array.array("h", [0] * n).tobytes())


def _write_tone_wav(path: Path, *, seconds: float = 1.0, sr: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tone = Sine(220).to_audio_segment(duration=int(seconds * 1000), volume=-12).set_frame_rate(sr)
    tone.export(str(path), format="wav")


def _base_sdp(*, with_open: bool = True, with_close: bool = True, cues: list | None = None) -> dict:
    assets = [
        {
            "asset_id": "show_theme_v1_underscore_loop",
            "role": "theme_underscore",
            "palette_kind": "underscore_loop",
            "duration_seconds": 12,
        }
    ]
    if with_open:
        assets.append(
            {
                "asset_id": "show_theme_v1_full_bed_open",
                "role": "theme_cold_open",
                "palette_kind": "full_bed",
                "placement_hint": "open",
                "duration_seconds": 14,
            }
        )
    if with_close:
        assets.append(
            {
                "asset_id": "show_theme_v1_full_bed_close",
                "role": "theme_outro",
                "palette_kind": "full_bed",
                "placement_hint": "close",
                "duration_seconds": 16,
            }
        )
    return {
        "version": 1,
        "assets": assets,
        "flow_plans": {
            "podcast": {
                "profile": "podcast",
                "cues": cues if cues is not None else [],
            }
        },
    }


def test_wav_is_audible_rejects_digital_silence(tmp_path: Path) -> None:
    silent = tmp_path / "silent.wav"
    tone = tmp_path / "tone.wav"
    _write_silent_wav(silent, seconds=2.0)
    _write_tone_wav(tone, seconds=1.0)
    assert wav_is_audible(silent) is False
    assert wav_is_audible(tone) is True


def test_refuse_silent_theme_overlay_for_speech_free_roles() -> None:
    err = refuse_silent_theme_overlay(
        role="theme_outro", asset_id="bed_close", missing_asset=True
    )
    assert err and "refusing silent duration" in err
    assert refuse_silent_theme_overlay(
        role="theme_underscore", asset_id="loop", missing_asset=True
    ) is None
    silent = AudioSegment.silent(duration=2000, frame_rate=16000)
    err2 = refuse_silent_theme_overlay(
        role="theme_cold_open",
        asset_id="bed_open",
        missing_asset=False,
        audio=silent,
    )
    assert err2 and "near-silent" in err2


def test_reserved_theme_includes_palette_bookends_even_without_cues(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "theme_reserve")
    _write_sdp(ctx, _base_sdp(cues=[]))
    _write_edl(
        ctx,
        [
            {
                "type": "silence",
                "air_kind": "opening_music",
                "duration_ms": 14400,
                "preserve_planned_music": True,
                "timeline_start_ms": 0,
            }
        ],
    )
    reserved = reserved_theme_asset_ids(ctx)
    assert "show_theme_v1_full_bed_open" in reserved
    assert "show_theme_v1_full_bed_close" in reserved
    assert "show_theme_v1_underscore_loop" not in reserved


def test_ensure_cold_open_cue_seeds_when_missing(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "theme_seed_open")
    _write_sdp(ctx, _base_sdp(cues=[]))
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_a", "seg_b"]},
        skip_handoff=True,
    )
    written = ensure_cold_open_cue(ctx)
    assert written
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    cues = ((sdp.get("flow_plans") or {}).get("podcast") or {}).get("cues") or []
    assert any(
        str(c.get("role")) == "theme_cold_open"
        and str(c.get("asset_id")) == "show_theme_v1_full_bed_open"
        for c in cues
        if isinstance(c, dict)
    )


def test_place_episode_close_allow_create_false_does_not_invent(tmp_path) -> None:
    from interview_mux.listen_quality import place_episode_close_cue

    ctx = isolated_run_ctx(tmp_path, "theme_no_invent")
    _write_sdp(ctx, _base_sdp(cues=[]))
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_a", "seg_b"]},
        skip_handoff=True,
    )
    place_episode_close_cue(ctx, allow_create=False)
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    cues = ((sdp.get("flow_plans") or {}).get("podcast") or {}).get("cues") or []
    assert not any(
        str(c.get("role")) == "theme_outro" for c in cues if isinstance(c, dict)
    )
    # Music epoch may create.
    written2 = place_episode_close_cue(ctx, allow_create=True)
    assert written2
    sdp2 = ctx.read_json("understanding/sound_design_plan.json")
    cues2 = ((sdp2.get("flow_plans") or {}).get("podcast") or {}).get("cues") or []
    assert any(str(c.get("role")) == "theme_outro" for c in cues2 if isinstance(c, dict))


def test_assert_mix_ready_fails_without_audible_bookend_wav(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "theme_mix_gate")
    _write_sdp(
        ctx,
        _base_sdp(
            cues=[
                {
                    "cue_id": "theme_outro_seed",
                    "role": "theme_outro",
                    "asset_id": "show_theme_v1_full_bed_close",
                    "placement": "after_segment",
                    "preserve_full_duration": True,
                }
            ]
        ),
    )
    with pytest.raises(RuntimeError, match="pin mmaudio_sfx"):
        assert_theme_bookends_ready_for_mix(ctx)


def test_assert_mix_ready_passes_with_audible_wavs(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "theme_mix_ok")
    _write_sdp(
        ctx,
        _base_sdp(
            cues=[
                {
                    "cue_id": "open",
                    "role": "theme_cold_open",
                    "asset_id": "show_theme_v1_full_bed_open",
                    "preserve_full_duration": True,
                },
                {
                    "cue_id": "theme_outro_seed",
                    "role": "theme_outro",
                    "asset_id": "show_theme_v1_full_bed_close",
                    "preserve_full_duration": True,
                },
            ]
        ),
    )
    assets = ctx.path("sound_design", "assets")
    _write_tone_wav(assets / "show_theme_v1_full_bed_open.wav", seconds=1.5)
    _write_tone_wav(assets / "show_theme_v1_full_bed_close.wav", seconds=1.5)
    assert theme_asset_audible(ctx, "show_theme_v1_full_bed_close")
    assert_theme_bookends_ready_for_mix(ctx)


def test_shrink_omit_clears_opening_music_and_skips_cues(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "theme_shrink")
    _write_sdp(
        ctx,
        _base_sdp(
            cues=[
                {
                    "cue_id": "open",
                    "role": "theme_cold_open",
                    "asset_id": "show_theme_v1_full_bed_open",
                    "preserve_full_duration": True,
                },
                {
                    "cue_id": "theme_outro_seed",
                    "role": "theme_outro",
                    "asset_id": "show_theme_v1_full_bed_close",
                    "preserve_full_duration": True,
                },
            ]
        ),
    )
    _write_edl(
        ctx,
        [
            {
                "type": "silence",
                "air_kind": "opening_music",
                "duration_ms": 14400,
                "preserve_planned_music": True,
                "timeline_start_ms": 0,
            },
            {
                "type": "speech",
                "segment_id": "seg_a",
                "source_start_ms": 0,
                "source_end_ms": 1000,
                "duration_ms": 1000,
                "timeline_start_ms": 14400,
            },
        ],
    )
    out = shrink_theme_reservations_for_omit(
        ctx, ["show_theme_v1_full_bed_open", "show_theme_v1_full_bed_close"]
    )
    assert out["cues_skipped"] >= 2
    assert out["opening_music_cleared"] == 1
    edl = ctx.read_json("master/edl.json")
    open_clip = next(
        c for c in edl["clips"] if str(c.get("air_kind")) == "opening_music"
    )
    assert int(open_clip["duration_ms"]) == 0
    assert open_clip.get("preserve_planned_music") is False
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    cues = ((sdp.get("flow_plans") or {}).get("podcast") or {}).get("cues") or []
    for c in cues:
        if str(c.get("asset_id")) in {
            "show_theme_v1_full_bed_open",
            "show_theme_v1_full_bed_close",
        }:
            assert c.get("skip") is True
            assert c.get("preserve_full_duration") is False


def test_collect_generation_includes_reserved_bookends(tmp_path) -> None:
    from interview_mux.stages.sfx_mmaudio import _collect_generation_items

    ctx = isolated_run_ctx(tmp_path, "theme_gen_items")
    # Underscore cue only — bookends must still be required.
    _write_sdp(
        ctx,
        _base_sdp(
            cues=[
                {
                    "cue_id": "bed",
                    "role": "theme_underscore",
                    "asset_id": "show_theme_v1_underscore_loop",
                }
            ]
        ),
    )
    items = _collect_generation_items(ctx=ctx, profile="podcast", fallback_cues=[])
    aids = {str(i.get("asset_id")) for i in items}
    assert "show_theme_v1_underscore_loop" in aids
    assert "show_theme_v1_full_bed_open" in aids
    assert "show_theme_v1_full_bed_close" in aids
