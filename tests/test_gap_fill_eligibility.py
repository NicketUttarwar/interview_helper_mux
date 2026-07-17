"""Gap-fill eligibility binary gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.conversation_context import build_gap_sensitivity
from interview_mux.gap_fill_eligibility import (
    assess_gap_fill_eligibility,
    gap_fill_was_skipped,
)
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, patch_merged_config


def _write_speakers(run: Path, doc: dict) -> None:
    (run / "understanding").mkdir(parents=True, exist_ok=True)
    (run / "understanding" / "speakers.json").write_text(json.dumps(doc), encoding="utf-8")
    (run / "understanding" / "analysis_state.json").write_text("{}", encoding="utf-8")
    (run / "run_meta.json").write_text("{}", encoding="utf-8")


def test_skip_when_no_frame_speakers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = tmp_path / "exec_no_frame"
    _write_speakers(
        run,
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewee", "confidence": 0.9},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.9},
            ],
            "conversation_profile": {"format_class_candidate": "one_on_one", "dynamics": {}},
            "gap_sensitivity": build_gap_sensitivity("one_on_one"),
        },
    )
    ctx = RunContext(str(run))
    decision = assess_gap_fill_eligibility(ctx)
    assert not decision.eligible
    assert "frame" in decision.reason.lower() or "skip" in decision.reason.lower()


def test_eligible_asymmetric_interview(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = tmp_path / "exec_asym"
    _write_speakers(
        run,
        {
            "speakers": [
                {
                    "speaker_id": "spk_0",
                    "role": "interviewer",
                    "confidence": 0.9,
                    "question_density": "high",
                },
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.9},
            ],
            "conversation_profile": {
                "format_class_candidate": "one_on_one",
                "dynamics": {"turn_asymmetry": "high", "question_density": "high"},
            },
            "gap_sensitivity": build_gap_sensitivity("one_on_one"),
        },
    )
    (run / "understanding" / "source_topology.json").write_text(
        json.dumps({"topology_class": "one_on_one_asymmetric", "speaker_stats": []}),
        encoding="utf-8",
    )
    ctx = RunContext(str(run))
    decision = assess_gap_fill_eligibility(ctx)
    assert decision.eligible


def test_forced_skip_via_run_meta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = tmp_path / "exec_forced"
    _write_speakers(
        run,
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.95},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.95},
            ],
        },
    )
    (run / "run_meta.json").write_text(json.dumps({"gap_fill_mode": "skipped"}), encoding="utf-8")
    ctx = RunContext(str(run))
    assert not assess_gap_fill_eligibility(ctx).eligible


def test_gap_fill_was_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "skip_flag")
    assert not gap_fill_was_skipped(ctx)
    ctx.write_json(
        "understanding/gap_fill_skip.json",
        {"status": "skipped", "reason": "test"},
        skip_handoff=True,
    )
    assert gap_fill_was_skipped(ctx)
