"""End-A…F cousin fixtures (MUX_FORENSICS=0) — no End-G ledger reopen.

Also covers exec_11630 residual heal-classify cousins that End-* did not pin:
#16 gap-VO missing WAV must not map to phase_a_edl; #19 narrative QC prose
must classify as selection_edl_order_drift on edl_narrative_audit.
"""

from __future__ import annotations

import pytest

from interview_mux.artifact_ownership import write_permitted
from interview_mux.heal_routing import classify_heal_error
from interview_mux.recovery_controller import classify_error_class
from interview_mux.thrash_hardening import FAIL_CLASS_VO_G1, fail_class_for_failure
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setenv("INTERVIEW_MUX_ARTIFACT_OWNERSHIP_FAIL_CLOSED", "1")
    return isolated_run_ctx(tmp_path, "end_cousin")


def test_endc_cousin_edl_must_not_mint_transitions(ctx) -> None:
    ok, reason = write_permitted(
        ctx, "master/transitions.json", "edl", role="producer", verb="persist"
    )
    assert not ok
    assert "mint" in reason or "deny" in reason or "not_allow" in reason


def test_enda_cousin_edl_must_not_rewrite_gap_copy(ctx) -> None:
    ok, reason = write_permitted(
        ctx,
        "understanding/gap_report.json",
        "edl",
        role="producer",
        fields=("interviewer_lines[].text",),
        verb="persist",
    )
    assert not ok


def test_endb_cousin_foreign_gap_promote_denied(ctx) -> None:
    ok, reason = write_permitted(
        ctx,
        "understanding/gap_report.json",
        "edl",
        role="producer",
        verb="promote_pending",
    )
    assert not ok
    assert "non_owner" in reason or "deny" in reason or "not_allow" in reason


def test_ende_cousin_wrong_stage_key_air_order(ctx) -> None:
    # air_order producers are edl/mix/junction — random stage must not persist.
    ok, reason = write_permitted(
        ctx, "master/air_order.json", "chapter_close_hitch", role="producer"
    )
    assert not ok


def test_endf_cousin_omit_under_freeze_owner_only(ctx) -> None:
    ok_owner, _ = write_permitted(
        ctx, "understanding/omit_ledger.json", "air_contract_sanitize", role="producer"
    )
    ok_foreign, _ = write_permitted(
        ctx, "understanding/omit_ledger.json", "edl", role="producer"
    )
    assert ok_owner
    assert not ok_foreign


# --- exec_11630 residual classify cousins ---------------------------------


def test_exec11630_narrative_qc_speech_clips_prose_classifies_as_order_drift() -> None:
    """#19: exact edl_narrative_qc prose must heal as selection_edl_order_drift."""
    msg = (
        "master/edl.json: speech clips do not match final selection "
        "ordered_segment_ids; expected ['seg_002', 'seg_005'], got ['seg_002']. "
        "Re-run edl after saving timeline edits."
    )
    for stage in ("edl_narrative_audit", "edl_narrative", "edl", "mix"):
        assert (
            classify_error_class(stage, ValueError(msg)) == "selection_edl_order_drift"
        ), stage
    route = classify_heal_error(msg)
    assert route is not None
    assert route.from_stage == "edl"
    assert route.action == "rebuild_edl"


def test_exec11630_gap_vo_missing_wav_fail_class_is_vo_g1_not_phase_a() -> None:
    """#16: 'edl: gap VO lines missing WAV' must not sticky-count as phase_a_edl."""
    reason = "edl: gap VO lines missing WAV: ['vo_layup_seg_005', 'vo_layup_seg_020']"
    assert classify_error_class("edl", RuntimeError(reason)) == "vo_seated_coverage"
    assert fail_class_for_failure(stage="edl", reason=reason) == FAIL_CLASS_VO_G1


# --- Ownership cousin hunts (ghost omit / nested VO / junction / speakers) ---


def test_ghost_master_omit_ledger_is_unknown_path(ctx) -> None:
    """Ghost master/omit_ledger.json must never ALLOW — SSOT is understanding/."""
    ok, reason = write_permitted(
        ctx, "master/omit_ledger.json", "air_contract_sanitize", role="producer"
    )
    assert not ok
    assert reason == "unknown_path"
    ok_edl, reason_edl = write_permitted(
        ctx, "master/omit_ledger.json", "edl", role="producer"
    )
    assert not ok_edl
    assert reason_edl == "unknown_path"


def test_nested_vo_under_edl_owner_promote_ok_foreign_deny(ctx) -> None:
    """Nested VO: vo_synthesize may persist/promote; edl promote_pending DENY."""
    ok_owner_persist, _ = write_permitted(
        ctx, "vo_pickup/vo_layup_seg_005.wav", "vo_synthesize", role="producer"
    )
    ok_owner_promote, _ = write_permitted(
        ctx,
        "vo_pickup/vo_layup_seg_005.wav",
        "vo_synthesize",
        role="producer",
        verb="promote_pending",
    )
    ok_edl_promote, reason = write_permitted(
        ctx,
        "vo_pickup/vo_layup_seg_005.wav",
        "edl",
        role="producer",
        verb="promote_pending",
    )
    assert ok_owner_persist
    assert ok_owner_promote
    assert not ok_edl_promote
    assert "non_owner" in reason or "deny" in reason or "not_allow" in reason


def test_foreign_edl_promote_gap_still_denied(ctx) -> None:
    ok, reason = write_permitted(
        ctx,
        "understanding/gap_report.json",
        "edl",
        role="producer",
        verb="promote_pending",
    )
    assert not ok
    assert "non_owner" in reason or "deny" in reason or "not_allow" in reason


def test_remutate_edl_must_not_mint_transitions(ctx) -> None:
    """End-C remutate cousin: edl never mints transitions.json (persist)."""
    ok, reason = write_permitted(
        ctx, "master/transitions.json", "edl", role="producer", verb="persist"
    )
    assert not ok
    assert "mint" in reason or "deny" in reason or "not_allow" in reason


def test_junction_exclude_paths_foreign_stage_denied(ctx) -> None:
    """chapter_close_hitch / random stage cannot write junction-owned bodies.

    Feel/thought audits are write_mode=operational (telemetry) — not exclude
    authority. Exclude authority lives on junction_snip_qa.json / seam_autopsy.
    """
    for path in ("master/junction_snip_qa.json", "master/seam_autopsy.json"):
        for stage in ("chapter_close_hitch", "edl", "full_master_ranking"):
            ok, reason = write_permitted(ctx, path, stage, role="producer")
            assert not ok, f"{path} unexpectedly ALLOW for {stage}: {reason}"
        ok_owner, _ = write_permitted(
            ctx, path, "junction_snip_qa", role="producer"
        )
        assert ok_owner, path


def test_speakers_manifest_foreign_stage_denied(ctx) -> None:
    """Analysis speakers/manifest: only catalog owners may persist."""
    ok_spk, _ = write_permitted(
        ctx, "understanding/speakers.json", "speaker_roles", role="producer"
    )
    ok_spk_foreign, reason_spk = write_permitted(
        ctx, "understanding/speakers.json", "edl", role="producer"
    )
    ok_man, _ = write_permitted(
        ctx, "segments/manifest.json", "segment_classification", role="producer"
    )
    ok_man_foreign, reason_man = write_permitted(
        ctx, "segments/manifest.json", "edl", role="producer"
    )
    assert ok_spk
    assert not ok_spk_foreign
    assert "not_allow" in reason_spk or "deny" in reason_spk
    assert ok_man
    assert not ok_man_foreign
    assert "not_allow" in reason_man or "deny" in reason_man
