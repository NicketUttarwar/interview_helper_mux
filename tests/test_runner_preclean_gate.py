from interview_mux.nle_state import save_nle
from interview_mux.operator_quality import record_qc_summary
from interview_mux.run_context import RunContext
from interview_mux.web.runner import JobRunner


def test_record_qc_summary_merges(tmp_path):
    ctx = RunContext("run_qc", create=True)
    ctx.write_json("run_meta.json", {"execution_id": "run_qc"})
    record_qc_summary(ctx, "narrative_qc", {"passed": True, "errors": []})
    meta = ctx.read_json("run_meta.json")
    assert meta["qc_summaries"]["narrative_qc"]["passed"] is True


def test_runner_preclean_gate_flow_warning_payload(tmp_path, monkeypatch):
    ctx = RunContext("run_flow_warn", create=True)
    ctx.write_json("run_meta.json", {"execution_id": "run_flow_warn", "audio_preclean": {"offered_at": []}})
    runner = JobRunner()
    monkeypatch.setattr(
        "interview_mux.web.runner.merged_config",
        lambda: {"mix": {"require_preclean_acknowledgment": True}},
    )
    runner._write_job(ctx, {"status": "running", "mode": "flow1", "message": "Running flow1"})
    runner._check_preclean_gate(ctx, "mix_flow1", mode="flow1")
    job = ctx.read_json("gui_job.json")
    assert job["status"] == "running_with_warnings"
    assert {"checkpoint": "before_flow_mix", "stage": "mix_flow1"} in job["preclean_warnings"]


def test_runner_preclean_gate_needs_operator(tmp_path, monkeypatch):
    ctx = RunContext("run_preclean_gate", create=True)
    ctx.write_json("run_meta.json", {"execution_id": "run_preclean_gate", "audio_preclean": {"offered_at": []}})
    runner = JobRunner()
    monkeypatch.setattr(
        "interview_mux.web.runner.run_single_stage",
        lambda *_a, **_k: None,
    )
    try:
        runner._execute_single_stage(ctx, "mix_flow1", None)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "before_flow_mix" in str(exc)


def test_nle_strict_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "interview_mux.config.merged_config",
        lambda: {"nle_edits": {"strict": True}},
    )
    ctx = RunContext("run_nle", create=True)
    try:
        save_nle(ctx, {"segment_overrides": "bad"})
        assert False
    except ValueError:
        pass
