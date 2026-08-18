"""Tests for mmaudio_asset_qa deterministic checks."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from interview_mux.mmaudio_asset_qa import (
    _expected_bucket_from_room_timbre,
    _peak_density,
    analyze_asset_wav,
    loop_seam_score,
    run_mmaudio_asset_qa,
)
from run_fixtures import (
    isolated_run_ctx,
    minimal_source_acoustic_profile,
    patch_merged_config,
    seed_from_sonic_fixture,
    sound_design_plan_with,
)


def _write_wav(path: Path, duration_sec: float = 1.0, amplitude: int = 5000) -> None:
    rate = 48000
    n = int(rate * duration_sec)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = struct.pack(f"<{n}h", *([amplitude] * n))
        wf.writeframes(frames)


def _write_transient_wav(path: Path, *, duration_sec: float = 0.8) -> None:
    rate = 48000
    n = int(rate * duration_sec)
    samples: list[int] = []
    for i in range(n):
        if i % 1200 < 80:
            samples.append(28000)
        else:
            samples.append(0)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack(f"<{n}h", *samples))


def test_analyze_missing_file():
    row = analyze_asset_wav(asset_id="x", path=Path("/nonexistent/x.wav"))
    assert row["verdict"] == "fail"
    assert "missing_wav" in row["reasons"]


def test_analyze_duration_exceeds_plan(tmp_path):
    wav = tmp_path / "bed.wav"
    _write_wav(wav, duration_sec=6.0)
    row = analyze_asset_wav(
        asset_id="bed",
        path=wav,
        plan_row={"role": "ambient_bed", "duration_seconds": 4.0},
    )
    assert row["verdict"] in {"warn", "fail"}
    assert "duration_exceeds_plan" in row["reasons"] or row.get("suggested_trim_ms")


def test_analyze_small_file(tmp_path):
    wav = tmp_path / "tiny.wav"
    wav.write_bytes(b"x")
    row = analyze_asset_wav(asset_id="t", path=wav)
    assert row["verdict"] == "fail"


def test_expected_bucket_from_room_timbre_mapping():
    assert _expected_bucket_from_room_timbre("dry_close_mic_warm_low_mid") == "ambient_territory"
    assert _expected_bucket_from_room_timbre("dry_close_mic_bright_presence") == "transition_family"
    assert _expected_bucket_from_room_timbre("dry_close_mic_neutral_mid") == "accent_texture"
    assert _expected_bucket_from_room_timbre("") is None


def test_peak_density_detects_transients(tmp_path):
    wav = tmp_path / "transient.wav"
    _write_transient_wav(wav)
    from interview_mux.mmaudio_asset_qa import _read_wav_frames

    samples, rate = _read_wav_frames(wav)
    density = _peak_density(samples, rate)
    assert density >= 0.3


def test_loop_seam_score_uses_waveform_boundary_and_correlation():
    rate = 1000
    seamless = [0.5 * math.sin(2 * math.pi * i / 100) for i in range(1000)]
    discontinuous = list(seamless)
    discontinuous[-80:] = [-value for value in seamless[:80]]
    discontinuous[-1] = -0.9

    good = loop_seam_score(seamless, rate)
    bad = loop_seam_score(discontinuous, rate)

    assert 0.0 <= bad < good <= 1.0
    assert good >= 0.8
    assert bad < 0.55


def test_run_mmaudio_qa_room_timbre_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "qa_room")
    assets = ctx.path("sound_design", "assets")
    assets.mkdir(parents=True, exist_ok=True)
    wav = assets / "stinger_a.wav"
    _write_wav(wav, duration_sec=1.0, amplitude=12000)
    ctx.write_json(
        "understanding/sound_design_plan.json",
        sound_design_plan_with(
            palettes=[
                {
                    "palette_id": "p1",
                    "sonic_bucket": "ambient_territory",
                    "segment_ids": ["seg_001"],
                    "theme_label": "warm",
                    "keywords": ["warm", "room"],
                    "ambient_description": "warm room tone",
                    "accent_description": "soft chime",
                    "avoid": ["harsh"],
                }
            ],
            assets=[
                {
                    "asset_id": "stinger_a",
                    "role": "chapter_stinger",
                    "palette_id": "p1",
                    "description": "chapter sting",
                    "duration_seconds": 1.0,
                }
            ],
        ),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/source_acoustic_profile.json",
        minimal_source_acoustic_profile(
            energy={"room_timbre_hint": "dry_close_mic_bright_presence"},
        ),
        skip_handoff=True,
    )
    seed_from_sonic_fixture(ctx, "one_on_one", seed_base=False)
    doc = run_mmaudio_asset_qa(ctx)
    row = doc["assets"][0]
    assert "room_timbre_mismatch" in row.get("reasons", [])


def test_run_mmaudio_qa_trauma_percussive_fail(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    patch_merged_config(monkeypatch, {"mmaudio": {"trauma_peak_density_threshold": 0.05}})
    ctx = isolated_run_ctx(tmp_path, "qa_trauma")
    assets = ctx.path("sound_design", "assets")
    assets.mkdir(parents=True, exist_ok=True)
    _write_transient_wav(assets / "stinger_t.wav")
    ctx.write_json(
        "understanding/sound_design_plan.json",
        sound_design_plan_with(
            assets=[
                {
                    "asset_id": "stinger_t",
                    "role": "chapter_stinger",
                    "description": "soft sting",
                    "duration_seconds": 0.8,
                }
            ],
        ),
        skip_handoff=True,
    )
    seed_from_sonic_fixture(ctx, "trauma_adjacent", seed_base=False)
    doc = run_mmaudio_asset_qa(ctx)
    row = doc["assets"][0]
    assert row["verdict"] == "fail"
    assert "trauma_percussive_transient" in row.get("reasons", [])


def test_heal_mmaudio_qa_drops_rows_without_wav(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "qa_parity")
    assets = ctx.path("sound_design", "assets")
    assets.mkdir(parents=True, exist_ok=True)
    _write_wav(assets / "bed_ok.wav")
    ctx.write_json(
        "sound_design/mmaudio_qa.json",
        {
            "version": 1,
            "assets": [
                {"asset_id": "bed_ok", "verdict": "pass"},
                {"asset_id": "ghost", "verdict": "pass"},
            ],
        },
        skip_handoff=True,
    )
    from interview_mux.mmaudio_asset_qa import heal_mmaudio_qa_wav_parity, load_mmaudio_qa

    heal = heal_mmaudio_qa_wav_parity(ctx)
    assert heal["healed"] is True
    assert "ghost" in heal["dropped"]
    qa = load_mmaudio_qa(ctx)
    assert {row["asset_id"] for row in qa["assets"]} == {"bed_ok"}

