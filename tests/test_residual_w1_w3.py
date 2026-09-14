"""Wave 1–3 residual closeout: pending_analysis, repair tags, driver heal-or-resume."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from interview_mux.artifact_repairs import repair_gap_evaluations
from interview_mux.homunculus.agenda import pending_analysis_for_delivery
from interview_mux.run_context import RunContext
from interview_mux.stage_completion import heal_or_refuse_mark, stage_artifact_incompleteness
from run_fixtures import isolated_run_ctx, mark_done_raw, minimal_manifest

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
import full_auto_driver as driver  # noqa: E402

_REL = "understanding/gap_evaluations.json"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "w1w3")
    run.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )
    monkeypatch.setattr(
        "interview_mux.mastering_research.research_shape_core_thin",
        lambda _ctx: False,
    )
    return run


def _filled(sid: str) -> dict:
    return {
        "segment_id": sid,
        "self_explanatory": True,
        "gap_type": "ok_with_light_bridge",
        "severity": "low",
        "listener_confusion": "",
        "_meta": {
            "filled_by": "missing_framing_batch_coverage",
            "reason": "llm_sparse_shard_output",
        },
    }


def test_w1a_pending_keeps_batch_fill_even_when_done(ctx: RunContext) -> None:
    ctx.write_json(_REL, {"evaluations": [_filled("seg_001")]}, skip_handoff=True)
    mark_done_raw(ctx, "missing_framing")
    pending = pending_analysis_for_delivery(ctx)
    assert "missing_framing" in pending
    assert not ctx.is_done("missing_framing")


def test_w1c_repair_tags_fabricated_rows(ctx: RunContext) -> None:
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest("seg_a", "seg_b"),
        skip_handoff=True,
    )
    repaired, notes = repair_gap_evaluations(ctx, {"evaluations": []})
    assert any(n.get("action") == "fabricate_evaluation" for n in notes)
    tagged = [
        r
        for r in (repaired.get("evaluations") or [])
        if isinstance(r, dict)
        and str((r.get("_meta") or {}).get("filled_by") or "") == "repair_gap_evaluations"
    ]
    assert len(tagged) == 2
    ctx.write_json(_REL, repaired, skip_handoff=True)
    reason = stage_artifact_incompleteness(ctx, "missing_framing")
    assert reason is not None
    assert "batch_fill" in reason


def test_w1c_skip_producer_rows_untagged(ctx: RunContext) -> None:
    row = {
        "segment_id": "seg_001",
        "severity": None,
        "gap_type": None,
        "_meta": {"producer": "gap_fill_skip"},
    }
    repaired, _notes = repair_gap_evaluations(ctx, {"evaluations": [row]})
    out = (repaired.get("evaluations") or [row])[0]
    assert str((out.get("_meta") or {}).get("filled_by") or "") == ""
    assert str((out.get("_meta") or {}).get("producer") or "") == "gap_fill_skip"


def test_w3_heal_or_resume_false_when_batch_fill(ctx: RunContext) -> None:
    ctx.write_json(_REL, {"evaluations": [_filled("seg_001")]}, skip_handoff=True)
    assert driver._heal_mark_or_resume(ctx, "missing_framing") is False
    assert not ctx.is_done("missing_framing")


def test_w3_heal_or_resume_true_when_llm_scored(ctx: RunContext) -> None:
    ctx.write_json(
        _REL,
        {
            "evaluations": [
                {
                    "segment_id": "seg_001",
                    "self_explanatory": True,
                    "gap_type": "ok_with_light_bridge",
                    "severity": "low",
                    "listener_confusion": "",
                }
            ]
        },
        skip_handoff=True,
    )
    assert heal_or_refuse_mark(ctx, "missing_framing", force=True).get("marked") is True
    assert driver._heal_mark_or_resume(ctx, "missing_framing") is True
    assert ctx.is_done("missing_framing")
