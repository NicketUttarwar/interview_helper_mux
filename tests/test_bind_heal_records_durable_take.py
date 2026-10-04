"""A bind-heal take that Chatterbox wrote before erroring is recorded (ISSUES 154).

exec_014: the heal re-rendered vo_preface_episode_orientation, Chatterbox wrote the
WAV then failed its JSON report, the heal accepted the bytes but never recorded
the new script hash, and assert_seated_vo_rendered failed vo_synthesize on
stale_script_hash until the next attempt rendered it again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux import vo_bind_authority as vba


def test_durable_take_is_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wav = tmp_path / "vo_preface_episode_orientation.wav"
    recorded: list[dict] = []

    def _synth(ctx, line, mode="synthesize"):
        wav.write_bytes(b"RIFF....WAVE")
        raise RuntimeError("chatterbox: unparsable runtime JSON")

    monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", _synth)
    monkeypatch.setattr("interview_mux.gap_vo_gates.framing_requires_nested_synth_gate", lambda c: False)
    monkeypatch.setattr("interview_mux.write_staging.promote_owner_vo_pickup", lambda c: [])
    monkeypatch.setattr("interview_mux.write_staging.active_stage_id", lambda: "vo_synthesize")
    monkeypatch.setattr(vba, "_line_wav_present", lambda c, l: wav.is_file())
    monkeypatch.setattr("interview_mux.vo_synthesis_audit.line_vo_wav_path", lambda c, l: wav)
    monkeypatch.setattr(
        "interview_mux.vo_synthesis_audit.record_synthesis",
        lambda c, l, **kw: recorded.append({"line": l["line_id"], **kw}),
    )
    assert vba._try_resynth_seated_line(object(), {"line_id": "vo_preface_episode_orientation", "text": "New text."})
    assert recorded and recorded[0]["wav_just_rendered"] is True


def test_an_old_wav_is_not_recorded_as_new(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    wav = tmp_path / "old.wav"
    wav.write_bytes(b"RIFF....WAVE")
    os.utime(wav, (1, 1))
    recorded: list[dict] = []

    def _synth(ctx, line, mode="synthesize"):
        raise RuntimeError("renderer failed before writing")

    monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", _synth)
    monkeypatch.setattr("interview_mux.gap_vo_gates.framing_requires_nested_synth_gate", lambda c: False)
    monkeypatch.setattr("interview_mux.write_staging.promote_owner_vo_pickup", lambda c: [])
    monkeypatch.setattr("interview_mux.write_staging.active_stage_id", lambda: "vo_synthesize")
    monkeypatch.setattr(vba, "_line_wav_present", lambda c, l: True)
    monkeypatch.setattr("interview_mux.vo_synthesis_audit.line_vo_wav_path", lambda c, l: wav)
    monkeypatch.setattr(
        "interview_mux.vo_synthesis_audit.record_synthesis",
        lambda c, l, **kw: recorded.append(kw),
    )
    vba._try_resynth_seated_line(object(), {"line_id": "x", "text": "t"})
    assert recorded == []
