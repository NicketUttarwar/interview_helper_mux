"""Wave 0 resilience harness — fail-open paths and observability contracts."""

from __future__ import annotations

import json
from unittest.mock import patch

from interview_mux.coherence.analyze import build_coherence_report, maybe_run_coherence_analysis
from interview_mux.session_log import read_log
from interview_mux.sonic_context import build_sonic_context
from interview_mux.stage_enrichment import (
    emphasis_regions_for_segments,
    quotability_signals,
    quality_trajectory_flags,
)
from interview_mux.stages import interview_spine_stage
from interview_mux.value_analysis.extract import (
    _spine_orchestration_investigations,
    maybe_auto_extract_value_features,
    maybe_enqueue_orchestration_investigations,
)
from run_fixtures import isolated_run_ctx, minimal_manifest, patch_merged_config, populated_analysis_state


def _minimal_spine_doc(*, boundary_events: list[dict] | None = None) -> dict:
    return {
        "schema_version": 1,
        "derived_from": {
            "normalized_wav": "ingest/normalized.wav",
            "transcript": "transcript/full.json",
            "computed_at": "2026-06-18T00:00:00Z",
            "stage": "interview_spine_build",
        },
        "encoders": {"dsp": "numpy_rms_v1", "clap": None, "ssl": None},
        "window_policy": {"window_sec": 10, "hop_sec": 5, "align_to": "words"},
        "windows": [],
        "boundary_events": boundary_events
        or [
            {"time_ms": 5000, "type": "trust_dip", "confidence": 0.9, "sources": ["dsp_rms"]},
        ],
        "retrieval": {
            "enabled": False,
            "model_id": None,
            "sidecar_path": None,
            "vector_dim": None,
            "window_count": 0,
        },
        "speaker_stats": [],
    }


def test_emphasis_regions_fail_open_without_wav(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "fo03")
    ctx.write_json("segments/manifest.json", minimal_manifest("seg_1"), skip_handoff=True)
    assert emphasis_regions_for_segments(ctx) == []


def test_quality_trajectory_flags_fail_open_without_wav(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "fo04")
    assert quality_trajectory_flags(ctx) == []


def test_quotability_signals_fail_open_without_segments(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "fo05")
    assert quotability_signals(ctx) == []


def test_value_analysis_skip_no_wav_logs_and_continues(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "fo20")
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "hello",
            "words": [{"text": "hello", "start_ms": 0, "end_ms": 200}],
        },
    )
    cfg = {
        "value_analysis": {
            "enabled": True,
            "transcript_features": True,
            "audio_features": True,
            "auto_extract_after_content_context": True,
        }
    }
    written = maybe_auto_extract_value_features(ctx, cfg=cfg)
    assert written == ["transcript"]
    entries = read_log(ctx.run_dir)
    skip = [e for e in entries if e.get("message") == "value_analysis_skip_no_wav"]
    assert len(skip) == 1
    assert skip[0]["stage"] == "content_context"
    assert skip[0]["level"] == "warning"


def test_value_analysis_disabled_returns_zero_investigations(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "fo06")
    cfg = {"value_analysis": {"enabled": False}}
    assert maybe_enqueue_orchestration_investigations(ctx, cfg=cfg) == 0


def test_trust_dip_without_low_confidence_words_no_investigation(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "fo19")
    ctx.write_json(
        "understanding/interview_spine.json",
        _minimal_spine_doc(),
        skip_handoff=True,
    )
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                {"text": "clear", "start_ms": 4800, "end_ms": 5200, "confidence": 0.99},
            ],
        },
        skip_handoff=True,
    )
    assert _spine_orchestration_investigations(ctx) == []


def test_coherence_short_run_empty_risks(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "fo07")
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                {"text": "a", "start_ms": 0, "end_ms": 1000},
                {"text": "b", "start_ms": 29 * 60 * 1000, "end_ms": 29 * 60 * 1000 + 1000},
            ],
        },
        skip_handoff=True,
    )
    patch_merged_config(
        monkeypatch,
        {
            "value_analysis": {"enabled": True, "orc03_enabled": True},
            "coherence": {"enabled": True, "min_duration_ms": 1_800_000},
        },
    )
    report = build_coherence_report(ctx, phase="post_reanchor")
    assert report["gate"]["activated"] is False
    assert report.get("risks") == []


def test_coherence_disabled_no_op(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "fo09")
    patch_merged_config(monkeypatch, {"coherence": {"enabled": False}})
    assert maybe_run_coherence_analysis(ctx, phase="post_reanchor") == 0


def test_sonic_context_sparse_manifest_defaults_one_on_one(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "fo12")
    state = populated_analysis_state(ctx.run_id)
    ctx.write_json("understanding/analysis_state.json", state, skip_handoff=True)
    doc = build_sonic_context(ctx)
    assert doc["scenario"]["atlas_bucket"] == "one_on_one"
    assert doc["version"] == 1


def test_interview_spine_disabled_marks_done_without_artifact(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "fo02")
    monkeypatch.setattr(
        "interview_mux.stages.interview_spine_stage.spine_enabled",
        lambda: False,
    )
    interview_spine_stage.run_interview_spine_build(ctx)
    assert ctx.is_done("interview_spine_build")
    assert not ctx.artifact_exists("understanding/interview_spine.json")
    entries = read_log(ctx.run_dir)
    assert any("Interview spine disabled" in e.get("message", "") for e in entries)


def test_interview_spine_clap_fail_open_logs_warning(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "fo01")
    monkeypatch.setattr(
        "interview_mux.stages.interview_spine_stage.spine_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "interview_mux.stages.interview_spine_stage.can_skip_rebuild",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.stages.interview_spine_stage.spine_cfg",
        lambda: {
            "window_sec_default": 10,
            "hop_sec": 5,
            "prosody_enabled": False,
            "clap_enabled": True,
            "clap_model_id": "laion/clap-htsat-fused",
            "clap_timeout_sec": 5,
            "boundary_fusion_min_sources": 1,
        },
    )
    monkeypatch.setattr(
        "interview_mux.stages.interview_spine_stage.build_clap_index",
        lambda *a, **k: (False, None, None),
    )
    monkeypatch.setattr(
        "interview_mux.stages.interview_spine_stage.build_windows",
        lambda words, **k: [
            {
                "window_id": "win_0001",
                "start_ms": 0,
                "end_ms": 1000,
                "text_span": "hi",
                "features": {"rms_p50": 0.1, "pause_before_ms": 0, "speaking_rate_wpm": 120},
            }
        ],
    )
    monkeypatch.setattr(
        "interview_mux.stages.interview_spine_stage.enrich_window_features",
        lambda windows, **k: windows,
    )
    monkeypatch.setattr(
        "interview_mux.stages.interview_spine_stage.build_boundary_events",
        lambda **k: [],
    )
    monkeypatch.setattr(
        "interview_mux.stages.interview_spine_stage.build_speaker_stats",
        lambda windows: [],
    )
    monkeypatch.setattr(
        "interview_mux.stages.interview_spine_stage.build_derived_from",
        lambda _ctx: {
            "normalized_wav": "ingest/normalized.wav",
            "transcript": "transcript/full.json",
            "computed_at": "2026-06-18T00:00:00Z",
            "stage": "interview_spine_build",
        },
    )

    wav = ctx.path("ingest", "normalized.wav")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"\x00" * 3200)
    ctx.write_json(
        "transcript/full.json",
        {"words": [{"text": "hi", "start_ms": 0, "end_ms": 500}]},
        skip_handoff=True,
    )
    sap_path = ctx.path("understanding", "source_acoustic_profile.json")
    sap_path.parent.mkdir(parents=True, exist_ok=True)
    sap_path.write_text(
        json.dumps({"schema_version": 1, "pacing": {"pace_class": "conversational"}}),
        encoding="utf-8",
    )

    interview_spine_stage.run_interview_spine_build(ctx)
    spine = ctx.read_json("understanding/interview_spine.json")
    assert spine["retrieval"]["enabled"] is False
    entries = read_log(ctx.run_dir)
    assert any("CLAP retrieval unavailable" in e.get("message", "") for e in entries)


def test_spine_quotability_boost_disabled(tmp_path, monkeypatch):
    from interview_mux.stage_enrichment import _spine_quotability_boost

    ctx = isolated_run_ctx(tmp_path, "fo18")
    ctx.write_json(
        "understanding/interview_spine.json",
        _minimal_spine_doc(
            boundary_events=[
                {"time_ms": 500, "type": "trust_dip", "confidence": 0.9, "sources": ["dsp_rms"]},
            ],
        ),
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.interview_spine.config.spine_flow2_quotability_enabled",
        lambda: False,
    )
    assert _spine_quotability_boost(ctx, 0, 1000) == 0.0


def test_post_stage_specialist_failure_does_not_propagate(tmp_path):
    from interview_mux.llm_specialists import maybe_run_post_stage_specialists

    ctx = isolated_run_ctx(tmp_path, "fo11")
    cfg = {"analysis": {"specialists": {"enabled": True}}}
    with patch(
        "interview_mux.llm_specialists.run_specialist",
        side_effect=RuntimeError("boom"),
    ):
        outputs = maybe_run_post_stage_specialists(
            ctx,
            "full_master_ranking",
            {"segments": {}},
            cfg=cfg,
        )
    assert outputs == []
    entries = read_log(ctx.run_dir)
    assert any("Post-stage specialist" in e.get("message", "") and "failed" in e.get("message", "") for e in entries)
