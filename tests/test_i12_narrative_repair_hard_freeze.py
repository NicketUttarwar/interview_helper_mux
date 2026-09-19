"""Cascade: narrative audit repair must not rewrite selection under hard freeze."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.audit_repair_loop import maybe_repair_after_narrative_audit
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "i12_narr_freeze")


def test_narrative_repair_skips_selection_write_under_hard_freeze(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active", lambda _ctx: True
    )
    writes: list[str] = []

    monkeypatch.setattr(
        "interview_mux.artifact_writes.write_validated_artifact",
        lambda _c, rel, _doc, **_k: writes.append(str(rel)),
    )
    monkeypatch.setattr(
        "interview_mux.artifact_repairs.repair_master_selection",
        lambda _c, sel: (sel, [{"action": "noop"}]),
    )
    monkeypatch.setattr(
        "interview_mux.artifact_repairs.align_narrative_plan_to_selection",
        lambda _c: [],
    )
    monkeypatch.setattr(
        "interview_mux.artifact_repairs.repair_edl_audit",
        lambda _c, arts: (dict(arts), []),
    )
    monkeypatch.setattr(ctx, "mutate_run_meta", lambda _fn: None)
    monkeypatch.setattr(ctx, "log", lambda *_a, **_k: None)
    monkeypatch.setattr(
        ctx,
        "artifact_exists",
        lambda rel: rel
        in {"master/selection.json", "run_meta.json", "master/narrative_plan.json"},
    )
    monkeypatch.setattr(
        ctx,
        "read_json",
        lambda rel: {
            "master/selection.json": {
                "ordered_segment_ids": ["seg_001"],
                "version": 1,
            },
            "run_meta.json": {"homunculus_version": "0.2.0"},
            "master/narrative_plan.json": {"chapters": []},
        }.get(rel, {}),
    )

    maybe_repair_after_narrative_audit(ctx, {"verdict": "fail"})
    assert "master/selection.json" not in writes, (
        "hard freeze must not rewrite selection from narrative repair"
    )
