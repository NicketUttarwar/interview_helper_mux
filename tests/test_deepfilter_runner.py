from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from interview_mux.deepfilter_runner import DeepFilterUnavailable, enhance_wav


def test_enhance_wav_subprocess_success(monkeypatch, tmp_path):
    inp = tmp_path / "in.wav"
    out = tmp_path / "out.wav"
    inp.write_bytes(b"RIFF")

    repo = tmp_path / "DeepFilterNet"
    repo.mkdir()
    monkeypatch.setattr(
        "interview_mux.deepfilter_runner.deepfilter_repo_dir",
        lambda: repo,
    )

    monkeypatch.setattr("interview_mux.deepfilter_runner._require_deepfilter_stack", lambda: None)
    fake_proc = MagicMock()
    fake_proc.returncode = 0
    fake_proc.stdout = "ok"
    fake_proc.stderr = ""
    monkeypatch.setattr(
        "interview_mux.deepfilter_runner.run_runtime_script",
        lambda *a, **k: fake_proc,
    )

    enhance_wav(inp, out)
    assert fake_proc.returncode == 0


def test_enhance_wav_missing_repo(monkeypatch, tmp_path):
    inp = tmp_path / "in.wav"
    out = tmp_path / "out.wav"
    inp.write_bytes(b"x")
    monkeypatch.setattr(
        "interview_mux.deepfilter_runner.deepfilter_repo_dir",
        lambda: tmp_path / "missing",
    )
    with pytest.raises(DeepFilterUnavailable, match="repo missing"):
        enhance_wav(inp, out)


def test_enhance_wav_unbuilt_stack_refuses_before_spawn(monkeypatch, tmp_path):
    """Repo on disk but no native df build: refuse quietly, never run the script."""
    inp = tmp_path / "in.wav"
    out = tmp_path / "out.wav"
    inp.write_bytes(b"x")
    repo = tmp_path / "DeepFilterNet"
    repo.mkdir()
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    fake_py = venv / "bin" / "python"
    fake_py.write_text("#!/bin/sh\necho \"No module named 'df'\" >&2\nexit 1\n")
    fake_py.chmod(0o755)
    monkeypatch.setattr("interview_mux.deepfilter_runner.deepfilter_repo_dir", lambda: repo)
    monkeypatch.setattr("interview_mux.local_runtime.resolve_venv_dir", lambda _rid: venv)
    monkeypatch.setattr("interview_mux.deepfilter_runner._IMPORT_PROBE", {})

    def _spawned(*_a, **_k):
        raise AssertionError("runtime script must not be spawned for an unbuilt stack")

    monkeypatch.setattr("interview_mux.deepfilter_runner.run_runtime_script", _spawned)
    with pytest.raises(DeepFilterUnavailable, match="not installed"):
        enhance_wav(inp, out)
