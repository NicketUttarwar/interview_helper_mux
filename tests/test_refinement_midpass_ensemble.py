"""Mid-pass shard and ensemble lint unit tests."""

from __future__ import annotations

import pytest

from interview_mux.refinement_ensemble import lint_gap_and_transitions
from interview_mux.refinement_midpass import early_exit_if_shard_fails, run_sharded, shard_lines_by_act
from interview_mux.run_context import RunContext
from run_fixtures import patch_executions_root


@pytest.fixture()
def ctx(tmp_path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    return RunContext("exec_refinement_mid", create=True)


def test_shard_by_size() -> None:
    lines = [{"line_id": f"l{i}"} for i in range(25)]
    shards = shard_lines_by_act(lines, max_per_shard=10)
    assert len(shards) == 3
    assert sum(len(s) for s in shards) == 25


def test_early_exit_on_first_fail() -> None:
    quit = early_exit_if_shard_fails([{"ok": False, "reason_code": "bad"}])
    assert quit and quit["quarantine"] is True


def test_run_sharded_merges(ctx: RunContext) -> None:
    lines = [{"line_id": "a"}, {"line_id": "b"}]

    def proc(shard, idx):
        return {"ok": True, "accepted": True, "lines": shard}

    out = run_sharded(lines, proc, max_per_shard=1)
    assert out["quarantine"] is False
    assert len(out["lines"]) == 2


def test_ensemble_lint_flags_overlap(ctx: RunContext) -> None:
    import json

    text = "welcome back to the show with our guest today discussing markets"
    gap_path = ctx.path("understanding", "gap_report.json")
    gap_path.parent.mkdir(parents=True, exist_ok=True)
    gap_path.write_text(
        json.dumps(
            {
                "interviewer_lines": [
                    {
                        "line_id": "g1",
                        "text": text,
                        "gap_type": "preface",
                        "placement": "before",
                        "delivery": "synthesize",
                        "targets_segment_id": "seg_1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    tr_path = ctx.path("master", "transitions.json")
    tr_path.parent.mkdir(parents=True, exist_ok=True)
    tr_path.write_text(json.dumps({"bridges": [{"id": "t1", "text": text}]}), encoding="utf-8")
    payload = lint_gap_and_transitions(ctx)
    assert payload["ok"] is False
    assert payload["issues"]
