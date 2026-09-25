"""EDL S1–S5 simplify: cut-only stage — no nested VO, spoof, orientation kitchen, glue mint."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from interview_mux.stages import assembly
from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "edl_s1_s5")


def test_edl_s1_no_nested_vo_kitchen_in_run_edl_source() -> None:
    src = inspect.getsource(assembly.run_edl)
    assert "resync_required_synthesize_wavs" not in src
    assert "heal_seated_bind_mismatch" not in src
    assert "synthesize_spoken_transitions" not in src
    assert "resync_spoken_transitions" not in src


def test_edl_s2_no_spoofed_foreign_stage_keys() -> None:
    src = inspect.getsource(assembly.run_edl)
    assert 'stage="nugget_layup_compose"' not in src
    assert 'stage_key="transitions"' not in src
    assert "adopt_layup_plan_to_selection" not in src


def test_edl_s3_no_orientation_ensure_in_edl() -> None:
    src = inspect.getsource(assembly.run_edl)
    assert "ensure_episode_orientation" not in src
    assert "retarget_orientation_to_open" not in src
    assert "revive_required_opening_orientation" not in src
    assert "validate_opening_orientation" in src


def test_edl_s4_no_seam_glue_mint_in_edl() -> None:
    src = inspect.getsource(assembly.run_edl)
    assert "ensure_seam_glue" not in src
    assert "bridge_completeness incomplete" in src


def test_edl_s5_no_selection_mutate_persist_kitchen() -> None:
    src = inspect.getsource(assembly.run_edl)
    assert "_prepare_locked_selection" not in src
    assert "_persist_selection_for_edl" not in src
    assert "enforce_air_script_omits" not in src
    assert "bump_order_lock" not in src


def test_edl_no_hollow_mark_done_on_exception() -> None:
    """Incompleteness / heal exceptions must not soft-stamp .stage_done/edl."""
    src = inspect.getsource(assembly.run_edl)
    assert 'ctx.mark_done("edl")' not in src
    assert "refusing hollow done" in src


def test_edl_s3_orientation_lives_on_vo_line_adjudicate() -> None:
    from interview_mux.stages import vo_line_adjudicate, vo_synthesize

    adj = inspect.getsource(vo_line_adjudicate.run_vo_line_adjudicate)
    assert (
        "retarget_orientation_to_open" in adj
        or "_prep_opening_orientation" in adj
        or "_pre_synth_gap_stamps" in adj
    )
    src = inspect.getsource(vo_synthesize.run_vo_synthesize)
    assert "retarget_orientation_to_open" not in src
    assert "revive_required_opening_orientation" not in src
    # Helper body (imported in adjudicate) still names the orientation ops.
    prep = inspect.getsource(vo_line_adjudicate._prep_opening_orientation)
    assert "retarget_orientation_to_open" in prep
    assert "revive_required_opening_orientation" in prep


def test_edl_s4_seam_glue_lives_on_transitions() -> None:
    from interview_mux.stages import selection

    src = inspect.getsource(selection.run_transitions)
    assert "ensure_seam_glue" in src


def test_edl_s1_missing_vo_refuses_without_resync(
    ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(assembly, "check_narrative_qc", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "interview_mux.edl_narrative_remutate.narrative_audit_blocks_edl",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "interview_mux.nugget_layup.assert_layup_fresh_vs_selection",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.nugget_layup.assert_gap_report_layup_authority",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.air_order_integrity.audit_and_report",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "interview_mux.bridge_completeness.missing_reorder_bridges",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "interview_mux.bridge_completeness.assert_bridges_complete",
        lambda *_a, **_k: {"complete": True, "missing_count": 0, "missing": []},
    )
    monkeypatch.setattr(
        "interview_mux.gap_vo_gates.gap_framing_enabled",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "interview_mux.transition_vo.assert_spoken_transitions_audible",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(assembly, "check_edl_qc", lambda *_a, **_k: None)
    monkeypatch.setattr(assembly, "check_edl_narrative_qc", lambda *_a, **_k: None)

    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_a"], "excluded_segment_ids": []},
        stage_key="selection_order_sanitize",
    )
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(minimal_manifest_segment("seg_a", start_ms=0, end_ms=1000)),
        skip_handoff=True,
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_need",
                    "text": "Need a WAV.",
                    "delivery": "synthesize",
                    "required": True,
                    "placement": "before",
                    "targets_segment_id": "seg_a",
                }
            ]
        },
        stage_key="nugget_layup_compose",
    )
    ctx.write_json("master/transitions.json", {"transitions": []}, stage_key="transitions")
    ctx.write_json(
        "understanding/reorder_bridges.json",
        {"pairs": []},
        stage_key="transitions",
    )

    with pytest.raises(RuntimeError, match="gap VO lines missing WAV"):
        assembly.run_edl(ctx)
