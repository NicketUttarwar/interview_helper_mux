from __future__ import annotations

from interview_mux.legacy_stage_warnings import legacy_sfx_warnings
from interview_mux.run_context import RunContext


def test_legacy_warnings_when_old_stage_done(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_legacy", create=True)
    ctx.mark_done("elevenlabs_sfx_flow1", force=True)
    warnings = legacy_sfx_warnings(ctx)
    assert warnings
    assert "elevenlabs_sfx_flow1" in warnings[0]


def test_no_legacy_warnings_on_clean_run(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_clean", create=True)
    assert legacy_sfx_warnings(ctx) == []
