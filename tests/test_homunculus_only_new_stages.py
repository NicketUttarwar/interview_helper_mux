"""4B — homunculus-only new stages (framing_posture_decide, vo_line_adjudicate)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.stages import framing_posture_decide as framing_stage
from interview_mux.stages import vo_line_adjudicate as adjudicate_stage
from run_fixtures import isolated_run_ctx, mark_done_raw


def _meta(version: str) -> dict:
    kind = "homunculus" if version >= "0.1.0" else "original_pipeline"
    return {"homunculus_version": version, "homunculus_kind": kind}


@pytest.mark.parametrize("version", ["0.0.0", "0.1.0"])
def test_framing_posture_homunculus_guard(tmp_path: Path, version: str) -> None:
    ctx = isolated_run_ctx(tmp_path, "homunc_guard")
    ctx.write_json("run_meta.json", _meta(version), skip_handoff=True)
    ctx.write_json(
        "understanding/source_topology.json",
        {"topology_class": "hosted_one_on_one"},
        skip_handoff=True,
    )
    framing_stage.run_framing_posture_decide(ctx)
    if version == "0.0.0":
        assert ctx.is_done("framing_posture_decide")
        assert ctx.artifact_exists("understanding/framing_posture_decision.json")
        assert (
            ctx.read_json("understanding/framing_posture_decision.json").get("decided_by")
            == "homunculus_skip"
        )
    else:
        assert ctx.is_done("framing_posture_decide")


@pytest.mark.parametrize("version", ["0.0.0"])
def test_vo_line_adjudicate_homunculus_guard_skips_legacy(tmp_path: Path, version: str) -> None:
    ctx = isolated_run_ctx(tmp_path, "homunc_guard")
    ctx.write_json("run_meta.json", _meta(version), skip_handoff=True)
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_test",
                    "gap_type": "nugget_layup",
                    "text": "Bridge line.",
                    "delivery": "synthesize",
                    "placement": "before",
                    "targets_segment_id": "seg_001",
                }
            ]
        },
        skip_handoff=True,
    )
    adjudicate_stage.run_vo_line_adjudicate(ctx)
    assert not ctx.is_done("vo_line_adjudicate")
    assert not ctx.artifact_exists("understanding/vo_line_adjudication.json")


def test_stage_order_migration_unmarks_downstream(tmp_path: Path) -> None:
    from interview_mux.stage_order_migration import migrate_stale_stage_order_on_resume

    ctx = isolated_run_ctx(tmp_path, "homunc_guard")
    ctx.write_json("run_meta.json", _meta("0.1.0"), skip_handoff=True)
    for stage in ("boundary_topic_resplit", "topic_coverage_audit"):
        mark_done_raw(ctx, stage)
    assert not ctx.is_done("framing_posture_decide")
    result = migrate_stale_stage_order_on_resume(ctx)
    assert result["migrated"] is True
    assert result["from_stage"] == "framing_posture_decide"
    assert not ctx.is_done("topic_coverage_audit")
