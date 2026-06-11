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
