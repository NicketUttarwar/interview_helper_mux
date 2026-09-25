"""vo_synthesize S1–S5 simplify pins (high-risk audit MODE=fix)."""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from interview_mux.stages import vo_synthesize as vs_mod
from interview_mux.stages.vo_line_adjudicate import _maybe_full_auto_record_to_synth
from interview_mux.vo_contract import vo_synthesize_render_incompleteness
from run_fixtures import isolated_run_ctx


def test_s1_run_vo_synthesize_source_has_no_edl_restamp() -> None:
    src = inspect.getsource(vs_mod.run_vo_synthesize)
    assert "restamp_edl_transition_source_paths" not in src
    assert "restamp_edl_vo_pickup_source_paths" not in src
    assert "write_live_edl" not in src


def test_s3_run_vo_synthesize_source_has_no_record_rewrite() -> None:
    src = inspect.getsource(vs_mod.run_vo_synthesize)
    assert "rewrite_full_auto_record_lines_to_synth" not in src
    assert callable(_maybe_full_auto_record_to_synth)


def test_s6_orientation_peeled_to_adjudicate() -> None:
    from interview_mux.stages.vo_line_adjudicate import _prep_opening_orientation

    src = inspect.getsource(vs_mod.run_vo_synthesize)
    assert "retarget_orientation_to_open" not in src
    assert "revive_required_opening_orientation" not in src
    prep = inspect.getsource(_prep_opening_orientation)
    assert "retarget_orientation_to_open" in prep
    assert "revive_required_opening_orientation" in prep


def test_s7_one_render_helper_covers_transition_and_gap() -> None:
    src = inspect.getsource(vs_mod._render_required_vo_wavs)
    assert "synthesize_spoken_transitions" in src
    assert "resync_required_synthesize_wavs" in src
    assert "heal_seated_bind_mismatch" in src
    run_src = inspect.getsource(vs_mod.run_vo_synthesize)
    assert "_render_required_vo_wavs" in run_src


def test_s4_render_incompleteness_ssot(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "vs_s4")
    reason = vo_synthesize_render_incompleteness(ctx)
    assert reason == "master/transitions.json is pending"


def test_s5_approve_incomplete_raises_not_fail_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import interview_mux.stage_resilience as resilience_mod
    from interview_mux.write_staging import approve_stage_writes

    ctx = isolated_run_ctx(tmp_path, "vs_s5")
    monkeypatch.setattr(
        "interview_mux.stage_completion.vo_synthesize_should_defer_done",
        lambda _c, _s: "seated synthesize VO missing WAV: vo_x",
    )
    monkeypatch.setattr(
        resilience_mod,
        "validate_staged_before_flush",
        lambda *_a, **_k: SimpleNamespace(
            action="continue", acceptance_ok=True, reasons=[]
        ),
    )
    monkeypatch.setattr(
        resilience_mod,
        "after_flush_resilience",
        lambda *_a, **_k: SimpleNamespace(
            action="continue", acceptance_ok=True, reasons=[]
        ),
    )
    monkeypatch.setattr(
        resilience_mod,
        "record_resilience_event",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.write_staging.flush_stage_writes",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "interview_mux.artifact_lifecycle.apply_fingerprints_on_flush",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_lifecycle.post_commit_validate",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "interview_mux.operator_action_trace.end_action",
        lambda *_a, **_k: None,
    )
    with pytest.raises(RuntimeError, match="vo_synthesize incomplete"):
        approve_stage_writes(ctx, "vo_synthesize")
