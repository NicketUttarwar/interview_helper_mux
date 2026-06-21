"""MMAudio SFX generation hard-fail after retry."""

from __future__ import annotations

import pytest

from interview_mux.run_context import RunContext
from interview_mux.session_log import read_log
from interview_mux.stages import sfx_mmaudio


def test_generate_with_retry_hard_fail_logs_and_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("run_mmaudio_fail", create=True)
    out = tmp_path / "out.wav"

    def always_fail(**kwargs):
        raise sfx_mmaudio.MMAudioUnavailable("timeout")

    monkeypatch.setattr(sfx_mmaudio, "generate_text_to_audio", always_fail)

    with pytest.raises(sfx_mmaudio.MMAudioUnavailable, match="timeout"):
        sfx_mmaudio._generate_with_retry(
            ctx=ctx,
            stage="mmaudio_sfx_flow1",
            asset_id="bed_a",
            params={"prompt": "x", "negative_prompt": "", "duration_seconds": 2.0},
            out_file=out,
        )

    entries = read_log(ctx.run_dir, tail=10)
    errors = [e for e in entries if e.get("level") == "error"]
    assert any("MMAudio SFX failed for bed_a" in e.get("message", "") for e in errors)
    warnings = [e for e in entries if e.get("level") == "warning"]
    assert any("MMAudio retry for bed_a" in e.get("message", "") for e in warnings)
