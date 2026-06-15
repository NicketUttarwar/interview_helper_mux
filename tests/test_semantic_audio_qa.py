"""Tests for Tier-2 semantic (CLAP) audio QA."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from interview_mux.semantic_audio_qa import (
    apply_semantic_verdict,
    maybe_semantic_similarity,
)


def test_maybe_semantic_similarity_disabled(monkeypatch):
    monkeypatch.setattr(
        "interview_mux.semantic_audio_qa.merged_config",
        lambda: {"mmaudio": {"semantic_qa_enabled": False}},
    )
    assert maybe_semantic_similarity(wav_path=Path("x.wav"), prompt_text="warm pad", asset_id="a") is None


def test_maybe_semantic_similarity_empty_prompt(monkeypatch):
    monkeypatch.setattr(
        "interview_mux.semantic_audio_qa.merged_config",
        lambda: {"mmaudio": {"semantic_qa_enabled": True}},
    )
    out = maybe_semantic_similarity(wav_path=Path("x.wav"), prompt_text="  ", asset_id="a")
    assert out is not None
    assert out["verdict"] == "skipped"
    assert out["skipped_reason"] == "empty_prompt"


def test_maybe_semantic_similarity_pass(monkeypatch, tmp_path):
    wav = tmp_path / "bed.wav"
    wav.write_bytes(b"RIFF")
    monkeypatch.setattr(
        "interview_mux.semantic_audio_qa.merged_config",
        lambda: {
            "mmaudio": {
                "semantic_qa_enabled": True,
                "semantic_qa_threshold": 0.18,
                "semantic_qa_fail_on_low": False,
            }
        },
    )

    with patch(
        "interview_mux.semantic_audio_qa.run_runtime_json",
        return_value={"available": True, "score": 0.42, "model_id": "laion/clap-htsat-fused"},
    ):
        out = maybe_semantic_similarity(
            wav_path=wav,
            prompt_text="soft ambient room tone",
            asset_id="bed",
        )
    assert out is not None
    assert out["verdict"] == "pass"
    assert out["score"] == 0.42


def test_maybe_semantic_similarity_warn_on_low_score(monkeypatch, tmp_path):
    wav = tmp_path / "bed.wav"
    wav.write_bytes(b"RIFF")
    monkeypatch.setattr(
        "interview_mux.semantic_audio_qa.merged_config",
        lambda: {
            "mmaudio": {
                "semantic_qa_enabled": True,
                "semantic_qa_threshold": 0.25,
                "semantic_qa_fail_on_low": False,
            }
        },
    )

    with patch(
        "interview_mux.semantic_audio_qa.run_runtime_json",
        return_value={"available": True, "score": 0.12, "model_id": "laion/clap-htsat-fused"},
    ):
        out = maybe_semantic_similarity(
            wav_path=wav,
            prompt_text="orchestral swell",
            asset_id="bed",
        )
    assert out is not None
    assert out["verdict"] == "warn"


def test_apply_semantic_verdict_fail_updates_row():
    row = {"asset_id": "x", "verdict": "pass", "recommended_action": "pass", "reasons": []}
    apply_semantic_verdict(
        row,
        {"score": 0.05, "verdict": "fail", "threshold": 0.18, "model_id": "laion/clap-htsat-fused"},
    )
    assert row["verdict"] == "fail"
    assert row["semantic_similarity"] == 0.05
    assert row["semantic_qa_verdict"] == "fail"
    assert "low_semantic_similarity" in row["reasons"]
    assert row["recommended_action"] == "refine"
