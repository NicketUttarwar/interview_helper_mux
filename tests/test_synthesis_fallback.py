"""Tests for Chatterbox → manual record fallback."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from interview_mux.gap_framing import normalize_interviewer_line
from interview_mux.gap_vo_gates import set_gap_framing_enabled, set_gap_vo_delivery
from interview_mux.run_context import RunContext
from interview_mux.synthesis_fallback import (
    SynthesisFallbackToManual,
    fallback_to_manual_collection,
    maybe_fallback_after_synthesis_failure,
)
from interview_mux import s2s_runner
from run_fixtures import init_run_meta_for_test, minimal_gap_line, patch_executions_root


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext("exec_manual_fallback", create=True)
    init_run_meta_for_test(run)
    set_gap_framing_enabled(run, True)
    set_gap_vo_delivery(run, "chatterbox")
    line = normalize_interviewer_line(
        {
            **minimal_gap_line(line_id="line_001", targets_segment_id="seg_001"),
            "line_category": "framing_question",
            "text": "What happened next?",
        },
        eligible="spk_0",
        delivery="synthesize",
    )
    run.path("understanding").mkdir(parents=True, exist_ok=True)
    run.path("understanding", "gap_report.json").write_text(
        json.dumps({"interviewer_lines": [line]}) + "\n",
        encoding="utf-8",
    )
    return run


def test_fallback_switches_line_to_record(ctx: RunContext) -> None:
    payload = fallback_to_manual_collection(ctx, reason="test failure", line_ids=["line_001"])
    assert payload["delivery"] == "record"
    report = ctx.read_json("understanding/gap_report.json")
    assert report["interviewer_lines"][0]["delivery"] == "record"
    meta = ctx.read_json("run_meta.json")
    assert meta.get("gap_vo_delivery") == "record"
    assert "manual record" in str(meta.get("synthesis_fallback_notice", "")).lower()


def test_maybe_fallback_raises_controlled_exception(ctx: RunContext) -> None:
    line = ctx.read_json("understanding/gap_report.json")["interviewer_lines"][0]
    with pytest.raises(SynthesisFallbackToManual):
        maybe_fallback_after_synthesis_failure(ctx, line, RuntimeError("all synth failed"))


def test_synthesize_line_falls_back_when_mlx_fails(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    line = ctx.read_json("understanding/gap_report.json")["interviewer_lines"][0]
    monkeypatch.setattr("interview_mux.chatterbox_runner.should_use_chatterbox", lambda _c: False)
    monkeypatch.setattr("interview_mux.s2s_runner.s2s_enabled", lambda: True)
    monkeypatch.setattr("interview_mux.s2s_runner.resolve_reference_audio", lambda _c, _l: Path("/tmp/ref.wav"))
    monkeypatch.setattr("interview_mux.s2s_runner.context_clip_for_line", lambda *_a: None)
    monkeypatch.setattr("interview_mux.s2s_runner.run_runtime_json", lambda *_a, **_k: {"ok": False, "error": "mlx down"})

    with pytest.raises(SynthesisFallbackToManual):
        s2s_runner.synthesize_line(ctx, line, mode="synthesize")

    report = ctx.read_json("understanding/gap_report.json")
    assert report["interviewer_lines"][0]["delivery"] == "record"
