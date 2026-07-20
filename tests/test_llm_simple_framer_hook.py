"""llm_simple local framer hook assembles OpenAI messages."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from interview_mux.local_volley_framer import LocalFramingResult
from interview_mux.llm_simple import run_llm_stage_simple


def test_run_llm_stage_simple_prepends_framer_turns():
    ctx = MagicMock()
    ctx.mark_done = MagicMock()
    framing = LocalFramingResult(
        used_local=True,
        volley_turns=[
            {"role": "assistant", "content": "Prior context"},
            {"role": "user", "content": "Focus gaps"},
        ],
    )
    envelope = {
        "status": "complete",
        "artifacts": {"speaker_roles": {"speakers": []}},
    }

    with patch("interview_mux.local_volley_framer.prepare_volley_for_llm", return_value=framing):
        with patch("interview_mux.llm_simple.ensure_analysis_workspace"):
            with patch("interview_mux.llm_simple.run_prompt_envelope", return_value=envelope) as run_env:
                with patch("interview_mux.llm_simple.validate_stage_artifacts", return_value=[]):
                    run_llm_stage_simple(
                        ctx,
                        "speaker_roles",
                        "speaker-roles.system.txt",
                        lambda _ctx: {"task": "x"},
                        lambda _ctx, _a: None,
                    )

    messages = run_env.call_args.kwargs["messages"]
    assert messages[0]["role"] == "assistant"
    assert messages[-1]["role"] == "user"
    assert "task" in messages[-1]["content"]
