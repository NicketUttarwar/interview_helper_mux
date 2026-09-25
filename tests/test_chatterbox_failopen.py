"""Chatterbox fail-open routes to mlx-audio S2S."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from interview_mux.run_context import RunContext
from interview_mux import s2s_runner
from run_fixtures import (
    confirm_test_pickup_speaker,
    patch_executions_root,
    write_fixture_json,
    write_fixture_vo_wav,
)


def _arm_vo_path(ctx: RunContext, speaker_id: str = "spk_host") -> None:
    confirm_test_pickup_speaker(ctx, speaker_id=speaker_id)
    write_fixture_vo_wav(
        ctx.final_path("understanding", "speaker_samples", f"{speaker_id}.wav"),
        duration_sec=3.2,
    )
    write_fixture_json(
        ctx,
        f"understanding/voice_reference/{speaker_id}.json",
        {
            "speaker_id": speaker_id,
            "approved": True,
            "wav": f"understanding/speaker_samples/{speaker_id}.wav",
        },
    )
    meta: dict = {}
    if ctx.artifact_exists("run_meta.json"):
        try:
            existing = ctx.read_json("run_meta.json")
            if isinstance(existing, dict):
                meta = dict(existing)
        except Exception:
            meta = {}
    meta.setdefault("gap_framing_enabled", True)
    meta.setdefault("gap_vo_delivery", "chatterbox")
    meta.setdefault("voice_reference_approved_at", "2026-01-01T00:00:00Z")
    write_fixture_json(ctx, "run_meta.json", meta)


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    run = RunContext("exec_cb_failopen", create=True)
    pickup = run.path("vo_pickup", "synthesized")
    pickup.mkdir(parents=True, exist_ok=True)
    out = pickup / "line_001.wav"
    out.write_bytes(b"RIFF" + b"\x00" * 64)
    _arm_vo_path(run)
    return run


def test_chatterbox_failure_uses_mlx(monkeypatch: pytest.MonkeyPatch, ctx: RunContext) -> None:
    line = {"line_id": "line_001", "text": "Hello there.", "targets_segment_id": "seg_001"}

    monkeypatch.setattr("interview_mux.chatterbox_runner.should_use_chatterbox", lambda _c: True)
    monkeypatch.setattr(
        "interview_mux.chatterbox_runner.synthesize_line",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("chatterbox down")),
    )
    monkeypatch.setattr(
        "interview_mux.s2s_runner.gap_vo_cfg",
        lambda: {"fail_open": True, "fallback_backend": "mlx_audio"},
    )
    monkeypatch.setattr("interview_mux.s2s_runner.s2s_enabled", lambda: True)
    monkeypatch.setattr("interview_mux.s2s_runner.resolve_reference_audio", lambda _c, _l: Path("/tmp/ref.wav"))
    monkeypatch.setattr("interview_mux.s2s_runner.context_clip_for_line", lambda *_a: None)
    monkeypatch.setattr("interview_mux.s2s_runner.resolve_s2s_model_id", lambda: "test-model")
    monkeypatch.setattr(
        "interview_mux.s2s_runner.run_runtime_json",
        lambda *_a, **_k: {"ok": True},
    )
    monkeypatch.setattr("interview_mux.s2s_runner._append_qa_sidecar", lambda *_a, **_k: None)

    out = s2s_runner.synthesize_line(ctx, line, mode="synthesize")
    assert out.is_file()
    doc = ctx.read_json("vo_pickup/synthesis_report.json")
    entry = (doc.get("entries") or [])[-1]
    assert entry["backend"] == "mlx_audio"
    assert entry.get("fallback_from") == "chatterbox"


def test_synthesis_blocks_spoken_internal_segment_id(ctx: RunContext) -> None:
    line = {
        "line_id": "line_002",
        "text": "What happens as we get to 153?",
        "targets_segment_id": "seg_153",
    }
    with pytest.raises(ValueError, match="spoken_internal_identifier"):
        s2s_runner.synthesize_line(ctx, line, mode="synthesize")
