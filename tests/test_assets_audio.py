from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

from interview_mux.assets_audio import ensure_wav_asset
from interview_mux.run_context import RunContext


def test_ensure_wav_asset_skips_non_m4a(tmp_path: Path) -> None:
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")
    assert ensure_wav_asset(wav) == wav.resolve()


def test_ensure_wav_asset_converts_m4a(tmp_path: Path, monkeypatch) -> None:
    m4a = tmp_path / "interview.m4a"
    m4a.write_bytes(b"fake-m4a")
    wav = tmp_path / "interview.wav"
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        wav.write_bytes(b"RIFF-converted")
        return CompletedProcess(cmd, 0)

    monkeypatch.setattr("interview_mux.operator_subprocess.subprocess.run", fake_run)

    out = ensure_wav_asset(m4a)
    assert out == wav.resolve()
    assert wav.is_file()
    assert calls[0][:4] == ["ffmpeg", "-y", "-i", str(m4a.resolve())]


def test_ensure_wav_asset_reuses_fresh_wav(tmp_path: Path, monkeypatch) -> None:
    m4a = tmp_path / "interview.m4a"
    wav = tmp_path / "interview.wav"
    m4a.write_bytes(b"m4a")
    wav.write_bytes(b"wav")
    m4a.touch()
    wav.touch()
    assert wav.stat().st_mtime >= m4a.stat().st_mtime

    def fail_run(*_args, **_kwargs):
        raise AssertionError("ffmpeg should not run when wav is up to date")

    monkeypatch.setattr("interview_mux.operator_subprocess.subprocess.run", fail_run)
    assert ensure_wav_asset(m4a) == wav.resolve()


def test_init_run_meta_stores_wav_path_for_m4a(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    assets = tmp_path / "ASSETS" / "input"
    assets.mkdir(parents=True)
    m4a = assets / "capture.m4a"
    m4a.write_bytes(b"m4a")
    wav = assets / "capture.wav"

    def fake_run(cmd, **_kwargs):
        wav.write_bytes(b"RIFF")
        return CompletedProcess(cmd, 0)

    monkeypatch.setattr("interview_mux.operator_subprocess.subprocess.run", fake_run)

    ctx = RunContext("exec_001_20260101T000000Z", create=True)
    ctx.init_run_meta(str(m4a))

    meta = ctx.read_json("run_meta.json")
    assert meta["input_audio_path"] == str(wav.resolve())
    assert ctx.input_audio() == wav.resolve()
