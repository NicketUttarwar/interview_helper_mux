"""End-A: hard seat freeze mutation constitution (MUX_FORENSICS=0)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.artifact_sanitize.air_script import (
    air_contract_sanitary_errors,
    sanitize_air_contract,
)
from interview_mux.omit_ledger import (
    OMIT_LEDGER_REL,
    air_contract_errors,
    heal_omit_ledger_air_contract,
    revive_required_opening_orientation,
)
from interview_mux.order_hash import bump_order_lock
from interview_mux.run_context import RunContext
from interview_mux.seat_authority import (
    HARD_FREEZE_ALLOWLIST_ACTIONS,
    HARD_FREEZE_FORBIDDEN_ACTIONS,
    hard_freeze_action_permitted,
    hard_freeze_blocks_action,
    seat_mutation_allowed,
    stamp_hard_seat_freeze,
)
from run_fixtures import isolated_run_ctx, minimal_gap_line, minimal_gap_report


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    run = isolated_run_ctx(tmp_path, "enda_hard_freeze")
    run.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "homunculus_kind": "homunculus",
            "delivery_epoch": {},
        },
        skip_handoff=True,
    )
    return run


def _stamp_hard(ctx: RunContext) -> None:
    stamp_hard_seat_freeze(ctx, reason="vo_synthesize")


def test_enda_allowlist_membership() -> None:
    assert hard_freeze_action_permitted("omit_ledger_revive_orientation")
    assert hard_freeze_action_permitted("protect_orientation_from_omit")
    assert hard_freeze_action_permitted("drop_seated_missing_from_gap")
    assert hard_freeze_action_permitted("stamp_pair_freeze")
    assert not hard_freeze_action_permitted("protect_hosted_vo_floor_reseat")
    assert not hard_freeze_action_permitted("invent_new_seats")
    assert "protect_hosted_vo_floor_reseat" in HARD_FREEZE_FORBIDDEN_ACTIONS
    assert "omit_ledger_revive_orientation" in HARD_FREEZE_ALLOWLIST_ACTIONS
    assert "protect_orientation_from_omit" in HARD_FREEZE_ALLOWLIST_ACTIONS
    # DP-A2 Option A: ship-blocking omit/integrity always End-A; CTA rows exist
    # but packaging is soft-freeze only under hard VO freeze.
    for action in (
        "junction_incomplete_cut_omit",
        "edl_overlap_repair_omit",
        "segment_id_remap_omit",
        "sdp_duration_band_repair",
        "soundscape_bed_trim",
        "opening_adjacency_suppress_duplicate",
        "opening_adjacency_drop_orphan",
        "sdp_theme_outro_rebind",
        "bridge_completeness_mint",
        "nugget_layup_gap_publish",
    ):
        assert action in HARD_FREEZE_ALLOWLIST_ACTIONS
        assert hard_freeze_action_permitted(action)
    for action in (
        "soundscape_bed_seed_repair",
        "optimizer_promote_sdp",
        "theme_outro_seed",
        "seed_theme_outro",
    ):
        assert action in HARD_FREEZE_FORBIDDEN_ACTIONS
        assert not hard_freeze_action_permitted(action)
    for action in (
        "media_ip_cta",
        "media_ip_cta_editorial_omits",
        "cta_omit",
        "cta_prune",
        "heal_on_air_cta",
        "artifact_sanitize.selection",
    ):
        assert action in HARD_FREEZE_ALLOWLIST_ACTIONS
        # Without ctx, packaging is listed; hard-freeze ctx refuses (soft-only).
        assert hard_freeze_action_permitted(action)


def test_enda_ship_blocking_omit_action_map() -> None:
    from interview_mux.seat_authority import end_a_action_for_ship_blocking_omit

    assert end_a_action_for_ship_blocking_omit("edl_overlap_repair") == (
        "edl_overlap_repair_omit"
    )
    assert end_a_action_for_ship_blocking_omit("segment_id_remap") == (
        "segment_id_remap_omit"
    )
    assert end_a_action_for_ship_blocking_omit("junction_snip_qa") == (
        "junction_incomplete_cut_omit"
    )
    assert end_a_action_for_ship_blocking_omit("unknown_producer") == ""
    assert hard_freeze_action_permitted(
        end_a_action_for_ship_blocking_omit("junction_snip_qa")
    )


def test_enda_packaging_soft_only_under_hard_freeze(ctx: RunContext) -> None:
    """Footgun #8: named CTA End-A under soft; hard freeze requires meta-gate."""
    from interview_mux.seat_authority import stamp_soft_seat_freeze

    stamp_soft_seat_freeze(ctx, reason="air_contract_sanitize")
    soft_ok, soft_why = seat_mutation_allowed(
        ctx, reason="media_ip_cta_editorial_omits", require_meta_gate=True
    )
    assert soft_ok is True
    assert soft_why == "end_a_allowlist"
    _stamp_hard(ctx)
    hard_ok, hard_why = seat_mutation_allowed(
        ctx, reason="media_ip_cta_editorial_omits", require_meta_gate=True
    )
    assert hard_ok is False
    assert hard_why.startswith("end_a_near_miss:") or hard_why == "frozen_needs_meta_gate"


def test_enda_packaging_substring_not_auto_allow(ctx: RunContext) -> None:
    """DP-A2 A: CUT packaging substring escape — only exact End-A names proceed."""
    _stamp_hard(ctx)
    # Exact packaging under hard freeze is soft-only → refuse (near-miss or meta).
    exact_ok, exact_why = seat_mutation_allowed(
        ctx, reason="media_ip_cta_editorial_omits", require_meta_gate=True
    )
    assert exact_ok is False
    assert exact_why.startswith("end_a_near_miss:") or exact_why == "frozen_needs_meta_gate"
    # Substring / compound reasons must refuse (near-miss preferred).
    for reason in (
        "selection_commit:media_ip_cta",
        "repair:cta_omit_residue",
    ):
        ok, why = seat_mutation_allowed(ctx, reason=reason, require_meta_gate=True)
        assert ok is False, reason
        assert why.startswith("end_a_near_miss:") or why == "frozen_needs_meta_gate", (
            reason,
            why,
        )
    ok2, why2 = seat_mutation_allowed(
        ctx, reason="sanitize_packaging_order", require_meta_gate=True
    )
    assert ok2 is False
    assert why2 == "frozen_needs_meta_gate"


def test_enda_allowlist_proceeds_forbidden_refused_under_hard_freeze(
    ctx: RunContext,
) -> None:
    """G-4/H-3 cascade: allowlisted actions proceed; forbidden/unknown refuse."""
    _stamp_hard(ctx)
    allowed, why = seat_mutation_allowed(
        ctx, reason="protect_orientation_from_omit", require_meta_gate=True
    )
    assert allowed is True
    assert why == "end_a_allowlist"

    revive_ok, revive_why = seat_mutation_allowed(
        ctx, reason="omit_ledger_revive_orientation", require_meta_gate=True
    )
    assert revive_ok is True
    assert revive_why == "end_a_allowlist"

    assert hard_freeze_blocks_action(ctx, "protect_hosted_vo_floor_reseat")
    blocked, why2 = seat_mutation_allowed(
        ctx, reason="protect_hosted_vo_floor_reseat", require_meta_gate=True
    )
    assert blocked is False

    unknown, why3 = seat_mutation_allowed(
        ctx, reason="unknown_expand_seats", require_meta_gate=True
    )
    assert unknown is False
    assert why3 == "frozen_needs_meta_gate"


def test_enda_seat_mutation_allowlist_bypasses_meta_gate(ctx: RunContext) -> None:
    _stamp_hard(ctx)
    allowed, why = seat_mutation_allowed(
        ctx, reason="omit_ledger_revive_orientation", require_meta_gate=True
    )
    assert allowed is True
    assert why == "end_a_allowlist"
    blocked, why2 = seat_mutation_allowed(
        ctx, reason="invent_new_seats", require_meta_gate=True
    )
    assert blocked is False
    assert why2 == "frozen_needs_meta_gate"


def test_enda_refuse_floor_reseat_under_hard_freeze(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When gap copy is below floor, hard freeze still refuses invent-reseat."""
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 3,
    )
    _stamp_hard(ctx)
    assert hard_freeze_blocks_action(ctx, "protect_hosted_vo_floor_reseat")

    # Only two active synth lines (< need=3) — must refuse, not invent.
    gap = minimal_gap_report(
        minimal_gap_line(
            line_id="vo_a",
            text="A short hosted line for the guest intro beat.",
            targets_segment_id="seg_001",
            delivery="synthesize",
        ),
        minimal_gap_line(
            line_id="vo_b",
            text="B short hosted line for the stakes beat.",
            targets_segment_id="seg_002",
            delivery="synthesize",
        ),
    )
    plan = {
        "air_script": {
            "vo_seats": {
                "seated_line_ids": ["vo_a"],
                "omitted_line_ids": ["vo_b"],
                "orientation_id": None,
            }
        }
    }
    omit = {"entries": []}
    before_seated = list(plan["air_script"]["vo_seats"]["seated_line_ids"])
    result = sanitize_air_contract(ctx, {"plan": plan, "gap": gap, "omit": omit})
    assert any(
        a.get("action") == "protect_hosted_vo_floor_reseat_refused_hard_freeze"
        for a in result.actions
    )
    assert not any(
        a.get("action") == "protect_hosted_vo_floor_reseat" for a in result.actions
    )
    assert not any(
        a.get("action") == "reseated_active_hosted_vo_for_wav" for a in result.actions
    )
    # Progress floors: count shortage under hard freeze → advisory-continue
    # (never invent seats). Legacy unsatisfiable hard-stop only when aspirational off.
    assert any(
        a.get("action") == "hosted_vo_floor_aspirational_continue"
        for a in result.actions
    )
    assert result.ok
    assert not any("hosted_vo_floor_unsatisfiable" in e for e in (result.errors or []))
    seats = (result.doc.get("air_script") or {}).get("vo_seats") or {}
    assert list(seats.get("seated_line_ids") or []) == before_seated
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    assert isinstance(meta, dict)
    assert meta.get("floor_aspirational_proceeded") is True
    assert not meta.get("hosted_vo_floor_unsatisfiable")


def test_enda_reseats_active_copy_for_wav_under_hard_freeze(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """active≥need but wav_backed short → End-A reseat + vo_synthesize pin."""
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.hosted_framing_requires_synthetic_vo",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        "interview_mux.gap_fill_eligibility.min_synthetic_vo_lines",
        lambda _ctx: 3,
    )
    monkeypatch.setattr(
        "interview_mux.vo_contract._gap_row_has_pickup_stem",
        lambda _ctx, row: str(row.get("line_id") or "") == "vo_a",
    )
    _stamp_hard(ctx)
    gap = minimal_gap_report(
        minimal_gap_line(
            line_id="vo_a",
            text="Hosted line A about the guest and topic for listeners.",
            targets_segment_id="seg_001",
            delivery="synthesize",
        ),
        minimal_gap_line(
            line_id="vo_b",
            text="Hosted line B about stakes and why this conversation matters.",
            targets_segment_id="seg_002",
            delivery="synthesize",
        ),
        minimal_gap_line(
            line_id="vo_c",
            text="Hosted line C connects the opening to the clinical arc ahead.",
            targets_segment_id="seg_003",
            delivery="synthesize",
        ),
    )
    plan = {
        "air_script": {
            "vo_seats": {
                "seated_line_ids": ["vo_a"],
                "omitted_line_ids": ["vo_b", "vo_c"],
                "orientation_id": None,
            }
        }
    }
    result = sanitize_air_contract(ctx, {"plan": plan, "gap": gap, "omit": {"entries": []}})
    assert any(
        a.get("action") == "reseated_active_hosted_vo_for_wav" for a in result.actions
    )
    seats = (result.doc.get("air_script") or {}).get("vo_seats") or {}
    seated = set(seats.get("seated_line_ids") or [])
    assert seated >= {"vo_a", "vo_b", "vo_c"}
    assert result.ok
    from interview_mux.artifact_sanitize.air_script import _floor_unmet_pin

    pin = _floor_unmet_pin([], list(result.actions or []))
    assert pin is not None and "hosted_vo_wav_coverage" in pin
    assert "vo_synthesize" in pin


def test_enda_auto_commit_skips_refuse_notes(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refuse-hard-freeze notes must not emit needs_sanitize forever."""
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.config.block_consumers_on_unsanitary",
        lambda: True,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.reentry.stamp_matches",
        lambda _doc: False,
    )
    monkeypatch.setattr(
        "interview_mux.artifact_sanitize.air_script.sanitize_air_contract",
        lambda _ctx, docs=None: type(
            "R",
            (),
            {
                "ok": True,
                "actions": [
                    {
                        "action": "protect_hosted_vo_floor_reseat_refused_hard_freeze",
                        "ids": ["vo_x"],
                    }
                ],
                "errors": [],
            },
        )(),
    )
    ctx.write_json("mastering/mastering_plan.json", {"air_script": {"vo_seats": {}}})
    _stamp_hard(ctx)
    errs = air_contract_sanitary_errors(ctx)
    # Progress floors: hard-freeze refuse of invent is advisory — no count-floor pin.
    assert errs == [] or not any("hosted_vo_floor_unsatisfiable" in e for e in errs)


def test_enda_protect_orientation_and_revive_under_hard_freeze(
    ctx: RunContext,
) -> None:
    gap = minimal_gap_report(
        minimal_gap_line(
            line_id="vo_orient",
            text="Welcome to the show.",
            episode_orientation=True,
            targets_segment_id="seg_001",
            delivery="synthesize",
            skipped_optional=True,
            air_script_omit=True,
        ),
    )
    gap["opening_orientation"] = {
        "required": True,
        "line_id": "vo_orient",
    }
    ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)
    _stamp_hard(ctx)

    omit = {
        "version": 1,
        "entries": [
            {
                "subject_id": "vo_orient",
                "kind": "gap_line_skip",
                "status": "active",
            }
        ],
        "summary": {
            "active_count": 1,
            "by_kind": {},
            "unresolved_high_salience": 0,
            "compensated_count": 0,
        },
    }
    dest = ctx.final_path(*OMIT_LEDGER_REL.split("/", 1))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(omit), encoding="utf-8")

    plan = {
        "air_script": {
            "vo_seats": {
                "seated_line_ids": ["vo_orient"],
                "omitted_line_ids": [],
                "orientation_id": "vo_orient",
            }
        }
    }
    result = sanitize_air_contract(
        ctx,
        {
            "plan": plan,
            "gap": ctx.read_json("understanding/gap_report.json"),
            "omit": json.loads(dest.read_text(encoding="utf-8")),
        },
    )
    assert any(
        a.get("action") == "protect_orientation_from_omit" for a in result.actions
    )

    out = revive_required_opening_orientation(ctx)
    assert out.get("changed") is True
    assert not any("seat_freeze_blocked" in str(n) for n in (out.get("notes") or []))
    gap2 = ctx.read_json("understanding/gap_report.json")
    orient = next(
        r
        for r in (gap2.get("interviewer_lines") or [])
        if isinstance(r, dict) and r.get("line_id") == "vo_orient"
    )
    assert not orient.get("skipped_optional")
    assert not orient.get("air_script_omit")


def test_enda_revive_clears_tier_d_under_hard_freeze(ctx: RunContext) -> None:
    """End-A Q2: hard freeze allowlisted revive clears tier-D stamps + reseats."""
    lid = "vo_orient_tier_d"
    gap = minimal_gap_report(
        minimal_gap_line(
            line_id=lid,
            text=(
                "Welcome to the show — meet the guest and hear why this "
                "conversation matters for listeners."
            ),
            episode_orientation=True,
            targets_segment_id="seg_001",
            delivery="synthesize",
            skipped_optional=True,
            air_script_omit=True,
            skip_reason_code="execution_contract_waive",
            compensating_path="tier_d_logged_waive",
            omit_notes=["vo_contract:execution_contract_waive"],
        ),
    )
    gap["opening_orientation"] = {
        "required": True,
        "line_id": lid,
        "target_segment_id": "seg_001",
    }
    ctx.write_json("understanding/gap_report.json", gap, skip_handoff=True)
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "beats": [
                    {"beat_id": "b1", "segment_id": "seg_001", "montage_move": "vo"}
                ],
                "vo_seats": {
                    "seated_line_ids": [],
                    "omitted_line_ids": [lid],
                    "orientation_id": None,
                },
            }
        },
        skip_handoff=True,
    )
    _stamp_hard(ctx)

    out = revive_required_opening_orientation(ctx)
    assert out.get("changed") is True
    assert not any("seat_freeze_blocked" in str(n) for n in (out.get("notes") or []))
    gap2 = ctx.read_json("understanding/gap_report.json")
    orient = next(
        r
        for r in (gap2.get("interviewer_lines") or [])
        if isinstance(r, dict) and r.get("line_id") == lid
    )
    assert not orient.get("skipped_optional")
    assert not orient.get("air_script_omit")
    assert str(orient.get("compensating_path") or "") != "tier_d_logged_waive"
    assert str(orient.get("skip_reason_code") or "") != "execution_contract_waive"
    plan = ctx.read_json("mastering/mastering_plan.json")
    seats = (plan.get("air_script") or {}).get("vo_seats") or {}
    assert lid in (seats.get("seated_line_ids") or [])
    assert seats.get("orientation_id") == lid


def test_enda_omit_order_lock_rebuild_under_hard_freeze(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "interview_mux.seat_authority.gate_seat_mutation",
        lambda *_a, **_k: False,
    )
    _stamp_hard(ctx)
    sel = bump_order_lock(
        {"ordered_segment_ids": ["seg_002", "seg_005"], "version": 1},
        source="enda",
    )
    ctx.write_json("master/selection.json", sel, skip_handoff=True)
    stale = {
        "version": 1,
        "order_content_hash": "deadbeefdeadbeef",
        "order_lock": {
            "version": 1,
            "revision": 1,
            "authority": "master/selection.json",
            "ordered_segment_ids": ["seg_002"],
            "order_content_hash": "deadbeefdeadbeef",
            "created_by": "test",
        },
        "entries": [],
        "summary": {
            "active_count": 0,
            "by_kind": {},
            "unresolved_high_salience": 0,
            "compensated_count": 0,
        },
    }
    dest = ctx.final_path(*OMIT_LEDGER_REL.split("/", 1))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(stale), encoding="utf-8")
    assert "omit_ledger_order_lock_stale" in air_contract_errors(ctx)
    out = heal_omit_ledger_air_contract(ctx)
    assert out.get("healed") is True
    assert "rebuilt_stale_order_lock" in (out.get("notes") or [])
    assert "omit_ledger_order_lock_stale" not in air_contract_errors(ctx)


def test_enda_transitions_strip_actions_allowlisted() -> None:
    for action in ("stamp_pair_freeze", "trim_pair_freeze", "framing_dedupe"):
        assert hard_freeze_action_permitted(action)


def test_enda_blank_drop_survives_freeze_order_preserve(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.air_order_boundary import _drop_blank_segments_under_freeze

    _stamp_hard(ctx)
    assert hard_freeze_action_permitted("drop_blank_segments_under_freeze")

    monkeypatch.setattr(
        "interview_mux.artifact_repairs._segment_is_blank_or_unusable",
        lambda _ctx, sid: str(sid) == "seg_blank",
    )
    sel = {
        "ordered_segment_ids": ["seg_blank", "seg_real"],
        "excluded_segment_ids": [],
        "chapters": [{"segment_ids": ["seg_blank", "seg_real"]}],
    }
    out = _drop_blank_segments_under_freeze(ctx, sel)
    assert "seg_blank" not in (out.get("ordered_segment_ids") or [])
    assert "seg_real" in (out.get("ordered_segment_ids") or [])
    excl_ids = {
        str(r.get("segment_id") if isinstance(r, dict) else r)
        for r in (out.get("excluded_segment_ids") or [])
    }
    assert "seg_blank" in excl_ids


def test_enda_persist_frozen_seat_doc_skips_unknown_reason(ctx: RunContext) -> None:
    """A3-1: gap/SDP/transitions writes under freeze skip unless End-A."""
    from interview_mux.seat_authority import persist_frozen_seat_doc

    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [{"line_id": "vo_a", "text": "A"}]},
        skip_handoff=True,
    )
    _stamp_hard(ctx)
    wrote = persist_frozen_seat_doc(
        ctx,
        "understanding/gap_report.json",
        {"interviewer_lines": [{"line_id": "vo_new", "text": "NEW"}]},
        reason="vo_line_adjudicate",
        skip_handoff=True,
    )
    assert wrote is False
    gap = ctx.read_json("understanding/gap_report.json")
    assert (gap.get("interviewer_lines") or [])[0].get("line_id") == "vo_a"

    wrote_ok = persist_frozen_seat_doc(
        ctx,
        "understanding/gap_report.json",
        {"interviewer_lines": [{"line_id": "vo_a", "text": "A", "omit": True}]},
        reason="stamp_gap_omit_flags",
        skip_handoff=True,
    )
    assert wrote_ok is True


def test_enda_optimizer_reasons_are_not_allowlisted() -> None:
    from interview_mux.seat_authority import hard_freeze_action_permitted

    assert not hard_freeze_action_permitted("optimizer_promote_gap_report")
    assert not hard_freeze_action_permitted("optimizer_promote_sdp")
    assert not hard_freeze_action_permitted("optimizer_promote_transitions")
    # A′′: synth-fail unseat / hitch reattach must-land under freeze.
    assert hard_freeze_action_permitted("catastrophe_seated_bind_synth_failed")
    assert hard_freeze_action_permitted("hitch_reattach_vo")
    assert hard_freeze_action_permitted("air_script_gap_omit_sync")
    assert hard_freeze_action_permitted("revive_discarded_floor_candidate")


def test_a3_global_freeze_sdp_and_transitions_skip_unknown(
    ctx: RunContext,
) -> None:
    """A′′: commit_sdp / commit_transitions End-A-or-skip under hard freeze."""
    from interview_mux.analysis_memory import default_sound_design_plan
    from interview_mux.artifact_sanitize.one_writer import (
        commit_sound_design_plan_doc,
        commit_transitions_doc,
    )
    from interview_mux.file_store import write_json as fs_write_json
    from interview_mux.seat_authority import seat_fingerprint

    sdp0 = default_sound_design_plan()
    # Seed on disk without hot-admit schema thrash (freeze gate is the subject).
    fs_write_json(ctx.final_path("understanding", "sound_design_plan.json"), sdp0)
    fs_write_json(
        ctx.final_path("master", "transitions.json"),
        {"transitions": [{"id": "t1", "text": "was"}]},
    )
    _stamp_hard(ctx)
    fp_before = seat_fingerprint(ctx)

    sdp_new = default_sound_design_plan()
    fp1 = dict(sdp_new.get("flow_plans") or {})
    pod1 = dict(fp1.get("podcast") or {})
    cues = list(pod1.get("cues") or [])
    if cues and isinstance(cues[0], dict):
        cues[0] = dict(cues[0])
        cues[0]["cue_id"] = "c_NEW_HIJACK"
    else:
        cues = [{"cue_id": "c_NEW_HIJACK"}]
    pod1["cues"] = cues
    fp1["podcast"] = pod1
    sdp_new["flow_plans"] = fp1

    prior_cue = None
    prior = ctx.read_json("understanding/sound_design_plan.json")
    prior_cues = (
        ((prior.get("flow_plans") or {}).get("podcast") or {}).get("cues") or []
    )
    if prior_cues and isinstance(prior_cues[0], dict):
        prior_cue = prior_cues[0].get("cue_id")

    commit_sound_design_plan_doc(ctx, sdp_new, reason="unknown_hijack_not_enda")
    sdp = ctx.read_json("understanding/sound_design_plan.json")
    after_cues = ((sdp.get("flow_plans") or {}).get("podcast") or {}).get("cues") or []
    after_id = after_cues[0].get("cue_id") if after_cues and isinstance(after_cues[0], dict) else None
    assert after_id == prior_cue
    assert after_id != "c_NEW_HIJACK"

    commit_transitions_doc(
        ctx,
        {"transitions": [{"id": "t_NEW", "text": "new"}]},
        reason="optimizer_promote_transitions",
    )
    tr = ctx.read_json("master/transitions.json")
    assert (tr.get("transitions") or [])[0].get("id") == "t1"
    assert seat_fingerprint(ctx) == fp_before


def test_a3_global_freeze_blocks_raw_escape(ctx: RunContext) -> None:
    """A′′: _one_writer_raw cannot bypass gap under freeze."""
    from interview_mux.artifact_sanitize.one_writer import maybe_admit_hot_write

    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": [{"line_id": "vo_a", "text": "A"}]},
        skip_handoff=True,
    )
    _stamp_hard(ctx)
    setattr(ctx, "_one_writer_raw", True)
    try:
        path = maybe_admit_hot_write(
            ctx,
            "understanding/gap_report.json",
            {"interviewer_lines": [{"line_id": "vo_hijack", "text": "X"}]},
            reason="sneaky_raw",
            skip_handoff=True,
        )
        # Under freeze raw escape is forced through admit → skip (not End-A).
        assert path is not None
        gap = ctx.read_json("understanding/gap_report.json")
        assert (gap.get("interviewer_lines") or [])[0].get("line_id") == "vo_a"
    finally:
        try:
            delattr(ctx, "_one_writer_raw")
        except Exception:
            setattr(ctx, "_one_writer_raw", False)


def test_a3_write_plan_preserves_vo_seats_under_freeze(ctx: RunContext) -> None:
    from interview_mux.mastering_plan_loader import write_plan

    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": ["vo_a"],
                    "omitted_line_ids": [],
                }
            }
        },
        skip_handoff=True,
    )
    _stamp_hard(ctx)
    write_plan(
        ctx,
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": ["vo_hijack"],
                    "omitted_line_ids": [],
                }
            },
            "information_packages": [],
        },
        seat_reason="",
    )
    plan = ctx.read_json("mastering/mastering_plan.json")
    seats = ((plan.get("air_script") or {}).get("vo_seats") or {})
    assert seats.get("seated_line_ids") == ["vo_a"]


def test_enda_episode_close_rebind_verified_under_hard_freeze(
    ctx: RunContext, tmp_path: Path
) -> None:
    """Footgun 1: outro rebind uses End-A verify; create skipped under freeze."""
    from interview_mux.listen_quality import place_episode_close_cue
    from run_fixtures import sound_design_plan_with

    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001", "seg_002"]},
        skip_handoff=True,
    )
    sdp = sound_design_plan_with(
        assets=[
            {
                "asset_id": "outro_bed",
                "role": "theme_outro",
                "description": "close",
                "duration_seconds": 8,
            }
        ],
        flow_plans={
            "podcast": {
                "cues": [
                    {
                        "cue_id": "theme_outro_old",
                        "role": "theme_outro",
                        "asset_id": "outro_bed",
                        "placement": "after_segment",
                        "segment_id": "seg_001",
                        "after_segment_id": "seg_001",
                    }
                ]
            }
        },
    )
    ctx.write_json("understanding/sound_design_plan.json", sdp, skip_handoff=True)
    _stamp_hard(ctx)
    written = place_episode_close_cue(ctx, allow_create=False)
    assert "understanding/sound_design_plan.json" in written
    live = ctx.read_json("understanding/sound_design_plan.json")
    cues = list(((live.get("flow_plans") or {}).get("podcast") or {}).get("cues") or [])
    outro = next(c for c in cues if c.get("cue_id") == "theme_outro_old")
    assert outro.get("after_segment_id") == "seg_002"

    # Create path refused under hard freeze (fresh plan with no outro cue).
    ctx2 = isolated_run_ctx(tmp_path, "enda_outro_create")
    ctx2.write_json(
        "run_meta.json",
        {
            "homunculus_version": "0.1.0",
            "homunculus_kind": "homunculus",
            "delivery_epoch": {},
        },
        skip_handoff=True,
    )
    ctx2.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001"]},
        skip_handoff=True,
    )
    empty = sound_design_plan_with(
        assets=[
            {
                "asset_id": "outro_bed",
                "role": "theme_outro",
                "description": "close",
                "duration_seconds": 8,
            }
        ],
        flow_plans={"podcast": {"cues": []}},
    )
    ctx2.write_json("understanding/sound_design_plan.json", empty, skip_handoff=True)
    stamp_hard_seat_freeze(ctx2, reason="vo_synthesize")
    written2 = place_episode_close_cue(ctx2, allow_create=True)
    assert "understanding/sound_design_plan.json" not in written2
    live2 = ctx2.read_json("understanding/sound_design_plan.json")
    cues2 = list(((live2.get("flow_plans") or {}).get("podcast") or {}).get("cues") or [])
    assert not any(
        isinstance(c, dict) and str(c.get("cue_id") or "") == "theme_outro_seed"
        for c in cues2
    )