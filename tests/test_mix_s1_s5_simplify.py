"""mix S1–S5 simplify pins (high-risk audit MODE=fix)."""

from __future__ import annotations

import inspect

from interview_mux.mix_completeness import enforce_mix_completeness
from interview_mux.sound_design import _check_bed_presence_band, mix
from interview_mux.stages import assembly as assembly_mod
from run_fixtures import isolated_run_ctx


def test_s1_run_mix_has_no_post_mix_delight() -> None:
    src = inspect.getsource(assembly_mod.run_mix)
    assert "rerun_listen_delight_after_mix" not in src
    assert "listen_delight" not in src


def test_s2_mix_has_no_listenability_live_edl_write() -> None:
    src = inspect.getsource(mix)
    assert "mix_listenability" not in src
    assert "remediate_listenability_edl" not in src
    assert 'source="mix_realized_times"' in src or "mix_realized_times" in src


def test_s3_mix_has_no_recursive_remux() -> None:
    src = inspect.getsource(mix)
    assert "return mix(ctx, remux_cycle=" not in src
    assert "remux_cycle + 1" not in src
    assert "no remux re-admit" in src
    band = inspect.getsource(_check_bed_presence_band)
    assert "mutate_run_meta" not in band


def test_s4_run_mix_refuses_missing_pairs_no_commit() -> None:
    src = inspect.getsource(assembly_mod.run_mix)
    assert "commit_current_transition_wavs" not in src
    assert "restamp_edl_transition_source_paths" not in src
    assert "missing_transition_wav" in src
    mix_src = inspect.getsource(mix)
    assert "last_chance_synth_missing_clip" not in mix_src
    assert "missing_vo_wav" in mix_src


def test_s5_run_mix_seats_via_helper_only() -> None:
    src = inspect.getsource(assembly_mod.run_mix)
    assert "_seat_after_mix" in src
    assert "clear_remaster" not in src  # body peeled into helper
    seat = inspect.getsource(assembly_mod._seat_after_mix)
    assert "clear_remaster" in seat
    assert "note_speech_first_mix" in seat
    assert "mix_outputs_seated" in seat


def test_s4_completeness_no_longer_softens_via_last_chance(
    tmp_path, monkeypatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "mix_s4_comp")
    monkeypatch.setattr(
        "interview_mux.first_try.first_try_mode_enabled", lambda cfg=None: False
    )
    monkeypatch.setattr(
        "interview_mux.first_try.allow_placeholder_mix", lambda cfg=None: False
    )

    def fake_cfg():
        return {
            "mix": {
                "completeness_gate": {
                    "enabled": True,
                    "mode": "block",
                    "hard_fail_missing_blocking_vo": True,
                },
                "missing_vo_retry_once": True,  # stale flag must not soft-pass
            }
        }

    monkeypatch.setattr("interview_mux.mix_completeness.merged_config", fake_cfg)
    import pytest

    with pytest.raises(RuntimeError, match="missing mix assets"):
        enforce_mix_completeness(
            ctx,
            flow="podcast",
            stage="mix",
            missing_vo=["line_001"],
        )
