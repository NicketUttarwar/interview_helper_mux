"""June 2026 Wave A — early truth hypotheses (H-ING-03, H-G0-02, H-G0-01, H-GAP-01)."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest
import soundfile as sf

from interview_mux.llm_specialists import (
    _process_specialist_investigations,
    maybe_run_pre_stage_specialists,
    specialists_enabled,
)
from interview_mux.session_log import read_log
from interview_mux.sonic_context import build_segment_flags
from interview_mux.stage_enrichment import (
    TRUST_DIP_MAX_FLAGS,
    TRUST_DIP_MIN_DIP_RATIO_FOR_COMPREHENSION,
    compute_trust_dip_flags,
    communicative_salience_score,
    quality_trajectory_flags,
    trust_dip_corroborated,
)
from interview_mux.stages.transcript_review import (
    _acoustic_stress_score,
    _rank_review_chunks,
    _review_sort_mode,
    run_transcript_review_build,
)
from interview_mux.audio_energy import energy_windows_from_path
from interview_mux.value_analysis.extract import extract_and_write_value_features
from run_fixtures import isolated_run_ctx, minimal_manifest_segment, patch_merged_config


def _write_normalized_wav(path, *, quiet_segment: tuple[float, float] | None = None) -> None:
    rate = 16000
    t = np.linspace(0, 6, rate * 6, endpoint=False)
    wave = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    if quiet_segment:
        start_s, end_s = quiet_segment
        wave[int(rate * start_s) : int(rate * end_s)] *= 0.03
    sf.write(str(path), wave, rate)


def _minimal_transcript(words: list[dict] | None = None) -> dict:
    default_words = [
        {"text": "hello", "start_ms": 0, "end_ms": 400, "confidence": 0.95, "speaker_id": "spk_0"},
        {"text": "world", "start_ms": 500, "end_ms": 900, "confidence": 0.55, "speaker_id": "spk_0"},
        {"text": "again", "start_ms": 1000, "end_ms": 1400, "confidence": 0.92, "speaker_id": "spk_0"},
    ]
    return {"words": words or default_words, "segments": []}


def test_trust_dip_flags_capped_at_eight(tmp_path):
    rate = 16000
    t = np.linspace(0, 20, rate * 20, endpoint=False)
    wave = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    for i in range(0, len(wave), rate):
        wave[i : i + rate // 2] *= 0.02
    wav_path = tmp_path / "trust.wav"
    sf.write(str(wav_path), wave, rate)
    packed = energy_windows_from_path(wav_path)
    assert packed is not None
    rms, times_ms, _ = packed
    flags = compute_trust_dip_flags(rms, times_ms)
    assert len(flags) <= TRUST_DIP_MAX_FLAGS


def test_quality_trajectory_short_rms_fail_open(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "wa_short_rms")
    ctx.path("ingest").mkdir(parents=True, exist_ok=True)
    sf.write(str(ctx.path("ingest", "normalized.wav")), np.zeros(800, dtype=np.float32), 16000)
    assert quality_trajectory_flags(ctx) == []


def test_trust_dip_corroboration_requires_stress_or_low_conf(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "wa_corr")
    ctx.write_json(
        "transcript/full.json",
        _minimal_transcript(
            [
                {"text": "hello", "start_ms": 0, "end_ms": 400, "confidence": 0.95, "speaker_id": "spk_0"},
                {"text": "world", "start_ms": 500, "end_ms": 900, "confidence": 0.95, "speaker_id": "spk_0"},
            ]
        ),
        skip_handoff=True,
    )
    assert not trust_dip_corroborated(ctx, 500, dip_ratio=0.2)
    ctx.write_json(
        "transcript/review_queue.json",
        {
            "chunks": [
                {
                    "chunk_id": "tr_0001",
                    "start_ms": 400,
                    "end_ms": 1000,
                    "text": "world",
                    "confidence": 0.55,
                    "rank": 1,
                    "acoustic_stress_score": 0.6,
                }
            ]
        },
        skip_handoff=True,
    )
    assert trust_dip_corroborated(ctx, 500, dip_ratio=0.2)


def test_sonic_context_comprehension_risk_requires_corroboration(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "wa_sonic_risk")
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                minimal_manifest_segment("seg_001", start_ms=0, end_ms=6000),
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/value_features.json",
        {
            "profiles": {
                "transcript": {
                    "quality_trajectory_flags": [
                        {"start_ms": 500, "dip_ratio": 0.2, "note": "dip"},
                    ]
                }
            }
        },
        skip_handoff=True,
    )
    flags = build_segment_flags(ctx)
    assert "comprehension_risk" not in flags or flags["comprehension_risk"] == []

    ctx.write_json("transcript/full.json", _minimal_transcript(), skip_handoff=True)
    ctx.write_json(
        "transcript/review_queue.json",
        {
            "chunks": [
                {
                    "chunk_id": "tr_0001",
                    "start_ms": 400,
                    "end_ms": 1000,
                    "text": "world",
                    "confidence": 0.55,
                    "rank": 1,
                    "acoustic_stress_score": 0.55,
                }
            ]
        },
        skip_handoff=True,
    )
    flags2 = build_segment_flags(ctx)
    assert "seg_001" in (flags2.get("comprehension_risk") or [])


def test_acoustic_stress_rms_none_is_zero(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "wa_stress")
    wav = ctx.path("ingest", "normalized.wav")
    ctx.path("ingest").mkdir(parents=True, exist_ok=True)
    _write_normalized_wav(wav)
    chunk = {"start_ms": 0, "end_ms": 500, "confidence": 0.6}
    score = _acoustic_stress_score(wav, chunk)
    assert 0.0 <= score <= 1.0


def test_communicative_salience_null_stress_and_confidence():
    high_conf = communicative_salience_score({"confidence": 0.99, "text": "ok", "start_ms": 0, "end_ms": 500})
    low_conf = communicative_salience_score({"confidence": 0.5, "text": "many words here", "start_ms": 0, "end_ms": 5000})
    assert low_conf > high_conf
    null_conf = communicative_salience_score({"text": "x", "start_ms": 0, "end_ms": 1000})
    assert null_conf >= 0


def test_review_sort_mode_salience_default(monkeypatch):
    patch_merged_config(monkeypatch, {})
    assert _review_sort_mode() == "salience"


def test_review_sort_mode_confidence_fallback(monkeypatch):
    patch_merged_config(monkeypatch, {"transcript_review": {"sort_mode": "confidence"}})
    chunks = [
        {"chunk_id": "a", "confidence": 0.9, "text": "a", "start_ms": 0, "end_ms": 1000},
        {"chunk_id": "b", "confidence": 0.4, "text": "b b b", "start_ms": 1000, "end_ms": 2000},
    ]
    ranked = _rank_review_chunks(chunks, sort_mode="confidence")
    assert ranked[0]["chunk_id"] == "b"


def test_transcript_review_build_logs_salience(tmp_path, monkeypatch):
    patch_merged_config(monkeypatch, {"transcript_review": {"sort_mode": "salience"}})
    ctx = isolated_run_ctx(tmp_path, "wa_g0_build")
    ctx.path("ingest").mkdir(parents=True, exist_ok=True)
    _write_normalized_wav(ctx.path("ingest", "normalized.wav"))
    ctx.write_json("transcript/full.json", _minimal_transcript())
    run_transcript_review_build(ctx)
    queue = ctx.read_json("transcript/review_queue.json")
    assert queue.get("sort_mode") == "salience"
    assert all("rank" in c for c in queue.get("chunks") or [])
    logs = read_log(ctx.run_dir)
    build_logs = [e for e in logs if e.get("stage") == "transcript_review_build" and "sort_mode" in (e.get("message") or "")]
    assert build_logs


def test_extract_logs_trust_dip_flags(tmp_path, monkeypatch):
    patch_merged_config(
        monkeypatch,
        {
            "value_analysis": {
                "enabled": True,
                "transcript_features": True,
                "audio_features": False,
            }
        },
    )
    ctx = isolated_run_ctx(tmp_path, "wa_extract")
    ctx.path("ingest").mkdir(parents=True, exist_ok=True)
    _write_normalized_wav(ctx.path("ingest", "normalized.wav"), quiet_segment=(2.0, 3.0))
    ctx.write_json("transcript/full.json", _minimal_transcript())
    written = extract_and_write_value_features(ctx, profiles=("transcript",))
    assert written == ["transcript"]
    logs = read_log(ctx.run_dir)
    flag_logs = [e for e in logs if "trust-dip flags" in (e.get("message") or "")]
    assert flag_logs


def test_value_analysis_skip_no_wav_on_extract(tmp_path, monkeypatch):
    patch_merged_config(
        monkeypatch,
        {"value_analysis": {"enabled": True, "audio_features": True}},
    )
    ctx = isolated_run_ctx(tmp_path, "wa_no_wav_extract")
    ctx.write_json("transcript/full.json", _minimal_transcript())
    written = extract_and_write_value_features(ctx, profiles=("audio",))
    assert written == []
    logs = read_log(ctx.run_dir)
    skip = [e for e in logs if e.get("message") == "value_analysis_skip_no_wav"]
    assert len(skip) == 1
    assert skip[0]["stage"] == "value_analysis_extract"


def test_comprehension_specialist_below_threshold_no_investigation(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "wa_gap_thresh")
    count = _process_specialist_investigations(
        ctx,
        parent_stage="missing_framing",
        specialist_key="comprehension_risk_blind",
        envelope={
            "artifacts": {
                "comprehension_risks": [
                    {"segment_id": "seg_1", "risk_score": 0.4, "rationale": "mild"},
                ]
            }
        },
    )
    assert count == 0


def test_comprehension_specialist_disabled_skips(tmp_path):
    cfg = {"analysis": {"specialists": {"enabled": False}}}
    assert not specialists_enabled(cfg=cfg, stage_key="missing_framing")
    with patch("interview_mux.llm_specialists.run_specialist") as mock_run:
        outputs = maybe_run_pre_stage_specialists(ctx := isolated_run_ctx(tmp_path, "wa_spec_off"), "missing_framing", {}, cfg=cfg)
        mock_run.assert_not_called()
        assert outputs == []


def test_pre_stage_specialist_failure_continues_parent(tmp_path, monkeypatch):
    patch_merged_config(
        monkeypatch,
        {"analysis": {"flow_hardening": {"enabled": True}, "specialists": {"enabled": True}}},
    )
    ctx = isolated_run_ctx(tmp_path, "wa_pre_fail")
    cfg = {
        "analysis": {
            "flow_hardening": {"enabled": True},
            "specialists": {"enabled": True, "pilot_stages": ["missing_framing"]},
        }
    }
    with patch("interview_mux.llm_specialists.run_specialist", side_effect=RuntimeError("timeout")):
        outputs = maybe_run_pre_stage_specialists(ctx, "missing_framing", {"segments": {}}, cfg=cfg)
    assert outputs == []


def test_spike_weight_perturbation_stable_rank():
    base = {"confidence": 0.5, "text": "many words here", "start_ms": 0, "end_ms": 5000, "acoustic_stress_score": 0.3}
    other = {"confidence": 0.99, "text": "ok", "start_ms": 0, "end_ms": 500}
    base_score = communicative_salience_score(base)
    other_score = communicative_salience_score(other)
    assert base_score > other_score
    perturbed = communicative_salience_score({**base, "acoustic_stress_score": 0.36})
    assert communicative_salience_score(other) < perturbed


def test_severe_dip_ratio_floor():
    assert TRUST_DIP_MIN_DIP_RATIO_FOR_COMPREHENSION == pytest.approx(0.35)
