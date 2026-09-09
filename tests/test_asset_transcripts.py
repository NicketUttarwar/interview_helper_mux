"""Sidecar transcripts + Apple master VTT assemble."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.asset_transcripts import (
    assemble_master_cues,
    cues_to_vtt,
    load_sidecar,
    run_master_transcript_build,
    sidecar_rel,
    slice_words,
    sync_speech_sidecars,
    vtt_timestamp,
    write_speech_sidecar,
    write_vo_sidecar,
)
from interview_mux.run_context import RunContext
from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setattr(
        RunContext,
        "_executions_root",
        staticmethod(lambda cfg: tmp_path),
    )
    return RunContext("exec_901_aaaaaaaaaaaa_20260101T000901Z", create=True)


def _seg(segment_id: str, start_ms: int, end_ms: int, **extra: object) -> dict:
    row = {
        "segment_id": segment_id,
        "type": "interviewee_answer",
        "speaker_id": "spk_0",
        "speaker_role": "interviewee",
        "topic_tags": ["test"],
        "start_ms": start_ms,
        "end_ms": end_ms,
    }
    row.update(extra)
    return row


def test_slice_words_by_window():
    words = [
        {"text": "Hello", "start_ms": 0, "end_ms": 400, "speaker_id": "spk_0"},
        {"text": "there.", "start_ms": 400, "end_ms": 900, "speaker_id": "spk_0"},
        {"text": "Later", "start_ms": 5000, "end_ms": 5400, "speaker_id": "spk_1"},
    ]
    sliced = slice_words(words, 0, 1000)
    assert [w["text"] for w in sliced] == ["Hello", "there."]


def test_speech_sidecar_from_full_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.write_json(
        "transcript/full.json",
        {
            "text": "Hello there world",
            "words": [
                {"text": "Hello", "start_ms": 0, "end_ms": 300, "speaker_id": "spk_0"},
                {"text": "there", "start_ms": 300, "end_ms": 600, "speaker_id": "spk_0"},
                {"text": "world", "start_ms": 2000, "end_ms": 2400, "speaker_id": "spk_1"},
            ],
        },
    )
    ctx.write_json(
        "understanding/speakers.json",
        {"speakers": [{"speaker_id": "spk_0", "role": "interviewee", "label": "Ada", "confidence": 0.9}]},
    )
    doc = write_speech_sidecar(ctx, segment_id="seg_001", start_ms=0, end_ms=1000, speaker_id="spk_0")
    assert doc["kind"] == "speech"
    assert doc["timebase"] == "source"
    assert doc["speaker_name"] == "Ada"
    assert "Hello" in doc["text"]
    assert "world" not in doc["text"]
    loaded = load_sidecar(ctx, "speech", "seg_001")
    assert loaded is not None
    assert loaded["asset_id"] == "seg_001"


def test_vo_sidecar_script_covers_duration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _ctx(tmp_path, monkeypatch)
    doc = write_vo_sidecar(
        ctx,
        line_id="line_001",
        text="Welcome back.",
        duration_ms=1800,
        speaker_id="spk_host",
    )
    assert doc["kind"] == "vo_pickup"
    assert doc["timebase"] == "asset"
    assert doc["start_ms"] == 0
    assert doc["end_ms"] == 1800
    assert doc["words"][0]["text"] == "Welcome back."


def test_fuse_prunes_absorbed_speech_sidecars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                {"text": "One", "start_ms": 0, "end_ms": 200, "speaker_id": "spk_0"},
                {"text": "two", "start_ms": 200, "end_ms": 400, "speaker_id": "spk_0"},
                {"text": "three", "start_ms": 400, "end_ms": 700, "speaker_id": "spk_0"},
            ]
        },
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                _seg("seg_001", 0, 400),
                _seg("seg_002", 400, 700),
            ]
        },
    )
    sync_speech_sidecars(ctx)
    assert load_sidecar(ctx, "speech", "seg_001") is not None
    assert load_sidecar(ctx, "speech", "seg_002") is not None

    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                _seg("seg_001", 0, 700, fused_from=["seg_001", "seg_002"]),
            ]
        },
    )
    result = sync_speech_sidecars(ctx)
    assert "seg_001" in result["live"]
    assert "seg_002" not in result["live"]
    survivor = load_sidecar(ctx, "speech", "seg_001")
    assert survivor is not None
    assert survivor["end_ms"] == 700
    assert "three" in survivor["text"]
    assert load_sidecar(ctx, "speech", "seg_002") is None
    assert not ctx.path(sidecar_rel("speech", "seg_002")).is_file()


def test_complete_thought_neighbors_keep_two_sidecars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                {"text": "Done.", "start_ms": 0, "end_ms": 400, "speaker_id": "spk_0"},
                {"text": "Next.", "start_ms": 800, "end_ms": 1100, "speaker_id": "spk_0"},
            ]
        },
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                _seg("seg_001", 0, 400),
                _seg("seg_002", 800, 1100),
            ]
        },
    )
    sync_speech_sidecars(ctx)
    assert load_sidecar(ctx, "speech", "seg_001")["text"].startswith("Done")
    assert load_sidecar(ctx, "speech", "seg_002")["text"].startswith("Next")


def test_vtt_timestamp_and_speaker_tags():
    assert vtt_timestamp(0) == "00:00:00.000"
    assert vtt_timestamp(125_500) == "00:02:05.500"
    vtt = cues_to_vtt(
        [
            {
                "start_ms": 0,
                "end_ms": 1200,
                "speaker_name": "Ada",
                "text": "Hello there.",
            },
            {
                "start_ms": 1300,
                "end_ms": 2500,
                "speaker_name": "Ada",
                "text": "Still me.",
            },
            {
                "start_ms": 2600,
                "end_ms": 4000,
                "speaker_name": "Host",
                "text": "Welcome back.",
            },
        ]
    )
    assert vtt.startswith("WEBVTT")
    assert "<v Ada>Hello there." in vtt
    assert "Still me." in vtt
    assert "<v Host>Welcome back." in vtt


def test_master_assemble_remaps_edl_and_repairs_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.write_json(
        "transcript/full.json",
        {
            "words": [
                {"text": "Native", "start_ms": 1000, "end_ms": 1600, "speaker_id": "spk_0"},
                {"text": "beat.", "start_ms": 1600, "end_ms": 2000, "speaker_id": "spk_0"},
            ]
        },
    )
    ctx.write_json(
        "understanding/speakers.json",
        {"speakers": [{"speaker_id": "spk_0", "role": "interviewee", "label": "Ada", "confidence": 0.9}]},
    )
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_001"],
            "timeline_duration_ms": 4500,
            "clips": [
                {
                    "type": "vo_pickup",
                    "line_id": "line_open",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "timeline_start_ms": 0,
                    "duration_ms": 1000,
                    "text": "Welcome in.",
                },
                {
                    "type": "speech",
                    "segment_id": "seg_001",
                    "source_start_ms": 1000,
                    "source_end_ms": 2000,
                    "timeline_start_ms": 1000,
                    "duration_ms": 1000,
                },
            ],
        },
    )
    ctx.path("master/master.wav").parent.mkdir(parents=True, exist_ok=True)
    ctx.path("master/master.wav").write_bytes(b"RIFF" + b"\x00" * 64)
    write_vo_sidecar(ctx, line_id="line_open", text="Welcome in.", duration_ms=1000, speaker_id="spk_host")

    cues = assemble_master_cues(ctx)
    kinds = [c["kind"] for c in cues]
    assert "vo_pickup" in kinds
    assert "speech" in kinds
    speech = next(c for c in cues if c["kind"] == "speech")
    assert speech["start_ms"] == 1000
    assert "Native" in speech["text"]

    run_master_transcript_build(ctx)
    vtt = ctx.read_path("master/transcript.vtt").read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT")
    assert "Welcome in." in vtt
    assert "Native" in vtt
    assert ctx.artifact_exists("master/transcript.json")
    assert ctx.artifact_exists("master/transcript.txt")


def test_snipped_timeline_remap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.write_json(
        "transcript/full.json",
        {"words": [{"text": "Hello", "start_ms": 5000, "end_ms": 5600, "speaker_id": "spk_0"}]},
    )
    write_speech_sidecar(ctx, segment_id="seg_009", start_ms=5000, end_ms=5600, speaker_id="spk_0")
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_009"],
            "timeline_duration_ms": 600,
            "clips": [
                {
                    "type": "speech",
                    "segment_id": "seg_009",
                    "source_start_ms": 5000,
                    "source_end_ms": 5600,
                    "timeline_start_ms": 250,
                    "duration_ms": 600,
                }
            ],
        },
    )
    cues = assemble_master_cues(ctx)
    assert cues[0]["start_ms"] == 250
    assert cues[0]["end_ms"] == 850


def test_delivery_order_places_transcript_after_finalize():
    assert "master_transcript_build" in DELIVERY_ORDER
    assert DELIVERY_ORDER.index("master_finalize") < DELIVERY_ORDER.index("master_transcript_build")
    assert DELIVERY_ORDER.index("master_transcript_build") < DELIVERY_ORDER.index("episode_meta_build")
    assert len(ANALYSIS_ORDER) + len(DELIVERY_ORDER) == 72
