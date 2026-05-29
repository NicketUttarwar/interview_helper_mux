from __future__ import annotations

import json

from interview_mux.run_context import RunContext
from interview_mux.session_log import read_log
from interview_mux.value_analysis.extract import (
    maybe_auto_extract_value_features,
    profiles_for_flags,
)
from interview_mux.value_analysis.features_transcript import VALUE_FEATURES_PATH
from run_fixtures import isolated_run_ctx


def _minimal_transcript() -> dict:
    return {
        "text": "hello world",
        "words": [
            {"text": "hello", "start_ms": 0, "end_ms": 200},
            {"text": "world", "start_ms": 400, "end_ms": 600},
        ],
        "segments": [{"speaker_label": "spk_0", "start_time": "0.0", "end_time": "0.6", "text": "hello world"}],
    }


def test_maybe_auto_extract_skipped_when_flag_off(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "run_va_off")
    ctx.write_json("transcript/full.json", _minimal_transcript())

    cfg = {
        "value_analysis": {
            "enabled": True,
            "transcript_features": True,
            "auto_extract_after_content_context": False,
        }
    }
    assert maybe_auto_extract_value_features(ctx, cfg=cfg) is None
    assert not ctx.artifact_exists(VALUE_FEATURES_PATH)


def test_maybe_auto_extract_writes_transcript_profile(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "run_va_on")
    ctx.write_json("transcript/full.json", _minimal_transcript())

    cfg = {
        "value_analysis": {
            "enabled": True,
            "transcript_features": True,
            "audio_features": False,
            "auto_extract_after_content_context": True,
        }
    }
    written = maybe_auto_extract_value_features(ctx, cfg=cfg)
    assert written == ["transcript"]
    out = ctx.read_json(VALUE_FEATURES_PATH)
    assert out["profiles"]["transcript"]["profile"] == "transcript"

    entries = read_log(ctx.run_dir)
    extracted = [e for e in entries if e.get("message") == "value_features_extracted"]
    assert len(extracted) == 1
    detail = json.loads(extracted[0]["detail"])
    assert detail["profiles"] == ["transcript"]


def test_profiles_for_flags_requires_master(tmp_path):
    cfg = {
        "value_analysis": {
            "enabled": False,
            "transcript_features": True,
            "audio_features": True,
        }
    }
    assert profiles_for_flags(cfg) == []
