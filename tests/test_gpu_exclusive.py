"""Unit tests for machine-wide GPU exclusive gate."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_local_gpu_defaults() -> None:
    from interview_mux.config import merged_config
    from interview_mux.gpu_exclusive import gpu_cooldown_sec, gpu_serialize_enabled

    block = merged_config().get("local_gpu") or {}
    assert block.get("serialize") is True
    assert float(block.get("cooldown_sec") or 0) == 5.0
    assert "musicgen" in (block.get("consumers") or [])
    assert "chatterbox" in (block.get("consumers") or [])
    # conftest zeros cooldown via env for unit speed
    assert gpu_serialize_enabled() is True
    assert gpu_cooldown_sec() == 0.0


def test_gpu_exclusive_cooldown_after_exit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import interview_mux.gpu_exclusive as ge

    sleeps: list[float] = []
    monkeypatch.delenv("INTERVIEW_MUX_GPU_COOLDOWN_SEC", raising=False)
    monkeypatch.setattr(ge, "gpu_cooldown_sec", lambda: 5.0)
    monkeypatch.setattr(ge, "gpu_serialize_enabled", lambda: True)
    monkeypatch.setattr(ge, "_lock_path", lambda: tmp_path / "gpu.lock")
    monkeypatch.setattr(ge.time, "sleep", lambda s: sleeps.append(float(s)))

    with ge.gpu_exclusive("musicgen"):
        assert sleeps == []
    assert sleeps == [5.0]


def test_gpu_exclusive_skips_unknown_consumer(monkeypatch: pytest.MonkeyPatch) -> None:
    import interview_mux.gpu_exclusive as ge

    sleeps: list[float] = []
    monkeypatch.setattr(ge, "gpu_cooldown_sec", lambda: 5.0)
    monkeypatch.setattr(ge.time, "sleep", lambda s: sleeps.append(float(s)))

    with ge.gpu_exclusive("not_a_gpu_thing"):
        pass
    assert sleeps == []


def test_gpu_exclusive_serializes_two_consumers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import interview_mux.gpu_exclusive as ge

    order: list[str] = []
    monkeypatch.setattr(ge, "gpu_cooldown_sec", lambda: 0.0)
    monkeypatch.setattr(ge, "_lock_path", lambda: tmp_path / "gpu.lock")

    with ge.gpu_exclusive("musicgen"):
        order.append("musicgen_start")
    with ge.gpu_exclusive("chatterbox"):
        order.append("chatterbox_start")
    assert order == ["musicgen_start", "chatterbox_start"]
