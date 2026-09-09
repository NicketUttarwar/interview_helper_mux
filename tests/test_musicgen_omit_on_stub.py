"""MU1: fail_closed_on_stub prevents stub ship / uses omit path."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux import musicgen_runner as mg
from run_fixtures import isolated_run_ctx, patch_executions_root


def test_fail_closed_omits_stub_wav(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = isolated_run_ctx(tmp_path, "exec_music_omit")
    monkeypatch.setattr(mg, "musicgen_enabled", lambda: True)
    monkeypatch.setattr(mg, "fail_closed_on_stub", lambda: True)
    monkeypatch.setattr(mg, "stub_allowed_for_role", lambda _r: True)
    monkeypatch.setattr(mg, "restore_prior_stem", lambda _p: None)
    monkeypatch.setattr(mg, "musicgen_venv_python", lambda: None)
    monkeypatch.setattr(mg, "_run_ctx_for_out_wav", lambda _p: ctx)
    out = tmp_path / "bed_001.wav"
    meta = mg.generate_music_clip(
        prompt="underscore bed",
        negative_prompt="",
        duration_sec=4.0,
        out_wav=out,
        role="theme_underscore",
    )
    assert not out.is_file()
    assert meta.get("backend") == "music_omitted"
    assert meta.get("music_omitted") is True


def test_generate_or_omit_bed_stamps_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = isolated_run_ctx(tmp_path, "exec_music_omit_ledger")
    monkeypatch.setattr(mg, "musicgen_enabled", lambda: True)
    monkeypatch.setattr(mg, "fail_closed_on_stub", lambda: True)
    monkeypatch.setattr(mg, "stub_allowed_for_role", lambda _r: True)
    monkeypatch.setattr(mg, "restore_prior_stem", lambda _p: None)
    monkeypatch.setattr(mg, "musicgen_venv_python", lambda: None)
    monkeypatch.setattr(mg, "_run_ctx_for_out_wav", lambda _p: ctx)
    out = tmp_path / "theme_open.wav"
    meta = mg.generate_or_omit_bed(
        prompt="cold open",
        out_wav=out,
        role="theme_cold_open",
        run_ctx=ctx,
    )
    assert meta.get("backend") == "music_omitted"
    assert not out.is_file()
    assert ctx.artifact_exists("operator/music_omitted.json")
    doc = ctx.read_json("operator/music_omitted.json")
    assert doc.get("omitted")


def test_stub_backend_counts_as_missing_sdp(tmp_path: Path, monkeypatch) -> None:
    patch_executions_root(monkeypatch, tmp_path)
    ctx = isolated_run_ctx(tmp_path, "exec_stub_missing")
    assets = ctx.path("sound_design", "assets")
    assets.mkdir(parents=True, exist_ok=True)
    wav = assets / "bed_001.wav"
    wav.write_bytes(b"RIFF" + b"\x00" * 2000)
    wav.with_suffix(".gen.json").write_text(
        '{"backend": "musical_stub"}\n', encoding="utf-8"
    )
    sdp_path = ctx.path("understanding", "sound_design_plan.json")
    sdp_path.parent.mkdir(parents=True, exist_ok=True)
    sdp_path.write_text(
        '{"assets": [{"asset_id": "bed_001", "role": "theme_underscore"}]}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.referenced_musicgen_asset_ids",
        lambda _c: {"bed_001"},
    )
    from interview_mux.sdp_cross_validate import missing_sdp_asset_wavs

    assert "bed_001" in missing_sdp_asset_wavs(ctx)
