"""Tests for truncation_policy."""

from __future__ import annotations

from interview_mux.truncation_policy import (
    MARKER_FLAG_MAP,
    build_framer_digest,
    scan_llm_input,
    scan_text,
    validate_framer_turns,
)


def test_scan_text_detects_all_markers():
    for marker, flag in MARKER_FLAG_MAP.items():
        scan = scan_text(f"prefix {marker} suffix")
        assert scan.truncated
        assert flag in scan.flags


def test_build_framer_digest_speaker_roles_limit():
    big = {"transcript_samples": "x" * 30000}
    digest, truncated = build_framer_digest(big, "speaker_roles")
    assert truncated
    assert "…[digest truncated]" in digest
    assert len(digest) > 24000


def test_validate_framer_turns_rejects_uncertainty():
    stage_input = {
        "speakers": {"speakers": [{"speaker_id": "spk_0"}]},
        "transcript_samples": [{"speaker_id": "spk_0", "text": "hello"}],
    }
    turns = [{"role": "assistant", "content": "The speaker role is unclear in the transcript."}]
    kept, rejected = validate_framer_turns(turns, stage_input, stage_key="speaker_roles")
    assert not kept
    assert rejected


def test_scan_llm_input_messages():
    messages = [{"role": "user", "content": "data\n…[stage data truncated]"}]
    scan = scan_llm_input(messages=messages)
    assert "max_stage_data_chars" in scan.flags
