"""Local MLX gateway truncation tests."""

from __future__ import annotations

from interview_mux.local_llm_runner import generate_local_chat


def test_generate_local_chat_skips_mlx_on_truncated_framer_input():
    user = '{"stage_input_digest": "' + ("x" * 9000) + '\\n…[digest truncated]"}'
    text, meta = generate_local_chat(
        system="framer",
        user=user,
        stage_key="speaker_roles",
        task_kind="local_primary",
        cfg={"analysis": {"truncation_integrity": {"enabled": True}}},
    )
    assert meta.get("skipped_mlx") is True
    import json

    parsed = json.loads(text)
    assert parsed.get("escalate") is True
    assert parsed.get("volley_turns") == []
