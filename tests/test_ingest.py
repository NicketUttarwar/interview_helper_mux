from __future__ import annotations

import pytest

from interview_mux.run_context import RunContext
from interview_mux.stages import ingest as ingest_mod


@pytest.fixture
def ingest_ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("MUX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("MUX_EXECUTIONS_ROOT", str(tmp_path / "executions"))
    ctx = RunContext("exec_test_ingest", create=True)
    wav = tmp_path / "input.wav"
    wav.write_bytes(b"\x00" * (2 * 1024 * 1024))
    ctx.init_run_meta(str(wav), source_audio_hash="a" * 64)
    return ctx, wav


def test_sha256_emits_progress(ingest_ctx, monkeypatch):
    ctx, wav = ingest_ctx
    logs: list[str] = []

    def capture(msg, **kwargs):
        logs.append(msg)

    monkeypatch.setattr(ctx, "log", capture)
    monkeypatch.setattr(ingest_mod, "touch_job_message", lambda *a, **k: None)
    monkeypatch.setattr(ingest_mod, "_HASH_PROGRESS_BYTES", 512 * 1024)
    digest = ingest_mod._sha256(wav, ctx=ctx, label="source")
    assert len(digest) == 64
    assert any("hashing source" in m for m in logs)
