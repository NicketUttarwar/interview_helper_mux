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


def test_reconcile_stage_status_downgrades_done():
    from interview_mux.ui_truth import reconcile_stage_status

    stage = {
        "id": "speaker_roles",
        "status": "done",
        "artifacts_status": {"understanding/speakers.json": "pending"},
        "artifacts_lifecycle": {"understanding/speakers.json": "missing"},
    }
    reconcile_stage_status(stage)
    assert stage["status"] == "incomplete"
    assert "speakers.json" in stage.get("incomplete_reason", "")


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


def test_t10_complete_job_no_write_approval_fields() -> None:
    job = {
        "status": "complete",
        "stage": "audio_preclean",
        "awaiting_write_approval": True,
        "pending_write_stage": "audio_preclean",
    }
    v = validate_run_snapshot(stages=[], job=job)
    assert any(x.code == "T10" for x in v)

    clean_job = {"status": "complete", "stage": "ingest"}
    assert not validate_run_snapshot(stages=[], job=clean_job)
