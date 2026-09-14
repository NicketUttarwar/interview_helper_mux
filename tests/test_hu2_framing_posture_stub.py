"""HU-2: framing_posture skip/disabled writes an allow-stub and marks done.

Does not skip gap fill. Seed/delivery must not pin missing_framing on this
stage. Do not start a run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.framing_posture import FRAMING_POSTURE_DECISION_REL
from interview_mux.gap_fill_eligibility import gap_fill_was_skipped
from interview_mux.homunculus.agenda import pending_analysis_for_delivery
from interview_mux.homunculus.runtime import _seed_prereq_block
from interview_mux.prompt_validation import validate_stage_artifacts
from interview_mux.run_context import RunContext
from interview_mux.stages import framing_posture_decide as stage_mod
from run_fixtures import isolated_run_ctx, minimal_content_brief, minimal_manifest_segment


def _meta(version: str) -> dict:
    kind = "homunculus" if version >= "0.1.0" else "original_pipeline"
    return {"homunculus_version": version, "homunculus_kind": kind}


def _hosted(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.9},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.9},
            ],
            "conversation_profile": {"format_class_candidate": "one_on_one", "dynamics": {}},
        },
    )
    ctx.write_json(
        "understanding/source_topology.json",
        {"topology_class": "one_on_one_asymmetric", "speaker_stats": []},
    )
    ctx.write_json(
        "understanding/content_brief.json",
        minimal_content_brief(thesis="Hosted product interview."),
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                minimal_manifest_segment(
                    segment_id="seg_001",
                    speaker_id="spk_0",
                    segment_type="interviewer_question",
                ),
                minimal_manifest_segment(
                    segment_id="seg_002",
                    speaker_id="spk_1",
                    segment_type="interviewee_answer",
                ),
            ]
        },
    )


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "hu2_posture")


def test_hu2_feature_disabled_writes_stub_and_marks(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx.write_json("run_meta.json", _meta("0.1.0"))
    _hosted(ctx)
    monkeypatch.setattr(stage_mod, "framing_posture_enabled", lambda *_a, **_k: False)
    stage_mod.run_framing_posture_decide(ctx)
    assert ctx.is_done("framing_posture_decide")
    doc = ctx.read_json(FRAMING_POSTURE_DECISION_REL)
    assert doc["decided_by"] == "feature_disabled"
    assert doc["recommended_framing"] == "yes"
    assert validate_stage_artifacts("framing_posture_decide", doc) == []
    assert not gap_fill_was_skipped(ctx)


def test_hu2_000_writes_stub_and_marks(ctx: RunContext) -> None:
    ctx.write_json("run_meta.json", _meta("0.0.0"))
    _hosted(ctx)
    stage_mod.run_framing_posture_decide(ctx)
    assert ctx.is_done("framing_posture_decide")
    doc = ctx.read_json(FRAMING_POSTURE_DECISION_REL)
    assert doc["decided_by"] == "homunculus_skip"
    assert not gap_fill_was_skipped(ctx)


def test_hu2_stub_does_not_pin_missing_framing(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx.write_json("run_meta.json", _meta("0.1.0"))
    _hosted(ctx)
    monkeypatch.setattr(stage_mod, "framing_posture_enabled", lambda *_a, **_k: False)
    stage_mod.run_framing_posture_decide(ctx)
    pending = pending_analysis_for_delivery(ctx)
    assert "framing_posture_decide" not in pending
    assert _seed_prereq_block(ctx, "missing_framing") != "framing_posture_decide"
    from interview_mux.homunculus.gates import recommended_framing_action

    assert recommended_framing_action(ctx) == "present_operator"
