"""Tests for mmaudio_runner CFG/seed resolution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from interview_mux.mmaudio_runner import (
    apply_prompt_influence_to_text,
    clamp_duration_seconds,
    generate_text_to_audio,
    resolve_cfg_strength,
    resolve_seed,
    MMAudioUnavailable,
)


def test_clamp_duration_seconds():
    assert clamp_duration_seconds(1.0) >= 3.0
    assert clamp_duration_seconds(20.0) <= 8.0


def test_resolve_cfg_strength_explicit_wins():
    assert resolve_cfg_strength(explicit_cfg=5.2) == 5.2


def test_resolve_cfg_strength_role_and_influence():
    low = resolve_cfg_strength(role="ambient_bed", prompt_influence=0.2)
    high = resolve_cfg_strength(role="ambient_bed", prompt_influence=0.45)
    assert high > low


def test_resolve_seed_asset_hash_stable():
    a = resolve_seed(asset_id="bed_main", run_id="run-1", cfg={"seed_strategy": "asset_id_hash"})
    b = resolve_seed(asset_id="bed_main", run_id="run-1", cfg={"seed_strategy": "asset_id_hash"})
    assert a == b


def test_generate_passes_negative_separately(monkeypatch, tmp_path):
    repo = tmp_path / "MMAudio"
    repo.mkdir()
    out = tmp_path / "out.wav"
    captured_args: list[str] = []

    def fake_run(runtime, script, args, **kwargs):
        captured_args.extend(args)
        out.write_bytes(b"RIFF" + b"\x00" * 8)
        proc = MagicMock()
        proc.returncode = 0
        return proc

    monkeypatch.setattr("interview_mux.mmaudio_runner.mmaudio_repo_dir", lambda: repo)
    monkeypatch.setattr("interview_mux.mmaudio_runner.run_runtime_script", fake_run)

    meta = generate_text_to_audio(
        prompt="soft bed",
        negative_prompt="no vocals no speech",
        duration_seconds=4.0,
        output_wav=out,
        asset_id="bed",
        role="ambient_bed",
    )
    assert meta["provider"] == "mmaudio"
    assert "no vocals" in " ".join(captured_args)
    assert "soft bed" in " ".join(captured_args)
    assert "Avoid:" not in " ".join(captured_args)


def test_generate_text_to_audio_missing_repo(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "interview_mux.mmaudio_runner.mmaudio_repo_dir",
        lambda: tmp_path / "missing",
    )
    with pytest.raises(MMAudioUnavailable, match="repo missing"):
        generate_text_to_audio(
            prompt="x",
            duration_seconds=4.0,
            output_wav=tmp_path / "out.wav",
        )


def test_apply_prompt_influence_high():
    text = apply_prompt_influence_to_text("bed", 0.45)
    assert "precisely" in text.lower()
