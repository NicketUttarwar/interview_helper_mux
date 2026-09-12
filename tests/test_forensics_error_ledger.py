"""Forensics error ledger — records all failures under MUX_FORENSICS."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.forensics_error_ledger import (
    FORENSICS_ERRORS_JSON,
    FORENSICS_ERRORS_MD,
    record_forensics_error,
    record_from_identical_failure_row,
)
from interview_mux.identical_failures import record_failure
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


@pytest.fixture()
def run_ctx(tmp_path: Path, request: pytest.FixtureRequest) -> RunContext:
    rid = f"exec_fe_{request.node.name}"[:80]
    return isolated_run_ctx(tmp_path, rid)


def test_noop_when_not_forensics(run_ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MUX_FORENSICS", raising=False)
    record_forensics_error(
        run_ctx,
        source="test",
        stage="edl",
        detail="should not write",
        predicate="seated_bind_stale",
    )
    assert not run_ctx.artifact_exists(FORENSICS_ERRORS_JSON)


def test_records_json_and_md_under_forensics(
    run_ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "1")
    record_forensics_error(
        run_ctx,
        source="full_auto_driver",
        stage="edl",
        detail="vo_unsanitary: seated_bind_stale:vo_layup_seg_012",
        predicate="seated_bind_stale",
        error_class="seated_bind_stale",
        identical_count=3,
        halt=False,
    )
    assert run_ctx.artifact_exists(FORENSICS_ERRORS_JSON)
    assert run_ctx.artifact_exists(FORENSICS_ERRORS_MD)
    doc = run_ctx.read_json(FORENSICS_ERRORS_JSON)
    assert doc["summary"]["count"] == 1
    assert "seated_bind_stale" in doc["entries"][0]["predicate"]
    assert doc["summary"]["unique_predicates"] == 1
    md = Path(run_ctx.path(FORENSICS_ERRORS_MD)).read_text(encoding="utf-8")
    assert "seated_bind_stale" in md
    assert "Forensics errors" in md


def test_identical_failures_mirror_under_forensics(
    run_ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "1")
    row = record_failure(
        run_ctx,
        kind="reason",
        failed_stage="edl",
        producer="bridge_completeness",
        reason="bridge_completeness: 3 reorder join(s) lack pair-specific glue",
    )
    assert row.get("count") == 1
    assert run_ctx.artifact_exists(FORENSICS_ERRORS_JSON)
    doc = run_ctx.read_json(FORENSICS_ERRORS_JSON)
    assert doc["summary"]["count"] >= 1
    assert any(
        "bridge" in str(e.get("detail") or "").lower()
        or "bridge" in str(e.get("predicate") or "").lower()
        for e in doc["entries"]
    )


def test_identical_row_helper(run_ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUX_FORENSICS", "1")
    record_from_identical_failure_row(
        run_ctx,
        {
            "signature": "abcd",
            "failed_stage": "vo_synthesize",
            "error_class": "seated_bind_stale",
            "raw_reason": "vo_unsanitary: seated_bind_stale:vo_layup_seg_012",
            "count": 2,
            "halt": False,
            "kind": "class",
        },
    )
    doc = run_ctx.read_json(FORENSICS_ERRORS_JSON)
    assert doc["entries"][0]["stage"] == "vo_synthesize"
    assert doc["entries"][0]["identical_count"] == 2
