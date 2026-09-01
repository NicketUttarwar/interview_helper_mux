"""Tests for Local Audio Probe Platform + vernacular sanitize."""

from __future__ import annotations

from pathlib import Path

from interview_mux.audio_probe_mlx import classify_clip_mlx, prompt_text_for_probe
from interview_mux.audio_probe_orchestrator import (
    build_audio_probe_artifacts,
    empty_probe_artifacts,
)
from interview_mux.audio_probe_parse import parse_binary, parse_keywords, parse_level, parse_spans
from interview_mux.vernacular_sanitize import sanitize_manifest_with_zones
from interview_mux.v2.config import ANALYSIS_ORDER


def test_analysis_order_includes_audio_probe_stages() -> None:
    assert "audio_probe_build" in ANALYSIS_ORDER
    assert "vernacular_segment_sanitize" in ANALYSIS_ORDER
    assert ANALYSIS_ORDER.index("transcribe") < ANALYSIS_ORDER.index("audio_probe_build")
    assert ANALYSIS_ORDER.index("transcript_review_build") < ANALYSIS_ORDER.index("audio_probe_build")
    assert ANALYSIS_ORDER.index("boundary_topic_resplit") < ANALYSIS_ORDER.index(
        "vernacular_segment_sanitize"
    )


def test_parse_contracts() -> None:
    assert parse_binary("The answer is YES.")["value"] is True
    assert parse_binary("nope")["ok"] is False
    assert parse_level("LEVEL: high")["value"] == "high"
    assert parse_keywords("KEYWORDS: jugaad, namaste")["value"] == ["jugaad", "namaste"]
    spans = parse_spans("SPANS: 00:01-00:03", clip_start_ms=1000)
    assert spans["ok"]
    assert spans["value"][0]["start_ms"] == 2000


def test_build_detects_non_ascii_vernacular() -> None:
    transcript = {
        "words": [
            {"text": "Hello", "start_ms": 0, "end_ms": 400, "speaker_id": "spk_00", "confidence": 0.95},
            {"text": "नमस्ते", "start_ms": 400, "end_ms": 900, "speaker_id": "spk_00", "confidence": 0.4},
            {"text": "friends", "start_ms": 900, "end_ms": 1300, "speaker_id": "spk_00", "confidence": 0.95},
        ]
    }
    arts = build_audio_probe_artifacts(transcript)
    assert arts["golden_facts"]["run"]["has_in_flow_vernacular"] is True
    assert arts["protected_zones"]["zones"]
    assert any(
        r.get("probe_id") == "vprobe.multilingual_or_uncommon" and not r.get("skipped")
        for r in arts["probe_report"]["rows"]
    )


def test_one_off_brick_not_vernacular() -> None:
    transcript = {
        "words": [
            {"text": "This", "start_ms": 0, "end_ms": 200, "speaker_id": "spk_00", "confidence": 0.95},
            {"text": "is", "start_ms": 200, "end_ms": 300, "speaker_id": "spk_00", "confidence": 0.95},
            {"text": "just", "start_ms": 300, "end_ms": 500, "speaker_id": "spk_00", "confidence": 0.95},
            {"text": "the", "start_ms": 500, "end_ms": 700, "speaker_id": "spk_00", "confidence": 0.95},
            {"text": "same", "start_ms": 700, "end_ms": 900, "speaker_id": "spk_00", "confidence": 0.2},
            {"text": "thing", "start_ms": 900, "end_ms": 1200, "speaker_id": "spk_00", "confidence": 0.95},
            {"text": "again", "start_ms": 1200, "end_ms": 1500, "speaker_id": "spk_00", "confidence": 0.95},
        ]
    }
    arts = build_audio_probe_artifacts(transcript)
    assert arts["golden_facts"]["run"]["has_in_flow_vernacular"] is False


def test_nway_sanitize_alternation() -> None:
    manifest = {
        "segments": [
            {
                "segment_id": "seg_014",
                "start_ms": 0,
                "end_ms": 10000,
                "text": "english switch english switch english",
                "speaker_id": "spk_00",
            }
        ]
    }
    zones = {
        "zones": [
            {
                "zone_id": "pz_001",
                "start_ms": 0,
                "end_ms": 10000,
                "retention": "must_keep",
                "keywords": ["hola"],
                "spans": [
                    {"start_ms": 2000, "end_ms": 3500},
                    {"start_ms": 6000, "end_ms": 8000},
                ],
            }
        ]
    }
    result = sanitize_manifest_with_zones(manifest, zones, min_child_ms=500)
    children = result["manifest"]["segments"]
    assert len(children) >= 3
    specials = [c for c in children if (c.get("audio_tags") or {}).get("is_special")]
    assert len(specials) >= 2
    assert len(result["must_keep_segment_ids"]) >= 2
    assert result["resplit_report"]["rows"]
    pattern = result["resplit_report"]["rows"][0]["pattern"]
    assert "SW" in pattern
    assert pattern.count("SW") >= 2


def test_empty_probe_artifacts_safe() -> None:
    arts = empty_probe_artifacts(reason="unit")
    assert arts["golden_facts"]["run"]["has_in_flow_vernacular"] is False
    assert arts["protected_zones"]["zones"] == []
    assert arts["probe_report"]["empty_reason"] == "unit"


def test_prompt_text_loads() -> None:
    text = prompt_text_for_probe("vprobe.multilingual_or_uncommon")
    assert len(text) > 20


def test_classify_fail_open_without_model(tmp_path: Path, monkeypatch) -> None:
    clip = tmp_path / "clip.wav"
    clip.write_bytes(b"RIFF" + b"\x00" * 40)

    def _boom(*_a, **_k):
        from interview_mux.local_runtime import LocalRuntimeUnavailable

        raise LocalRuntimeUnavailable("speech venv missing")

    monkeypatch.setattr("interview_mux.audio_probe_mlx.run_runtime_json", _boom)
    out = classify_clip_mlx(
        probe_id="vprobe.multilingual_or_uncommon",
        clip_wav=clip,
        warmup_wav=None,
        output_contract="YES_NO",
    )
    assert out.get("ok") is False
    assert out.get("fallback") == "heuristic"


def test_answer_from_listen_detects_vernacular() -> None:
    from interview_mux.audio_probe_listen import answer_from_listen_evidence

    flow = {
        "speaker_flow_id": "sf_1",
        "speaker_id": "spk_00",
        "start_ms": 0,
        "end_ms": 2000,
        "text": "Hello friends",
        "words": [],
    }
    evidence = {
        "stt_text": "Hello नमस्ते friends",
        "words": [
            {"text": "Hello", "start_ms": 0, "end_ms": 400},
            {"text": "नमस्ते", "start_ms": 400, "end_ms": 900},
            {"text": "friends", "start_ms": 900, "end_ms": 1300},
        ],
        "model_id": "test-whisper",
    }
    ans = answer_from_listen_evidence("vprobe.multilingual_or_uncommon", evidence, flow)
    assert ans["source"] == "stt_listen"
    assert "YES" in ans["text"]
    assert ans.get("listen_fused") is True


def test_long_turn_triggers_vernacular_relisten() -> None:
    from interview_mux.audio_probe_flows import flow_signals, passes_prefilter

    flow = {
        "text": " ".join(
            [
                "the",
                "and",
                "that",
                "this",
                "with",
                "from",
                "they",
                "have",
                "been",
                "about",
                "when",
                "what",
                "their",
                "would",
                "there",
                "could",
                "other",
                "into",
                "than",
                "them",
            ]
            * 2
        ),
        "mean_confidence": 0.88,
        "duration_ms": 25_000,
        "word_count": 40,
        "words": [{"text": "the", "confidence": 0.88}] * 40,
    }
    sig = flow_signals(flow)
    ok, reason = passes_prefilter("vernacular_candidate", sig)
    assert ok is True
    assert reason == "long_turn_relisten"


def test_probe_report_tracks_answer_source() -> None:
    transcript = {
        "words": [
            {"text": "Hello", "start_ms": 0, "end_ms": 400, "speaker_id": "spk_00", "confidence": 0.95},
            {"text": "नमस्ते", "start_ms": 400, "end_ms": 900, "speaker_id": "spk_00", "confidence": 0.4},
            {"text": "friends", "start_ms": 900, "end_ms": 1300, "speaker_id": "spk_00", "confidence": 0.95},
        ]
    }
    arts = build_audio_probe_artifacts(transcript)
    rows = [r for r in arts["probe_report"]["rows"] if not r.get("skipped")]
    assert rows
    assert any(r.get("answer_source") for r in rows)
    assert "answer_stats" in (arts["golden_facts"].get("meta") or {})
