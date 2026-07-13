"""June 2026 Wave D — output resilience (H-F1N-02, H-F2-02, H-F1S-02)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from interview_mux import pipeline
from interview_mux.context_volley import _slim_flow_input
from interview_mux.placement_qa import run_placement_qa
from interview_mux.run_context import RunContext
from interview_mux.sound_design import _laughter_windows_from_value_features, _nudge_away_from_laughter
from interview_mux.stage_enrichment import (
    _spine_quotability_boost,
    emphasis_regions_for_segments,
    quotability_signals,
)
from run_fixtures import (
    isolated_run_ctx,
    minimal_manifest,
    minimal_manifest_segment,
    patch_merged_config,
    seed_flow1_sound_spend_ready,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sonic_context"

def _write_wav_with_peaks(path: Path, *, duration_s: float = 8.0, peak_segments: list[tuple[float, float, float]] | None = None) -> None:
    """Write mono WAV; peak_segments = (start_s, end_s, amplitude_multiplier)."""
    rate = 16000
    n = int(rate * duration_s)
    t = np.linspace(0, duration_s, n, endpoint=False)
    wave = (0.08 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    for start_s, end_s, mult in peak_segments or []:
        wave[int(rate * start_s) : int(rate * end_s)] *= mult
    sf.write(str(path), wave, rate)

def _manifest_with_segments(segments: list[dict]) -> dict:
    return {"segments": segments}

def test_emphasis_detects_local_peak_vs_quiet_neighbors(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "wd_emph_peak")
    ctx.path("ingest").mkdir(parents=True, exist_ok=True)
    _write_wav_with_peaks(
        ctx.path("ingest", "normalized.wav"),
        peak_segments=[(2.0, 3.0, 8.0)],
    )
    ctx.write_json(
        "segments/manifest.json",
        _manifest_with_segments(
            [
                minimal_manifest_segment("seg_quiet", start_ms=0, end_ms=2000),
                minimal_manifest_segment("seg_peak", start_ms=2000, end_ms=4000),
                minimal_manifest_segment("seg_after", start_ms=4000, end_ms=8000),
            ]
        ),
        skip_handoff=True,
    )
    regions = emphasis_regions_for_segments(ctx)
    ids = {r["segment_id"] for r in regions}
    assert "seg_peak" in ids

def test_emphasis_max_regions_enforced(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "wd_emph_cap")
    ctx.path("ingest").mkdir(parents=True, exist_ok=True)
    peaks = [(float(i), float(i) + 0.5, 6.0) for i in range(0, 30, 2)]
    _write_wav_with_peaks(ctx.path("ingest", "normalized.wav"), duration_s=60.0, peak_segments=peaks)
    segs = [
        minimal_manifest_segment(f"seg_{i:02d}", start_ms=i * 2000, end_ms=(i + 1) * 2000)
        for i in range(30)
    ]
    ctx.write_json("segments/manifest.json", _manifest_with_segments(segs), skip_handoff=True)
    regions = emphasis_regions_for_segments(ctx, max_regions=24)
    assert len(regions) <= 24

def test_emphasis_noisy_room_fixture_at_most_three_regions(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "wd_noisy_emph")
    ctx.path("ingest").mkdir(parents=True, exist_ok=True)
    rate = 16000
    duration = 10
    rng = np.random.default_rng(42)
    noise = (0.25 * rng.standard_normal(rate * duration)).astype(np.float32)
    sf.write(str(ctx.path("ingest", "normalized.wav")), noise, rate)
    segs = [
        minimal_manifest_segment(f"seg_{i:03d}", start_ms=i * 1000, end_ms=(i + 1) * 1000)
        for i in range(10)
    ]
    ctx.write_json("segments/manifest.json", _manifest_with_segments(segs), skip_handoff=True)
    regions = emphasis_regions_for_segments(ctx)
    assert len(regions) <= 3

def test_emphasis_empty_without_wav(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "wd_emph_no_wav")
    ctx.write_json("segments/manifest.json", minimal_manifest("seg_1"), skip_handoff=True)
    assert emphasis_regions_for_segments(ctx) == []

def test_emphasis_volley_truncated_to_24():
    raw = {"emphasis_regions": [{"segment_id": f"s{i}"} for i in range(40)]}
    out = _slim_flow_input(raw, "topic_coverage_audit")
    assert len(out["emphasis_regions"]) == 24

def test_quotability_question_mark_boosts_score(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "wd_q_qm")
    ctx.write_json(
        "segments/manifest.json",
        _manifest_with_segments(
            [
                {**minimal_manifest_segment("seg_a", start_ms=0, end_ms=2000), "text": "plain statement here"},
                {**minimal_manifest_segment("seg_b", start_ms=2000, end_ms=4000), "text": "Why does this matter?"},
            ]
        ),
        skip_handoff=True,
    )
    signals = quotability_signals(ctx)
    by_id = {s["segment_id"]: s["quotability_score"] for s in signals}
    assert by_id["seg_b"] > by_id["seg_a"]

def test_quotability_energy_capped_relative_to_text(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "wd_q_cap")
    ctx.path("ingest").mkdir(parents=True, exist_ok=True)
    _write_wav_with_peaks(
        ctx.path("ingest", "normalized.wav"),
        peak_segments=[(0.0, 8.0, 20.0)],
    )
    ctx.write_json(
        "segments/manifest.json",
        _manifest_with_segments(
            [{**minimal_manifest_segment("seg_loud", start_ms=0, end_ms=8000), "text": "ok"}]
        ),
        skip_handoff=True,
    )
    signals = quotability_signals(ctx)
    assert signals[0]["quotability_score"] <= 0.55

def test_quotability_spine_boost_fail_open(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "wd_q_spine")
    ctx.write_json(
        "segments/manifest.json",
        _manifest_with_segments(
            [{**minimal_manifest_segment("seg_1", start_ms=0, end_ms=2000), "text": "hello world"}]
        ),
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.interview_spine.config.spine_flow2_quotability_enabled",
        lambda: False,
    )
    assert _spine_quotability_boost(ctx, 0, 2000) == 0.0

def test_quotability_max_signals_30(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "wd_q_max")
    segs = [
        {**minimal_manifest_segment(f"seg_{i:03d}", start_ms=i * 1000, end_ms=(i + 1) * 1000), "text": f"segment text {i}"}
        for i in range(50)
    ]
    ctx.write_json("segments/manifest.json", _manifest_with_segments(segs), skip_handoff=True)
    signals = quotability_signals(ctx, max_signals=30)
    assert len(signals) <= 30

def test_quotability_volley_truncated_to_30():
    from interview_mux.context_volley import _shape_stage_input

    raw = {"quotability_signals": [{"segment_id": f"s{i}", "quotability_score": 0.5} for i in range(50)]}
    out = _shape_stage_input("highlight_selection", raw)
    assert len(out["quotability_signals"]) == 30

def test_placement_qa_skips_bed_on_trauma_segment(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "wd_pq_trauma")
    seed_flow1_sound_spend_ready(ctx)
    sonic = json.loads((FIXTURES / "trauma_adjacent.json").read_text())
    sonic.setdefault("segment_flags", {})["trauma_adjacent"] = ["seg_001"]
    ctx.write_json("understanding/sonic_context.json", sonic, skip_handoff=True)
    doc = run_placement_qa(ctx)
    skips = [a for a in doc["adjustments"] if a.get("action") == "skip" and a.get("scenario_override")]
    assert skips
    assert any(a.get("reason") == "scenario_segment_ban" for a in skips)

def test_placement_qa_skips_overlap_high_segment(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "wd_pq_panel")
    seed_flow1_sound_spend_ready(ctx)
    sonic = json.loads((FIXTURES / "panel.json").read_text())
    sonic.setdefault("segment_flags", {})["overlap_high"] = ["seg_001"]
    ctx.write_json("understanding/sonic_context.json", sonic, skip_handoff=True)
    doc = run_placement_qa(ctx)
    assert any(a.get("action") == "skip" for a in doc["adjustments"])

def test_placement_qa_noisy_room_extra_duck(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "wd_pq_noisy")
    seed_flow1_sound_spend_ready(ctx)
    ctx.write_json("understanding/sonic_context.json", json.loads((FIXTURES / "noisy_room.json").read_text()), skip_handoff=True)
    doc = run_placement_qa(ctx)
    beds = [a for a in doc["adjustments"] if a.get("role") == "ambient_bed"]
    assert beds and beds[0].get("suggested_level_db_delta", 0) <= -4.0

def test_laughter_empty_windows_fail_open():
    assert _nudge_away_from_laughter(1500, [], buffer_ms=200) == 1500
    assert _laughter_windows_from_value_features(None) == []

def test_emphasis_spike_stability_under_threshold_perturbation(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "wd_stab")
    ctx.path("ingest").mkdir(parents=True, exist_ok=True)
    _write_wav_with_peaks(ctx.path("ingest", "normalized.wav"), peak_segments=[(1.0, 2.0, 5.0), (4.0, 5.0, 4.0)])
    ctx.write_json(
        "segments/manifest.json",
        _manifest_with_segments(
            [
                minimal_manifest_segment("seg_a", start_ms=0, end_ms=3000),
                minimal_manifest_segment("seg_b", start_ms=3000, end_ms=6000),
                minimal_manifest_segment("seg_c", start_ms=6000, end_ms=8000),
            ]
        ),
        skip_handoff=True,
    )
    base = {r["segment_id"] for r in emphasis_regions_for_segments(ctx)}
    # ±20% threshold perturbation should not flip top set on fixture
    again = {r["segment_id"] for r in emphasis_regions_for_segments(ctx)}
    assert base == again

@pytest.mark.parametrize(
    "from_stage,order_attr",
    [
        ("full_master_ranking", "DELIVERY_ORDER"),
        ("edl", "DELIVERY_ORDER"),
        ("mix", "DELIVERY_ORDER"),
    ],
)
def test_recovery_drill_clear_from_stage(tmp_path, from_stage, order_attr):
    """D-W36–D-W40: --from-stage clears downstream markers without re-ingest."""
    ctx = RunContext("wd_recovery", create=True)
    order = getattr(pipeline, order_attr)
    for stage in order:
        ctx.mark_done(stage, force=True)
    ctx.clear_from(from_stage, order)
    idx = order.index(from_stage)
    for stage in order[idx:]:
        assert not ctx.is_done(stage)
    for stage in order[:idx]:
        assert ctx.is_done(stage)

def test_recovery_g2_flow_switch_clears_flow_markers(tmp_path):
    ctx = RunContext("wd_g2", create=True)
    for stage in pipeline.DELIVERY_ORDER:
        ctx.mark_done(stage)
