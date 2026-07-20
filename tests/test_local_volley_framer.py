"""Tests for local volley framer (LX-01) fail-open behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from interview_mux.local_volley_framer import LocalFramingResult, parse_framer_response, prepare_volley_for_llm


def test_parse_framer_response_caps_turns():
    raw = """{"escalate": true, "confidence": 0.9, "reason": "ok", "volley_turns": [
        {"role": "assistant", "content": "a"},
        {"role": "user", "content": "b"},
        {"role": "assistant", "content": "c"}
    ]}"""
    parsed = parse_framer_response(raw, max_turns=2)
    assert len(parsed["volley_turns"]) == 2


def test_prepare_volley_disabled_returns_empty():
    ctx = MagicMock()
    with patch("interview_mux.local_volley_framer.local_llm_enabled", return_value=False):
        result = prepare_volley_for_llm(ctx, "speaker_roles", {"x": 1})
    assert isinstance(result, LocalFramingResult)
    assert not result.used_local
    assert result.fallback == "disabled"


def test_prepare_volley_not_allowlisted():
    ctx = MagicMock()
    with patch("interview_mux.local_volley_framer.local_llm_enabled", return_value=True):
        with patch("interview_mux.local_volley_framer.stage_on_quality_allowlist", return_value=False):
            result = prepare_volley_for_llm(ctx, "episode_structure_compose", {"x": 1})
    assert result.fallback == "not_allowlisted"
