from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from interview_mux.local_llm_runner import LocalLlmUnavailable, generate_local_chat


def test_generate_local_chat_subprocess_success(monkeypatch, tmp_path):
    weights = tmp_path / "weights"
    weights.mkdir()
    (weights / "config.json").write_text("{}", encoding="utf-8")

    fake_proc = MagicMock()
    fake_proc.returncode = 0
    fake_proc.stdout = '{"text": "hello", "meta": {"latency_ms": 42}}'
    fake_proc.stderr = ""

    monkeypatch.setattr(
        "interview_mux.local_llm_runner.resolve_model_path",
        lambda cfg=None: weights,
    )
    monkeypatch.setattr(
        "interview_mux.local_llm_runner.run_runtime_script",
        lambda *a, **k: fake_proc,
    )

    text, meta = generate_local_chat(system="sys", user="user")
    assert text == "hello"
    assert meta["latency_ms"] == 42


def test_generate_local_chat_subprocess_failure(monkeypatch, tmp_path):
    weights = tmp_path / "weights"
    weights.mkdir()

    monkeypatch.setattr(
        "interview_mux.local_llm_runner.resolve_model_path",
        lambda cfg=None: weights,
    )
    fake_proc = MagicMock()
    fake_proc.returncode = 1
    fake_proc.stdout = ""
    fake_proc.stderr = "mlx failed"
    monkeypatch.setattr(
        "interview_mux.local_llm_runner.run_runtime_script",
        lambda *a, **k: fake_proc,
    )

    with pytest.raises(LocalLlmUnavailable, match="subprocess failed"):
        generate_local_chat(system="sys", user="user")
