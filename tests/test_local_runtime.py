from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.local_runtime import LocalRuntimeUnavailable, resolve_venv_dir


def test_resolve_venv_dir_paths():
    mlx = resolve_venv_dir("mlx")
    assert mlx.name == "venv"
    assert "local_llm" in str(mlx)


def test_resolve_venv_python_missing_raises():
    with pytest.raises(LocalRuntimeUnavailable):
        from interview_mux.local_runtime import resolve_venv_python

        # Use fake runtime with nonexistent venv path via monkeypatch on resolve_venv_dir
        import interview_mux.local_runtime as lr

        lr.resolve_venv_dir = lambda _id: Path("/nonexistent/venv/path")  # type: ignore[method-assign]
        lr.resolve_venv_python("deepfilter")
