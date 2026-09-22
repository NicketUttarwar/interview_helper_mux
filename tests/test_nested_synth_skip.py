"""Cascade: Partial nested Chatterbox skip-not-stamp (cross-surface H-1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.gap_vo_gates import nested_synth_may_mint
from interview_mux.stages.assembly import resync_required_synthesize_wavs
from interview_mux.transition_vo import resync_spoken_transitions
from run_fixtures import isolated_run_ctx


def _partial_framing_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "nested_synth_skip")
    ctx.write_json(
        "run_meta.json",
        {
            "partial_auto": True,
            "run_mode": "partially-accelerated",
            "gap_framing_enabled": True,
            "gap_vo_delivery": "chatterbox",
            # Consent / pickup intentionally open — ladder not ready.
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/speakers.json",
        {
            "speakers": [
                {"speaker_id": "spk_host", "role": "interviewer", "confidence": 0.9},
                {"speaker_id": "spk_guest", "role": "interviewee", "confidence": 0.9},
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/source_topology.json",
        {
            "topology_class": "one_on_one_asymmetric",
            "pickup_eligible_speaker_id": "spk_host",
            "least_spoken_speaker_id": "spk_host",
            "speaker_stats": [
                {"speaker_id": "spk_host", "role": "interviewer", "talk_time_ms": 5_000},
                {"speaker_id": "spk_guest", "role": "interviewee", "talk_time_ms": 90_000},
            ],
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/flow_adaptation.json",
        {
            "pickup_eligible_speaker_id": "spk_host",
            "operator_overrides": {"gap_framing_enabled": True},
        },
        skip_handoff=True,
    )
    return ctx


def test_nested_synth_may_mint_skips_partial_when_ladder_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _partial_framing_ctx(tmp_path, monkeypatch)
    ok, note = nested_synth_may_mint(ctx)
    assert ok is False
    assert note.startswith("nested_synth_skipped:vo_path_not_ready:")
    meta = ctx.read_json("run_meta.json")
    assert "voice_clone_consent" not in meta
    assert meta.get("pickup_speaker_confirmed") is not True


def test_resync_gap_skips_mint_no_systemexit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _partial_framing_ctx(tmp_path, monkeypatch)
    called: list[str] = []

    def _boom(_ctx, row, *, mode="synthesize"):
        called.append(str(row.get("line_id")))
        raise AssertionError("must not mint")

    monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", _boom)
    line = {
        "line_id": "vo_preface_episode_orientation",
        "episode_orientation": True,
        "text": "Welcome.",
        "targets_segment_id": "seg_a",
        "placement": "before",
        "delivery": "synthesize",
    }
    notes = resync_required_synthesize_wavs(ctx, {"interviewer_lines": [line]})
    assert called == []
    assert notes and notes[0].startswith("nested_synth_skipped:vo_path_not_ready")
    assert not list(ctx.path("vo_pickup", "synthesized").glob("*.wav"))


def test_resync_transitions_skips_mint_no_systemexit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _partial_framing_ctx(tmp_path, monkeypatch)
    ctx.write_json(
        "master/transitions.json",
        {
            "transitions": [
                {
                    "type": "spoken",
                    "after_segment_id": "seg_a",
                    "before_segment_id": "seg_b",
                    "text": "And next.",
                }
            ]
        },
        skip_handoff=True,
    )
    called: list[str] = []

    def _boom(_ctx, row, *, mode="synthesize"):
        called.append(str(row.get("line_id")))
        raise AssertionError("must not mint")

    monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", _boom)
    notes = resync_spoken_transitions(ctx)
    assert called == []
    assert notes and notes[0].startswith("nested_synth_skipped:vo_path_not_ready")


def test_resync_gap_probe_error_skips_not_mints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DP-NESTED-SYNTH A: nested_synth_may_mint boom → skip, never mint."""
    ctx = _partial_framing_ctx(tmp_path, monkeypatch)
    called: list[str] = []

    def _boom_mint(_ctx, row, *, mode="synthesize"):
        called.append("mint")
        raise AssertionError("must not mint")

    def _boom_gate(*_a, **_k):
        raise RuntimeError("gate probe boom")

    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.nested_synth_may_mint",
        _boom_gate,
    )
    monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", _boom_mint)
    line = {
        "line_id": "vo_preface_episode_orientation",
        "episode_orientation": True,
        "text": "Welcome.",
        "targets_segment_id": "seg_a",
        "placement": "before",
        "delivery": "synthesize",
        "required": True,
    }
    notes = resync_required_synthesize_wavs(ctx, {"interviewer_lines": [line]})
    assert called == []
    assert notes and notes[0].startswith("nested_synth_skipped:probe_error")


def test_resync_transitions_probe_error_skips_not_mints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _partial_framing_ctx(tmp_path, monkeypatch)
    ctx.write_json(
        "master/transitions.json",
        {
            "transitions": [
                {
                    "type": "spoken",
                    "after_segment_id": "seg_a",
                    "before_segment_id": "seg_b",
                    "text": "And next.",
                }
            ]
        },
        skip_handoff=True,
    )
    called: list[str] = []

    def _boom_mint(_ctx, row, *, mode="synthesize"):
        called.append("mint")
        raise AssertionError("must not mint")

    def _boom_gate(*_a, **_k):
        raise RuntimeError("gate probe boom")

    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.nested_synth_may_mint",
        _boom_gate,
    )
    monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", _boom_mint)
    notes = resync_spoken_transitions(ctx)
    assert called == []
    assert notes and notes[0].startswith("nested_synth_skipped:probe_error")


def test_framing_detect_exception_skips_not_mints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Residual #1: framing probe boom must not fail-open to ungated mint."""
    ctx = _partial_framing_ctx(tmp_path, monkeypatch)
    called: list[str] = []

    def _boom_mint(_ctx, row, *, mode="synthesize"):
        called.append(str(row.get("line_id")))
        raise AssertionError("must not mint")

    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.framing_requires_nested_synth_gate",
        lambda _ctx: (_ for _ in ()).throw(RuntimeError("framing detect boom")),
    )
    monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", _boom_mint)
    line = {
        "line_id": "vo_preface_episode_orientation",
        "episode_orientation": True,
        "text": "Welcome.",
        "targets_segment_id": "seg_a",
        "placement": "before",
        "delivery": "synthesize",
        "required": True,
    }
    notes = resync_required_synthesize_wavs(ctx, {"interviewer_lines": [line]})
    assert called == []
    assert notes and (
        notes[0].startswith("nested_synth_skipped:vo_path_not_ready")
        or notes[0].startswith("nested_synth_skipped:probe_error")
    )


def test_framing_yes_record_delivery_skips_nested_mint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Residual #2: framing Yes + delivery not Chatterbox still gates (skip)."""
    ctx = _partial_framing_ctx(tmp_path, monkeypatch)
    meta = ctx.read_json("run_meta.json")
    meta["gap_vo_delivery"] = "record"
    ctx.write_json("run_meta.json", meta, skip_handoff=True)
    called: list[str] = []

    def _boom_mint(_ctx, row, *, mode="synthesize"):
        called.append(str(row.get("line_id")))
        raise AssertionError("must not mint")

    monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", _boom_mint)
    line = {
        "line_id": "vo_preface_episode_orientation",
        "episode_orientation": True,
        "text": "Welcome.",
        "targets_segment_id": "seg_a",
        "placement": "before",
        "delivery": "synthesize",
        "required": True,
    }
    notes = resync_required_synthesize_wavs(ctx, {"interviewer_lines": [line]})
    assert called == []
    assert notes and "record_delivery" in notes[0]


def test_vo_bind_heal_refuses_when_ladder_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Residual #3: vo_bind nested heal must honor mint SSOT at call site."""
    from interview_mux.vo_bind_authority import _try_resynth_seated_line

    ctx = _partial_framing_ctx(tmp_path, monkeypatch)
    called: list[str] = []

    def _boom_mint(_ctx, row, *, mode="synthesize"):
        called.append("mint")
        raise AssertionError("must not mint")

    monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", _boom_mint)
    ok = _try_resynth_seated_line(
        ctx,
        {
            "line_id": "vo_heal_line",
            "text": "Heal me.",
            "delivery": "synthesize",
        },
    )
    assert ok is False
    assert called == []


def test_host_tools_refuse_when_ladder_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Residual #3: host Chatterbox/S2S refuse before runner when ladder open."""
    from interview_mux.homunculus.host_tools import run_chatterbox_host, run_s2s_host

    ctx = _partial_framing_ctx(tmp_path, monkeypatch)
    called: list[str] = []

    def _boom_cb(_ctx, line):
        called.append("cb")
        raise AssertionError("must not mint")

    def _boom_s2s(_ctx, line, *, mode="synthesize"):
        called.append("s2s")
        raise AssertionError("must not mint")

    monkeypatch.setattr("interview_mux.chatterbox_runner.synthesize_line", _boom_cb)
    monkeypatch.setattr("interview_mux.s2s_runner.synthesize_line", _boom_s2s)
    out_cb = run_chatterbox_host(ctx, {"line_id": "h1", "text": "Hi"})
    out_s2s = run_s2s_host(ctx, {"line_id": "h2", "text": "Hi"})
    assert out_cb.get("ok") is False
    assert out_cb.get("error") == "vo_path_not_ready"
    assert out_s2s.get("ok") is False
    assert out_s2s.get("error") == "vo_path_not_ready"
    assert called == []
