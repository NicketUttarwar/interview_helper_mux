"""Air-script Shape realization: paper-edit, story contract, sonic architecture."""

from __future__ import annotations

import json

from interview_mux.air_script import (
    compile_circumstance_card,
    compose_pass_a,
    compose_pass_b,
    cues_from_sonic_plan,
    filter_gap_lines_for_air_script,
    lint_story_clarity,
    native_handoff_segment_ids,
    persist_air_script_omits_on_gap_report,
    unused_required_opportunities,
)
from interview_mux.mastering_plan_loader import forced_sparse_plan, write_plan
from interview_mux.stages.assembly import build_flow1_edl
from interview_mux.v2.config import DELIVERY_ORDER
from run_fixtures import isolated_run_ctx


def _write_raw(ctx, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _seed_plan(ctx, *, ordered: list[str], talking_points: list[str] | None = None) -> None:
    segs = []
    t = 0
    for i, sid in enumerate(ordered):
        segs.append(
            {
                "segment_id": sid,
                "speaker_id": "spk_host" if i % 2 == 0 else "spk_guest",
                "speaker_role": "interviewer" if i % 2 == 0 else "interviewee",
                "type": "interviewer_question" if i % 2 == 0 else "interviewee_answer",
                "start_ms": t,
                "end_ms": t + 8_000,
                "text": f"Beat {i} on {sid}",
                "topic_tags": ["origin_story"],
            }
        )
        t += 8_500
    ctx.write_json("segments/manifest.json", {"segments": segs})
    ctx.write_json("master/selection.json", {"ordered_segment_ids": list(ordered)})
    if talking_points:
        _write_raw(
            ctx,
            "understanding/talking_points.json",
            {
                "talking_points": [
                    {"segment_id": sid, "claim": f"claim {sid}"} for sid in talking_points
                ]
            },
        )
    write_plan(ctx, forced_sparse_plan(reason="air_script_test"))


def test_delivery_order_places_air_script_passes():
    assert "air_script_compose" in DELIVERY_ORDER
    assert "air_script_seams" in DELIVERY_ORDER
    assert DELIVERY_ORDER.index("air_script_compose") > DELIVERY_ORDER.index(
        "full_master_ranking"
    )
    assert DELIVERY_ORDER.index("air_script_compose") < DELIVERY_ORDER.index(
        "nugget_corpus_mine"
    )
    assert DELIVERY_ORDER.index("air_script_seams") > DELIVERY_ORDER.index(
        "selection_framing_apply"
    )
    assert DELIVERY_ORDER.index("air_script_seams") < DELIVERY_ORDER.index("transitions")
    assert DELIVERY_ORDER.index("air_script_seams") < DELIVERY_ORDER.index("edl")


def test_air_script_compose_contract_tier_is_process():
    """ASC-B1: Pass A is deterministic — contract must not claim llm_full."""
    from interview_mux.stage_contract import load_contract

    contract = load_contract("air_script_compose")
    assert contract is not None
    assert contract.tier == "process"
    assert "llm_execute" not in contract.lifecycle_phases
    assert "execute" in contract.lifecycle_phases


def test_air_script_seams_contract_tier_is_process():
    """ASS-B1: Pass B is deterministic — contract must not claim llm_full."""
    from interview_mux.stage_contract import load_contract

    contract = load_contract("air_script_seams")
    assert contract is not None
    assert contract.tier == "process"
    assert "llm_execute" not in contract.lifecycle_phases
    assert "execute" in contract.lifecycle_phases


def test_air_script_compose_disabled_writes_skip_and_marks_done(tmp_path, monkeypatch):
    """ASC-B2 / CSP-01: enable=false must write skip latch + heal."""
    from interview_mux.air_script import run_air_script_compose

    ctx = isolated_run_ctx(tmp_path, "exec_air_compose_disabled")
    monkeypatch.setattr("interview_mux.air_script.air_script_enabled", lambda: False)
    run_air_script_compose(ctx)
    plan = ctx.read_json("mastering/mastering_plan.json")
    script = plan.get("air_script") or {}
    assert script.get("skip_reason") == "air_script_disabled"
    assert script.get("enabled") is False
    assert script.get("pass") == "pass_a"
    assert ctx.is_done("air_script_compose")
    omit = ctx.read_json("understanding/omit_ledger.json")
    assert omit.get("skip_reason") == "air_script_disabled"


def test_air_script_seams_disabled_writes_skip_and_marks_done(tmp_path, monkeypatch):
    """ASS-B2 / CSP-01: enable=false must write skip latch + heal."""
    from interview_mux.air_script import run_air_script_seams

    ctx = isolated_run_ctx(tmp_path, "exec_air_seams_disabled")
    monkeypatch.setattr("interview_mux.air_script.air_script_enabled", lambda: False)
    run_air_script_seams(ctx)
    plan = ctx.read_json("mastering/mastering_plan.json")
    script = plan.get("air_script") or {}
    assert script.get("skip_reason") == "air_script_disabled"
    assert script.get("enabled") is False
    assert script.get("pass") == "pass_b"
    assert ctx.is_done("air_script_seams")


def test_air_contract_sanitize_contract_lifecycle_is_non_llm():
    """ACS-B2: commit/heal host — contract must not claim llm_execute."""
    from interview_mux.stage_contract import load_contract

    contract = load_contract("air_contract_sanitize")
    assert contract is not None
    assert contract.tier == "process"
    assert "llm_execute" not in contract.lifecycle_phases
    assert "execute" in contract.lifecycle_phases


def test_pass_a_does_not_omit_setup_or_hard_keeps(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "exec_air_setup")
    ordered = [f"seg_{i:03d}" for i in range(1, 13)]
    _seed_plan(ctx, ordered=ordered, talking_points=["seg_001", "seg_002", "seg_005"])
    monkeypatch.setattr(
        "interview_mux.air_script.hard_keep_segment_ids",
        lambda _c: {"seg_003"},
    )
    monkeypatch.setattr(
        "interview_mux.air_script.compile_circumstance_card",
        lambda _c: {
            "tape_character": ["long_meander"],
            "passion_segment_ids": ["seg_010"],
            "g1_skip": False,
            "nle_locked": False,
            "dry_beds": False,
        },
    )
    plan = compose_pass_a(ctx)
    omitted = {row["subject_id"] for row in (plan["air_script"]["omits"] or [])}
    assert "seg_001" not in omitted
    assert "seg_002" not in omitted
    assert "seg_003" not in omitted
    assert "seg_010" not in omitted
    aired = [b["segment_id"] for b in plan["air_script"]["beats"]]
    assert "seg_001" in aired
    sel = ctx.read_json("master/selection.json")
    assert "seg_001" in sel["ordered_segment_ids"]


def test_native_handoff_when_host_already_asked(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_air_handoff")
    ordered = ["seg_001", "seg_002", "seg_003"]
    _seed_plan(ctx, ordered=ordered)
    compose_pass_a(ctx)
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_leak",
                    "gap_type": "framing",
                    "targets_segment_id": "seg_002",
                    "placement": "before",
                    "delivery": "synthesize",
                    "origin": "nugget_layup",
                    "selected_nugget_ids": ["nug_a"],
                    "text": "So what happened next?",
                }
            ]
        },
    )
    plan = compose_pass_b(ctx)
    guest = next(b for b in plan["air_script"]["beats"] if b.get("segment_id") == "seg_002")
    assert guest["montage_move"] == "native_handoff"
    assert not guest.get("line_id")


def test_vo_leak_filtered_from_edl(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_air_vo_leak")
    ordered = ["seg_a", "seg_b"]
    _seed_plan(ctx, ordered=ordered)
    compose_pass_a(ctx)
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "seat_ok",
                    "gap_type": "framing",
                    "targets_segment_id": "seg_a",
                    "placement": "before",
                    "delivery": "record",
                    "line_category": "episode_preface",
                    "episode_orientation": True,
                    "text": "Today we sit down with Maya about the raise.",
                },
                {
                    "line_id": "vo_leak",
                    "gap_type": "framing",
                    "targets_segment_id": "seg_b",
                    "placement": "before",
                    "delivery": "record",
                    "origin": "nugget_layup",
                    "text": "Restating the raise again.",
                },
            ]
        },
    )
    plan = compose_pass_b(ctx)
    filtered = filter_gap_lines_for_air_script(
        ctx.read_json("understanding/gap_report.json"), plan
    )
    leaked = [
        ln
        for ln in filtered["interviewer_lines"]
        if ln.get("line_id") == "vo_leak" and not ln.get("skipped_optional")
    ]
    assert leaked == []
    orient = [
        ln
        for ln in filtered["interviewer_lines"]
        if ln.get("line_id") == "seat_ok" and not ln.get("skipped_optional")
    ]
    assert orient

    vo = tmp_path / "vo.wav"
    vo.write_bytes(b"\x00")
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ordered},
        segments_by_id={
            "seg_a": {"segment_id": "seg_a", "start_ms": 0, "end_ms": 4000},
            "seg_b": {"segment_id": "seg_b", "start_ms": 5000, "end_ms": 9000},
        },
        gap_report=filtered,
        resolve_vo_path=lambda line: vo,
        vo_relpath=lambda p: "vo.wav",
        vo_duration_ms=lambda _p: 500,
    )
    line_ids = [c.get("line_id") for c in edl["clips"] if c.get("line_id")]
    assert "vo_leak" not in line_ids
    assert "seat_ok" in line_ids


def test_recovery_layup_after_guest_is_seated(tmp_path):
    """Interviewee must not match as host via 'interview' substring."""
    ctx = isolated_run_ctx(tmp_path, "exec_air_guest_layup")
    ordered = ["seg_015", "seg_016"]
    segs = [
        {
            "segment_id": "seg_015",
            "speaker_id": "spk_guest",
            "speaker_role": "interviewee",
            "type": "interviewee_answer",
            "start_ms": 0,
            "end_ms": 8_000,
            "text": "We created protein chips as a new concept.",
            "topic_tags": ["product"],
        },
        {
            "segment_id": "seg_016",
            "speaker_id": "spk_host",
            "speaker_role": "interviewer",
            "type": "interviewer_question",
            "start_ms": 9_000,
            "end_ms": 17_000,
            "text": "We built the business to 160 crores and now need resources.",
            "topic_tags": ["scale"],
        },
    ]
    ctx.write_json("segments/manifest.json", {"segments": segs})
    ctx.write_json("master/selection.json", {"ordered_segment_ids": list(ordered)})
    write_plan(ctx, forced_sparse_plan(reason="air_script_test"))
    compose_pass_a(ctx)
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_016",
                    "gap_type": "nugget_layup",
                    "targets_segment_id": "seg_016",
                    "placement": "before",
                    "delivery": "synthesize",
                    "origin": "nugget_layup",
                    "required": True,
                    "severity": "high",
                    "nugget_ids": ["nug_019"],
                    "selected_nugget_ids": ["nug_019"],
                    "text": "The Zydus transaction closed yesterday.",
                    "air_script_omit": True,
                    "skipped_optional": True,
                }
            ]
        },
    )
    plan = compose_pass_b(ctx)
    beat = next(b for b in plan["air_script"]["beats"] if b.get("segment_id") == "seg_016")
    assert beat["montage_move"] == "vo_then_clip"
    assert beat.get("line_id") == "vo_layup_seg_016"
    seats = plan["air_script"]["vo_seats"]
    assert "vo_layup_seg_016" in (seats.get("seated_line_ids") or [])
    assert "vo_layup_seg_016" not in (seats.get("omitted_line_ids") or [])


def test_unpaid_cold_open_fails_story_lint():
    lint = lint_story_clarity(
        beats=[
            {
                "id": "beat_001",
                "segment_id": "seg_body",
                "montage_move": "native_handoff",
                "know_entering": "oriented",
                "know_leaving": "native",
            }
        ],
        ordered=["seg_body"],
        cold_open={"kind": "segment_hook", "segment_id": "seg_tease"},
    )
    assert lint["ok"] is False
    assert "unpaid_cold_open" in lint["errors"]
    assert lint["story_followability"] < 0.85


def test_competing_host_and_vo_wall_penalize():
    beats = [
        {
            "id": "b1",
            "segment_id": "s1",
            "montage_move": "vo_then_clip",
            "is_orientation": True,
            "know_entering": "open",
            "know_leaving": "next",
        },
        {
            "id": "b2",
            "segment_id": "s2",
            "montage_move": "vo_then_clip",
            "know_entering": "prior",
            "know_leaving": "next",
        },
        {
            "id": "b3",
            "segment_id": "s3",
            "montage_move": "vo_then_clip",
            "know_entering": "prior",
            "know_leaving": "next",
        },
    ]
    lint = lint_story_clarity(beats=beats, ordered=["s1", "s2", "s3"])
    assert "vo_wall" in lint["warnings"]
    assert lint["story_followability"] < 0.9



def test_requested_vo_line_ids_excludes_omitted_seats():
    from interview_mux.air_script import requested_vo_line_ids

    plan = {
        "air_script": {
            "vo_seats": {
                "seated_line_ids": ["vo_keep"],
                "omitted_line_ids": ["vo_omit"],
            },
            "beats": [
                {"montage_move": "vo_then_clip", "line_id": "vo_keep", "segment_id": "s1"},
                {"montage_move": "vo_then_clip", "line_id": "vo_omit", "segment_id": "s2"},
            ],
        }
    }
    assert requested_vo_line_ids(plan) == {"vo_keep"}


def test_ordered_ids_prefers_plan_over_thin_reseat_beats():
    from interview_mux.air_script import ordered_ids_from_air_script

    plan = {
        "ordered_segment_ids": ["seg_a", "seg_b", "seg_c", "seg_d"],
        "air_script": {
            "beats": [
                {
                    "segment_id": "seg_b",
                    "montage_move": "vo_then_clip",
                    "role": "hosted_framing_reseat",
                    "line_id": "vo_1",
                },
                {
                    "segment_id": "seg_c",
                    "montage_move": "vo_then_clip",
                    "role": "hosted_framing_reseat",
                    "line_id": "vo_2",
                },
            ]
        },
    }
    assert ordered_ids_from_air_script(plan) == ["seg_a", "seg_b", "seg_c", "seg_d"]


def test_hosted_framing_reseat_beats_do_not_trip_vo_wall():
    beats = [
        {
            "segment_id": "s1",
            "montage_move": "vo_then_clip",
            "role": "hosted_framing_reseat",
            "line_id": "vo_1",
        },
        {
            "segment_id": "s2",
            "montage_move": "vo_then_clip",
            "role": "hosted_framing_reseat",
            "line_id": "vo_2",
        },
        {
            "segment_id": "s3",
            "montage_move": "vo_then_clip",
            "role": "hosted_framing_reseat",
            "line_id": "vo_3",
        },
    ]
    lint = lint_story_clarity(beats=beats, ordered=["s1", "s2", "s3"])
    assert "vo_wall" not in lint["warnings"]
    assert not any(str(w).startswith("missing_know_") for w in lint["warnings"])


def test_circumstance_card_diversity(tmp_path):
    fireside = isolated_run_ctx(tmp_path, "exec_air_card_fire")
    _seed_plan(fireside, ordered=["seg_001", "seg_002"])
    _write_raw(
        fireside,
        "understanding/source_topology.json",
        {"topology_class": "dyad", "speaker_count": 2},
    )
    _write_raw(
        fireside,
        "understanding/analysis_state.json",
        {"style": {"format_class": "fireside", "tone_class": "conversational"}},
    )
    _write_raw(
        fireside,
        "understanding/source_acoustic_profile.json",
        {
            "duration_sec": 2400,
            "source_music_risk": "low",
            "mix_contract": {"underscore_policy": "normal"},
        },
    )
    fire_card = compile_circumstance_card(fireside)
    assert fire_card["dry_beds"] is False
    assert fire_card["speaker_count"] == 2

    panel = isolated_run_ctx(tmp_path, "exec_air_card_panel")
    _seed_plan(panel, ordered=["seg_001", "seg_002"])
    _write_raw(
        panel,
        "understanding/source_topology.json",
        {"topology_class": "panel", "speaker_count": 5},
    )
    _write_raw(
        panel,
        "understanding/analysis_state.json",
        {"style": {"format_class": "panel", "tone_class": "journalistic"}},
    )
    _write_raw(
        panel,
        "understanding/source_acoustic_profile.json",
        {
            "duration_sec": 3600,
            "source_music_risk": "high",
            "mix_contract": {"underscore_policy": "skip"},
        },
    )
    panel_card = compile_circumstance_card(panel)
    assert panel_card["dry_beds"] is True
    assert panel_card["panel_overlap"] is True
    assert fire_card["dry_beds"] != panel_card["dry_beds"]


def test_fireside_abundant_beds_and_motif_reprise(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_air_music_fire")
    ordered = ["seg_001", "seg_002", "seg_003", "seg_004"]
    _seed_plan(ctx, ordered=ordered, talking_points=["seg_001", "seg_003"])
    _write_raw(
        ctx,
        "master/narrative_plan.json",
        {
            "chapters": [
                {"chapter_id": "ch1", "segment_ids": ["seg_001", "seg_002"]},
                {"chapter_id": "ch2", "segment_ids": ["seg_003", "seg_004"]},
            ]
        },
    )
    compose_pass_a(ctx)
    compose_pass_b(ctx)
    from interview_mux.air_script import attach_sonic_scenes

    plan = attach_sonic_scenes(ctx)
    kinds = {o["kind"] for o in plan["sonic_opportunities"]}
    assert "open_motif" in kinds
    assert "scene_bed" in kinds
    assert "episode_close" in kinds
    assets_by_kind = {
        "full_bed": [{"asset_id": "bed_open", "role": "theme_cold_open"}],
        "underscore_loop": [{"asset_id": "loop_a", "role": "theme_underscore"}],
        "optional_loop": [{"asset_id": "loop_b", "role": "optional_loop"}],
        "stinger": [{"asset_id": "sting_1", "role": "theme_emphasis"}],
        "motif": [{"asset_id": "motif_1", "role": "motif"}],
    }
    cues = cues_from_sonic_plan(plan, assets_by_kind=assets_by_kind)
    roles = {c["role"] for c in cues}
    assert "theme_cold_open" in roles or "motif" in roles
    assert "theme_outro" in roles
    assert any(c.get("placement") == "under_segment" for c in cues)
    assert unused_required_opportunities(plan, cues) == []
    assert not any("whoosh" in str(c.get("role") or "") for c in cues)
    assert not any("foley" in str(c.get("role") or "") for c in cues)


def test_panel_overlap_stays_dry(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_air_music_dry")
    ordered = ["seg_001", "seg_002"]
    _seed_plan(ctx, ordered=ordered)
    compose_pass_a(ctx)
    plan = ctx.read_json("mastering/mastering_plan.json")
    plan["circumstance_card"] = {
        "dry_beds": True,
        "source_music_risk": True,
        "source_music_risk_level": "high",
        "panel_overlap": True,
        "passion_segment_ids": [],
    }
    write_plan(ctx, plan)
    compose_pass_b(ctx)
    from interview_mux.air_script import attach_sonic_scenes

    plan = attach_sonic_scenes(ctx)
    kinds = [o["kind"] for o in plan["sonic_opportunities"]]
    assert "scene_bed" not in kinds
    assert "open_motif" in kinds
    assert "episode_close" in kinds


def test_every_nth_only_is_unused_opportunities(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_air_nth")
    ordered = ["seg_001", "seg_002", "seg_003", "seg_004"]
    _seed_plan(ctx, ordered=ordered)
    compose_pass_a(ctx)
    compose_pass_b(ctx)
    from interview_mux.air_script import attach_sonic_scenes

    plan = attach_sonic_scenes(ctx)
    wallpaper = [
        {
            "cue_id": "nth_1",
            "role": "theme_underscore",
            "placement": "under_segment",
            "under_segment_id": "seg_001",
        }
    ]
    unused = unused_required_opportunities(plan, wallpaper)
    assert unused
    assert any(u == "episode_close" or u.startswith("scene_bed") for u in unused)


def test_fail_open_without_plan(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_air_no_plan")
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_001"]})
    assert compose_pass_a(ctx) == {}
    gap = {
        "interviewer_lines": [
            {
                "line_id": "keep_me",
                "targets_segment_id": "seg_001",
                "placement": "before",
                "delivery": "record",
                "text": "hello",
            }
        ]
    }
    assert filter_gap_lines_for_air_script(gap, None) is gap


def test_required_orientation_revives_stale_air_script_omit(tmp_path):
    """Required opening_orientation meta wins over stale air_script_omit flags."""
    plan = {
        "air_script": {
            "beats": [
                {
                    "id": "b0",
                    "segment_id": "seg_001",
                    "montage_move": "vo_setup",
                    "line_id": "vo_preface_precision_oncology",
                }
            ],
            "vo_seats": {
                "seated_line_ids": ["vo_preface_precision_oncology"],
                "omitted_line_ids": [],
                "orientation_id": "vo_preface_precision_oncology",
            },
        }
    }
    gap = {
        "opening_orientation": {
            "line_id": "vo_preface_precision_oncology",
            "required": True,
            "target_segment_id": "seg_001",
        },
        "interviewer_lines": [
            {
                "line_id": "vo_preface_precision_oncology",
                "gap_type": "missing_setup",
                "targets_segment_id": "seg_001",
                "placement": "before",
                "delivery": "synthesize",
                "line_category": "episode_preface",
                "episode_orientation": True,
                "skipped_optional": True,
                "air_script_omit": True,
                "skip_reason_code": "air_script_omit_sync",
                "text": "Precision oncology orients the listener.",
            }
        ],
    }
    filtered = filter_gap_lines_for_air_script(gap, plan)
    orient = next(
        ln
        for ln in filtered["interviewer_lines"]
        if ln.get("line_id") == "vo_preface_precision_oncology"
    )
    assert orient.get("skipped_optional") is False
    assert not orient.get("air_script_omit")
    # build_vo_seats must also seat from the *stale* gap row — omit_sync alone
    # is not a durable waive when opening_orientation.required stays true.
    from interview_mux.air_script import build_vo_seats, seated_vo_line_ids

    seats = build_vo_seats(plan, gap)
    assert "vo_preface_precision_oncology" in set(seats.get("seated_line_ids") or [])
    assert "vo_preface_precision_oncology" not in set(seats.get("omitted_line_ids") or [])


def test_opening_layup_suppressed_when_orientation_owns_slot(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_air_open_adj")
    ordered = ["seg_001", "seg_002"]
    _seed_plan(ctx, ordered=ordered)
    compose_pass_a(ctx)
    # Layup listed first so first-match would steal the opening seat without the fix.
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_layup_seg_001",
                    "gap_type": "framing",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "delivery": "synthesize",
                    "origin": "nugget_layup",
                    "selected_nugget_ids": ["nug_a"],
                    "text": "What should we listen for next?",
                },
                {
                    "line_id": "vo_preface_episode_orientation",
                    "gap_type": "framing",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "delivery": "synthesize",
                    "line_category": "episode_preface",
                    "episode_orientation": True,
                    "text": "Before the science, meet the founder.",
                },
            ]
        },
    )
    plan = compose_pass_b(ctx)
    vo_ids = [b.get("line_id") for b in plan["air_script"]["beats"] if b.get("line_id")]
    assert "vo_preface_episode_orientation" in vo_ids
    assert "vo_layup_seg_001" not in vo_ids
    stamped = persist_air_script_omits_on_gap_report(ctx)
    assert stamped >= 1
    gap = ctx.read_json("understanding/gap_report.json")
    layup = next(ln for ln in gap["interviewer_lines"] if ln.get("line_id") == "vo_layup_seg_001")
    orient = next(
        ln
        for ln in gap["interviewer_lines"]
        if ln.get("line_id") == "vo_preface_episode_orientation"
    )
    assert layup.get("skipped_optional") and layup.get("air_script_omit")
    assert not orient.get("skipped_optional")
    assert not orient.get("air_script_omit")
    from interview_mux.mastering_plan_loader import load_plan_raw

    seats = (load_plan_raw(ctx) or {}).get("air_script", {}).get("vo_seats") or {}
    assert "vo_preface_episode_orientation" in (seats.get("seated_line_ids") or [])
    assert "vo_layup_seg_001" in (seats.get("omitted_line_ids") or [])


def test_persist_unskips_orientation_even_under_pending_edl(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_air_pending_orient")
    ordered = ["seg_001", "seg_002"]
    _seed_plan(ctx, ordered=ordered)
    compose_pass_a(ctx)
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_preface_episode_orientation",
                    "gap_type": "framing",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "delivery": "synthesize",
                    "line_category": "episode_preface",
                    "episode_orientation": True,
                    "skipped_optional": True,
                    "text": "Before the science, meet the founder.",
                },
                {
                    "line_id": "vo_layup_seg_002",
                    "gap_type": "framing",
                    "targets_segment_id": "seg_002",
                    "placement": "before",
                    "delivery": "synthesize",
                    "origin": "nugget_layup",
                    "text": "What should we listen for next?",
                },
            ]
        },
    )
    compose_pass_b(ctx)
    pending = ctx.run_dir / ".pending_writes" / "edl" / "understanding"
    pending.mkdir(parents=True, exist_ok=True)
    pending.joinpath("gap_report.json").write_text(
        ctx.path("understanding", "gap_report.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    persist_air_script_omits_on_gap_report(ctx)
    gap = ctx.read_json("understanding/gap_report.json")
    orient = next(
        ln for ln in gap["interviewer_lines"] if ln.get("line_id") == "vo_preface_episode_orientation"
    )
    assert not orient.get("skipped_optional")


def test_omitted_orientation_is_not_force_aired(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_air_omit_orient")
    ordered = ["seg_001", "seg_002"]
    _seed_plan(ctx, ordered=ordered)
    compose_pass_a(ctx)
    _write_raw(
        ctx,
        "understanding/gap_report.json",
        {
            "opening_orientation": {
                "required": False,
                "omitted": True,
                "omit_reason": "native_open_self_orients",
                "sequence": "music_body",
                "target_segment_id": "seg_001",
            },
            "interviewer_lines": [
                {
                    "line_id": "vo_preface_episode_orientation",
                    "gap_type": "framing",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "delivery": "synthesize",
                    "line_category": "episode_preface",
                    "episode_orientation": True,
                    "skipped_optional": True,
                    "air_script_omit": True,
                    "text": "Before the science, meet the founder.",
                },
                {
                    "line_id": "vo_layup_seg_001",
                    "gap_type": "framing",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "delivery": "synthesize",
                    "origin": "nugget_layup",
                    "selected_nugget_ids": ["nug_a"],
                    "text": "What should we listen for next?",
                },
            ],
        },
    )
    plan = compose_pass_b(ctx)
    first = next(b for b in plan["air_script"]["beats"] if b.get("segment_id") == "seg_001")
    assert first.get("montage_move") == "native_handoff"
    assert not first.get("is_orientation")
    assert first.get("line_id") in {None, ""}
    persist_air_script_omits_on_gap_report(ctx)
    gap = ctx.read_json("understanding/gap_report.json")
    orient = next(
        ln for ln in gap["interviewer_lines"] if ln.get("line_id") == "vo_preface_episode_orientation"
    )
    assert orient.get("skipped_optional")
    assert orient.get("air_script_omit")
    from interview_mux.air_script import build_vo_seats
    from interview_mux.mastering_plan_loader import load_plan_raw

    seats = build_vo_seats(load_plan_raw(ctx), gap)
    assert "vo_preface_episode_orientation" not in (seats.get("seated_line_ids") or [])
    assert "vo_preface_episode_orientation" in (seats.get("omitted_line_ids") or [])
    assert seats.get("orientation_id") in {None, ""}


def test_build_vo_seats_respects_execution_contract_waive(tmp_path):
    from interview_mux.air_script import build_vo_seats

    ctx = isolated_run_ctx(tmp_path, "exec_air_waive_orient")
    plan = {
        "air_script": {
            "beats": [],
            "vo_seats": {
                "seated_line_ids": ["vo_preface_precision_oncology"],
                "omitted_line_ids": [],
                "orientation_id": "vo_preface_precision_oncology",
            },
        }
    }
    gap = {
        "interviewer_lines": [
            {
                "line_id": "vo_preface_precision_oncology",
                "delivery": "synthesize",
                "line_category": "episode_preface",
                "episode_orientation": True,
                "skipped_optional": True,
                "air_script_omit": True,
                "skip_reason_code": "execution_contract_waive",
                "compensating_path": "tier_d_logged_waive",
                "text": "Waived orientation.",
            }
        ]
    }
    seats = build_vo_seats(plan, gap)
    assert "vo_preface_precision_oncology" not in seats["seated_line_ids"]
    assert "vo_preface_precision_oncology" in seats["omitted_line_ids"]
    assert seats.get("orientation_id") in {None, ""}


def test_native_handoff_waives_reorder_bridge_requirement():
    from interview_mux.bridge_completeness import missing_reorder_bridges

    plan = {
        "air_script": {
            "beats": [
                {"segment_id": "seg_009", "montage_move": "native_handoff"},
                {"segment_id": "seg_011", "montage_move": "native_handoff"},
            ]
        }
    }
    waived = native_handoff_segment_ids(plan)
    assert "seg_011" in waived
    missing = missing_reorder_bridges(
        {
            "pairs": [
                {
                    "after_segment_id": "seg_009",
                    "before_segment_id": "seg_011",
                    "kind": "reorder",
                }
            ]
        },
        justified_skip_before_ids=waived,
    )
    assert missing == []


def test_native_handoff_ledger_glue_waived_reason(tmp_path):
    from interview_mux.assembly_ledger import build_assembly_ledger
    from interview_mux.mastering_plan_loader import forced_sparse_plan, write_plan

    ctx = isolated_run_ctx(tmp_path, "exec_air_ledger_nh")
    ordered = ["seg_009", "seg_011"]
    _seed_plan(ctx, ordered=ordered)
    plan = forced_sparse_plan(reason="native_handoff_ledger")
    plan["air_script"] = {
        "version": 1,
        "pass": "pass_b",
        "beats": [
            {"id": "b1", "segment_id": "seg_009", "montage_move": "native_handoff"},
            {"id": "b2", "segment_id": "seg_011", "montage_move": "native_handoff"},
        ],
        "omits": [],
        "energy_curve": [],
        "cold_open": {"kind": "none"},
    }
    write_plan(ctx, plan)
    man = ctx.read_json("segments/manifest.json")
    segs = list(man.get("segments") or [])
    for row in segs:
        if row.get("segment_id") == "seg_011":
            row["start_ms"] = 80_000
            row["end_ms"] = 88_000
    ctx.write_json("segments/manifest.json", {"segments": segs})
    by_id = {str(s["segment_id"]): s for s in segs}
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ordered},
        segments_by_id=by_id,
        transitions={"transitions": []},
    )
    ledger = build_assembly_ledger(ctx, edl=edl)
    dest = [s for s in ledger["seams"] if s.get("before_segment_id") == "seg_011"]
    assert dest
    assert dest[0].get("glue_waived") == "native_handoff"
    assert dest[0].get("naked") is False
    assert ledger["naked_seam_count"] == 0


def test_compose_pass_b_seat_gate_error_fail_closed(tmp_path, monkeypatch):
    """Cascade: freeze-gate Exception → return existing plan, no seat mutation."""
    ctx = isolated_run_ctx(tmp_path, "exec_air_gate_err")
    ordered = ["seg_001", "seg_002"]
    _seed_plan(ctx, ordered=ordered)
    plan = forced_sparse_plan(reason="gate_err")
    plan["air_script"] = {
        "version": 1,
        "pass": "pass_a",
        "beats": [
            {"id": "b1", "segment_id": "seg_001", "montage_move": "native_handoff"},
        ],
        "omits": [],
        "energy_curve": [],
        "cold_open": {"kind": "none"},
    }
    write_plan(ctx, plan)
    from interview_mux.mastering_plan_loader import load_plan_raw

    before = load_plan_raw(ctx) or {}

    def _boom(_ctx):
        raise RuntimeError("soft_freeze_active boom")

    monkeypatch.setattr(
        "interview_mux.seat_authority.soft_freeze_active",
        _boom,
    )
    out = compose_pass_b(ctx)
    assert out.get("air_script", {}).get("pass") == "pass_a"
    after = load_plan_raw(ctx) or {}
    assert after.get("air_script", {}).get("pass") == before.get("air_script", {}).get("pass")


def test_persist_air_script_omits_seat_gate_error_fail_closed(tmp_path, monkeypatch):
    ctx = isolated_run_ctx(tmp_path, "exec_air_omit_gate_err")
    ordered = ["seg_001"]
    _seed_plan(ctx, ordered=ordered)
    plan = forced_sparse_plan(reason="omit_gate")
    plan["air_script"] = {
        "version": 1,
        "pass": "pass_b",
        "beats": [],
        "omits": [],
        "energy_curve": [],
        "cold_open": {"kind": "none"},
        "vo_seats": {"seated_line_ids": [], "omitted_line_ids": []},
    }
    write_plan(ctx, plan)
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_x",
                    "targets_segment_id": "seg_001",
                    "placement": "before",
                    "delivery": "synthesize",
                    "text": "hello",
                }
            ]
        },
        skip_handoff=True,
    )

    def _boom(_ctx):
        raise RuntimeError("soft_freeze_active boom")

    monkeypatch.setattr(
        "interview_mux.seat_authority.soft_freeze_active",
        _boom,
    )
    assert persist_air_script_omits_on_gap_report(ctx) == 0
    gap = ctx.read_json("understanding/gap_report.json")
    assert not (gap["interviewer_lines"][0].get("skipped_optional"))
