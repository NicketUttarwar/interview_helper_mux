from __future__ import annotations

import json
from pathlib import Path

from interview_mux.llm_call_record import (
    build_call_id,
    build_call_label,
    messages_to_openai_format,
    messages_to_volley_only,
    reconstruct_volley_from_calls,
    record_to_markdown,
    split_messages_for_volley,
)
from interview_mux.run_context import RunContext


def test_build_label_and_call_id():
    label = build_call_label(
        stage_key="missing_framing",
        attempt=2,
        sequence=3,
        task_kind="arbiter",
    )
    assert label == "analysis:missing_framing:a002:03:arbiter"
    cid = build_call_id(
        run_id="exec_001_test",
        stage_key="missing_framing",
        attempt=2,
        sequence=3,
        task_kind="arbiter",
    )
    assert "exec_001_test/missing_framing/a002/03_arbiter" == cid


def test_split_and_reconstruct_volley():
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Task"},
        {"role": "assistant", "content": "Prior"},
        {"role": "user", "content": "Evidence"},
    ]
    system, volley = split_messages_for_volley(messages)
    assert "helpful" in system
    assert len(volley) == 3
    rec = {
        "volley": {"system_prompt": system, "turns": volley},
        "request": {"messages": messages},
        "response": {"raw_content": '{"status":"complete"}'},
        "attempt": 1,
        "sequence": 1,
    }
    assert messages_to_volley_only(rec) == volley
    assert messages_to_openai_format(rec) == messages
    merged = reconstruct_volley_from_calls([rec])
    assert merged[-1]["role"] == "assistant"
    assert "complete" in merged[-1]["content"]


def test_record_llm_call_writes_files(tmp_path, monkeypatch):
    from run_fixtures import patch_merged_config

    monkeypatch.setattr("interview_mux.config.repo_root", lambda: tmp_path)
    monkeypatch.setattr("interview_mux.run_context.repo_root", lambda: tmp_path)
    cfg = {
        "assets_root": "ASSETS",
        "executions_root": str(tmp_path / "ASSETS" / "executions"),
        "data_root": "data",
        "journey_ui": {"require_write_approval_per_stage": False},
        "analysis": {"llm_call_records": {"enabled": True, "write_markdown_sidecar": True}},
    }
    patch_merged_config(monkeypatch, cfg)

    run_id = "exec_099_20260101T000000Z"
    ctx = RunContext(run_id, create=True)
    from interview_mux.llm_call_record import record_llm_call

    record_llm_call(
        ctx,
        stage_key="speaker_roles",
        prompt_ref="analysis/speaker-roles.system.txt",
        request_messages=[
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "do it"},
        ],
        raw_response='{"status":"complete","artifacts":{}}',
        parsed_envelope={"status": "complete", "artifacts": {}},
        task_kind="primary",
        model_id="gpt-4o-mini",
        model_tier="economy",
        call_attempt=1,
    )
    json_path = ctx.path(
        "understanding",
        "llm_calls",
        "speaker_roles",
        "attempt_001",
        "01_primary.json",
    )
    assert json_path.is_file()
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    assert doc["label"] == "analysis:speaker_roles:a001:01:primary"
    assert doc["importance"] == "high"
    md_path = json_path.with_suffix(".md")
    assert md_path.is_file()
    assert "speaker_roles" in record_to_markdown(doc)
    index = ctx.path("understanding", "llm_calls", "index.jsonl")
    assert index.is_file()
