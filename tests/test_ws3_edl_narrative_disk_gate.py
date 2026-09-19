"""Category B WS3: disk-grounded EDL narrative audit gate cascades."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "ws3_edl_disk_gate")


def _plant_duplicate_spoken_seam(ctx: RunContext) -> None:
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001", "seg_002"], "chapters": []},
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_002",
                    "text": "What changed next?",
                    "delivery": "synthesize",
                    "placement": "before",
                    "prior_segment_id": "seg_001",
                    "targets_segment_id": "seg_002",
                    "required": True,
                    "gap_type": "missing_setup",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "master/transitions.json",
        {
            "transitions": [
                {
                    "type": "transition",
                    "after_segment_id": "seg_001",
                    "before_segment_id": "seg_002",
                    "text": "The next decision changed the trajectory.",
                }
            ]
        },
        stage_key="transitions",
        skip_handoff=True,
    )


def test_pre_llm_persists_disk_grounded_occupancy(ctx: RunContext) -> None:
    from interview_mux.stages.edl_narrative_audit import (
        prepare_edl_narrative_audit_inputs,
    )

    _plant_duplicate_spoken_seam(ctx)
    payload = prepare_edl_narrative_audit_inputs(ctx)

    assert payload["transitions"]["transitions"] == []
    occupancy = payload["seam_occupancy"]
    assert occupancy["clean"] is True
    assert occupancy["seams"][0]["kind"] == "layup"
    assert occupancy["seams"][0]["line_id"] == "vo_layup_seg_002"
    assert ctx.read_json("master/seam_occupancy.json") == occupancy


@pytest.mark.parametrize("epoch", ["soft_freeze", "hard_freeze"])
def test_occupancy_write_is_transitions_safe_under_freeze(
    ctx: RunContext,
    monkeypatch: pytest.MonkeyPatch,
    epoch: str,
) -> None:
    from interview_mux.seam_occupancy import build_seam_occupancy

    monkeypatch.setattr(
        "interview_mux.artifact_ownership.current_epoch", lambda _ctx: epoch
    )
    doc = build_seam_occupancy(
        ctx,
        selection={"ordered_segment_ids": ["seg_001", "seg_002"]},
        gap_report={"interviewer_lines": []},
        transitions_doc={"transitions": []},
        stage_key="transitions",
    )
    assert doc["clean"] is True
    assert ctx.artifact_exists("master/seam_occupancy.json")


def test_effective_gate_ignores_disk_contradicted_fail(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.edl_narrative_remutate import (
        classify_edl_narrative_audit,
        narrative_audit_blocks_edl,
    )
    from interview_mux.stage_completion import stage_artifact_incompleteness
    from interview_mux.stages import assembly

    ctx.write_json(
        "master/seam_occupancy.json",
        {"version": 1, "selection_order": [], "seams": [], "clean": True},
        stage_key="transitions",
        skip_handoff=True,
    )
    ctx.write_json(
        "master/edl_narrative_audit.json",
        {
            "verdict": "fail",
            "blocking_issues": [
                {
                    "code": "duplicate_spoken_seam",
                    "issue": "stale duplicate prose",
                    "evidence": [],
                    "recommended_action": "rerun transitions",
                }
            ],
            "warnings": [],
            "recommended_actions": [],
            "reasoning_summary": "fixture",
        },
        stage_key="edl_narrative_audit",
        skip_handoff=True,
    )

    assert classify_edl_narrative_audit(ctx.read_json("master/edl_narrative_audit.json")) == [
        "transitions"
    ]
    assert narrative_audit_blocks_edl(ctx) is False
    monkeypatch.setattr(
        "interview_mux.stage_completion._edl_narrative_audit_heard_wav_incompleteness",
        lambda _ctx: None,
    )
    reason = stage_artifact_incompleteness(ctx, "edl_narrative_audit")
    assert not reason or "effective blocking" not in reason

    class PassedNarrativeGate(RuntimeError):
        pass

    monkeypatch.setattr(
        assembly,
        "check_narrative_qc",
        lambda *_a, **_k: (_ for _ in ()).throw(PassedNarrativeGate()),
    )
    with pytest.raises(PassedNarrativeGate):
        assembly.run_edl(ctx)


def test_freeze_transition_dedupe_upgrades_fail_audit(ctx: RunContext) -> None:
    from interview_mux.edl_narrative_remutate import (
        _dedupe_framing_transitions_under_freeze,
        narrative_audit_blocks_edl,
    )

    _plant_duplicate_spoken_seam(ctx)
    ctx.write_json(
        "master/edl_narrative_audit.json",
        {
            "verdict": "fail",
            "blocking_issues": [
                {
                    "code": "duplicate_spoken_seam",
                    "issue": "Both spoken rows occupy seg_001 to seg_002.",
                    "evidence": ["seg_001 -> seg_002"],
                    "recommended_action": "dedupe transitions",
                }
            ],
            "warnings": [],
            "recommended_actions": [],
            "reasoning_summary": "fixture",
        },
        stage_key="edl_narrative_audit",
        skip_handoff=True,
    )
    # Keep the pre-repair duplicate on disk: writing the audit may invoke the
    # repository's shared-path sanitizer before this explicit freeze cascade.
    transitions_path = ctx.final_path("master/transitions.json")
    transitions_path.write_text(
        json.dumps(
            {
                "transitions": [
                    {
                        "type": "transition",
                        "after_segment_id": "seg_001",
                        "before_segment_id": "seg_002",
                        "text": "The next decision changed the trajectory.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    notes = _dedupe_framing_transitions_under_freeze(ctx)

    assert "dedupe_transitions_for_framing" in notes
    assert "upgrade_fail_audit_after_clean_occupancy" in notes
    assert ctx.read_json("master/transitions.json")["transitions"] == []
    assert ctx.read_json("master/seam_occupancy.json")["clean"] is True
    audit = ctx.read_json("master/edl_narrative_audit.json")
    assert audit["verdict"] in {"pass", "warn"}
    assert audit["blocking_issues"] == []
    assert narrative_audit_blocks_edl(ctx) is False
