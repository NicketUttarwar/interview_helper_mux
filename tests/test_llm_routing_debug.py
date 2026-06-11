from __future__ import annotations

import json

from interview_mux.llm_routing_debug import list_stage_routing_attempts
from run_fixtures import isolated_run_ctx


def test_list_stage_routing_includes_lint_and_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "routing_dbg")
    stage_dir = ctx.path("understanding", "stage_runs", "missing_framing")
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / "attempt_001.json").write_text(
        json.dumps(
            {
                "attempt": 1,
                "task_kind": "primary",
                "arbiter_result": {"verdict": "reject"},
                "deterministic_lint_errors": ["segment_coverage_ratio: 0.1 < 0.85"],
                "primary_attempt_count": 2,
                "budget_remaining_primary": 1,
                "stuck_count": 0,
            }
        ),
        encoding="utf-8",
    )
    (stage_dir / "specialist_comprehension_risk_blind.json").write_text(
        json.dumps({"arbiter_result": {"verdict": "accept"}, "artifacts": {}}),
        encoding="utf-8",
    )
    rows = list_stage_routing_attempts(ctx)
    primary = [r for r in rows if r["task_kind"] == "primary"][0]
    assert primary["deterministic_lint_errors"]
    assert primary["primary_attempt_count"] == 2
    assert any(r["task_kind"] == "specialist" for r in rows)
