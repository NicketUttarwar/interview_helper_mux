"""OpenAI gateway truncation escalation tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from interview_mux.stages import llm_runner
from interview_mux.truncation_policy import TruncationEscalationRequired


def test_run_prompt_envelope_blocks_truncated_primary_without_calling_model():
    messages = [{"role": "user", "content": "evidence\n…[stage data truncated]"}]

    with patch.object(llm_runner, "_execute_openai_envelope_call") as mock_exec:
        with pytest.raises(TruncationEscalationRequired) as exc_info:
            llm_runner.run_prompt_envelope(
                "speaker_roles",
                "understanding/speaker-roles.system.txt",
                messages=messages,
                task_kind="primary",
            )
        assert mock_exec.called is False
        assert "max_stage_data_chars" in exc_info.value.flags


def test_run_prompt_envelope_returns_blocked_for_truncated_shard():
    messages = [{"role": "user", "content": "evidence\n…[digest truncated]"}]

    with patch.object(llm_runner, "_execute_openai_envelope_call") as mock_exec:
        envelope = llm_runner.run_prompt_envelope(
            "content_context",
            "understanding/content-context.system.txt",
            messages=messages,
            task_kind="shard",
        )
        assert mock_exec.called is False
        assert envelope.get("status") == "blocked"
        needs = envelope.get("needs") or []
        assert needs and needs[0].get("type") == "decompose"
        assert "framer_digest_truncated" in (
            (envelope.get("_llm_meta") or {}).get("truncation_escalation") or {}
        ).get("final_flags", [])


def test_run_prompt_envelope_attaches_truncation_meta_when_clean():
    with patch.object(llm_runner, "_execute_openai_envelope_call") as mock_exec:
        mock_exec.return_value = {
            "status": "complete",
            "artifacts": {},
            "_llm_meta": {"truncation_escalation": {"rounds": 0, "provider": "openai"}},
        }
        llm_runner.run_prompt_envelope(
            "content_context",
            "understanding/content-context.system.txt",
            user_content='{"transcript":"hi"}',
            task_kind="primary",
        )
        esc = mock_exec.call_args.kwargs.get("esc_meta")
        assert esc is not None
        assert esc.provider == "openai"
        assert mock_exec.called is True
