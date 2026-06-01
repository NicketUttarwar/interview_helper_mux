from __future__ import annotations

import json

from interview_mux.llm_call_record import record_llm_call
from interview_mux.llm_calls_gui import (
    get_llm_call_record,
    list_llm_calls_summary,
    update_llm_call_record,
)
from interview_mux.run_context import RunContext


def test_list_and_update_llm_calls_gui(tmp_path, monkeypatch):
    cfg = {
        "assets_root": "ASSETS",
        "executions_root": str(tmp_path / "ASSETS" / "executions"),
        "data_root": "data",
        "analysis": {"llm_call_records": {"enabled": True, "write_markdown_sidecar": False}},
    }
    for mod in ("interview_mux.config", "interview_mux.llm_call_record", "interview_mux.run_context", "interview_mux.llm_calls_gui"):
        monkeypatch.setattr(f"{mod}.merged_config", lambda: cfg)
    monkeypatch.setattr("interview_mux.config.repo_root", lambda: tmp_path)

    run_id = "exec_050_20260101T000000Z"
    ctx = RunContext(run_id, create=True)
    record_llm_call(
        ctx,
        stage_key="speaker_roles",
        prompt_ref="analysis/speaker-roles.system.txt",
        request_messages=[
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "task"},
            {"role": "assistant", "content": "prior"},
        ],
        raw_response='{"status":"complete","artifacts":{}}',
        parsed_envelope={"status": "complete", "artifacts": {}},
        task_kind="primary",
        model_id="gpt-4o-mini",
        model_tier="economy",
        call_attempt=1,
    )

    summary = list_llm_calls_summary(ctx)
    assert summary["call_count"] == 1
    assert "speaker_roles" in summary["stages"]
    path = summary["calls"][0]["path"]

    full = get_llm_call_record(ctx, path)
    assert len(full["volley"]["turns"]) == 2
    assert full["_gui"]["openai_messages"][0]["role"] == "system"

    updated = update_llm_call_record(
        ctx,
        path,
        volley={
            "system_prompt": "sys2",
            "turns": [{"role": "user", "content": "edited"}],
        },
        raw_response='{"status":"partial"}',
    )
    assert updated["volley"]["system_prompt"] == "sys2"
    assert updated["request"]["messages"][0]["content"] == "sys2"

    on_disk = json.loads((ctx.run_dir / path).read_text(encoding="utf-8"))
    assert on_disk["response"]["raw_content"] == '{"status":"partial"}'
