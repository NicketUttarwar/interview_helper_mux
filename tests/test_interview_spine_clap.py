from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from interview_mux.interview_spine import clap_index


def _ctx(tmp_path):
    ctx = MagicMock()
    ctx.path.side_effect = lambda *parts: tmp_path.joinpath(*parts)
    ctx.log = MagicMock()
    return ctx


def _patch_venv(monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_mux.local_runtime.resolve_venv_python",
        lambda *_a, **_k: Path("/usr/bin/true"),
    )


def test_build_clap_index_fail_open_on_subprocess_error(monkeypatch, tmp_path):
    ctx = _ctx(tmp_path)
    _patch_venv(monkeypatch)
    monkeypatch.setattr(
        "interview_mux.interview_spine.clap_index.subprocess.run",
        lambda *_a, **_k: MagicMock(returncode=1, stdout="", stderr="boom"),
    )
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
    ctx = _ctx(tmp_path)
    _patch_venv(monkeypatch)

    def fake_run(*_args, **kwargs):
        payload = json.loads(kwargs.get("input") or "{}")
        out = Path(payload["output_path"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({"available": True, "vectors": [[1.0, 0.0, 0.5]]}),
            encoding="utf-8",
        )
        receipt = json.dumps({"available": True, "output_path": str(out), "count": 1})
        return MagicMock(
            returncode=0,
            stdout=f"Loading weights: 100%\n{receipt}\n",
            stderr="",
        )

    monkeypatch.setattr("interview_mux.interview_spine.clap_index.subprocess.run", fake_run)
    per_window = MagicMock(side_effect=AssertionError("per-window fallback must not run"))
    monkeypatch.setattr("interview_mux.local_runtime.run_runtime_script", per_window)

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


def test_build_clap_index_skips_serial_fallback_for_many_windows(monkeypatch, tmp_path):
    ctx = _ctx(tmp_path)
    _patch_venv(monkeypatch)
    monkeypatch.setattr(
        "interview_mux.interview_spine.clap_index.subprocess.run",
        lambda *_a, **_k: MagicMock(returncode=0, stdout="not-json progress", stderr=""),
    )
    calls: list[int] = []

    def fake_script(*_a, **_k):
        calls.append(1)
        return MagicMock(returncode=0, stdout=json.dumps({"available": True, "vector": [1.0]}))

    monkeypatch.setattr("interview_mux.local_runtime.run_runtime_script", fake_script)

    windows = [
        {"window_id": f"win_{i:04d}", "start_ms": i * 1000, "end_ms": i * 1000 + 500}
        for i in range(20)
    ]
    enabled, sidecar, dim = clap_index.build_clap_index(
        ctx,
        windows,
        wav_path=tmp_path / "audio.wav",
        model_id="laion/clap-htsat-fused",
        timeout_sec=5,
    )
    assert enabled is False
    assert sidecar is None
    assert dim is None
    assert calls == []
    logged = " ".join(str(c.args[0]) for c in ctx.log.call_args_list if c.args)
    assert "skipping per-window fallback" in logged


def test_build_windows_drops_zero_duration_span():
    from interview_mux.interview_spine.windows import build_windows

    words = [
        {"text": "hello", "start_ms": 0, "end_ms": 800, "speaker_id": "a"},
        {"text": "end", "start_ms": 3567460, "end_ms": 3567460, "speaker_id": "a"},
    ]
    wins = build_windows(words, pace_class="conversational", cfg={"window_sec_default": 10, "hop_sec": 5})
    assert wins
    assert all(int(w["end_ms"]) > int(w["start_ms"]) for w in wins)
