"""Prompt-edit promotion stays run-local by default."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.mastering_prompt_promotion import (
    can_promote,
    promotion_blockers,
    record_promotion_request,
)
from interview_mux.run_context import RunContext
from tests.run_fixtures import patch_executions_root


def test_promotion_blocked_by_default_config():
    blockers = promotion_blockers(
        corpus_results={
            "integrity_recall": 1.0,
            "integrity_false_positive_rate": 0.0,
            "diversity_floor_met": 1.0,
        },
        operator_approval={"approved": True, "approved_by": "operator"},
    )
    assert "allow_global_promotion is false" in blockers[0]
    assert can_promote(
        corpus_results={
            "integrity_recall": 1.0,
            "integrity_false_positive_rate": 0.0,
            "diversity_floor_met": 1.0,
        },
        operator_approval={"approved": True},
    ) is False


def test_promotion_requires_corpus_and_approval_even_when_enabled():
    cfg = {"mastering": {"prompt_edit": {"allow_global_promotion": True}}}
    assert promotion_blockers(corpus_results=None, operator_approval=None, cfg=cfg)
    assert not can_promote(
        corpus_results={
            "integrity_recall": 1.0,
            "integrity_false_positive_rate": 0.0,
            "diversity_floor_met": 1.0,
        },
        operator_approval=None,
        cfg=cfg,
    )
    assert can_promote(
        corpus_results={
            "integrity_recall": 1.0,
            "integrity_false_positive_rate": 0.0,
            "diversity_floor_met": 1.0,
        },
        operator_approval={"approved": True},
        cfg=cfg,
    )


def test_promotion_ledger_records_run_local_decision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    patch_executions_root(monkeypatch, tmp_path)
    ctx = RunContext("exec_prompt_promo", create=True)
    entry = record_promotion_request(
        ctx,
        step_id="shape_l2",
        version=2,
        corpus_results={"integrity_recall": 0.5},
    )
    assert entry["promoted"] is False
    assert entry["scope"] == "run_local"
    ledger = ctx.read_json("mastering/prompt_promotions.json")
    assert ledger["promotions"][-1]["step_id"] == "shape_l2"
