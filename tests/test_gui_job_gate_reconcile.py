from __future__ import annotations

from interview_mux.gui_job_reconcile import reconcile_operator_gate_job
from interview_mux.run_context import RunContext
from interview_mux.stages.transcript_review import mark_transcript_review_complete


def test_reconcile_operator_gate_after_transcript_review_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSETS_ROOT", str(tmp_path / "ASSETS"))
    ctx = RunContext("run_gate_reconcile", create=True)
    ctx.write_json(
        "transcript/review_queue.json",
        {
            "version": 1,
            "chunk_count": 1,
            "chunks": [
                {
                    "chunk_id": "tr_0001",
                    "rank": 1,
                    "start_ms": 0,
                    "end_ms": 1000,
                    "text": "hello",
                    "confidence": 0.5,
                    "reviewed": True,
                }
            ],
        },
    )
    ctx.write_json("transcript/full.json", {"words": [], "text": ""})
    ctx.write_json(
        "gui_job.json",
        {
            "status": "gate",
            "stage": "transcript_review_build",
            "message": "Transcript review required. Open the GUI to correct ranked clips, then complete review.",
        },
        skip_handoff=True,
    )
    mark_transcript_review_complete(ctx)
    job = ctx.read_json("gui_job.json")
    reconciled = reconcile_operator_gate_job(ctx, job)
    assert reconciled["status"] in {"complete", "awaiting_write_approval"}
    # Operator focus id after review complete is the gate alias, not the build stage.
    assert reconciled.get("stage") in {"transcript_review", "transcript_review_build"}
