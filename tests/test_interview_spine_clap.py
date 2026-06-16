from __future__ import annotations

import json
from unittest.mock import MagicMock

from interview_mux.interview_spine import clap_index


def test_build_clap_index_fail_open_on_subprocess_error(monkeypatch, tmp_path):
    ctx = MagicMock()
    ctx.path.side_effect = lambda *parts: tmp_path.joinpath(*parts)
    ctx.log = MagicMock()

    monkeypatch.setattr(
        "interview_mux.local_runtime.run_runtime_script",
        lambda *a, **k: MagicMock(returncode=1, stdout=""),
    )

    enabled, sidecar, dim = clap_index.build_clap_index(
        ctx,
        [{"window_id": "win_0001", "start_ms": 0, "end_ms": 1000, "embedding_ref": None}],
        wav_path=tmp_path / "audio.wav",
        model_id="laion/clap-htsat-fused",
        timeout_sec=5,
    )
    assert enabled is False
    assert sidecar is None
    assert dim is None


def test_build_clap_index_writes_sidecar_on_success(monkeypatch, tmp_path):
    ctx = MagicMock()
    ctx.path.side_effect = lambda *parts: tmp_path.joinpath(*parts)

    def fake_script(*args, **kwargs):
        return MagicMock(
            returncode=0,
            stdout=json.dumps({"available": True, "vector": [1.0, 0.0, 0.5]}),
        )

    monkeypatch.setattr("interview_mux.local_runtime.run_runtime_script", fake_script)

    windows = [{"window_id": "win_0001", "start_ms": 0, "end_ms": 1000, "embedding_ref": None}]
    enabled, sidecar, dim = clap_index.build_clap_index(
        ctx,
        windows,
        wav_path=tmp_path / "audio.wav",
        model_id="laion/clap-htsat-fused",
        timeout_sec=5,
    )
    assert enabled is True
    assert sidecar == "understanding/interview_spine/embeddings.npz"
    assert dim == 3
    assert windows[0]["embedding_ref"] == 0
