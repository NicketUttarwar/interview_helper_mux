"""A durably omitted opening orientation is a decision the narrative audit cannot overturn (ISSUES 117)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.artifact_repairs import repair_edl_audit
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    c = isolated_run_ctx(tmp_path, "audit_orientation")
    c.write_json("master/selection.json", {"ordered_segment_ids": ["seg_001", "seg_004"]}, skip_handoff=True)
    return c


def _gap(ctx, *, omitted: bool, required: bool) -> None:
    p = ctx.final_path("understanding", "gap_report.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "interviewer_lines": [],
                "opening_orientation": {
                    "line_id": None,
                    "target_segment_id": "seg_001",
                    "required": required,
                    "omitted": omitted,
                    "omit_reason": "gap_framing_disabled",
                },
            }
        ),
        encoding="utf-8",
    )


def _audit() -> dict:
    return {
        "verdict": "fail",
        "blocking_issues": [
            {
                "code": "opening_orientation_invalid",
                "issue": "The selected master opens directly on seg_001 without an orientation line.",
                "evidence": ["selection.ordered_segment_ids[0]=seg_001"],
                "recommended_action": "Rerun transitions to add an opening orientation.",
            }
        ],
        "warnings": [],
    }


def test_durably_omitted_orientation_demotes_the_blocking_issue(ctx) -> None:
    _gap(ctx, omitted=True, required=False)
    out, notes = repair_edl_audit(ctx, _audit())
    assert out.get("blocking_issues") == [], out
    assert out.get("verdict") != "fail", out
    assert any("opening_orientation_invalid" in json.dumps(w) for w in out.get("warnings") or []), out


def test_a_half_state_omission_does_not_demote(ctx) -> None:
    # omitted without required=False is not durable: consumers revive instead.
    _gap(ctx, omitted=True, required=True)
    out, _notes = repair_edl_audit(ctx, _audit())
    assert out.get("verdict") == "fail"
    assert out.get("blocking_issues"), out
