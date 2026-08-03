"""Local STT contract shapes and re-transcribe invalidation."""

from __future__ import annotations

from interview_mux.pipeline import ANALYSIS_ORDER
from interview_mux.run_context import RunContext


def test_retranscribe_clear_from_invalidates_downstream(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext(create=True)
    ctx.write_json("transcript/full.json", {"text": "hi", "words": []}, skip_handoff=True)
    ctx.mark_done("transcribe", force=True)
    ctx.mark_done("interview_spine_build", force=True)
    ctx.clear_from("transcribe", ANALYSIS_ORDER)
    assert not ctx.is_done("interview_spine_build")


def test_transcribe_local_module_uses_local_runtime_not_boto3():
    from pathlib import Path

    text = Path("src/interview_mux/stages/transcribe_local.py").read_text(encoding="utf-8")
    assert "boto3" not in text
    assert "stt_runner" in text
    assert "transcribe_audio" in text
