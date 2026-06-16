from __future__ import annotations

import shutil
from pathlib import Path

from interview_mux.coherence.analyze import build_coherence_report
from interview_mux.prompt_validation import validate_coherence_report
from interview_mux.run_context import RunContext

FIXTURE = Path(__file__).parent / "fixtures" / "runs" / "coherence_30m_planted_drift"


def test_fixture_detects_planted_risks(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    run_dir = tmp_path / "planted"
    shutil.copytree(FIXTURE, run_dir)
    ctx = RunContext("planted", create=False)
    ctx.run_dir = run_dir
    report = build_coherence_report(ctx, phase="post_reanchor")
    assert report["gate"]["activated"] is True
    assert validate_coherence_report(report) == []
    kinds = {r["kind"] for r in report.get("risks") or []}
    assert "claim_contradiction" in kinds
    assert "missing_callback" in kinds
    drift = [r for r in report["risks"] if r["kind"] == "topic_drift"]
    decoy_only = all("decoy" not in str((r.get("evidence") or {})).lower() for r in drift)
    assert decoy_only or len(drift) == 0
