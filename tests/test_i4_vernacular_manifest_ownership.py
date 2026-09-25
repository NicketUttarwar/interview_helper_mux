"""i4: vernacular_segment_sanitize may persist segments/manifest.json.

exec_11871: sanitize computed a resplit then failed
authority_denied:persist:segments/manifest.json:vernacular_segment_sanitize
(not_allow:owner=segment_classification), finished hollow, and thrashed on
seed-order vs connector_fuse_pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.artifact_ownership import row_for_path, write_permitted
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "i4_vernacular_manifest")


def test_i4_vernacular_may_persist_manifest(ctx: RunContext) -> None:
    ok, reason = write_permitted(
        ctx,
        "segments/manifest.json",
        "vernacular_segment_sanitize",
        role="producer",
        verb="persist",
    )
    assert ok is True, reason


def test_i4_segment_classification_still_owns_manifest(ctx: RunContext) -> None:
    ok, reason = write_permitted(
        ctx,
        "segments/manifest.json",
        "segment_classification",
        role="producer",
        verb="persist",
    )
    assert ok is True, reason


def test_i4_vernacular_does_not_require_golden_facts_write(ctx: RunContext) -> None:
    """Sanitize must_keep lives on vernacular_must_keep.json — not golden facts."""
    ok, reason = write_permitted(
        ctx,
        "analysis/vernacular_must_keep.json",
        "vernacular_segment_sanitize",
        role="producer",
        verb="persist",
    )
    assert ok is True, reason
    ok_gf, reason_gf = write_permitted(
        ctx,
        "analysis/run_golden_facts.json",
        "vernacular_segment_sanitize",
        role="producer",
        verb="persist",
    )
    assert ok_gf is False
    assert "not_allow" in reason_gf or "owner" in reason_gf


def test_i5_connector_fuse_may_persist_manifest(ctx: RunContext) -> None:
    ok, reason = write_permitted(
        ctx,
        "segments/manifest.json",
        "connector_fuse_pass",
        role="producer",
        verb="persist",
    )
    assert ok is True, reason


def test_i6_connector_fuse_may_persist_boundaries_and_rounds(ctx: RunContext) -> None:
    for path in (
        "segments/boundaries.json",
        "analysis/connector_fuse_rounds.json",
    ):
        ok, reason = write_permitted(
            ctx, path, "connector_fuse_pass", role="producer", verb="persist"
        )
        assert ok is True, f"{path}: {reason}"


def test_i7_research_wave_field_notes_allowed(ctx: RunContext) -> None:
    ok, reason = write_permitted(
        ctx,
        "mastering/research/preclean_lineage.json",
        "mastering_research_waves",
        role="producer",
        verb="persist",
    )
    assert ok is True, reason
    assert reason == "operational"


def test_i8_voice_reference_candidates_allowed_for_gui(ctx: RunContext) -> None:
    """Voice reference gate must persist candidates/manifest under fail-closed ownership."""
    cand = "understanding/voice_reference/spk_1_candidates.json"
    ok, reason = write_permitted(ctx, cand, "", role="gui", verb="persist")
    assert ok is True, reason
    assert reason == "operational"
    ctx.write_json(cand, {"speaker_id": "spk_1", "segments": []}, stage_key="")
    assert ctx.artifact_exists(cand)

    man = "understanding/voice_reference/spk_1.json"
    ok2, reason2 = write_permitted(ctx, man, "", role="gui", verb="persist")
    assert ok2 is True, reason2
    ctx.write_json(
        man,
        {"speaker_id": "spk_1", "approved": True},
        stage_key="",
    )
    assert ctx.artifact_exists(man)


def test_i9_stage_runs_last_volley_input_allowed(ctx: RunContext) -> None:
    """Homunculus/LLM stages must persist stage_runs volley inputs under fail-closed ownership."""
    rel = "understanding/stage_runs/missing_framing/last_volley_input.json"
    ok, reason = write_permitted(
        ctx, rel, "missing_framing", role="producer", verb="persist"
    )
    assert ok is True, reason
    assert reason == "operational"
    ctx.write_json(rel, {"stage": "missing_framing", "segments": []}, stage_key="missing_framing")
    assert ctx.artifact_exists(rel)

    # Specialist sidecars under the same tree
    rel2 = "understanding/stage_runs/segment_classification/specialist_theme_coverage_pass.json"
    ok2, reason2 = write_permitted(
        ctx, rel2, "segment_classification", role="producer", verb="persist"
    )
    assert ok2 is True, reason2


def test_i10_evidence_packets_direct_child_allowed(ctx: RunContext) -> None:
    """evidence_packets live as direct children — **/ glob alone misses them."""
    rel = "mastering/evidence_packets/shape_confirm_pass2.json"
    ok, reason = write_permitted(
        ctx, rel, "mastering_plan_confirm", role="producer", verb="persist"
    )
    assert ok is True, reason
    assert reason == "operational"
    ctx.write_json(rel, {"pass": 2}, stage_key="mastering_plan_confirm")
    assert ctx.artifact_exists(rel)


def test_i11_refinement_champion_gap_vo_allowed(ctx: RunContext) -> None:
    rel = "understanding/refinement_champion/gap_vo.json"
    ok, reason = write_permitted(
        ctx, rel, "gap_framing_compose", role="producer", verb="persist"
    )
    assert ok is True, reason
    assert reason == "operational"
    ctx.write_json(rel, {"champion": True}, stage_key="gap_framing_compose")
    assert ctx.artifact_exists(rel)


def test_i12_full_master_ranking_reorder_bridges_allowed(ctx: RunContext) -> None:
    """Ranking apply must persist reorder_bridges (co-producer with sanitize/transitions)."""
    rel = "understanding/reorder_bridges.json"
    ok, reason = write_permitted(
        ctx, rel, "full_master_ranking", role="producer", verb="persist"
    )
    assert ok is True, reason
    ctx.write_json(rel, {"bridges": []}, stage_key="full_master_ranking")
    assert ctx.artifact_exists(rel)


def test_i13_information_package_plan_may_write_mastering_plan(ctx: RunContext) -> None:
    rel = "mastering/mastering_plan.json"
    ok, reason = write_permitted(
        ctx, rel, "information_package_plan", role="producer", verb="persist"
    )
    assert ok is True, reason
    ctx.write_json(rel, {"episode_close": {}}, stage_key="information_package_plan")
    assert ctx.artifact_exists(rel)


def test_i14_nugget_and_recompose_ownership(ctx: RunContext) -> None:
    """Layup + recompose must co-produce plan artifacts; VO transcript sidecars operational."""
    ok, reason = write_permitted(
        ctx,
        "mastering/mastering_plan.json",
        "nugget_layup_compose",
        role="producer",
        verb="persist",
    )
    assert ok is True, reason

    ok2, reason2 = write_permitted(
        ctx,
        "understanding/nugget_layup_plan.json",
        "gap_framing_recompose",
        role="producer",
        verb="persist",
    )
    assert ok2 is True, reason2

    ok3, reason3 = write_permitted(
        ctx,
        "transcripts/vo/vo_layup_seg_004.json",
        "nugget_layup_compose",
        role="producer",
        verb="persist",
    )
    assert ok3 is True, reason3
    assert reason3 == "operational"


def test_i15_selection_framing_apply_may_stamp_gap_omit_delivery(ctx: RunContext) -> None:
    """S9: framing apply may stamp omit/delivery/targets — not body text ownership."""
    ok, reason = write_permitted(
        ctx,
        "understanding/gap_report.json",
        "selection_framing_apply",
        role="producer",
        verb="persist",
        fields=("interviewer_lines[].targets_segment_id",),
    )
    assert ok is True, reason
    row = row_for_path("understanding/gap_report.json")
    assert row is not None
    assert "selection_framing_apply" not in row.producers
    assert row.authoritative == "nugget_layup_compose"


def test_i16_synthetic_context_packet_allowed_for_transitions(ctx: RunContext) -> None:
    ok, reason = write_permitted(
        ctx,
        "understanding/synthetic_context_packet.json",
        "transitions",
        role="producer",
        verb="persist",
    )
    assert ok is True, reason
    assert reason == "operational"
    ok2, reason2 = write_permitted(
        ctx,
        "understanding/synthetic_framing_plan.json",
        "transitions",
        role="producer",
        verb="persist",
    )
    assert ok2 is True, reason2


def test_i17_vo_line_adjudicate_and_shadow_ownership(ctx: RunContext) -> None:
    """S9: adjudicate stamps omit/delivery; shadow scores are operational sidecars."""
    ok, reason = write_permitted(
        ctx,
        "understanding/gap_report.json",
        "vo_line_adjudicate",
        role="producer",
        verb="persist",
        fields=("interviewer_lines[].skipped_optional",),
    )
    assert ok is True, reason
    row = row_for_path("understanding/gap_report.json")
    assert row is not None
    assert "vo_line_adjudicate" not in row.producers
    ok2, reason2 = write_permitted(
        ctx,
        "understanding/refinement_shadow/gap_framing_recompose.json",
        "gap_framing_recompose",
        role="producer",
        verb="persist",
    )
    assert ok2 is True, reason2
    assert reason2 == "operational"


def test_vs_b3_vo_synthesize_may_rewrite_gap_delivery(ctx: RunContext) -> None:
    """VS-B3: vo_synthesize ALLOW to persist delivery rewrite on gap_report."""
    ok, reason = write_permitted(
        ctx,
        "understanding/gap_report.json",
        "vo_synthesize",
        role="producer",
        verb="persist",
        fields=("interviewer_lines[].delivery",),
    )
    assert ok is True, reason


def test_i23_sound_design_plan_cue_writers_allowed(tmp_path, monkeypatch) -> None:
    """music_palette_compose / sfx_prompt_craft / vo_finalize seat cues into the SDP.

    exec_11871 halted on
    authority_denied:persist:understanding/sound_design_plan.json:music_palette_compose:edl_sealed
    even though that stage is the product writer of the music cue arrangement.
    """
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "i23_sdp_owners")
    rel = "understanding/sound_design_plan.json"

    for stage in (
        "sound_design_palettes",
        "sound_design_plan",
        "music_palette_compose",
        "sfx_prompt_craft",
        "sound_design_vo_finalize",
    ):
        allowed, reason = write_permitted(ctx, rel, stage, role="producer", verb="persist")
        assert allowed, f"{stage} must be able to seat SDP cues ({reason})"

    denied, _reason = write_permitted(ctx, rel, "mix", role="producer", verb="persist")
    assert not denied, "mix must not rewrite the sound design plan"


def test_i24_master_sfx_manifest_and_wavs_allowed(tmp_path, monkeypatch) -> None:
    """mmaudio_sfx writes generated beds + manifest under master/sfx/ (exec_11871 unknown_path)."""
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "i24_sfx_manifest")

    for rel in ("master/sfx/manifest.json", "master/sfx/show_theme_v1_stinger_01.wav"):
        allowed, reason = write_permitted(
            ctx, rel, "mmaudio_sfx", role="producer", verb="persist"
        )
        assert allowed, f"mmaudio_sfx must own {rel} ({reason})"

    allowed, _reason = write_permitted(
        ctx, "master/sfx/manifest.json", "mix", role="producer", verb="persist"
    )
    assert not allowed, "mix must not rewrite the generated sfx manifest"


def test_i27_junction_may_omit_from_selection(tmp_path, monkeypatch) -> None:
    """Junction fuse/omit of an unrecoverable incomplete cut must reach selection.

    exec_11871 stalled with two `unrecoverable_within_clip` criticals (seg_014
    chapter_bleed_incomplete, seg_071 on_a_roll) whose only resolution is
    fuse-into-neighbor / omit — both denied by
    authority_denied:persist:master/selection.json:junction_snip_qa.
    """
    monkeypatch.setenv("MUX_FORENSICS", "0")
    ctx = isolated_run_ctx(tmp_path, "i27_junction_omit")
    rel = "master/selection.json"

    for stage in (
        "full_master_ranking",
        "selection_order_sanitize",
        "selection",
        "junction_snip_qa",
    ):
        allowed, reason = write_permitted(ctx, rel, stage, role="producer", verb="persist")
        assert allowed, f"{stage} must be able to seat the selection omit ({reason})"

    for stage in ("edl", "mix", "master_finalize"):
        allowed, _reason = write_permitted(ctx, rel, stage, role="producer", verb="persist")
        assert not allowed, f"{stage} must never rewrite selection"
