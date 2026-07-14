"""Sanity: pipeline stages must read prior-stage artifacts via read_path, not staging roots."""

from __future__ import annotations

import math
import wave
from pathlib import Path

import pytest

from interview_mux.interview_spine.lineage import build_derived_from
from interview_mux.pipeline import ANALYSIS_ORDER, DELIVERY_ORDER
from interview_mux.run_context import RunContext
from interview_mux.stage_enrichment import emphasis_regions_for_segments
from interview_mux.stages.ingest import _ingest_source
from interview_mux.stages.interview_spine_stage import run_interview_spine_build
from interview_mux.value_analysis.features_audio import extract_audio_features
from interview_mux.write_staging import enter_stage_staging, exit_stage_staging

from test_write_staging import _ctx


def _write_tone_wav(path: Path, *, duration_sec: float = 1.0, rate: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(rate * duration_sec)
    amp = 8000
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = bytearray()
        for i in range(n):
            sample = int(amp * math.sin(2.0 * math.pi * 220.0 * (i / rate)))
            frames += int(sample).to_bytes(2, byteorder="little", signed=True)
        wf.writeframes(bytes(frames))


def _minimal_transcript() -> dict:
    return {
        "text": "hello world",
        "words": [
            {"text": "hello", "start_ms": 0, "end_ms": 400, "speaker_id": "spk_0"},
            {"text": "world", "start_ms": 450, "end_ms": 900, "speaker_id": "spk_0"},
        ],
        "segments": [{"speaker_label": "spk_0", "start_time": "0.0", "end_time": "1.0"}],
    }


def _write_minimal_sap(ctx: RunContext) -> None:
    import json

    path = ctx.final_path("understanding", "source_acoustic_profile.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pacing": {"pace_class": "conversational", "global_wpm": 120},
            }
        ),
        encoding="utf-8",
    )


def _minimal_sap() -> dict:
    return {
        "schema_version": 1,
        "pacing": {"pace_class": "conversational", "global_wpm": 120},
    }


@pytest.mark.parametrize(
    ("stage_id", "artifact_rel"),
    [
        ("transcribe", "ingest/normalized.wav"),
        ("transcript_review_build", "ingest/normalized.wav"),
        ("transcript_review_build", "transcript/full.json"),
        ("disfluency_extract", "ingest/normalized.wav"),
        ("disfluency_extract", "transcript/full.json"),
        ("source_acoustic_profile", "ingest/normalized.wav"),
        ("interview_spine_build", "ingest/normalized.wav"),
        ("content_context", "ingest/normalized.wav"),
        ("assembly_preview", "ingest/normalized.wav"),
        ("mix", "ingest/normalized.wav"),
        ("master_finalize", "master/assembly.wav"),
    ],
)
def test_read_path_finds_final_artifact_during_stage_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage_id: str,
    artifact_rel: str,
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    dest = ctx.final_path(*artifact_rel.split("/"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    if artifact_rel.endswith(".wav"):
        _write_tone_wav(dest)
    else:
        dest.write_text("{}", encoding="utf-8")

    enter_stage_staging(stage_id)
    try:
        assert not ctx.path(*artifact_rel.split("/")).is_file()
        assert ctx.read_path(*artifact_rel.split("/")).is_file()
        assert ctx.artifact_exists(artifact_rel)
    finally:
        exit_stage_staging()


def test_ingest_reads_approved_preclean_during_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    preclean = ctx.final_path("preclean", "isolated.wav")
    _write_tone_wav(preclean)
    enter_stage_staging("ingest")
    try:
        assert not ctx.path("preclean", "isolated.wav").is_file()
        src, isolated = _ingest_source(ctx)
        assert isolated == preclean
        assert src == preclean
    finally:
        exit_stage_staging()


def test_interview_spine_build_reads_prior_stage_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    _write_tone_wav(ctx.final_path("ingest", "normalized.wav"))
    ctx.write_json("transcript/full.json", _minimal_transcript(), skip_handoff=True)
    _write_minimal_sap(ctx)
    monkeypatch.setattr(
        "interview_mux.interview_spine.config.spine_enabled",
        lambda cfg=None: True,
    )
    monkeypatch.setattr(
        "interview_mux.interview_spine.config.spine_cfg",
        lambda cfg=None: {
            "enabled": True,
            "clap_enabled": False,
            "prosody_enabled": False,
            "window_sec_default": 10,
            "hop_sec": 5,
            "boundary_fusion_min_sources": 1,
        },
    )
    monkeypatch.setattr(
        "interview_mux.stages.interview_spine_stage.build_clap_index",
        lambda *args, **kwargs: (False, None, None),
    )
    enter_stage_staging("interview_spine_build")
    try:
        assert not ctx.path("ingest", "normalized.wav").is_file()
        run_interview_spine_build(ctx)
    finally:
        exit_stage_staging()
    assert ctx.artifact_exists("understanding/interview_spine.json")


def test_lineage_build_derived_from_reads_prior_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    _write_tone_wav(ctx.final_path("ingest", "normalized.wav"))
    ctx.write_json("transcript/full.json", _minimal_transcript(), skip_handoff=True)
    _write_minimal_sap(ctx)
    enter_stage_staging("interview_spine_build")
    try:
        derived = build_derived_from(ctx)
    finally:
        exit_stage_staging()
    assert derived["normalized_wav_sha256"]
    assert derived["transcript_sha256"]
    assert derived["source_acoustic_profile_sha256"]


def test_stage_enrichment_reads_normalized_during_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    _write_tone_wav(ctx.final_path("ingest", "normalized.wav"), duration_sec=2.0)
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "one two",
            "words": [
                {"text": "one", "start_ms": 0, "end_ms": 500, "speaker_id": "spk_0"},
                {"text": "two", "start_ms": 600, "end_ms": 1100, "speaker_id": "spk_0"},
            ],
            "segments": [
                {
                    "segment_id": "seg_1",
                    "start_ms": 0,
                    "end_ms": 1200,
                    "speaker_label": "spk_0",
                }
            ],
        },
        skip_handoff=True,
    )
    enter_stage_staging("content_context")
    try:
        regions = emphasis_regions_for_segments(ctx)
    finally:
        exit_stage_staging()
    assert isinstance(regions, list)


def test_value_analysis_audio_reads_normalized_during_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    _write_tone_wav(ctx.final_path("ingest", "normalized.wav"))
    monkeypatch.setattr(
        "interview_mux.value_analysis.features_audio.require_value_analysis_flag",
        lambda cfg, flag: None,
    )
    enter_stage_staging("content_context")
    try:
        profile = extract_audio_features(ctx)
    finally:
        exit_stage_staging()
    assert profile["duration_sec"] > 0


def test_mastering_reads_assembly_during_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    assembly = ctx.final_path("master", "assembly.wav")
    _write_tone_wav(assembly)
    enter_stage_staging("master_finalize")
    try:
        assert not ctx.path("master", "assembly.wav").is_file()
        assert ctx.read_path("master", "assembly.wav").is_file()
    finally:
        exit_stage_staging()


def test_all_registered_stages_have_read_path_coverage() -> None:
    """Document stages covered by parametrized read-path checks."""
    covered = {
        "ingest",
        "transcribe",
        "transcript_review_build",
        "disfluency_extract",
        "source_acoustic_profile",
        "interview_spine_build",
        "content_context",
        "assembly_preview",
        "mix",
        "master_finalize",
    }
    analysis_with_inputs = {
        s
        for s in ANALYSIS_ORDER
        if s
        not in {
            "audio_preclean",
            "speaker_roles",
            "boundary_detection",
            "segment_classification",
            "content_brief_reanchor",
            "sonic_context_build",
            "source_topology_build",
            "sound_design_palettes",
            "missing_framing",
            "optimal_questions",
            "delivery_brief_build",
            "soundscape_policy_build",
            "episode_structure_compose",
        }
    }
    flow_with_inputs = {
        s
        for s in DELIVERY_ORDER
        if s
        not in {
            "topic_coverage_audit",
            "narrative_arc_plan",
            "full_master_ranking",
            "transitions",
            "sound_design_plan",
            "sound_design_vo_finalize",
            "edl_narrative_audit",
            "edl",
            "sfx_prompt_craft",
            "mmaudio_sfx",
        }
    }
    assert analysis_with_inputs <= covered
    assert {"assembly_preview", "mix", "master_finalize"} <= covered
    assert flow_with_inputs <= covered | {"assembly_preview", "mix", "master_finalize"}
