from __future__ import annotations

from interview_mux.llm_preflight import run_preflight
from run_fixtures import isolated_run_ctx, minimal_speakers


def test_preflight_speaker_roles_missing_transcript(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "pf_speakers")
    errors = run_preflight("speaker_roles", ctx)
    assert any("transcript" in e for e in errors)


def test_preflight_boundary_detection_requires_interviewer(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "pf_boundary")
    speakers = minimal_speakers()
    speakers["speakers"] = [
        {"speaker_id": "spk_0", "role": "unknown", "confidence": 0.9, "evidence": ["x"]},
    ]
    ctx.write_json("understanding/speakers.json", speakers, stage_key="speaker_roles")
    errors = run_preflight("boundary_detection", ctx)
    assert any("interviewer" in e for e in errors)


def test_preflight_segment_classification_requires_boundaries(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "pf_seg")
    errors = run_preflight("segment_classification", ctx)
    assert any("boundaries" in e for e in errors)
