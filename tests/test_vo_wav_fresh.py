from __future__ import annotations

import sys
import wave
from pathlib import Path

from interview_mux import s2s_runner
from interview_mux.vo_line_adjudicate import lines_needing_adjudicate
from interview_mux.vo_synthesis_audit import (
    line_vo_wav_fresh,
    nuke_all_synth_wavs_on_adjudicate_change,
    record_synthesis,
    should_skip_adjudicate_for_line,
    synthesis_entry_for_line,
    synthesis_entry_matches_line,
)
from run_fixtures import isolated_run_ctx, patch_merged_config

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))


def _wav(path: Path, duration_ms: int = 300) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 48_000
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(rate * duration_ms / 1000))


def _patch_vo_qc_off(monkeypatch) -> None:
    patch_merged_config(
        monkeypatch,
        {
            "analysis": {
                "gap_vo": {
                    "post_synthesis_qc": {
                        "enabled": False,
                        "speech_qa_enabled": False,
                    }
                }
            }
        },
    )
    monkeypatch.setattr(
        "interview_mux.vo_speech_qa.vo_passes_speech_qa",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "interview_mux.vo_synthesis_audit.analyze_vo_wav",
        lambda *_a, **_k: {"pass": True, "reasons": []},
    )


def _base_line(**overrides) -> dict:
    row = {
        "line_id": "line_1",
        "text": "Protein buyers rewrote the addressable market.",
        "targets_segment_id": "seg_1",
        "placement": "before",
        "delivery": "synthesize",
        "gap_type": "missing_question",
    }
    row.update(overrides)
    return row


def test_stale_script_hash_rejects_fresh_wav(tmp_path, monkeypatch) -> None:
    _patch_vo_qc_off(monkeypatch)
    ctx = isolated_run_ctx(tmp_path, "run_stale_fresh")
    wav = ctx.path("vo_pickup", "synthesized", "line_1.wav")
    _wav(wav)
    original = _base_line()
    record_synthesis(ctx, original, backend="mlx_audio", out_wav=wav)
    changed = _base_line(text="What made the deal possible?")

    matches, reason = synthesis_entry_matches_line(ctx, changed)
    assert matches is False
    assert reason == "stale_script_hash"

    fresh, fresh_reason = line_vo_wav_fresh(ctx, changed)
    assert fresh is False
    assert fresh_reason == "stale_script_hash"

    skip, skip_reason = should_skip_adjudicate_for_line(ctx, changed)
    assert skip is False
    assert skip_reason == "stale_script_hash"


def test_fresh_match_skips_adjudicate(tmp_path, monkeypatch) -> None:
    _patch_vo_qc_off(monkeypatch)
    ctx = isolated_run_ctx(tmp_path, "run_fresh_match")
    wav = ctx.path("vo_pickup", "synthesized", "line_1.wav")
    _wav(wav)
    line = _base_line()
    record_synthesis(ctx, line, backend="mlx_audio", out_wav=wav)

    fresh, reason = line_vo_wav_fresh(ctx, line)
    assert fresh is True
    assert reason in {"match", "script_match_stale_context"}

    skip, _ = should_skip_adjudicate_for_line(ctx, line)
    assert skip is True


def test_lines_needing_adjudicate_filters_fresh_wav(tmp_path, monkeypatch) -> None:
    _patch_vo_qc_off(monkeypatch)
    ctx = isolated_run_ctx(tmp_path, "run_lines_needing")
    wav = ctx.path("vo_pickup", "synthesized", "line_fresh.wav")
    _wav(wav)
    fresh_line = _base_line(line_id="line_fresh")
    stale_line = _base_line(
        line_id="line_stale",
        text="A rewritten host question after adjudicate.",
    )
    record_synthesis(ctx, fresh_line, backend="mlx_audio", out_wav=wav)
    gap_report = {"interviewer_lines": [fresh_line, stale_line]}
    ctx.write_json("understanding/gap_report.json", gap_report, skip_handoff=True)

    needing = lines_needing_adjudicate(ctx, gap_report)
    ids = {str(row.get("line_id")) for row in needing}
    assert "line_stale" in ids
    assert "line_fresh" not in ids


def test_s2s_resynth_on_script_drift(tmp_path, monkeypatch) -> None:
    _patch_vo_qc_off(monkeypatch)
    ctx = isolated_run_ctx(tmp_path, "run_s2s_resynth")
    wav = ctx.path("vo_pickup", "synthesized", "line_1.wav")
    _wav(wav, duration_ms=400)
    original = _base_line()
    record_synthesis(ctx, original, backend="mlx_audio", out_wav=wav)
    changed = _base_line(text="What made the deal possible?")
    calls: list[str] = []

    monkeypatch.setattr("interview_mux.s2s_runner.s2s_enabled", lambda: True)
    monkeypatch.setattr(
        "interview_mux.s2s_runner.resolve_reference_audio",
        lambda _c, _l: Path("/tmp/ref.wav"),
    )
    monkeypatch.setattr("interview_mux.s2s_runner.context_clip_for_line", lambda *_a: None)
    monkeypatch.setattr("interview_mux.s2s_runner.resolve_s2s_model_id", lambda: "test-model")

    def _fake_runtime(*_args, payload=None, **_k):
        body = payload if isinstance(payload, dict) else (_args[2] if len(_args) > 2 else {})
        calls.append(str(body.get("text") or ""))
        out = Path(str(body.get("out_wav") or ""))
        _wav(out, duration_ms=400)
        return {"ok": True}

    monkeypatch.setattr("interview_mux.s2s_runner.run_runtime_json", _fake_runtime)
    monkeypatch.setattr("interview_mux.s2s_runner._append_qa_sidecar", lambda *_a, **_k: None)
    monkeypatch.setattr("interview_mux.chatterbox_runner.should_use_chatterbox", lambda _c: False)
    monkeypatch.setattr(
        "interview_mux.s2s_runner.promote_synthesized_vo",
        lambda ctx, *, line_id, src: src,
    )

    out = s2s_runner.synthesize_line(ctx, changed, mode="synthesize")
    assert calls, "stale_script_hash must fall through to re-synth"
    assert "What made the deal possible?" in calls[0]
    assert out.is_file()
    assert out.stat().st_size > 1000


def test_nuke_all_synth_wavs_on_adjudicate_change(tmp_path, monkeypatch) -> None:
    _patch_vo_qc_off(monkeypatch)
    ctx = isolated_run_ctx(tmp_path, "run_nuke_synth")
    top = ctx.path("vo_pickup", "line_1.wav")
    sub = ctx.path("vo_pickup", "synthesized", "line_2.wav")
    _wav(top)
    _wav(sub)
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                _base_line(line_id="line_1"),
                _base_line(line_id="line_2", text="Second line."),
            ]
        },
        skip_handoff=True,
    )
    record_synthesis(ctx, _base_line(line_id="line_1"), backend="mlx_audio", out_wav=top)
    record_synthesis(
        ctx,
        _base_line(line_id="line_2", text="Second line."),
        backend="mlx_audio",
        out_wav=sub,
    )
    ctx.mark_done("vo_synthesize", force=True)
    ctx.mark_done("edl_narrative_audit", force=True)

    deleted = nuke_all_synth_wavs_on_adjudicate_change(ctx)
    assert deleted == 2
    assert not top.is_file()
    assert not sub.is_file()
    assert synthesis_entry_for_line(ctx, "line_1") is None
    assert synthesis_entry_for_line(ctx, "line_2") is None
    assert not ctx.is_done("vo_synthesize")
    assert not ctx.is_done("edl_narrative_audit")
