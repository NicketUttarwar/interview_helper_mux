from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from export_llm_calls import _stage_run_audit_appendix  # noqa: E402
from run_fixtures import isolated_run_ctx


def test_stage_run_audit_appendix_includes_lint_and_arbiter(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "export_audit")
    stage = "missing_framing"
    base = ctx.path("understanding", "stage_runs", stage)
    base.mkdir(parents=True, exist_ok=True)
    attempt = {
        "arbiter_result": {"verdict": "reject"},
        "deterministic_lint_errors": ["thesis empty"],
        "attempt_signature": ["partial", [], 1200],
    }
    (base / "attempt_001.json").write_text(json.dumps(attempt), encoding="utf-8")
    md = _stage_run_audit_appendix(ctx.run_dir, None)
    assert "deterministic_lint" in md
    assert "thesis empty" in md
    assert "arbiter_verdict: reject" in md


def test_export_cli_markdown_with_audit(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "export_cli")
    stage = "missing_framing"
    base = ctx.path("understanding", "stage_runs", stage)
    base.mkdir(parents=True, exist_ok=True)
    (base / "attempt_001.json").write_text(
        json.dumps({"arbiter_result": {"verdict": "accept"}, "deterministic_lint_errors": []}),
        encoding="utf-8",
    )
    calls_dir = ctx.path("understanding", "llm_calls", stage, "attempt_001")
    calls_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "stage_key": stage,
        "attempt": 1,
        "label": "primary",
        "importance": "high",
        "volley": {"system_prompt": "sys", "turns": [{"role": "user", "content": "hi"}]},
        "response": {"raw_content": "{}"},
    }
    (calls_dir / "001_primary.json").write_text(json.dumps(record), encoding="utf-8")

    from export_llm_calls import main as export_main  # noqa: E402

    monkeypatch.setattr("export_llm_calls._resolve_run_dir", lambda _rid: ctx.run_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export_llm_calls",
            "--run-id",
            ctx.run_id,
            "--format",
            "markdown",
        ],
    )
    export_main()
    out = capsys.readouterr().out
    assert "Stage run audit" in out
    assert "arbiter_verdict: accept" in out
