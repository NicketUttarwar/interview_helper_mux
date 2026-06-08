from interview_mux.nle_state import save_nle
from interview_mux.operator_quality import record_qc_summary
from interview_mux.run_context import RunContext


def test_record_qc_summary_merges(tmp_path):
    ctx = RunContext("run_qc", create=True)
    ctx.write_json("run_meta.json", {"execution_id": "run_qc"})
    record_qc_summary(ctx, "narrative_qc", {"passed": True, "errors": []})
    meta = ctx.read_json("run_meta.json")
    assert meta["qc_summaries"]["narrative_qc"]["passed"] is True


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
