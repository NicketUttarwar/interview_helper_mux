from __future__ import annotations

from unittest.mock import MagicMock, patch

from interview_mux.stages import llm_runner


def test_primary_call_uses_json_object_response_format():
    captured: dict = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        msg = MagicMock()
        msg.content = '{"status":"complete","artifacts":{}}'
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    client = MagicMock()
    client.chat.completions.create = fake_create

    with patch.object(llm_runner, "OpenAI", return_value=client):
        with patch.object(llm_runner, "require_secret", return_value="sk-test"):
            with patch.object(llm_runner, "load_system_prompt_for_stage", return_value="system"):
                llm_runner.run_prompt_envelope(
                    "missing_framing",
                    "interviewer-gap/missing-framing.system.txt",
                    user_content='{"task":"test"}',
                    task_kind="primary",
                )

    assert captured.get("response_format") == {"type": "json_object"}


def test_load_compact_examples_for_missing_framing():
    text = llm_runner.load_compact_examples("missing_framing")
    assert text is not None
    assert "missing_question" in text or "Compact examples" in text
