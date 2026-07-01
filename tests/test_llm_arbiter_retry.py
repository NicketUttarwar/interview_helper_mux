"""Tests for arbiter parse auto-retry."""

from __future__ import annotations

from unittest.mock import patch

from interview_mux.llm_arbiter import run_llm_arbiter, sanitize_arbiter_payload


def test_arbiter_parse_retries_once():
    calls = {"n": 0}

    def fake_run(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("bad json")
        return {"artifacts": {"verdict": "accept", "confidence": 0.9, "gaps": []}}

    with patch("interview_mux.llm_arbiter.run_prompt_envelope", side_effect=fake_run):
        result = run_llm_arbiter(
            stage_key="speaker_roles",
            attempt_number=1,
            envelope={"status": "complete", "artifacts": {"speakers": []}},
            schema_errors=[],
            context_chars=100,
            truncation_flags=[],
            stage_expectations={},
        )
    assert calls["n"] == 2
    assert result["verdict"] == "accept"


def test_sanitize_arbiter_payload_drops_empty_investigation():
    cleaned = sanitize_arbiter_payload(
        {
            "verdict": "accept",
            "confidence": 0.9,
            "gaps": [],
            "shard_plan": [],
            "suggested_investigation": {"kind": None, "question": None, "blocking": False},
            "reasoning_summary": "ok",
        }
    )
    assert cleaned["suggested_investigation"] is None
