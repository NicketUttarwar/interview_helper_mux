from __future__ import annotations

import shutil
from pathlib import Path

from interview_mux.coherence import maybe_run_coherence_analysis
from interview_mux.run_context import RunContext

FIXTURE = Path(__file__).parent / "fixtures" / "runs" / "coherence_30m_planted_drift"


def test_post_reanchor_hook_writes_report(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    run_dir = tmp_path / "hook"
    shutil.copytree(FIXTURE, run_dir)
    ctx = RunContext("hook", create=False)
    ctx.run_dir = run_dir
    count = maybe_run_coherence_analysis(ctx, phase="post_reanchor")
    assert (run_dir / "understanding" / "coherence_report.json").is_file()
    assert count >= 0
