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
