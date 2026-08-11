"""MusicGen MPS abort hardening: device resolve, CLI python, SIGABRT ban."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.musicgen_runner import (
    ban_mps,
    best_of_n_for_role,
    cli_python_executable,
    effective_musicgen_device,
    is_abort_returncode,
    mps_banned,
    musicgen_hf_home,
)


def test_is_abort_returncode() -> None:
    assert is_abort_returncode(-6)
    assert is_abort_returncode(134)
    assert not is_abort_returncode(0)
    assert not is_abort_returncode(1)
    assert not is_abort_returncode(None)


def test_hf_home_is_local_musicgen_cache() -> None:
    home = musicgen_hf_home()
    assert home.as_posix().endswith("ASSETS/local_musicgen/hf_cache")


def test_effective_device_never_auto_mps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MUX_MUSICGEN_BAN_MPS", raising=False)
    assert effective_musicgen_device(requested="auto") == "cpu"
    assert effective_musicgen_device(requested="") == "cpu"
    assert effective_musicgen_device(requested="cpu") == "cpu"
    assert effective_musicgen_device(requested="mps") == "mps"


def test_ban_mps_forces_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_MUSICGEN_BAN_MPS", "1")
    assert mps_banned() is True
    assert effective_musicgen_device(requested="mps") == "cpu"


def test_cli_python_rewrites_python_app(tmp_path: Path) -> None:
    version_root = tmp_path / "Python.framework" / "Versions" / "3.12"
    app_py = version_root / "Resources" / "Python.app" / "Contents" / "MacOS" / "Python"
    cli_py = version_root / "bin" / "python3.12"
    app_py.parent.mkdir(parents=True)
    cli_py.parent.mkdir(parents=True)
    app_py.write_text("#!/bin/sh\n")
    cli_py.write_text("#!/bin/sh\n")
    app_py.chmod(0o755)
    cli_py.chmod(0o755)
    assert cli_python_executable(app_py) == cli_py


def test_cli_python_passthrough_venv(tmp_path: Path) -> None:
    py = tmp_path / "venv" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("#!/bin/sh\n")
    py.chmod(0o755)
    assert cli_python_executable(py) == py


def test_best_of_n_capped_at_one() -> None:
    assert best_of_n_for_role("theme_cold_open") == 1
    assert best_of_n_for_role("theme_underscore") == 1


def test_generate_retries_cpu_after_mps_abort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    from interview_mux import musicgen_runner as mg

    monkeypatch.delenv("MUX_MUSICGEN_BAN_MPS", raising=False)
    monkeypatch.setattr(mg, "musicgen_enabled", lambda: True)
    monkeypatch.setattr(mg, "fail_closed_on_stub", lambda: False)
    monkeypatch.setattr(mg, "musicgen_venv_python", lambda: tmp_path / "python")
    (tmp_path / "python").write_text("#!/bin/sh\n")
    monkeypatch.setattr(mg, "musicgen_cfg", lambda: {"device": "mps", "ban_mps_on_abort": True, "request_timeout_sec": 5})
    monkeypatch.setattr(mg, "cli_python_executable", lambda p: p)
    monkeypatch.setattr(mg, "effective_musicgen_device", lambda **kwargs: "mps")
    monkeypatch.setattr(mg, "musicgen_hf_home", lambda: tmp_path / "hf_cache")

    class _DummyLock:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            pass

        def acquire(self, *args, **kwargs) -> bool:  # noqa: ANN002, ANN003
            return True

        def release(self) -> None:
            pass

    import filelock

    monkeypatch.setattr(filelock, "FileLock", _DummyLock)
    calls: list[str] = []

    def fake_spawn(**kwargs):  # noqa: ANN003
        req = Path(kwargs["req"])
        payload = __import__("json").loads(req.read_text())
        calls.append(str(payload.get("device")))
        if payload.get("device") == "mps":
            return subprocess.CompletedProcess(kwargs["py"], -6, "", "abort")
        out = Path(payload["out_wav"])
        out.write_bytes(b"0" * 2000)
        return subprocess.CompletedProcess(kwargs["py"], 0, "", "")

    monkeypatch.setattr(mg, "_spawn_musicgen", fake_spawn)
    out = tmp_path / "stem.wav"
    meta = mg.generate_music_clip(
        prompt="theme",
        negative_prompt="",
        duration_sec=4.0,
        out_wav=out,
        role="theme_cold_open",
    )
    assert calls[0] == "mps"
    assert "cpu" in calls
    assert meta.get("device") == "cpu"
    assert out.is_file()


def test_ban_mps_writes_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MUX_MUSICGEN_BAN_MPS", raising=False)

    class _Ctx:
        run_dir = tmp_path

        def mutate_run_meta(self, fn):  # noqa: ANN001
            meta: dict = {}
            fn(meta)
            (tmp_path / "run_meta.json").write_text(str(meta))

    ban_mps(run_ctx=_Ctx(), reason="returncode=-6")
    assert (tmp_path / ".musicgen_ban_mps").is_file()
    assert mps_banned(run_ctx=_Ctx()) is True


def test_generate_always_writes_wav_after_ladder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    from interview_mux import musicgen_runner as mg

    monkeypatch.setattr(mg, "musicgen_enabled", lambda: True)
    monkeypatch.setattr(mg, "musicgen_venv_python", lambda: tmp_path / "python")
    (tmp_path / "python").write_text("#!/bin/sh\n")
    monkeypatch.setattr(
        mg,
        "musicgen_cfg",
        lambda: {"device": "cpu", "ban_mps_on_abort": True, "request_timeout_sec": 5},
    )
    monkeypatch.setattr(mg, "cli_python_executable", lambda p: p)
    monkeypatch.setattr(mg, "effective_musicgen_device", lambda **kwargs: "cpu")
    monkeypatch.setattr(mg, "musicgen_hf_home", lambda: tmp_path / "hf_cache")

    class _DummyLock:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            pass

        def acquire(self, *args, **kwargs) -> bool:  # noqa: ANN002, ANN003
            return True

        def release(self) -> None:
            pass

    import filelock

    monkeypatch.setattr(filelock, "FileLock", _DummyLock)
    timeouts: list[int] = []

    def fake_spawn(**kwargs):  # noqa: ANN003
        timeouts.append(int(kwargs["timeout"]))
        return subprocess.CompletedProcess(kwargs["py"], 1, "", "timeout after 5s")

    monkeypatch.setattr(mg, "_spawn_musicgen", fake_spawn)
    out = tmp_path / "bed.wav"
    meta = mg.generate_music_clip(
        prompt="lush orchestral theme with choir and 48k fidelity",
        negative_prompt="",
        duration_sec=12.0,
        out_wav=out,
        role="theme_underscore",
        seed=7,
    )
    assert out.is_file() and out.stat().st_size > 1000
    assert meta.get("backend") == "musical_stub"
    assert meta.get("fidelity_step") == "short_bare_cpu"
    assert timeouts[0] == 5
    assert timeouts[-1] <= 5
