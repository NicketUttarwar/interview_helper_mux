"""Conversation context kernel — load, attach, gap sensitivity, hypotheses."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.conversation_context import (
    apply_confirmed_hypothesis,
    attach_conversation_context,
    build_gap_sensitivity,
    enrich_speakers_artifact,
    hypotheses_require_confirmation,
    load_conversation_context,
    role_is_content,
    role_is_frame,
    sync_conversation_to_analysis_state,
)
from interview_mux.run_context import RunContext


def _write_speakers(run: Path, doc: dict) -> None:
    run.mkdir(parents=True, exist_ok=True)
    (run / "understanding").mkdir(exist_ok=True)
    (run / "understanding" / "speakers.json").write_text(json.dumps(doc), encoding="utf-8")
    (run / "understanding" / "analysis_state.json").write_text("{}", encoding="utf-8")
    (run / "run_meta.json").write_text("{}", encoding="utf-8")


def test_role_helpers():
    assert role_is_frame("moderator")
    assert role_is_frame("co_host")
    assert role_is_content("panelist")
    assert not role_is_content("off_mic")


def test_build_gap_sensitivity_panel_overlay():
    gs = build_gap_sensitivity(
        "panel",
        tone_class="technical",
        dynamics={"overlap_risk": "high", "turn_asymmetry": "medium", "question_density": "low"},
        speakers=[
            {"speaker_id": "spk_0", "role": "moderator"},
            {"speaker_id": "spk_1", "role": "panelist"},
            {"speaker_id": "spk_2", "role": "panelist"},
        ],
    )
    assert gs["format_class"] == "panel"
    assert "missing_definition" in gs["priority_gap_types"]
    assert gs["segment_focus"] == "interviewee_answer_per_guest"
    assert gs["severity_hints"]["missing_callback"] == "relaxed"


def test_load_conversation_context_resolves_confirmed_hypothesis(tmp_path: Path):
    run = tmp_path / "exec_conv"
    _write_speakers(
        run,
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "unknown", "confidence": 0.4},
                {"speaker_id": "spk_1", "role": "unknown", "confidence": 0.4},
            ],
            "conversation_profile": {"format_class_candidate": "one_on_one", "format_confidence": 0.5},
            "conversation_hypotheses": [
                {
                    "id": "hyp_panel",
                    "format_class": "panel",
                    "confidence": 0.7,
                    "speaker_role_map": {"spk_0": "moderator", "spk_1": "panelist"},
                }
            ],
            "confirmed_conversation_hypothesis_id": "hyp_panel",
        },
    )
    ctx = RunContext(str(run))
    conv = load_conversation_context(ctx)
    assert conv.format_class == "panel"
    assert conv.confirmed_hypothesis_id == "hyp_panel"
    assert not conv.hypotheses_pending


def test_apply_confirmed_hypothesis_updates_roles_and_gap_policy():
    doc = {
        "speakers": [
            {"speaker_id": "spk_0", "role": "unknown", "confidence": 0.5},
            {"speaker_id": "spk_1", "role": "unknown", "confidence": 0.5},
        ],
        "conversation_profile": {"format_class_candidate": "one_on_one", "dynamics": {}},
        "conversation_hypotheses": [
            {
                "id": "hyp_panel",
                "format_class": "panel",
                "confidence": 0.8,
                "speaker_role_map": {"spk_0": "moderator", "spk_1": "panelist"},
            }
        ],
    }
    out = apply_confirmed_hypothesis(doc, "hyp_panel")
    assert out["confirmed_conversation_hypothesis_id"] == "hyp_panel"
    assert out["speakers"][0]["role"] == "moderator"
    assert out["gap_sensitivity"]["format_class"] == "panel"


def test_attach_conversation_context_stage_slices(tmp_path: Path):
    run = tmp_path / "exec_attach"
    _write_speakers(
        run,
        {
            "speakers": [{"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.9}],
            "conversation_profile": {"format_class_candidate": "one_on_one", "format_confidence": 0.9},
            "gap_sensitivity": build_gap_sensitivity("one_on_one"),
        },
    )
    ctx = RunContext(str(run))
    payload: dict = {}
    out = attach_conversation_context(ctx, payload, "missing_framing")
    assert "gap_sensitivity" in out
    assert out["profile_style"]["format_class"] == "one_on_one"

    payload2: dict = {}
    out2 = attach_conversation_context(ctx, payload2, "content_context")
    assert "speakers" in out2
    assert "conversation_profile" in out2


def test_hypotheses_require_confirmation():
    assert hypotheses_require_confirmation(
        {"conversation_hypotheses": [{"id": "a"}], "confirmed_conversation_hypothesis_id": None}
    )
    assert not hypotheses_require_confirmation(
        {"conversation_hypotheses": [{"id": "a"}], "confirmed_conversation_hypothesis_id": "a"}
    )


def test_sync_conversation_to_analysis_state_seeds_style(tmp_path: Path):
    from interview_mux.analysis_memory import default_analysis_state, save_analysis_state

    run = tmp_path / "exec_sync"
    _write_speakers(run, {"speakers": []})
    ctx = RunContext(str(run))
    save_analysis_state(ctx, default_analysis_state(str(run)))
    sync_conversation_to_analysis_state(
        ctx,
        {
            "speakers": [{"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.9}],
            "conversation_profile": {
                "format_class_candidate": "panel",
                "tone_class_candidate": "journalistic",
            },
            "gap_sensitivity": build_gap_sensitivity("panel"),
        },
    )
    state = ctx.read_json("understanding/analysis_state.json")
    assert state["style"]["format_class"] == "panel"
    assert state["style"]["tone_class"] == "journalistic"
    assert state["gap_sensitivity"]["format_class"] == "panel"


def test_enrich_speakers_artifact_backfills_profile(tmp_path: Path):
    run = tmp_path / "exec_enrich"
    run.mkdir(parents=True)
    (run / "transcript").mkdir()
    (run / "understanding").mkdir()
    (run / "transcript" / "full.json").write_text(
        json.dumps({"text": "Host: Hi?\nGuest: Hello there.", "words": []}),
        encoding="utf-8",
    )
    ctx = RunContext(str(run))
    out = enrich_speakers_artifact(
        ctx,
        {
            "speakers": [
                {"speaker_id": "spk_0", "role": "interviewer", "confidence": 0.8},
                {"speaker_id": "spk_1", "role": "interviewee", "confidence": 0.8},
            ]
        },
    )
    assert out["conversation_profile"]["format_class_candidate"]
    assert out["gap_sensitivity"]["severity_hints"]
