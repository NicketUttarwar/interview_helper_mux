from __future__ import annotations

from unittest.mock import MagicMock, patch

from interview_mux.stages import llm_runner


def _patch_cfg(monkeypatch):
    monkeypatch.setattr(
        llm_runner,
        "merged_config",
        lambda: {
            "analysis": {
                "structured_outputs": {
                    "enabled": True,
                    "strict": True,
                    "fail_on_verify_error": False,
                },
            },
        },
    )


def test_primary_call_uses_json_schema_response_format(monkeypatch):
    captured: dict = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        msg = MagicMock()
        msg.content = (
            '{"status":"complete","artifacts":{"speakers":[{"speaker_id":"spk_0",'
            '"role":"interviewer","confidence":0.9}]},"memory_updates":{},'
            '"needs":[],"follow_up_investigations":[],"confidence":0.9,'
            '"reasoning_summary":"ok"}'
        )
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    client = MagicMock()
    client.chat.completions.create = fake_create
    _patch_cfg(monkeypatch)

    with patch.object(llm_runner, "OpenAI", return_value=client):
        with patch.object(llm_runner, "require_secret", return_value="sk-test"):
            with patch.object(llm_runner, "load_system_prompt_for_stage", return_value="system"):
                llm_runner.run_prompt_envelope(
                    "speaker_roles",
                    "understanding/speaker-roles.system.txt",
                    user_content='{"task":"test"}',
                    task_kind="primary",
                )

    rf = captured.get("response_format") or {}
    assert rf.get("type") == "json_schema"
    assert rf.get("json_schema", {}).get("strict") is True


def test_primary_call_omits_temperature_for_o3(monkeypatch):
    captured: dict = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        msg = MagicMock()
        msg.content = (
            '{"status":"complete","artifacts":{"speakers":[{"speaker_id":"spk_0",'
            '"role":"interviewer","confidence":0.9}]},"memory_updates":{},'
            '"needs":[],"follow_up_investigations":[],"confidence":0.9,'
            '"reasoning_summary":"ok"}'
        )
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    client = MagicMock()
    client.chat.completions.create = fake_create
    _patch_cfg(monkeypatch)

    with patch.object(llm_runner, "OpenAI", return_value=client):
        with patch.object(llm_runner, "require_secret", return_value="sk-test"):
            with patch.object(llm_runner, "load_system_prompt_for_stage", return_value="system"):
                with patch.object(llm_runner, "resolve_model") as mock_resolve:
                    mock_resolve.return_value = MagicMock(model_id="o3", tier="flagship")
                    llm_runner.run_prompt_envelope(
                        "speaker_roles",
                        "understanding/speaker-roles.system.txt",
                        user_content='{"task":"test"}',
                        task_kind="primary",
                    )

    assert "temperature" not in captured


def test_primary_call_sets_temperature_for_gpt4o_mini(monkeypatch):
    captured: dict = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        msg = MagicMock()
        msg.content = (
            '{"status":"complete","artifacts":{"speakers":[{"speaker_id":"spk_0",'
            '"role":"interviewer","confidence":0.9}]},"memory_updates":{},'
            '"needs":[],"follow_up_investigations":[],"confidence":0.9,'
            '"reasoning_summary":"ok"}'
        )
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    client = MagicMock()
    client.chat.completions.create = fake_create
    _patch_cfg(monkeypatch)

    with patch.object(llm_runner, "OpenAI", return_value=client):
        with patch.object(llm_runner, "require_secret", return_value="sk-test"):
            with patch.object(llm_runner, "load_system_prompt_for_stage", return_value="system"):
                with patch.object(llm_runner, "resolve_model") as mock_resolve:
                    mock_resolve.return_value = MagicMock(model_id="gpt-4o-mini", tier="economy")
                    llm_runner.run_prompt_envelope(
                        "speaker_roles",
                        "understanding/speaker-roles.system.txt",
                        user_content='{"task":"test"}',
                        task_kind="primary",
                    )

    assert captured.get("temperature") == 0.2


def test_load_compact_examples_for_missing_framing():
    text = llm_runner.load_compact_examples("missing_framing")
    assert text is not None
    assert "missing_question" in text or "Compact examples" in text


def test_extract_json_strips_markdown_fences():
    raw = '```json\n{"status":"complete","artifacts":{"thesis":"x"}}\n```'
    parsed = llm_runner._extract_json(raw)
    assert parsed["status"] == "complete"
    assert parsed["artifacts"]["thesis"] == "x"


def test_normalize_envelope_preserves_null():
    env = llm_runner.normalize_envelope(
        {"status": "complete", "artifacts": {"thesis": "x", "audience": None}}
    )
    assert env["artifacts"]["audience"] is None


def test_normalize_envelope_coerces_null_confidence():
    env = llm_runner.normalize_envelope(
        {"status": "complete", "artifacts": {"verdict": "pass"}, "confidence": None}
    )
    assert env["confidence"] == 0.0
    flat = llm_runner.normalize_envelope({"verdict": "pass"})
    assert flat["confidence"] == 0.0
