"""Forensics minor-fixes ledger — only under MUX_FORENSICS."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.forensics_minor_fixes import (
    FORENSICS_MINOR_FIXES_JSON,
    FORENSICS_MINOR_FIXES_MD,
    record_forensics_minor_fix,
    record_from_recovery_action,
)
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


@pytest.fixture()
def run_ctx(tmp_path: Path, request: pytest.FixtureRequest) -> RunContext:
    rid = f"exec_ff_{request.node.name}"[:80]
    return isolated_run_ctx(tmp_path, rid)


def test_noop_when_not_forensics(run_ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MUX_FORENSICS", raising=False)
    record_forensics_minor_fix(
        run_ctx,
        source="test",
        stage="edl",
        action="heal",
        detail="should not write",
    )
    assert not run_ctx.artifact_exists(FORENSICS_MINOR_FIXES_JSON)


def test_records_json_and_md_under_forensics(
    run_ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "1")
    record_forensics_minor_fix(
        run_ctx,
        source="recovery_controller",
        stage="vo_synthesize",
        action="vo_contract_ladder",
        detail="tier_a_publish_orientation",
        status="recovered",
    )
    assert run_ctx.artifact_exists(FORENSICS_MINOR_FIXES_JSON)
    assert run_ctx.artifact_exists(FORENSICS_MINOR_FIXES_MD)
    doc = run_ctx.read_json(FORENSICS_MINOR_FIXES_JSON)
    assert doc["summary"]["count"] == 1
    assert doc["entries"][0]["action"] == "vo_contract_ladder"
    md = Path(run_ctx.path(FORENSICS_MINOR_FIXES_MD)).read_text(encoding="utf-8")
    assert "vo_contract_ladder" in md
    assert "Forensics minor fixes" in md


def test_recovery_hook_only_on_recovered(
    run_ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "1")
    record_from_recovery_action(
        run_ctx,
        {
            "status": "escalate",
            "playbook_id": "budget_exhausted",
            "signature": "edl:seed_order_prereq",
            "detail": "budget_exhausted",
        },
    )
    assert not run_ctx.artifact_exists(FORENSICS_MINOR_FIXES_JSON)
    record_from_recovery_action(
        run_ctx,
        {
            "status": "recovered",
            "playbook_id": "seed_order_prereq",
            "signature": "mix:seed_order_prereq",
            "detail": "unmark_pin",
            "tier": "",
        },
    )
    doc = run_ctx.read_json(FORENSICS_MINOR_FIXES_JSON)
    assert len(doc["entries"]) == 1
    assert doc["entries"][0]["stage"] == "mix"
