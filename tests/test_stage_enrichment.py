from __future__ import annotations

import json

import numpy as np
import pytest
import soundfile as sf

from interview_mux.llm_specialists import _process_specialist_investigations
from interview_mux.stage_enrichment import (
    communicative_salience_score,
    pause_ladder_hints,
    pause_ladder_hints_from_words,
    quality_trajectory_flags,
)
from run_fixtures import isolated_run_ctx, minimal_manifest


def test_pause_ladder_hints_from_words(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_enrich")
    ctx.path("transcript").mkdir(parents=True, exist_ok=True)
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                {"start_ms": 0, "end_ms": 100, "text": "a"},
                {"start_ms": 900, "end_ms": 1000, "text": "b"},
                {"start_ms": 2000, "end_ms": 2100, "text": "c"},
            ]
        },
    )
    hints = pause_ladder_hints(ctx)
    assert hints["thresholds_ms"] == [400, 700, 1200]
    assert any(c["count"] >= 1 for c in hints["candidates"])


def test_communicative_salience_prefers_low_confidence():
    low = communicative_salience_score({"confidence": 0.5, "text": "many words here", "start_ms": 0, "end_ms": 5000})
    high = communicative_salience_score({"confidence": 0.99, "text": "ok", "start_ms": 0, "end_ms": 500})
    assert low > high


def test_quality_trajectory_flags_on_synthetic_wav(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_qt")
    ctx.path("ingest").mkdir(parents=True, exist_ok=True)
    rate = 16000
    t = np.linspace(0, 4, rate * 4, endpoint=False)
    wave = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    wave[rate * 2 : rate * 3] *= 0.05
    sf.write(str(ctx.path("ingest", "normalized.wav")), wave, rate)
    flags = quality_trajectory_flags(ctx)
    assert isinstance(flags, list)


def test_quality_trajectory_flags_empty_without_wav(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_qt_no_wav")
    assert quality_trajectory_flags(ctx) == []


def test_emphasis_regions_empty_without_wav(tmp_path):
    from interview_mux.stage_enrichment import emphasis_regions_for_segments

    ctx = isolated_run_ctx(tmp_path, "run_emph_no_wav")
    ctx.write_json("segments/manifest.json", minimal_manifest("seg_1"), skip_handoff=True)
    assert emphasis_regions_for_segments(ctx) == []


def test_specialist_comprehension_enqueues_investigation(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "run_spec")
    count = _process_specialist_investigations(
        ctx,
        parent_stage="missing_framing",
        specialist_key="comprehension_risk_blind",
        envelope={
            "artifacts": {
                "comprehension_risks": [
                    {"segment_id": "seg_1", "risk_score": 0.9, "rationale": "confusing"},
                ]
            }
        },
    )
    assert count == 1
    queue = ctx.read_json("understanding/investigation_queue.json")
    assert len(queue.get("items") or []) >= 1
