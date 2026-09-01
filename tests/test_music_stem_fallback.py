"""Music stem preservation and quality-first fallback ladder."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from interview_mux.musicgen_runner import (
    backup_prior_stem,
    generate_music_clip,
    restore_prior_stem,
    stub_allowed_for_role,
)


def test_stub_blocked_for_cold_open() -> None:
    assert not stub_allowed_for_role("theme_cold_open")
    assert not stub_allowed_for_role("theme_outro")
    assert stub_allowed_for_role("theme_underscore")


def test_backup_and_restore_prior_stem(tmp_path: Path) -> None:
    out = tmp_path / "motif.wav"
    out.write_bytes(b"x" * 5000)
    gen = out.with_suffix(".gen.json")
    gen.write_text(json.dumps({"backend": "musicgen", "role": "theme_cold_open"}), encoding="utf-8")

    assert backup_prior_stem(out) is True
    assert Path(str(out) + ".prior.bak").is_file()

    out.write_bytes(b"stub")
    gen.write_text(json.dumps({"backend": "musical_stub"}), encoding="utf-8")

    restored = restore_prior_stem(out)
    assert restored is not None
    assert restored.get("fallback") == "kept_prior_stem"
    assert out.stat().st_size > 1000
    gmeta = json.loads(gen.read_text(encoding="utf-8"))
    assert gmeta.get("backend") == "musicgen"


def test_generate_sigterm_backoff_between_ladder_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import interview_mux.musicgen_runner as mg

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
            "step_down_duration_ratio": 0.85,
        },
    )
    monkeypatch.setattr(mg, "cli_python_executable", lambda p: p)
    monkeypatch.setattr(mg, "effective_musicgen_device", lambda **kwargs: "cpu")
    monkeypatch.setattr(mg, "musicgen_hf_home", lambda: tmp_path / "hf_cache")
    hub = tmp_path / "hf_cache" / "hub"
    for mid in (
        "facebook/musicgen-large",
        "facebook/musicgen-medium",
        "facebook/musicgen-small",
    ):
        (hub / ("models--" + mid.replace("/", "--"))).mkdir(parents=True)
    monkeypatch.setattr(mg, "stub_allowed_for_role", lambda role: role != "theme_cold_open")

    backoff_calls: list[str] = []

    def fake_backoff(ctx, consumer):  # noqa: ANN001
        backoff_calls.append(consumer)
        return 0.0

    monkeypatch.setattr("interview_mux.heavy_task_policy.wait_abort_backoff", fake_backoff)

    class _DummyLock:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            pass

        def acquire(self, *args, **kwargs) -> bool:  # noqa: ANN002, ANN003
            return True

        def release(self) -> None:
            pass

    import filelock

    monkeypatch.setattr(filelock, "FileLock", _DummyLock)

    call_count = {"n": 0}

    def fake_spawn(**kwargs):  # noqa: ANN003
        call_count["n"] += 1
        return subprocess.CompletedProcess(kwargs["py"], -15, "", "killed")

    monkeypatch.setattr(mg, "_spawn_musicgen", fake_spawn)
    out = tmp_path / "cold_open.wav"
    meta = mg.generate_music_clip(
        prompt="theme",
        negative_prompt="",
        duration_sec=8.0,
        out_wav=out,
        role="theme_cold_open",
    )
    assert call_count["n"] >= 2
    assert backoff_calls
    assert meta.get("backend") in {"musicgen_failed", "musical_stub"}
