"""i29/i30: the junction incomplete-cut ladder must be able to finish its work.

exec_11871 spun on ``incomplete_cut_unresolved`` (mix refused → junction pinned →
junction refused) for two reasons found in this run:

* i29 — ``run_junction_feel_audit`` runs nested inside ``run_junction_snip_qa``
  and unconditionally deleted the ``_junction_snip_qa_inner`` marker on exit, so
  the outer ladder's own commitment remaster refused itself on the residuals it
  was repairing.
* i30 — junction's omit/fuse of a hanging clip was refused by seat freeze as a
  generic ``order_change`` (``opportunity_below_threshold``), so the EDL dropped
  the clip while selection kept it; the divergence rebuild put it straight back
  and mix refused forever on a residual nobody could clear.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.air_order_boundary import (
    _ship_blocking_omit_ids,
    commit_selection_mutation,
)
from interview_mux.junction_snip_qa import refuse_mix_if_live_incomplete_cuts
from interview_mux.loud_fail import LoudStageFailure
from interview_mux.run_context import RunContext
from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "i29_junction_ladder_omit")


_LIVE = [
    {"kind": "on_a_roll", "severity": "critical", "segment_id": "seg_071"},
    {
        "kind": "chapter_bleed_incomplete",
        "severity": "critical",
        "segment_id": "seg_014",
    },
]


def _pin_live(monkeypatch: pytest.MonkeyPatch, findings: list[dict]) -> None:
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: list(findings),
    )


# --- i29: nested feel audit must not strip the outer ladder marker -------------


def test_i29_nested_feel_audit_keeps_outer_inner_flag(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Feel audit inside the ladder leaves ``_junction_snip_qa_inner`` armed."""
    import interview_mux.junction_snip_qa as jq

    monkeypatch.setattr(jq, "build_feel_audit_context", lambda _ctx, _rpt: {"tape": []})
    monkeypatch.setattr(
        "interview_mux.stages.llm_runner.run_prompt_envelope",
        lambda *a, **k: {"parsed": {"verdict": "pass", "directives": [], "findings": []}},
    )
    _pin_live(monkeypatch, _LIVE)

    setattr(ctx, "_junction_snip_qa_inner", True)
    jq.run_junction_feel_audit(ctx, {"version": 1}, cfg={"feel_audit_enabled": True})
    assert getattr(ctx, "_junction_snip_qa_inner", False) is True, (
        "nested feel audit must not strip the outer ladder's inner marker"
    )
    # …and the ladder's own commitment remaster therefore does not self-refuse.
    refuse_mix_if_live_incomplete_cuts(ctx)

    delattr(ctx, "_junction_snip_qa_inner")
    jq.run_junction_feel_audit(ctx, {"version": 2}, cfg={"feel_audit_enabled": True})
    assert not getattr(ctx, "_junction_snip_qa_inner", False), (
        "a standalone feel audit still clears the marker it armed"
    )


def test_i29_outer_mix_still_refuses_live_residuals(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pin_live(monkeypatch, _LIVE)
    with pytest.raises(LoudStageFailure):
        refuse_mix_if_live_incomplete_cuts(ctx)


# --- i30: seat freeze must let ship-blocking omits leave air -------------------


def _selection(order: list[str], excluded: list[dict]) -> dict:
    return {
        "ordered_segment_ids": list(order),
        "excluded_segment_ids": list(excluded),
    }


def test_i30_junction_incomplete_cut_omit_is_freeze_exempt(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pin_live(monkeypatch, _LIVE)
    sel = _selection(
        ["seg_001", "seg_014", "seg_071"],
        [{"segment_id": "seg_071", "reason": "junction_snip_qa:on_a_roll:omit_noop_recut"}],
    )
    exempt = _ship_blocking_omit_ids(
        ctx,
        prev_ids=["seg_001", "seg_014", "seg_071"],
        cur_ids=["seg_001", "seg_014"],
        selection=sel,
    )
    assert exempt == ["seg_071"], (
        "classifier still names the junction omit shape; End-A lands it (DP-A2 A)"
    )


def test_i30_generic_omit_stays_freeze_owned(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pin_live(monkeypatch, _LIVE)
    sel = _selection(
        ["seg_001", "seg_014"],
        [{"segment_id": "seg_071", "reason": "junction_snip_qa:exclude_micro"}],
    )
    assert (
        _ship_blocking_omit_ids(
            ctx,
            prev_ids=["seg_001", "seg_014", "seg_071"],
            cur_ids=["seg_001", "seg_014"],
            selection=sel,
        )
        == []
    ), "only ship-blocking incomplete-cut kinds are exempt"


def test_i30_reorder_is_never_freeze_exempt(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pin_live(monkeypatch, _LIVE)
    sel = _selection(
        ["seg_014", "seg_001"],
        [{"segment_id": "seg_071", "reason": "junction_snip_qa:on_a_roll:omit_noop_recut"}],
    )
    assert (
        _ship_blocking_omit_ids(
            ctx,
            prev_ids=["seg_001", "seg_014", "seg_071"],
            cur_ids=["seg_014", "seg_001"],
            selection=sel,
        )
        == []
    ), "reordering under freeze stays the freeze owner's call"


def test_i30_no_live_residual_means_no_exemption(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pin_live(monkeypatch, [])
    sel = _selection(
        ["seg_001", "seg_014"],
        [{"segment_id": "seg_071", "reason": "junction_snip_qa:on_a_roll:omit_noop_recut"}],
    )
    assert (
        _ship_blocking_omit_ids(
            ctx,
            prev_ids=["seg_001", "seg_014", "seg_071"],
            cur_ids=["seg_001", "seg_014"],
            selection=sel,
        )
        == []
    ), "no live residual → freeze keeps ownership of the delta"


def test_i30_commit_under_hard_freeze_lands_ship_blocking_omit(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DP-A2 Option A: named End-A lets junction incomplete-cut omit leave air."""
    import interview_mux.air_order_boundary as bnd

    monkeypatch.setattr(bnd, "soft_freeze_active", lambda _ctx: False, raising=False)
    monkeypatch.setattr(
        "interview_mux.seat_authority.soft_freeze_active", lambda _ctx: False
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active", lambda _ctx: True
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.request_seat_rewrite",
        lambda *a, **k: {"allow": False, "refuse_reason": "opportunity_below_threshold"},
    )
    _pin_live(monkeypatch, _LIVE)
    prev = _selection(["seg_001", "seg_014", "seg_071"], [])
    ctx.write_json("master/selection.json", prev)
    proposed = _selection(
        ["seg_001", "seg_014"],
        [{"segment_id": "seg_071", "reason": "junction_snip_qa:on_a_roll:omit_noop_recut"}],
    )
    out = commit_selection_mutation(
        ctx,
        proposed,
        producer="junction_snip_qa",
        stage_key="junction_snip_qa",
        checkpoint_mode="detect",
        skip_checkpoint=True,
    )
    assert "seg_071" not in list(out.get("ordered_segment_ids") or []), (
        "DP-A2 A: End-A ship-blocking omit lands — hanging clip leaves air"
    )


# --- i31: pre_mix publishability must not abort the ladder's own remaster ------


def test_i31_inner_remaster_passes_pre_mix_critical_junction(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.publishability_boundary import _check_critical_junction

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.has_critical_residuals", lambda _ctx: True
    )
    _pin_live(monkeypatch, _LIVE)
    setattr(ctx, "_junction_snip_qa_inner", True)
    assert _check_critical_junction(ctx) == [], (
        "junction's own remaster round must render; the terminal gate still blocks ship"
    )


def test_i31_mix_still_blocked_by_critical_junction(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.publishability_boundary import _check_critical_junction

    monkeypatch.setattr(
        "interview_mux.delivery_guardrails.has_critical_residuals", lambda _ctx: True
    )
    _pin_live(monkeypatch, _LIVE)
    monkeypatch.setattr("interview_mux.write_staging.active_stage_id", lambda: "mix")
    out = _check_critical_junction(ctx)
    assert out and out[0].error_class == "incomplete_cut_unresolved", (
        "the real mix stage keeps refusing on critical junction residuals"
    )


# --- i32: consumer VO pair-gap bookkeeping must not fight the VO owner ---------


def test_i32_vo_pair_gap_skips_sealed_report(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.transition_vo import persist_vo_pair_gap

    ctx.write_json("mastering/vo_synthesize.json", {"version": 1, "sealed": True})
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted",
        lambda *a, **k: (False, "edl_sealed:vo_synthesize"),
    )
    persist_vo_pair_gap(ctx, ["seg_a|seg_b"], source="junction_snip_qa")
    doc = ctx.read_json("mastering/vo_synthesize.json")
    assert "still_missing_pairs" not in doc, (
        "sealed VO report must not be rewritten from a consumer"
    )


def test_i32_vo_pair_gap_lands_for_owner(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.transition_vo import persist_vo_pair_gap

    ctx.write_json("mastering/vo_synthesize.json", {"version": 1})
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted",
        lambda *a, **k: (True, "owner_rerun"),
    )
    persist_vo_pair_gap(ctx, ["seg_a|seg_b"], source="vo_synthesize")
    doc = ctx.read_json("mastering/vo_synthesize.json")
    assert doc.get("still_missing_pairs") == ["seg_a|seg_b"]


# --- i33: the overlap-union repair owns its manifest/boundary rows -------------


def test_i33_edl_overlap_repair_may_seat_manifest_rows() -> None:
    from interview_mux.artifact_ownership import owners_of

    assert "edl_overlap_repair" in owners_of("segments/manifest.json"), (
        "the delivery-time overlap union must be able to seat its survivor row"
    )
    assert "edl_overlap_repair" in owners_of("segments/boundaries.json")


def test_i33_segment_classification_stays_authoritative() -> None:
    from interview_mux.artifact_ownership import owners_of, row_for_path

    row = row_for_path("segments/manifest.json")
    assert row is not None
    assert owners_of("segments/manifest.json")[-1] == "segment_classification", (
        "classification remains the authoritative manifest owner"
    )


def test_i33_overlap_repair_write_is_permitted_under_edl_seal(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.artifact_ownership import write_permitted

    monkeypatch.setattr(
        "interview_mux.artifact_ownership.current_epoch", lambda _ctx: "edl_sealed"
    )
    allowed, _reason = write_permitted(
        ctx, "segments/manifest.json", "edl_overlap_repair", role="producer"
    )
    assert allowed, "overlap union must not be denied mid-remaster"


# --- i34: exec-contract seat sync must not rewrite a sealed plan ---------------


def test_i34_reconcile_skips_sealed_mastering_plan(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.execution_contract import _plan_write_permitted

    monkeypatch.setattr(
        "interview_mux.write_staging.active_stage_id", lambda: "junction_snip_qa"
    )
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted",
        lambda *a, **k: (False, "edl_sealed:air_contract_sanitize"),
    )
    assert _plan_write_permitted(ctx) is False


def test_i34_reconcile_without_active_stage_keeps_legacy_write(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLI / ladder helpers have no active stage — do not silently drop seats."""
    from interview_mux.execution_contract import _plan_write_permitted

    monkeypatch.setattr("interview_mux.write_staging.active_stage_id", lambda: "")
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted",
        lambda *a, **k: (False, "edl_sealed:air_contract_sanitize"),
    )
    assert _plan_write_permitted(ctx) is True


def test_i34_reconcile_writes_for_plan_owner(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.execution_contract import _plan_write_permitted

    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted",
        lambda *a, **k: (True, "owner_rerun"),
    )
    assert _plan_write_permitted(ctx) is True


# --- i33b: the id-remap walker is integrity, not authoring --------------------


def test_i33b_remap_path_list_matches_walker() -> None:
    from interview_mux.artifact_ownership import SEGMENT_ID_REMAP_PATHS
    from interview_mux.segment_id_remap import SHARED_REMAP_RELS

    assert set(SHARED_REMAP_RELS) == set(SEGMENT_ID_REMAP_PATHS), (
        "keep the ownership remap surface in parity with the walker"
    )


@pytest.mark.parametrize(
    "rel",
    ["master/selection.json", "understanding/gap_report.json", "master/transitions.json"],
)
def test_i33b_remap_allowed_in_sealed_epochs(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch, rel: str
) -> None:
    from interview_mux.artifact_ownership import write_permitted

    monkeypatch.setattr(
        "interview_mux.artifact_ownership.current_epoch", lambda _ctx: "edl_sealed"
    )
    allowed, _reason = write_permitted(
        ctx,
        rel,
        "edl_overlap_repair",
        role="producer",
        mutation_class="segment_id_remap",
    )
    assert allowed, "retiring a consumed segment id must not be denied"


def test_i33b_remap_allow_is_stage_scoped(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.artifact_ownership import write_permitted

    monkeypatch.setattr(
        "interview_mux.artifact_ownership.current_epoch", lambda _ctx: "edl_sealed"
    )
    allowed, _reason = write_permitted(
        ctx, "master/selection.json", "mix", role="producer"
    )
    assert not allowed, "the remap carve-out must not open selection to mix"


@pytest.mark.parametrize(
    "fuse_stage",
    ["connector_fuse_pass", "connector_fuse_pass_pre_ranking"],
)
def test_i33b_fuse_remap_allowed_content_brief_pre_soft_freeze(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch, fuse_stage: str
) -> None:
    """Cascade: fuse must remap content_brief seg_* refs (owner stays reanchor)."""
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.artifact_ownership import write_permitted

    monkeypatch.setattr(
        "interview_mux.artifact_ownership.current_epoch", lambda _ctx: "pre_soft_freeze"
    )
    allowed, reason = write_permitted(
        ctx,
        "understanding/content_brief.json",
        fuse_stage,
        role="producer",
        mutation_class="segment_id_remap",
    )
    assert allowed, (
        f"{fuse_stage} must rewrite content_brief ids after fuse ({reason})"
    )
    foreign, _ = write_permitted(
        ctx, "understanding/content_brief.json", "mix", role="producer"
    )
    assert not foreign, "fuse remap carve-out must not open content_brief to mix"


def test_i33c_chapter_close_hitch_remap_allowed_content_brief(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cascade: hitch remap must rewrite content_brief (exec_13157 AuthorityDenied)."""
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.artifact_ownership import write_permitted

    monkeypatch.setattr(
        "interview_mux.artifact_ownership.current_epoch", lambda _ctx: "pre_soft_freeze"
    )
    allowed, reason = write_permitted(
        ctx,
        "understanding/content_brief.json",
        "chapter_close_hitch",
        role="producer",
        mutation_class="segment_id_remap",
    )
    assert allowed, (
        f"chapter_close_hitch must remap content_brief seg_* refs ({reason})"
    )
    foreign, _ = write_permitted(
        ctx, "understanding/content_brief.json", "mix", role="producer"
    )
    assert not foreign, "hitch remap carve-out must not open content_brief to mix"


def test_i33d_chapter_close_hitch_materialized_needs_remap_class(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cascade (MUX_FORENSICS=0): hitch ideal_cuts_materialized write needs remap class.

    exec_13159: mutation_class_required:segment_id_remap on MATERIALIZED_REL.
    """
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.artifact_ownership import write_permitted

    monkeypatch.setattr(
        "interview_mux.artifact_ownership.current_epoch", lambda _ctx: "pre_soft_freeze"
    )
    denied, reason = write_permitted(
        ctx,
        "understanding/ideal_cuts_materialized.json",
        "chapter_close_hitch",
        role="producer",
    )
    assert not denied and "mutation_class_required" in reason
    allowed, ok_reason = write_permitted(
        ctx,
        "understanding/ideal_cuts_materialized.json",
        "chapter_close_hitch",
        role="producer",
        mutation_class="segment_id_remap",
    )
    assert allowed, f"hitch+remap class must write materialized ({ok_reason})"


# --- i35: a matrix-version mismatch must not silence operator telemetry --------


def _seal_stale_matrix(ctx: RunContext) -> None:
    ctx.write_json(
        "run_meta.json",
        {"version": 1, "artifact_ownership_matrix_version": "stale_hash_0000"},
    )


def test_i35_version_mismatch_still_allows_operator_scaffold(ctx: RunContext) -> None:
    from interview_mux.artifact_ownership import write_permitted

    _seal_stale_matrix(ctx)
    for rel in (
        "operator/execution_status.json",
        "operator/forensics_errors.json",
        "operator/driver_claim.json",
    ):
        allowed, reason = write_permitted(ctx, rel, "", role="ops")
        assert allowed, f"{rel} must stay writable so the mismatch is reportable ({reason})"


def test_i35_version_mismatch_still_seals_owner_bodies(ctx: RunContext) -> None:
    from interview_mux.artifact_ownership import write_permitted

    _seal_stale_matrix(ctx)
    allowed, reason = write_permitted(
        ctx, "master/selection.json", "full_master_ranking", role="producer"
    )
    assert not allowed and "matrix_version_mismatch" in reason, (
        "owner bodies stay sealed across an ALLOW-seed change"
    )


# --- i36: derived sidecars + sealed-plan outro rebind --------------------------


def test_i36_speech_sidecars_are_operational(ctx: RunContext) -> None:
    from interview_mux.artifact_ownership import write_permitted

    allowed, reason = write_permitted(
        ctx, "transcripts/speech/seg_001.json", "junction_snip_qa", role="producer"
    )
    assert allowed and reason == "operational", (
        f"derived speech sidecars must be writable by any sync pass ({reason})"
    )


def test_i36_episode_close_rebind_skips_sealed_plan(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.listen_quality import _plan_write_permitted

    monkeypatch.setattr("interview_mux.write_staging.active_stage_id", lambda: "mix")
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted",
        lambda *a, **k: (False, "edl_sealed:air_contract_sanitize"),
    )
    assert _plan_write_permitted(ctx) is False


def test_i36_episode_close_rebind_writes_for_owner(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.listen_quality import _plan_write_permitted

    monkeypatch.setattr(
        "interview_mux.write_staging.active_stage_id", lambda: "air_script_compose"
    )
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted",
        lambda *a, **k: (True, "owner_rerun"),
    )
    assert _plan_write_permitted(ctx) is True


# --- i37: a fuse/overlap-union consumed id must leave selection too ------------


def test_i37_overlap_union_retire_is_freeze_exempt(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pin_live(monkeypatch, [])
    sel = _selection(["seg_001", "seg_071"], [])
    assert _ship_blocking_omit_ids(
        ctx,
        prev_ids=["seg_001", "seg_071", "seg_073"],
        cur_ids=["seg_001", "seg_071"],
        selection=sel,
        producer="edl_overlap_repair",
    ) == ["seg_073"], "the survivor already covers the consumed span — nothing leaves air"


def test_i37_overlap_union_reorder_still_refused(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pin_live(monkeypatch, [])
    sel = _selection(["seg_071", "seg_001"], [])
    assert (
        _ship_blocking_omit_ids(
            ctx,
            prev_ids=["seg_001", "seg_071", "seg_073"],
            cur_ids=["seg_071", "seg_001"],
            selection=sel,
            producer="edl_overlap_repair",
        )
        == []
    ), "an integrity pass never gets to reshuffle air order"


def test_i37_other_producers_do_not_inherit_the_carve_out(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pin_live(monkeypatch, [])
    sel = _selection(["seg_001", "seg_071"], [])
    assert (
        _ship_blocking_omit_ids(
            ctx,
            prev_ids=["seg_001", "seg_071", "seg_073"],
            cur_ids=["seg_001", "seg_071"],
            selection=sel,
            producer="air_order",
        )
        == []
    ), "only the fuse/remap passes get the integrity exemption"


def test_i37_commit_under_hard_freeze_lands_consumed_id(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DP-A2 Option A: edl_overlap_repair_omit End-A lands union retire."""
    import interview_mux.air_order_boundary as bnd

    monkeypatch.setattr(bnd, "soft_freeze_active", lambda _ctx: False, raising=False)
    monkeypatch.setattr(
        "interview_mux.seat_authority.soft_freeze_active", lambda _ctx: False
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active", lambda _ctx: True
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.request_seat_rewrite",
        lambda *a, **k: {"allow": False, "refuse_reason": "opportunity_below_threshold"},
    )
    prev = _selection(["seg_001", "seg_071", "seg_073"], [])
    ctx.write_json("master/selection.json", prev)
    proposed = _selection(["seg_001", "seg_071"], [])
    out = commit_selection_mutation(
        ctx,
        proposed,
        producer="edl_overlap_repair",
        stage_key="edl",
        checkpoint_mode="detect",
        skip_checkpoint=True,
    )
    assert "seg_073" not in list(out.get("ordered_segment_ids") or []), (
        "DP-A2 A: End-A integrity omit lands — consumed id leaves selection"
    )


# --- i38: an absorbed id must not strand selection ahead of the EDL ------------


def _nle_with_absorbed(ctx: RunContext, sid: str) -> None:
    ctx.write_json(
        "segments/nle_edits.json",
        {
            "version": 1,
            "segment_overrides": {
                sid: {"excluded": True, "exclude_reason": "edl_overlap_repair"}
            },
        },
    )


def test_i38_consumed_ids_are_detected_from_nle(ctx: RunContext) -> None:
    from interview_mux.edl_overlap_repair import consumed_segment_ids

    _nle_with_absorbed(ctx, "seg_073")
    assert consumed_segment_ids(ctx) == {"seg_073"}


def test_i38_creative_exclude_is_not_a_consumed_id(ctx: RunContext) -> None:
    from interview_mux.edl_overlap_repair import consumed_segment_ids

    ctx.write_json(
        "segments/nle_edits.json",
        {
            "version": 1,
            "segment_overrides": {
                "seg_050": {"excluded": True, "exclude_reason": "operator_cut"}
            },
        },
    )
    assert consumed_segment_ids(ctx) == set()


def test_i38_retire_drops_absorbed_id_from_selection(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.edl_overlap_repair import retire_consumed_ids_from_selection

    monkeypatch.setattr(
        "interview_mux.seat_authority.hard_freeze_active", lambda _ctx: True
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.soft_freeze_active", lambda _ctx: False
    )
    monkeypatch.setattr(
        "interview_mux.seat_authority.request_seat_rewrite",
        lambda *a, **k: {"allow": False, "refuse_reason": "opportunity_below_threshold"},
    )
    _nle_with_absorbed(ctx, "seg_073")
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_071", "seg_073", "seg_074"],
            "excluded_segment_ids": [],
            "chapters": [
                {
                    "chapter_id": "ch1",
                    "title": "Chapter one",
                    "segment_ids": ["seg_071", "seg_073"],
                }
            ],
        },
    )
    retired = retire_consumed_ids_from_selection(ctx)
    assert retired == ["seg_073"]
    disk = ctx.read_json("master/selection.json")
    assert "seg_073" not in list(disk.get("ordered_segment_ids") or []), (
        "DP-A2 A: End-A integrity omit lands union-absorbed id"
    )


def test_i38_retire_is_a_noop_without_absorbed_ids(ctx: RunContext) -> None:
    from interview_mux.edl_overlap_repair import retire_consumed_ids_from_selection

    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_071"], "excluded_segment_ids": []},
    )
    assert retire_consumed_ids_from_selection(ctx) == []


# --- i39: G-Framing floor must not re-spin compose ----------------------------
#
# exec_11871: a fresh compose typed-skipped / copy-repaired its way down to two
# active synthetic lines while the prior gap_report held three. The publish path
# raised `refuse hollow gap_report publish under G-Framing Yes` on a *non-hollow*
# plan, the stage failed, and the driver re-executed the whole two-shard LLM
# compose forever. Hold the floor from the prior authority lines instead.


def _prior_line(seg: str, text: str = "Prior host framing line about the beat.") -> dict:
    return {
        "line_id": f"vo_layup_{seg}",
        "origin": "nugget_layup",
        "placement": "before",
        "targets_segment_id": seg,
        "text": text,
        "delivery": "synthesize",
    }


def test_i39_floor_topup_restores_prior_authority_line(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import nugget_layup as nl

    monkeypatch.setattr(
        nl, "_ordered_ids", lambda _c: ["seg_004", "seg_047", "seg_055", "seg_069"]
    )
    plan = {
        "layups": [
            {"target_segment_id": "seg_004", "skip": False, "text": "fresh a"},
            {"target_segment_id": "seg_047", "skip": False, "text": "fresh b"},
            {
                "target_segment_id": "seg_055",
                "skip": True,
                "skip_reason_code": "listener_already_oriented",
            },
        ]
    }
    candidate = [_prior_line("seg_004", "fresh a"), _prior_line("seg_047", "fresh b")]
    prior = candidate + [_prior_line("seg_055")]
    filled, _notes, plan_out = nl._framing_floor_topup(
        ctx,
        candidate_lines=candidate,
        prior_lines=prior,
        seen_targets={"seg_004", "seg_047"},
        need=3,
        plan=plan,
    )
    tids = {
        str(ln.get("targets_segment_id"))
        for ln in filled
        if isinstance(ln, dict) and str(ln.get("text") or "").strip()
    }
    assert "seg_055" in tids
    assert plan_out is not None


def test_i39_floor_topup_refuses_dead_or_superseded_targets(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import nugget_layup as nl

    monkeypatch.setattr(nl, "_ordered_ids", lambda _c: ["seg_004"])
    candidate = [_prior_line("seg_004", "fresh a")]
    prior = candidate + [
        # off-air target (retired by an omit / union) — must not come back
        _prior_line("seg_073"),
        # already re-seated by this compose — must not double-seat
        _prior_line("seg_004", "fresh a"),
        # foreign origin — layup authority only
        {**_prior_line("seg_009"), "origin": "gap_framing_compose"},
        # explicitly skipped prior line — stays skipped
        {**_prior_line("seg_011"), "skipped_optional": True},
    ]
    filled, _notes, _plan = nl._framing_floor_topup(
        ctx,
        candidate_lines=candidate,
        prior_lines=prior,
        seen_targets={"seg_004"},
        need=3,
        plan={"layups": []},
    )
    tids = [
        str(ln.get("targets_segment_id"))
        for ln in filled
        if isinstance(ln, dict) and str(ln.get("text") or "").strip()
    ]
    assert "seg_073" not in tids  # off-air target stays out
    assert tids.count("seg_004") == 1  # no double-seat


# --- i40: transition synth must not abort on its own stage attribution --------
#
# exec_11871 vo_synthesize: `authority_denied:persist:master/transitions.json:edl:
# hard_freeze:transitions` → "transition synth failed open", discarding every
# transition synth result because the guard-normalized copy writeback hardcoded
# stage_key="edl" (a DENY row) regardless of the calling stage.


def test_i40_transition_writeback_skips_when_caller_cannot_persist(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import transition_vo as tv

    monkeypatch.setattr(tv, "active_stage_id", lambda: "edl", raising=False)
    monkeypatch.setattr(
        "interview_mux.write_staging.active_stage_id", lambda: "edl", raising=False
    )
    calls: list[str | None] = []
    monkeypatch.setattr(
        tv,
        "persist_transitions_doc",
        lambda _c, _d, stage_key=None, **_k: calls.append(stage_key),
    )
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted",
        lambda *_a, **_k: (False, "authority_denied:edl_must_not_mint_transitions"),
    )
    # Must not raise — losing the whole synth pass is the bug.
    tv._persist_transitions_copy_normalization(ctx, {"transitions": []})
    assert calls == []


def test_i40_transition_writeback_uses_active_stage_when_permitted(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import transition_vo as tv

    monkeypatch.setattr(
        "interview_mux.write_staging.active_stage_id",
        lambda: "vo_synthesize",
        raising=False,
    )
    calls: list[str | None] = []
    monkeypatch.setattr(
        tv,
        "persist_transitions_doc",
        lambda _c, _d, stage_key=None, **_k: calls.append(stage_key),
    )
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted", lambda *_a, **_k: (True, "")
    )
    tv._persist_transitions_copy_normalization(ctx, {"transitions": []})
    assert calls == ["vo_synthesize"]


# --- i42: rendered VO must bind into the EDL ----------------------------------
#
# exec_11871: vo_synthesize rendered vo_layup_seg_004/047/055, but the EDL clips
# kept `source_path: null`, so mix inserted 500 ms of silence for every host line.
# The only heal (`heal_vo_pickup_clip_source`) lived inside run_preview, while the
# assembly_preview *input check* refused on exactly those unsourced clips — the
# heal was unreachable. Bind producer-side and stop refusing bindable clips.


def _write_wav(path: Path, ms: int = 1200) -> None:
    """Speech-ish noise burst — passes vo_speech_qa (no pure tone / flat envelope)."""
    import math
    import random
    import struct
    import wave

    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 48000
    n = int(rate * ms / 1000)
    rng = random.Random(7)
    frames = bytearray()
    for i in range(n):
        syllable = 0.5 + 0.5 * math.sin(2 * math.pi * 4.0 * i / rate)
        env = syllable**2
        sample = int(11000 * env * (rng.random() * 2 - 1))
        frames += struct.pack("<h", max(-32000, min(32000, sample)))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(frames))


def _seat_vo_run(ctx: RunContext, monkeypatch: pytest.MonkeyPatch | None = None) -> None:
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_004",
                    "origin": "nugget_layup",
                    "placement": "before",
                    "targets_segment_id": "seg_004",
                    "text": "Host framing line before the fourth beat.",
                    "delivery": "synthesize",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_004"],
            "timeline_duration_ms": 4500,
            "clips": [
                {
                    "type": "vo_pickup",
                    "line_id": "vo_layup_seg_004",
                    "targets_segment_id": "seg_004",
                    "placement": "before",
                    "source_path": None,
                    "timeline_start_ms": 0,
                    "duration_ms": 500,
                },
                {
                    "type": "speech",
                    "segment_id": "seg_004",
                    "source_start_ms": 0,
                    "source_end_ms": 4000,
                    "timeline_start_ms": 500,
                    "duration_ms": 4000,
                },
            ],
        },
        skip_handoff=True,
    )
    wav = ctx.final_path("vo_pickup", "vo_layup_seg_004.wav")
    _write_wav(wav)
    from interview_mux.vo_synthesis_audit import record_synthesis

    record_synthesis(
        ctx,
        {
            "line_id": "vo_layup_seg_004",
            "targets_segment_id": "seg_004",
            "text": "Host framing line before the fourth beat.",
            "delivery": "synthesize",
        },
        backend="chatterbox",
        out_wav=wav,
        wav_just_rendered=True,
    )


def test_i42_rendered_vo_binds_into_edl(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.stages.assembly import restamp_edl_vo_pickup_source_paths

    _seat_vo_run(ctx, monkeypatch)
    written: dict[str, object] = {}

    def _fake_write(_c, doc, source=None, **_k):
        written["doc"] = doc
        written["source"] = source
        _c.write_json("master/edl.json", doc, skip_handoff=True)

    monkeypatch.setattr("interview_mux.air_order.write_live_edl", _fake_write)
    healed = restamp_edl_vo_pickup_source_paths(ctx)
    assert healed == ["vo_layup_seg_004"]
    clip = ctx.read_json("master/edl.json")["clips"][0]
    assert str(clip["source_path"]).endswith("vo_pickup/vo_layup_seg_004.wav")
    assert int(clip["duration_ms"]) > 500


def test_i42_preflight_does_not_refuse_bindable_vo(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.stage_completion import assembly_preview_unsourced_glue_ids
    from interview_mux.stage_input_checks import _check_assembly_preview

    _seat_vo_run(ctx, monkeypatch)
    edl = ctx.read_json("master/edl.json")
    # The raw ledger still sees the unsourced clip …
    assert assembly_preview_unsourced_glue_ids(edl) == ["vo_layup_seg_004"]
    # … but the preflight must not block the stage that heals it.
    issues = _check_assembly_preview(ctx)
    assert not [
        i for i in issues if "current transition pairs missing WAV" in str(i.message)
    ]


# --- i43: a union fuse must not be blocked by hard keeps -----------------------
#
# exec_11871: seg_014 carried an `unrecoverable_within_clip` chapter_bleed_incomplete
# whose recommended cut landed *before* the clip start (nothing in the clip completes
# the thought). 60 of 61 clips were hard keeps, so the fuse ladder refused the union
# and fell to `skipped_no_recommendation` — mix refused forever on a residual nobody
# could clear. A union fuse preserves the retired clip's audio in the survivor, so
# only the content-losing omit branch may honour hard keeps.


def _hanging_clips() -> list[dict]:
    return [
        {
            "type": "speech",
            "segment_id": "seg_013",
            "source_start_ms": 372160,
            "source_end_ms": 404450,
        },
        {
            "type": "speech",
            "segment_id": "seg_014",
            "source_start_ms": 462800,
            "source_end_ms": 469530,
        },
        {
            "type": "speech",
            "segment_id": "seg_015",
            "source_start_ms": 469580,
            "source_end_ms": 504440,
        },
    ]


def _hanging_finding() -> dict:
    return {
        "kind": "chapter_bleed_incomplete",
        "severity": "critical",
        "segment_id": "seg_014",
        "action": "cut_earlier",
        "detail": {"recommended_ms": 462400, "unrecoverable_within_clip": True},
    }


def test_i43_union_fuse_lands_even_when_both_sides_are_hard_keeps(
    ctx: RunContext,
) -> None:
    from interview_mux import junction_snip_qa as jq

    clips = _hanging_clips()
    segs = {
        sid: {"segment_id": sid, "speaker_id": "spk_1"}
        for sid in ("seg_013", "seg_014", "seg_015")
    }
    selection = {"ordered_segment_ids": ["seg_013", "seg_014", "seg_015"]}
    applied: list[dict] = []
    overrides: dict[str, object] = {}
    excluded: set[str] = set()
    out, changed = jq._fuse_or_omit_hanging_clip(
        ctx,
        clips=clips,
        finding=_hanging_finding(),
        overrides=overrides,
        excluded=excluded,
        exclude_reasons={},
        segs=segs,
        selection=selection,
        hard_keeps={"seg_013", "seg_014", "seg_015"},
        applied=applied,
    )
    assert changed is True
    assert [a.get("status") for a in applied] == ["fused_neighbor"]
    assert applied[0]["drop_segment_id"] == "seg_014"
    survivor = [c for c in out if c.get("segment_id") == "seg_015"][0]
    # Union covers the retired clip's audio — nothing is lost.
    assert int(survivor["source_start_ms"]) <= 462800
    assert int(survivor["source_end_ms"]) >= 504440
    assert "seg_014" in excluded


def test_i43_omit_still_refuses_hard_keeps_without_a_neighbor(
    ctx: RunContext,
) -> None:
    from interview_mux import junction_snip_qa as jq

    # Lone clip: no fuse candidate at all, so the ladder may only omit — and a
    # hard keep must still refuse that (no silent content loss).
    clips = [
        {
            "type": "speech",
            "segment_id": "seg_014",
            "source_start_ms": 462800,
            "source_end_ms": 469530,
        }
    ]
    applied: list[dict] = []
    excluded: set[str] = set()
    _out, changed = jq._fuse_or_omit_hanging_clip(
        ctx,
        clips=clips,
        finding=_hanging_finding(),
        overrides={},
        excluded=excluded,
        exclude_reasons={},
        segs={"seg_014": {"segment_id": "seg_014", "speaker_id": "spk_1"}},
        selection={"ordered_segment_ids": ["seg_014"]},
        hard_keeps={"seg_014"},
        applied=applied,
    )
    # ISSUES 72: the keep stays on air and the accepted hang is recorded, so
    # detection does not re-raise it forever. Still no omit.
    assert [a.get("status") for a in applied] == ["accepted_hard_keep_hang"]
    assert changed is True
    assert "seg_014" not in excluded
    assert [c["segment_id"] for c in _out] == ["seg_014"]


def test_i43b_chapter_bleed_fuses_into_source_adjacent_next_chapter(
    ctx: RunContext,
) -> None:
    """A chapter_bleed_incomplete's only candidate is across the boundary."""
    from interview_mux import junction_snip_qa as jq

    clips = _hanging_clips()
    segs = {
        sid: {"segment_id": sid, "speaker_id": "spk_1"}
        for sid in ("seg_013", "seg_014", "seg_015")
    }
    selection = {
        "ordered_segment_ids": ["seg_013", "seg_014", "seg_015"],
        "chapters": [
            {"chapter_id": "ch_1", "title": "One", "segment_ids": ["seg_013", "seg_014"]},
            {"chapter_id": "ch_2", "title": "Two", "segment_ids": ["seg_015"]},
        ],
    }
    applied: list[dict] = []
    excluded: set[str] = set()
    out, changed = jq._fuse_or_omit_hanging_clip(
        ctx,
        clips=clips,
        finding=_hanging_finding(),
        overrides={},
        excluded=excluded,
        exclude_reasons={},
        segs=segs,
        selection=selection,
        hard_keeps={"seg_013", "seg_014", "seg_015"},
        applied=applied,
    )
    assert changed is True
    assert applied[0]["status"] == "fused_neighbor"
    assert applied[0]["survivor_segment_id"] == "seg_015"
    survivor = [c for c in out if c.get("segment_id") == "seg_015"][0]
    assert int(survivor["source_start_ms"]) <= 462800


def test_i43b_distant_next_chapter_neighbor_is_not_fused(ctx: RunContext) -> None:
    from interview_mux import junction_snip_qa as jq

    clips = _hanging_clips()
    # Push the next chapter far away in source — no honest union any more.
    clips[2]["source_start_ms"] = 900000
    clips[2]["source_end_ms"] = 930000
    selection = {
        "ordered_segment_ids": ["seg_013", "seg_014", "seg_015"],
        "chapters": [
            {"chapter_id": "ch_1", "title": "One", "segment_ids": ["seg_013", "seg_014"]},
            {"chapter_id": "ch_2", "title": "Two", "segment_ids": ["seg_015"]},
        ],
    }
    applied: list[dict] = []
    _out, changed = jq._fuse_or_omit_hanging_clip(
        ctx,
        clips=clips,
        finding=_hanging_finding(),
        overrides={},
        excluded=set(),
        exclude_reasons={},
        segs={
            sid: {"segment_id": sid, "speaker_id": "spk_1"}
            for sid in ("seg_013", "seg_014", "seg_015")
        },
        selection=selection,
        hard_keeps={"seg_013", "seg_014", "seg_015"},
        applied=applied,
    )
    # Distant next-chapter neighbour is still not fused (ISSUES 72: the hang
    # on the hard keep is recorded as accepted instead of re-raised).
    assert applied[0]["status"] == "accepted_hard_keep_hang"
    assert changed is True
    assert "seg_015" in [c["segment_id"] for c in _out]


# --- i44: sealed SDP must not abort the junction commitment remaster ----------
#
# exec_11871 09:10: `authority_denied:persist:understanding/sound_design_plan.json:
# junction_snip_qa:edl_sealed:sound_design_vo_finalize` raised out of
# soundscape_verify's bed remediation *during* mix/post_mix_qc, killing the
# junction commitment remaster right after assembly.wav had rendered clean.


def _seat_sdp(ctx: RunContext) -> None:
    ctx.write_json(
        "understanding/sound_design_plan.json",
        {
            "version": 1,
            "assets": [
                {"asset_id": "bed_asset", "kind": "music"},
            ],
            "flow_plans": {
                "podcast": {
                    "profile": "podcast",
                    "cues": [
                        {
                            "cue_id": "bed_1",
                            "asset_id": "bed_asset",
                            "placement": "under_segment",
                            "segment_id": "seg_004",
                            "level_db": -22.0,
                            "duck_under_speech_db": 12.0,
                        },
                        {
                            "cue_id": "bed_2",
                            "asset_id": "bed_asset",
                            "placement": "under_segment",
                            "segment_id": "seg_047",
                            "level_db": -20.0,
                        },
                    ]
                }
            },
        },
        skip_handoff=True,
    )


def test_i44_sealed_sdp_keeps_bed_remediation_advisory(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import soundscape_verify as sv

    _seat_sdp(ctx)
    before = json.dumps(ctx.read_json("understanding/sound_design_plan.json"))
    monkeypatch.setattr(
        "interview_mux.write_staging.active_stage_id",
        lambda: "junction_snip_qa",
        raising=False,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted",
        lambda *_a, **_k: (False, "not_allow:owner=sound_design_vo_finalize"),
    )
    actions = sv.apply_cheap_remediation(ctx)
    assert actions and all(a.endswith("advisory_sdp_sealed") for a in actions)
    # Sealed plan untouched — and no exception escaped into the remaster.
    assert json.dumps(ctx.read_json("understanding/sound_design_plan.json")) == before


def test_i44_open_sdp_still_persists_bed_remediation(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux import soundscape_verify as sv

    _seat_sdp(ctx)
    monkeypatch.setattr(
        "interview_mux.write_staging.active_stage_id",
        lambda: "sound_design_vo_finalize",
        raising=False,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted", lambda *_a, **_k: (True, "")
    )
    actions = sv.apply_cheap_remediation(ctx)
    assert actions and not any("advisory_sdp_sealed" in a for a in actions)
    cues = ctx.read_json("understanding/sound_design_plan.json")["flow_plans"][
        "podcast"
    ]["cues"]
    levels = {c["cue_id"]: c.get("level_db") for c in cues}
    # Persisted (sanitize may clamp the exact dB) — the seal is what was broken.
    assert levels["bed_1"] != -22.0


def test_i46_vo_bind_retimes_so_vo_does_not_overlap_next_speech(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """i46: binding a seconds-long VO over a 500 ms placeholder must re-time."""
    from interview_mux.stages.assembly import restamp_edl_vo_pickup_source_paths

    _seat_vo_run(ctx)
    monkeypatch.setattr(
        "interview_mux.air_order.write_live_edl",
        lambda _c, doc, source=None, **_k: _c.write_json(
            "master/edl.json", doc, skip_handoff=True
        ),
    )
    assert restamp_edl_vo_pickup_source_paths(ctx) == ["vo_layup_seg_004"]
    clips = ctx.read_json("master/edl.json")["clips"]
    vo, speech = clips[0], clips[1]
    vo_end = int(vo["timeline_start_ms"]) + int(vo["duration_ms"])
    assert int(speech["timeline_start_ms"]) >= vo_end


def test_i46_bound_vo_with_placeholder_duration_is_retimed(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Already-bound VO keeps an honest length (idempotent across restarts)."""
    from interview_mux.stages.assembly import restamp_edl_vo_pickup_source_paths

    _seat_vo_run(ctx)
    monkeypatch.setattr(
        "interview_mux.air_order.write_live_edl",
        lambda _c, doc, source=None, **_k: _c.write_json(
            "master/edl.json", doc, skip_handoff=True
        ),
    )
    # Pretend an earlier pass bound the path but kept the 500 ms placeholder.
    edl = ctx.read_json("master/edl.json")
    edl["clips"][0]["source_path"] = "vo_pickup/vo_layup_seg_004.wav"
    edl["clips"][0]["duration_ms"] = 500
    ctx.write_json("master/edl.json", edl, skip_handoff=True)
    touched = restamp_edl_vo_pickup_source_paths(ctx)
    assert touched == ["vo_layup_seg_004"]
    clips = ctx.read_json("master/edl.json")["clips"]
    assert int(clips[0]["duration_ms"]) > 500
    assert int(clips[1]["timeline_start_ms"]) >= int(clips[0]["duration_ms"])


# --- i47: staged master could never satisfy the committed-master invariant ----
#
# exec_11871: loudnorm rendered a full 255 MB master into the stage's staging root,
# then `committed_master_integrity_ok` (which reads `final_path`) refused
# mark_done — "pending/truncated master cannot soft-complete ship". Staging flush
# only runs after mark_done, so finalize looped forever. Promote first, then judge.


def test_i47_staged_master_is_promoted_before_the_integrity_gate(
    ctx: RunContext,
) -> None:
    from interview_mux.delivery_invariants import committed_master_integrity_ok
    from interview_mux.write_staging import (
        enter_stage_staging,
        exit_stage_staging,
        promote_staged_side_effects,
    )

    enter_stage_staging("master_finalize")
    try:
        staged = ctx.path("master/master.wav")
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(b"RIFF" + b"\0" * 20_000)
        assert staged != ctx.final_path("master", "master.wav")
        # This is exactly the state the gate used to refuse forever.
        assert committed_master_integrity_ok(ctx) is False
        promoted = promote_staged_side_effects(
            ctx, ("master/master.wav",), stage_id="master_finalize"
        )
        assert promoted == ["master/master.wav"]
        assert committed_master_integrity_ok(ctx) is True
    finally:
        exit_stage_staging()


# --- i48/i49: the ship pass could score the master but never record ----------
#
# exec_11871: master_finalize runs the authoritative listen-delight audit and
# rebuilds the post_master seam autopsy on the committed master, but the matrix
# named only listen_delight_audit / junction_snip_qa as producers — every ship
# attempt died on `authority_denied:persist:...:master_finalize` and finalize
# looped. The ship gate is a co-producer of the verdicts it computes; the
# assembly-ledger *annotation* stays advisory when the ledger is sealed.


def test_i48_ship_pass_may_record_the_delight_audit_and_autopsy(
    ctx: RunContext,
) -> None:
    from interview_mux.artifact_ownership import write_permitted

    for rel, owner in (
        ("mastering/listen_delight_audit.json", "listen_delight_audit"),
        ("master/seam_autopsy.json", "junction_snip_qa"),
    ):
        allowed, reason = write_permitted(
            ctx, rel, "master_finalize", role="producer", verb="persist"
        )
        # Ship may record delight; seam autopsy stays junction-owned.
        if rel.endswith("seam_autopsy.json"):
            assert allowed is False
            assert "junction_snip_qa" in reason
            continue
        assert allowed, f"{rel}: {reason}"
        # The owner keeps its authority …
        assert write_permitted(ctx, rel, owner, role="producer", verb="persist")[0]
        # … and the grant is not a free-for-all.
        assert not write_permitted(
            ctx, rel, "transcribe", role="producer", verb="persist"
        )[0]


def test_i49_sealed_assembly_ledger_annotation_stays_advisory(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.seam_autopsy import enrich_ledger

    ctx.write_json(
        "master/assembly_ledger.json",
        {"seams": [{"after_segment_id": "seg_001", "before_segment_id": "seg_002"}]},
        skip_handoff=True,
    )
    autopsy = {"seams": [], "generated_at": "now", "scores": {"continuity": 0.9}}
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted",
        lambda *_a, **_k: (False, "not_allow:owner=edl"),
    )
    monkeypatch.setattr(
        "interview_mux.write_staging.active_stage_id", lambda: "master_finalize"
    )
    # Must not raise and must not rewrite the sealed ledger.
    assert enrich_ledger(ctx, autopsy) is None
    assert "autopsy_version" not in ctx.read_json("master/assembly_ledger.json")


# --- i50: a JPEG producer artifact was read as JSON -------------------------
#
# exec_11871: publish/cover.jpg is episode_cover_generate's primary artifact.
# `artifact_status` read it as JSON — UnicodeDecodeError is a ValueError, so it was
# swallowed into status="pending" and mark_done was refused; `post_commit_validate`
# raised the same decode error and killed the delivery walk. The ship walk then
# re-ran the stage (three paid cover generations) forever at 69/72.


def test_i50_image_producer_artifacts_are_treated_as_binary(ctx: RunContext) -> None:
    from interview_mux.artifact_completeness import artifact_status
    from interview_mux.stage_acceptance import _is_binary_artifact_rel, stage_acceptance_ok

    jpeg = ctx.final_path("publish", "cover.jpg")
    jpeg.parent.mkdir(parents=True, exist_ok=True)
    # 0xFF 0xD8 is a real JPEG SOI marker — not decodable as UTF-8.
    jpeg.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 4096)

    assert _is_binary_artifact_rel("publish/cover.jpg")
    assert artifact_status("publish/cover.jpg", ctx) == "complete"
    # post_commit_validate's path must not raise on the bytes.
    result = stage_acceptance_ok(
        ctx, "episode_cover_generate", staged=False, include_downstream=False
    )
    assert result.ok, (result.errors, result.schema_errors)


# --- i51: the local episode package was never cataloged ---------------------
#
# exec_11871 at 70/72: `authority_denied:persist:publish/chapters.json:
# podcast_publish:junction_committed: (unknown_path)` failed the ship stage on every
# dispatch. podcast_publish writes the whole `s3_layout.episode_files` set.


def test_i51_podcast_publish_owns_its_episode_package(ctx: RunContext) -> None:
    from interview_mux.artifact_ownership import write_permitted

    for rel in (
        "publish/chapters.json",
        "publish/episode.json",
        "publish/description.txt",
        "publish/transcript.vtt",
        "publish/master.wav",
    ):
        allowed, reason = write_permitted(
            ctx, rel, "podcast_publish", role="producer", verb="persist"
        )
        assert allowed, f"{rel}: {reason}"
        assert "unknown_path" not in reason


# --- i52: the packaged episode promised files the flush dropped --------------
#
# exec_11871 shipped a publish/package_ready.json listing episode.json and
# description.txt; neither existed on disk. `operator_visible_staging_path` filters
# the flush by the stage's declared artifacts, so any undeclared staged write is
# silently discarded — an S3 sync of that package would 404.


def test_i52_podcast_publish_declares_every_packaged_file() -> None:
    from interview_mux.write_staging import operator_visible_staging_path

    for rel in (
        "publish/package_ready.json",
        "publish/publish_result.json",
        "publish/chapters.json",
        "publish/transcript.vtt",
        "publish/episode.json",
        "publish/description.txt",
    ):
        assert operator_visible_staging_path("podcast_publish", rel), rel


# --- i53: the master shipped over the true-peak ceiling ----------------------
#
# exec_11871: `tools/verify_master.py` FAILed the shipped master at −0.40 dBTP
# (pass ≤ −0.75). The limiter sat *before* loudnorm, whose make-up gain then pushed
# peaks back up, and the runner waived every true-peak miss as measurement noise.


def test_i53_master_chain_limits_after_loudnorm() -> None:
    import math

    from interview_mux.config import merged_config
    from interview_mux.stages.mastering import _master_filter_chain

    chain = _master_filter_chain(
        merged_config(),
        target_lufs=-16.0,
        true_peak_dbtp=-1.0,
        measured={
            "input_i": "-18.14",
            "input_lra": "9.0",
            "input_tp": "-3.54",
            "input_thresh": "-29.0",
            "target_offset": "-0.01",
        },
    )
    stages = chain.split(",")
    assert stages[-1].startswith("alimiter="), chain
    assert "level=disabled" in stages[-1], "post limiter must not auto-level the loudness"
    ceiling = math.pow(10.0, -1.0 / 20.0)
    assert f"limit={ceiling:.6f}" in stages[-1], chain
    # loudnorm must sit *between* the two limiters.
    assert any(part.startswith("loudnorm=") for part in stages[:-1]), chain


def test_i53_real_true_peak_overshoot_is_not_waived_as_noise(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.master_qc import MasterMetrics, VerificationResult
    from interview_mux.web.runner import JobRunner

    master = ctx.final_path("master", "master.wav")
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF" + b"\0" * 4096)

    def _result(tp: float) -> VerificationResult:
        return VerificationResult(
            flow="podcast",
            source=master,
            metrics=MasterMetrics(
                duration_seconds=100.0,
                sample_rate_hz=48000,
                channels=1,
                integrated_lufs=-16.0,
                true_peak_dbtp=tp,
            ),
            checks=[],
            failures=[f"True peak {tp:.2f} dBTP exceeds ceiling -0.75 dBTP."],
        )

    runner = JobRunner.__new__(JobRunner)

    # 0.35 dB over the pass ceiling: a real overshoot, must refuse.
    monkeypatch.setattr(
        "interview_mux.web.runner.verify_master", lambda *_a, **_k: _result(-0.40)
    )
    with pytest.raises(RuntimeError, match="verify_master failed"):
        runner._run_master_qa(ctx, flow="podcast", rel_path="master/master.wav")

    # Inside the noise band: still advisory.
    monkeypatch.setattr(
        "interview_mux.web.runner.verify_master", lambda *_a, **_k: _result(-0.70)
    )
    runner._run_master_qa(ctx, flow="podcast", rel_path="master/master.wav")


# --- i54: the ship-time delight verdict never reached disk -------------------
#
# exec_11871 shipped with `mastering/listen_delight_audit.json` from a pre-mix pass
# hours earlier (advisory=true): master_finalize's authoritative post_master audit is
# a *staged* write, and undeclared staged paths are dropped at flush (same class as
# i52). The §2 ship bar reads that file, so the ship claim was unbacked.


def test_i54_master_finalize_declares_its_ship_verdicts() -> None:
    from interview_mux.write_staging import operator_visible_staging_path

    for rel in (
        "master/post_master_quality.json",
        "master/listener_scorecard.json",
        "mastering/listen_delight_audit.json",
        "master/seam_autopsy.json",
        "master/master.wav",
    ):
        assert operator_visible_staging_path("master_finalize", rel), rel


def test_i54_undeclared_owned_staging_path_is_committed_not_dropped(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An owned-but-undeclared staged write must land, and say it was undeclared.

    This previously asserted the *drop* plus a warning, on the reasoning that the
    silent-drop class should at least announce itself. Announcing it is not
    enough: operator_visible_staging_path answers "does the GUI list this?", and
    using it as the commit gate deleted every artifact a stage legitimately owns
    but does not surface. exec_11871 lost this very file that way, and a full
    traversal dropped 26 paths including every understanding/llm_calls/** record
    and every volley pack, which is the forensic trail needed to debug a run.

    Ownership decides persistence now, so the bytes survive and the undeclared
    status is still reported. The original intent, not losing bytes quietly, is
    what this asserts.
    """
    from interview_mux import write_staging

    logged: list[str] = []
    monkeypatch.setattr(
        write_staging,
        "operator_visible_staging_path",
        lambda _sid, _rel: False,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_ownership.write_permitted",
        lambda *_a, **_k: (True, "owner_rerun"),
    )
    monkeypatch.setattr(ctx, "log", lambda msg, **_k: logged.append(str(msg)))

    write_staging.enter_stage_staging("master_finalize")
    try:
        staged = ctx.path("mastering/listen_delight_audit.json")
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_text("{}", encoding="utf-8")
        flushed = write_staging.flush_stage_writes(ctx, "master_finalize")
    finally:
        write_staging.exit_stage_staging()

    # Owned, so it must be committed rather than discarded.
    assert "mastering/listen_delight_audit.json" in flushed, flushed
    # Still reported, so a missing StageInfo declaration stays visible.
    assert any("undeclared" in m for m in logged), logged


def test_missing_framing_may_write_flow_adaptation(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cascade (MUX_FORENSICS=0): G-Framing overrides on flow_adaptation.

    exec_13157: missing_framing AuthorityDenied owner=source_topology_build.
    """
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.artifact_ownership import write_permitted

    monkeypatch.setattr(
        "interview_mux.artifact_ownership.current_epoch", lambda _ctx: "pre_soft_freeze"
    )
    allowed, reason = write_permitted(
        ctx, "understanding/flow_adaptation.json", "missing_framing", role="producer"
    )
    assert allowed, f"missing_framing must patch flow_adaptation overrides ({reason})"
