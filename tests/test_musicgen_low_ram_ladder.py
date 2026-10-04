"""On a machine that cannot hold MusicGen-large, the ladder starts at medium (ISSUES 149).

exec_011 (8 GB M1): every stem tried large first and thrashed swap to the hang
timeout; one stem sat 80 minutes in uninterruptible wait and disk fell to 257 MB.
"""

from __future__ import annotations

import subprocess

import pytest

from interview_mux import musicgen_runner as mg


def _run_ladder(tmp_path, monkeypatch, ram_gb: float) -> dict:
    monkeypatch.setattr(mg, "physical_ram_gb", lambda: ram_gb)
    monkeypatch.setattr(mg, "musicgen_enabled", lambda: True)
    monkeypatch.setattr(mg, "musicgen_venv_python", lambda: tmp_path / "python")
    (tmp_path / "python").write_text("#!/bin/sh\n")
    monkeypatch.setattr(
        mg,
        "musicgen_cfg",
        lambda: {
            "device": "cpu",
            "ban_mps_on_abort": True,
            "request_timeout_sec": 5,
            "default_duration_sec": 12.0,
            "step_down_timeout_sec": 5,
            "max_request_timeout_sec": 5,
        },
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
    monkeypatch.setattr(
        mg,
        "_spawn_musicgen",
        lambda **kw: subprocess.CompletedProcess(kw["py"], 1, "", "timeout after 5s"),
    )
    return mg.generate_music_clip(
        prompt="warm piano theme",
        negative_prompt="",
        duration_sec=12.0,
        out_wav=tmp_path / "bed.wav",
        role="theme_underscore",
        seed=7,
    )


def test_eight_gb_starts_the_ladder_at_medium(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    meta = _run_ladder(tmp_path, monkeypatch, 8.0)
    ladder = meta.get("model_ladder") or []
    assert ladder and "medium" in ladder[0]
    assert not any("large" in m for m in ladder)
    assert meta.get("musicgen_large_skipped_low_ram_gb") == 8.0


def test_sixteen_gb_keeps_large_first(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    meta = _run_ladder(tmp_path, monkeypatch, 16.0)
    assert "large" in (meta.get("model_ladder") or [""])[0]


def test_unknown_ram_keeps_large_first(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    meta = _run_ladder(tmp_path, monkeypatch, 0.0)
    assert "large" in (meta.get("model_ladder") or [""])[0]
