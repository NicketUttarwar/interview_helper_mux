from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

from interview_mux.assets_audio import ensure_wav_asset
from interview_mux.run_context import RunContext


def test_ensure_wav_asset_skips_wav(tmp_path: Path) -> None:
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
    assert "-vn" in calls[0]


def test_ensure_wav_asset_converts_mp4(tmp_path: Path, monkeypatch) -> None:
    mp4 = tmp_path / "town_hall.mp4"
    mp4.write_bytes(b"fake-mp4")
    wav = tmp_path / "town_hall.wav"
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        wav.write_bytes(b"RIFF-converted")
        return CompletedProcess(cmd, 0)

    monkeypatch.setattr("interview_mux.operator_subprocess.subprocess.run", fake_run)

    out = ensure_wav_asset(mp4)
    assert out == wav.resolve()
    assert wav.is_file()
    assert calls[0][:4] == ["ffmpeg", "-y", "-i", str(mp4.resolve())]
    assert "-vn" in calls[0]


def test_ensure_wav_asset_converts_mp3(tmp_path: Path, monkeypatch) -> None:
    mp3 = tmp_path / "interview.mp3"
    mp3.write_bytes(b"fake-mp3")
    wav = tmp_path / "interview.wav"
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        wav.write_bytes(b"RIFF-converted")
        return CompletedProcess(cmd, 0)

    monkeypatch.setattr("interview_mux.operator_subprocess.subprocess.run", fake_run)

    out = ensure_wav_asset(mp3)
    assert out == wav.resolve()
    assert wav.is_file()
    assert calls[0][:4] == ["ffmpeg", "-y", "-i", str(mp3.resolve())]
    assert "pcm_s16le" in calls[0]


def test_ensure_wav_asset_converts_unknown_suffix(tmp_path: Path, monkeypatch) -> None:
    """Any non-wav suffix is converted by default (not an allowlist)."""
    src = tmp_path / "capture.flac"
    src.write_bytes(b"fake-flac")
    wav = tmp_path / "capture.wav"

    def fake_run(cmd, **kwargs):
        wav.write_bytes(b"RIFF-converted")
        return CompletedProcess(cmd, 0)

    monkeypatch.setattr("interview_mux.operator_subprocess.subprocess.run", fake_run)
    assert ensure_wav_asset(src) == wav.resolve()


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
    assert meta["input_audio_path_original"] == str(m4a.resolve())
    assert ctx.input_audio() == wav.resolve()


def test_init_run_meta_stores_wav_path_for_mp3(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    assets = tmp_path / "ASSETS"
    assets.mkdir(parents=True)
    mp3 = assets / "show.mp3"
    mp3.write_bytes(b"mp3")
    wav = assets / "show.wav"

    def fake_run(cmd, **_kwargs):
        wav.write_bytes(b"RIFF")
        return CompletedProcess(cmd, 0)

    monkeypatch.setattr("interview_mux.operator_subprocess.subprocess.run", fake_run)

    ctx = RunContext("exec_002_20260101T000000Z", create=True)
    ctx.init_run_meta(str(mp3))

    meta = ctx.read_json("run_meta.json")
    assert meta["input_audio_path"] == str(wav.resolve())
    assert meta["input_audio_path_original"] == str(mp3.resolve())
    assert ctx.input_audio() == wav.resolve()
