"""Hollow-done guard — scan + forensics escalate.

MUX_FORENSICS=0 for scan unit tests; one escalate write under forensics=1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.hollow_done_guard import (
    HOLLOW_ESCALATION_REL,
    escalate_hollow_done,
    scan_hollow_done,
)
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx, mark_done_raw


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    return isolated_run_ctx(tmp_path, "hollow_done_guard")


def test_hollow_mark_done_raw_scan_finds(ctx: RunContext) -> None:
    mark_done_raw(ctx, "transitions")
    found = scan_hollow_done(ctx, stages=("transitions",))
    assert len(found) == 1
    assert found[0]["stage"] == "transitions"
    assert found[0]["reason"]


def test_land_honest_stage_not_reported(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    mark_done_raw(ctx, "transitions")
    monkeypatch.setattr(
        "interview_mux.done_authority.land_honest",
        lambda _c, sid: sid == "transitions",
    )
    assert scan_hollow_done(ctx, stages=("transitions",)) == []


def test_escalate_under_forensics_writes_artifact(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "1")
    mark_done_raw(ctx, "edl")
    found = escalate_hollow_done(ctx, stages=("edl",), raise_on_find=False)
    assert len(found) == 1
    assert found[0]["stage"] == "edl"
    assert ctx.artifact_exists(HOLLOW_ESCALATION_REL)
    doc = ctx.read_json(HOLLOW_ESCALATION_REL)
    assert doc.get("kind") == "hollow_done_escalation"
    assert isinstance(doc.get("hollow"), list)
    assert doc["hollow"][0]["stage"] == "edl"


def test_escalate_non_forensics_no_artifact(ctx: RunContext) -> None:
    mark_done_raw(ctx, "mix")
    found = escalate_hollow_done(ctx, stages=("mix",), raise_on_find=False)
    assert len(found) == 1
    assert not ctx.artifact_exists(HOLLOW_ESCALATION_REL)
