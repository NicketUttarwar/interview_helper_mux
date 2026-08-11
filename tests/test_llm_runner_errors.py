"""LLM runner logs OpenAI failures to gui_log.jsonl."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from interview_mux.run_context import RunContext
from interview_mux.session_log import read_log
from interview_mux.stages import llm_runner


def test_openai_failure_logs_to_gui_log(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_llm_err", create=True)
    ctx.write_json("run_meta.json", {"execution_id": ctx.run_id}, skip_handoff=True)

    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("rate limit")

    with pytest.raises(RuntimeError, match="rate limit"):
        with patch.object(llm_runner, "OpenAI", return_value=client):
            with patch.object(llm_runner, "require_secret", return_value="sk-test"):
                with patch.object(llm_runner, "load_system_prompt_for_stage", return_value="system"):
                    llm_runner.run_prompt_envelope(
                        "missing_framing",
                        "interviewer-gap/missing-framing.system.txt",
                        user_content='{"task":"test","excerpts":["tape from the interview"]}',
                        task_kind="primary",
                        ctx=ctx,
                    )

    entries = read_log(ctx.run_dir, tail=10)
    fail = next(
        e for e in entries if "OpenAI chat.completions failed" in e.get("message", "")
    )
    assert fail["level"] == "error"
    detail = json.loads(fail["detail"])
    assert detail["error_class"] == "RuntimeError"
    assert detail["provider"] == "OpenAI"
