from __future__ import annotations

from interview_mux.gate_focus import gate_focus_stage, upstream_stage_from_gate_message


def test_upstream_stage_from_prerequisite_artifact_message():
    msg = (
        "Prerequisite artifact understanding/speakers.json from stage speaker_roles "
        "is incomplete. Use Fill gaps or re-run --from-stage speaker_roles."
    )
    assert upstream_stage_from_gate_message(msg, current_stage="content_context") == "speaker_roles"
    assert gate_focus_stage(msg, job_stage="content_context") == "speaker_roles"


def test_upstream_stage_from_prerequisite_stage_message():
    msg = "Prerequisite stage speaker_roles is not complete. Run analysis from --from-stage speaker_roles."
    assert upstream_stage_from_gate_message(msg) == "speaker_roles"


def test_gate_focus_maps_g0_to_transcript_review():
    msg = "Transcript review required. Open the GUI to correct ranked clips, then complete review."
    assert gate_focus_stage(msg, job_stage="transcript_review_build") == "transcript_review"


def test_gate_focus_maps_g05_to_disfluency_review():
    msg = "Disfluency review required. Confirm or reject filler events in the GUI."
    assert gate_focus_stage(msg, job_stage="disfluency_extract") == "disfluency_review"


def test_gate_focus_keeps_job_stage_when_no_upstream():
    msg = "LLM stage gate (speaker_roles): artifact not complete (status=blocked)."
    assert gate_focus_stage(msg, job_stage="speaker_roles") == "speaker_roles"
