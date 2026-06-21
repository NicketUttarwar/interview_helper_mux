"""Disfluency extract with zero events — no_assets status and auto-review."""

from __future__ import annotations

from interview_mux.disfluency.context import disfluency_summary_for_ctx
from interview_mux.disfluency.extract import run_extraction
from interview_mux.run_context import RunContext
from interview_mux.stages.disfluency import run_disfluency_extract
from run_fixtures import isolated_run_ctx, patch_merged_config


def test_extraction_no_assets_status(tmp_path, monkeypatch) -> None:
    patch_merged_config(
        monkeypatch,
        {"disfluency_extract": {"enabled": True}, "disfluency_restore": {"enabled": True}},
    )
    ctx = isolated_run_ctx(tmp_path, "run_df_no_assets")
    ctx.write_json("transcript/full.json", {"words": [{"start_ms": 0, "end_ms": 500, "text": "hello"}]})
    wav = ctx.path("ingest/normalized.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" + b"\x00" * 64)

    doc = run_extraction(ctx)
    assert doc["status"] == "no_assets"
    assert doc["stats"]["total"] == 0


def test_no_assets_auto_completes_review(tmp_path, monkeypatch) -> None:
    patch_merged_config(
        monkeypatch,
        {"disfluency_extract": {"enabled": True}, "disfluency_restore": {"enabled": True}},
    )
    ctx = isolated_run_ctx(tmp_path, "run_df_auto_review")
    ctx.write_json("transcript/full.json", {"words": [{"start_ms": 0, "end_ms": 500, "text": "hello"}]})
    wav = ctx.path("ingest/normalized.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" + b"\x00" * 64)

    run_disfluency_extract(ctx)
    doc = ctx.read_json("transcript/disfluencies.json")
    assert doc["status"] == "no_assets"
    assert ctx.is_done("disfluency_extract")
    assert ctx.is_done("disfluency_review")


def test_no_assets_summary_omitted_from_llm_context(tmp_path, monkeypatch) -> None:
    patch_merged_config(
        monkeypatch,
        {"disfluency_extract": {"enabled": True}, "disfluency_restore": {"enabled": True}},
    )
    ctx = isolated_run_ctx(tmp_path, "run_df_ctx")
    ctx.write_json(
        "transcript/disfluencies.json",
        {
            "schema_version": 1,
            "status": "no_assets",
            "events": [],
            "stats": {"total": 0, "pending": 0, "confirmed": 0, "rejected": 0},
        },
    )
    assert disfluency_summary_for_ctx(ctx) is None
