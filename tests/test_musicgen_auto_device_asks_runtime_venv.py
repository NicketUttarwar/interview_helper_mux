"""MusicGen auto device must consult the runtime venv, not only the core one.

The core venv is deliberately lean and here carries no torch at all; CUDA torch
lives in the MusicGen venv. effective_musicgen_device resolved "auto" with the
core interpreter, found no CUDA, and sent a 20-second bed to CPU on a host with
a 6 GB card. macOS is unchanged: MPS is resolved before this branch.
"""

from __future__ import annotations

import pytest

from interview_mux import musicgen_runner as mr


@pytest.fixture(autouse=True)
def _no_mps(monkeypatch):
    monkeypatch.setattr(mr, "_mps_available_for_musicgen", lambda: False)
    monkeypatch.setattr(mr, "mps_banned", lambda *a, **k: False)
    monkeypatch.setattr(mr, "musicgen_cfg", lambda: {"device": "auto"})
    monkeypatch.setitem(mr._RUNTIME_CUDA_CACHE, "musicgen", True)  # overwritten per test


def test_auto_prefers_cuda_when_only_the_runtime_venv_has_it(monkeypatch) -> None:
    monkeypatch.delitem(mr._RUNTIME_CUDA_CACHE, "musicgen", raising=False)
    monkeypatch.setattr(mr, "_runtime_venv_cuda_available", lambda: True)
    assert mr.effective_musicgen_device() == "cuda"


def test_auto_falls_back_to_cpu_when_no_venv_has_cuda(monkeypatch) -> None:
    monkeypatch.delitem(mr._RUNTIME_CUDA_CACHE, "musicgen", raising=False)
    monkeypatch.setattr(mr, "_runtime_venv_cuda_available", lambda: False)
    assert mr.effective_musicgen_device() == "cpu"


def test_explicit_device_still_wins(monkeypatch) -> None:
    monkeypatch.setattr(mr, "musicgen_cfg", lambda: {"device": "cpu"})
    monkeypatch.setattr(mr, "_runtime_venv_cuda_available", lambda: True)
    assert mr.effective_musicgen_device() == "cpu"
