"""OpenAI gateway truncation escalation tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from interview_mux.stages import llm_runner


def test_run_prompt_envelope_bumps_tier_on_truncated_volley():
    messages = [{"role": "user", "content": "evidence\n…[stage data truncated]"}]

    with patch.object(llm_runner, "_execute_openai_envelope_call") as mock_exec:
        mock_exec.return_value = {"status": "complete", "artifacts": {}, "_llm_meta": {}}
        llm_runner.run_prompt_envelope(
            "speaker_roles",
            "understanding/speaker-roles.system.txt",
            messages=messages,
            task_kind="primary",
        )
        assert mock_exec.called
        kwargs = mock_exec.call_args.kwargs
        assert kwargs.get("bump_tier") is True
        esc = kwargs.get("esc_meta")
        assert esc is not None
        assert esc.final_flags == ["max_stage_data_chars"]


def test_run_prompt_envelope_attaches_truncation_meta():
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
