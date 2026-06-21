"""Disfluency extract hard failures surface clearly."""

from __future__ import annotations

import pytest

from interview_mux.stages.disfluency import run_disfluency_extract
from run_fixtures import isolated_run_ctx, patch_merged_config


def test_disfluency_extract_missing_transcript(tmp_path, monkeypatch) -> None:
    patch_merged_config(
        monkeypatch,
        {"disfluency_extract": {"enabled": True}, "disfluency_restore": {"enabled": True}},
    )
    ctx = isolated_run_ctx(tmp_path, "run_df_missing_tx")
    wav = ctx.path("ingest/normalized.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" + b"\x00" * 64)

    with pytest.raises(FileNotFoundError):
        run_disfluency_extract(ctx)

    assert not ctx.is_done("disfluency_extract")


def test_disfluency_extract_missing_audio(tmp_path, monkeypatch) -> None:
    patch_merged_config(
        monkeypatch,
        {"disfluency_extract": {"enabled": True}, "disfluency_restore": {"enabled": True}},
    )
    ctx = isolated_run_ctx(tmp_path, "run_df_missing_audio")
    ctx.write_json("transcript/full.json", {"words": [{"start_ms": 0, "end_ms": 500, "text": "hello"}]})

    with pytest.raises(FileNotFoundError, match="No normalized audio"):
        run_disfluency_extract(ctx)
