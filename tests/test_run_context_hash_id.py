from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.run_context import EXEC_ID_RE, RunContext


def test_exec_id_re_accepts_hash_segment() -> None:
    assert EXEC_ID_RE.match("exec_001_a3f2b1c9d4e5_20260101T000000Z")
    assert EXEC_ID_RE.match("exec_001_20260101T000000Z")
    assert EXEC_ID_RE.match("exec_1008_a3f2b1c9d4e5_20260622T211817Z")


def test_allocate_run_id_with_hash() -> None:
    rid = RunContext.allocate_run_id(source_hash="a3f2b1c9d4e5")
    assert "a3f2b1c9d4e5" in rid
    assert EXEC_ID_RE.match(rid)


def test_init_run_meta_stores_source_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "repo"
    assets = root / "ASSETS" / "input"
    assets.mkdir(parents=True)
    wav = assets / "interview.wav"
    wav.write_bytes(b"RIFF" + b"\x00" * 64)

    executions = root / "ASSETS" / "executions"
    executions.mkdir(parents=True)

    monkeypatch.setenv("INTERVIEW_MUX_REPO_ROOT", str(root))
    monkeypatch.setattr(
        "interview_mux.run_context.repo_root",
        lambda: root,
    )
    monkeypatch.setattr(
        "interview_mux.run_context.merged_config",
        lambda: {
            "assets_root": "ASSETS",
            "executions_root": "ASSETS/executions",
            "data_root": "data",
        },
    )

    rid = RunContext.allocate_run_id(source_hash="abc")
    ctx = RunContext(rid, create=True)
    ctx.init_run_meta("ASSETS/input/interview.wav")
    meta = ctx.read_json("run_meta.json")
    assert meta.get("source_audio_hash")
    assert meta.get("source_audio_hash_short")
    assert meta["input_audio_path"].endswith(".wav")
