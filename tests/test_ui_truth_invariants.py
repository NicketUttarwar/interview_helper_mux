from __future__ import annotations

from interview_mux.ui_truth import Violation, validate_run_snapshot


def test_t1_done_stage_no_pending_artifacts() -> None:
    stages = [
        {
            "id": "ingest",
            "status": "done",
            "artifacts_status": {"ingest/checksums.json": "pending"},
            "artifacts_lifecycle": {"ingest/checksums.json": "missing"},
        }
    ]
    v = validate_run_snapshot(stages=stages)
    assert any(x.code == "T1" for x in v)


def test_t8_outputs_view_pending_on_done_stage() -> None:
    stages = [
        {
            "id": "audio_preclean",
            "status": "done",
            "outputs_view": [{"path": "preclean/provider.json", "status": "pending", "phase": "missing"}],
        }
    ]
    v = validate_run_snapshot(stages=stages)
    assert any(x.code == "T8" for x in v)


def test_skip_artifacts_allowed() -> None:
    stages = [
        {
            "id": "audio_preclean",
            "status": "done",
            "artifacts_status": {"preclean/provider.json": "pending"},
            "artifacts_lifecycle": {"preclean/provider.json": "n_a"},
            "outputs_view": [{"path": "preclean/provider.json", "status": "n_a", "phase": "n_a"}],
        }
    ]
    assert not validate_run_snapshot(stages=stages)
