"""Tests for Shape information packages + required episode_close music."""

from __future__ import annotations

from interview_mux.artifact_repairs import repair_sound_design_plan
from interview_mux.information_packages import (
    AUDIT_REL,
    CANDIDATES_REL,
    build_candidates,
    count_before_vo_for_target,
    default_episode_close,
    dense_targets_from_plan,
    ensure_episode_close_on_plan,
    information_packages_cfg,
    package_from_candidate,
    packages_affect_air,
    run_information_package_plan,
    select_commits,
)
from interview_mux.listen_quality import music_hinge_issues
from interview_mux.mastering_plan_loader import forced_sparse_plan, write_plan
from interview_mux.narrative_mode import GRAMMAR_MOVES
from interview_mux.nugget_layup import build_layup_compose_input, publish_layup_plan_to_gap_report
from interview_mux.run_context import RunContext
from interview_mux.v2.config import DELIVERY_ORDER


def _seed_run(ctx: RunContext, *, ordered: list[str]) -> None:
    segs = []
    t = 0
    for i, sid in enumerate(ordered):
        start = t
        end = t + 10_000
        segs.append(
            {
                "segment_id": sid,
                "speaker_id": "spk_a" if i % 2 == 0 else "spk_b",
                "speaker_role": "interviewee" if i % 2 == 0 else "interviewer",
                "type": "interviewee_answer" if i % 2 == 0 else "interviewer_question",
                "start_ms": start,
                "end_ms": end,
                "text": f"Topic block {i} about {'funding' if i < 2 else 'exit strategy and ESOP detail'} for {sid}",
                "topic_tags": ["funding"] if i < 2 else ["exit", "esop"],
            }
        )
        # Non-contiguous jump between early and late blocks
        t = end + (50_000 if i == 1 else 500)
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ordered})
    ctx.write_json("segments/manifest.json", {"segments": segs})
    ctx.write_json(
        "understanding/nugget_corpus.json",
        {
            "nuggets": [
                {
                    "nugget_id": "nug_a",
                    "text_claim": "Bootstrap capital came from family savings",
                    "evidence_quote": "we bootstrapped",
                    "in_selection": False,
                    "salience": "high",
                },
                {
                    "nugget_id": "nug_b",
                    "text_claim": "Snack pivot rewrote the go-to-market",
                    "evidence_quote": "snack pivot",
                    "in_selection": False,
                    "salience": "high",
                },
                {
                    "nugget_id": "nug_c",
                    "text_claim": "ESOP locked employee ownership",
                    "evidence_quote": "ESOP",
                    "in_selection": False,
                    "salience": "high",
                },
            ]
        },
    )
    write_plan(ctx, forced_sparse_plan(reason="test_seed"))


def test_delivery_order_places_package_between_corpus_and_layup():
    assert "information_package_plan" in DELIVERY_ORDER
    assert DELIVERY_ORDER.index("information_package_plan") > DELIVERY_ORDER.index(
        "nugget_corpus_mine"
    )
    assert DELIVERY_ORDER.index("nugget_layup_compose") > DELIVERY_ORDER.index(
        "information_package_plan"
    )


def test_grammar_move_registered():
    assert "information_package_then_block" in GRAMMAR_MOVES


def test_episode_close_always_on_plan():
    plan = ensure_episode_close_on_plan({})
    assert plan["episode_close"]["music"]["required"] is True
    assert plan["episode_close"]["music"]["role"] == "theme_outro"
    sparse = forced_sparse_plan(reason="x")
    assert sparse["episode_close"]["music"]["role"] == "theme_outro"


def test_shadow_mode_does_not_commit_packages(monkeypatch):
    ctx = RunContext("exec_info_pkg_shadow", create=True)
    ordered = [f"seg_{i:03d}" for i in range(1, 6)]
    _seed_run(ctx, ordered=ordered)
    from interview_mux import information_packages as ip

    original = ip.information_packages_cfg

    def _cfg(_c=None):
        c = original(_c)
        c["mode"] = "shadow"
        c["enable"] = True
        c["min_novelty"] = 0.1
        c["min_necessity"] = 0.1
        c["min_listen_uplift"] = 0.1
        c["min_dense_words"] = 10
        c["min_nugget_count"] = 1
        return c

    monkeypatch.setattr(ip, "information_packages_cfg", _cfg)
    run_information_package_plan(ctx)
    assert ctx.artifact_exists(CANDIDATES_REL)
    assert ctx.artifact_exists(AUDIT_REL)
    plan = ctx.read_json("mastering/mastering_plan.json")
    assert plan.get("information_packages") == []
    assert plan["episode_close"]["music"]["required"] is True
    audit = ctx.read_json(AUDIT_REL)
    assert audit["mode"] == "shadow"
    assert isinstance(audit.get("would_commit"), list)


def test_commit_music_vo_writes_packages(monkeypatch):
    ctx = RunContext("exec_info_pkg_commit", create=True)
    ordered = [f"seg_{i:03d}" for i in range(1, 6)]
    _seed_run(ctx, ordered=ordered)
    from interview_mux import information_packages as ip

    original = ip.information_packages_cfg

    def _cfg(_c=None):
        c = original(_c)
        c["mode"] = "commit_music_vo"
        c["enable"] = True
        c["min_novelty"] = 0.1
        c["min_necessity"] = 0.1
        c["min_listen_uplift"] = 0.1
        c["min_dense_words"] = 10
        c["min_nugget_count"] = 1
        c["max_per_episode"] = 2
        c["min_seam_gap_segments"] = 1
        return c

    monkeypatch.setattr(ip, "information_packages_cfg", _cfg)
    run_information_package_plan(ctx)
    plan = ctx.read_json("mastering/mastering_plan.json")
    pkgs = plan.get("information_packages") or []
    assert 1 <= len(pkgs) <= 2
    for p in pkgs:
        assert p["music"]["faceout_role"] == "theme_chapter_resolve"
        assert p["vo"]["detail_budget"] == "dense"
        assert p["after_segment_id"] != ordered[-1]
    assert packages_affect_air(_cfg()) is True


def test_final_seam_never_would_commit():
    ctx = RunContext("exec_info_pkg_final", create=True)
    ordered = ["seg_001", "seg_002", "seg_003"]
    _seed_run(ctx, ordered=ordered)
    doc = build_candidates(ctx)
    last = [c for c in doc["candidates"] if c["before_segment_id"] == ordered[-1]]
    assert last
    assert last[0]["would_commit"] is False
    assert "final_seam_reserved_for_episode_close" in last[0]["reject_reasons"]


def test_select_commits_respects_cap_and_gap():
    doc = {
        "ordered_segment_ids": ["a", "b", "c", "d", "e"],
        "candidates": [
            {
                "after_segment_id": "a",
                "before_segment_id": "b",
                "before_segment_ids": ["b"],
                "would_commit": True,
                "gate_scores": {"listen_uplift": 0.9, "novelty": 0.9},
                "confidence": 0.9,
            },
            {
                "after_segment_id": "b",
                "before_segment_id": "c",
                "before_segment_ids": ["c"],
                "would_commit": True,
                "gate_scores": {"listen_uplift": 0.95, "novelty": 0.9},
                "confidence": 0.9,
            },
            {
                "after_segment_id": "d",
                "before_segment_id": "e",
                "before_segment_ids": ["e"],
                "would_commit": True,
                "gate_scores": {"listen_uplift": 0.8, "novelty": 0.8},
                "confidence": 0.8,
            },
        ],
    }
    chosen = select_commits(
        doc,
        cfg={
            "max_per_episode": 2,
            "min_seam_gap_segments": 2,
        },
    )
    assert len(chosen) <= 2
    idxs = [
        doc["ordered_segment_ids"].index(c["after_segment_id"]) for c in chosen
    ]
    if len(idxs) == 2:
        assert abs(idxs[0] - idxs[1]) >= 2


def test_layup_publish_singleton_and_dense_stamp(monkeypatch):
    ctx = RunContext("exec_info_pkg_layup", create=True)
    ordered = ["seg_001", "seg_002", "seg_003"]
    _seed_run(ctx, ordered=ordered)
    from interview_mux import information_packages as ip

    original = ip.information_packages_cfg

    def _cfg(_c=None):
        c = original(_c)
        c["mode"] = "commit_music_vo"
        c["enable"] = True
        return c

    monkeypatch.setattr(ip, "information_packages_cfg", _cfg)
    plan = ctx.read_json("mastering/mastering_plan.json")
    plan["information_packages"] = [
        package_from_candidate(
            {
                "after_segment_id": "seg_001",
                "before_segment_id": "seg_002",
                "before_segment_ids": ["seg_002"],
                "nugget_ids": ["nug_a"],
                "new_information_claim": "bootstrap",
                "why_package_required": "needed",
                "confidence": 0.9,
                "gate_scores": {},
            },
            idx=1,
        )
    ]
    ctx.write_json("mastering/mastering_plan.json", plan)
    assert dense_targets_from_plan(plan)["seg_002"]["detail_budget"] == "dense"

    ctx.write_json(
        "understanding/nugget_layup_plan.json",
        {
            "ordered_segment_ids": ordered,
            "layups": [
                {
                    "target_segment_id": "seg_002",
                    "text": "Before the exit, bootstrap and snack facts set the stakes for the scale cliff.",
                    "nugget_ids": ["nug_a"],
                    "skip": False,
                },
                {
                    "target_segment_id": "seg_002",
                    "text": "Duplicate should be dropped.",
                    "nugget_ids": ["nug_b"],
                    "skip": False,
                },
            ],
        },
    )
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": "old_before",
                    "gap_type": "missing_setup",
                    "line_category": "story_bridge",
                    "placement": "before",
                    "targets_segment_id": "seg_002",
                    "text": "Old competing before VO",
                    "delivery": "synthesize",
                    "origin": "gap_framing",
                }
            ]
        },
    )
    report = publish_layup_plan_to_gap_report(ctx)
    assert count_before_vo_for_target(report, "seg_002") == 1
    line = next(
        ln
        for ln in report["interviewer_lines"]
        if ln.get("targets_segment_id") == "seg_002" and ln.get("placement") == "before"
    )
    assert line.get("detail_budget") == "dense"
    assert line.get("origin") == "nugget_layup"

    packet = build_layup_compose_input(ctx)
    assert "seg_002" in packet["information_package_dense_targets"]
    assert packet["dense_max_layup_words"] >= packet["max_layup_words"]


def test_repair_seeds_theme_outro_and_package_resolve(monkeypatch):
    ctx = RunContext("exec_info_pkg_sdp", create=True)
    ordered = ["seg_001", "seg_002", "seg_003"]
    _seed_run(ctx, ordered=ordered)
    from interview_mux import information_packages as ip

    original = ip.information_packages_cfg

    def _cfg(_c=None):
        c = original(_c)
        c["mode"] = "commit_music_vo"
        c["enable"] = True
        return c

    monkeypatch.setattr(ip, "information_packages_cfg", _cfg)
    plan = ctx.read_json("mastering/mastering_plan.json")
    plan["information_packages"] = [
        package_from_candidate(
            {
                "after_segment_id": "seg_001",
                "before_segment_ids": ["seg_002"],
                "nugget_ids": ["nug_a"],
                "confidence": 0.9,
                "gate_scores": {},
                "why_package_required": "x",
                "new_information_claim": "y",
            },
            idx=1,
        )
    ]
    ctx.write_json("mastering/mastering_plan.json", plan)

    sdp = {
        "version": 1,
        "assets": [
            {"asset_id": "m_cold", "role": "theme_cold_open"},
            {"asset_id": "m_bed", "role": "theme_underscore"},
            {"asset_id": "m_resolve", "role": "theme_chapter_resolve"},
            {"asset_id": "m_outro", "role": "theme_outro"},
        ],
        "cues": [],
        "flow_plans": {"podcast": {"cues": []}},
    }
    repaired, applied = repair_sound_design_plan(ctx, sdp)
    cues = repaired.get("cues") or repaired.get("flow_plans", {}).get("podcast", {}).get("cues") or []
    # repair writes into podcast cues or root depending on structure — normalize
    if not cues and isinstance(repaired.get("flow_plans"), dict):
        podcast = repaired["flow_plans"].get("podcast") or {}
        cues = podcast.get("cues") or []
    if not cues:
        cues = repaired.get("cues") or []
    roles = []
    for c in cues:
        if not isinstance(c, dict) or c.get("skip"):
            continue
        roles.append(str(c.get("role") or ""))
    actions = {str(a.get("action") or "") for a in applied if isinstance(a, dict)}
    assert "seed_theme_outro" in actions or any("outro" in r for r in roles)
    assert "seed_information_package_resolve" in actions or any(
        "resolve" in str(a) for a in applied
    )


def test_music_hinge_issues_require_outro_cue():
    sdp = {
        "assets": [{"asset_id": "m_outro", "role": "theme_outro"}],
        "cues": [],
    }
    issues = music_hinge_issues(sdp)
    codes = {i["code"] for i in issues}
    assert "missing_episode_close_outro_cue" in codes


def test_music_hinge_issues_sees_flow_plan_outro_cue():
    """Podcast flow_plans cues count — top-level cues may be empty."""
    sdp = {
        "assets": [{"asset_id": "show_theme_v1_full_bed_close", "role": "theme_outro"}],
        "cues": [],
        "flow_plans": {
            "podcast": {
                "cues": [
                    {
                        "cue_id": "close_bed",
                        "asset_id": "show_theme_v1_full_bed_close",
                        "after_segment_id": "seg_034",
                    }
                ]
            }
        },
    }
    issues = music_hinge_issues(sdp)
    assert not any(
        i.get("code") in {"missing_episode_close_outro", "missing_episode_close_outro_cue"}
        for i in issues
    )


def test_default_episode_close_shape():
    close = default_episode_close()
    assert close["music"]["fade_out"] == "gentle_long"
    assert close["music"]["fade_out_ms"] >= 1800


def test_repair_drops_overlap_high_bed_cues():
    """Beds on overlap_high segments are dropped, not remapped back onto them."""
    import json
    from pathlib import Path

    ctx = RunContext("exec_sdp_overlap_high_repair", create=True)
    ordered = ["seg_021", "seg_030", "seg_040"]
    _seed_run(ctx, ordered=ordered)
    sonic_path = Path(__file__).parent / "fixtures" / "sonic_context" / "fireside.json"
    sonic = json.loads(sonic_path.read_text(encoding="utf-8"))
    flags = sonic.setdefault("segment_flags", {})
    flags["overlap_high"] = ["seg_021"]
    ctx.write_json("understanding/sonic_context.json", sonic, skip_handoff=True)
    sdp = {
        "version": 1,
        "assets": [{"asset_id": "m_bed", "role": "theme_underscore"}],
        "palettes": [{"palette_id": "p1", "segment_ids": ["seg_021", "seg_030", "seg_040"]}],
        "flow_plans": {
            "podcast": {
                "cues": [
                    {
                        "cue_id": "bed_bad",
                        "placement": "under_segment",
                        "segment_id": "seg_021",
                        "asset_id": "m_bed",
                    },
                    {
                        "cue_id": "bed_ok",
                        "placement": "under_segment",
                        "segment_id": "seg_030",
                        "asset_id": "m_bed",
                    },
                ]
            }
        },
    }
    repaired, applied = repair_sound_design_plan(ctx, sdp)
    podcast = (repaired.get("flow_plans") or {}).get("podcast") or {}
    cues = [c for c in (podcast.get("cues") or []) if isinstance(c, dict) and not c.get("skip")]
    bed_segs = {
        str(c.get("segment_id") or "")
        for c in cues
        if str(c.get("placement") or "") == "under_segment"
    }
    assert "seg_021" not in bed_segs
    assert "seg_030" in bed_segs
    assert any(
        isinstance(a, dict) and a.get("action") == "drop_overlap_high_bed"
        for a in applied
    )
    from interview_mux.sdp_cross_validate import validate_post_sound_plan

    sdp_path = ctx.path("understanding", "sound_design_plan.json")
    sdp_path.parent.mkdir(parents=True, exist_ok=True)
    sdp_path.write_text(json.dumps(repaired), encoding="utf-8")
    errors = validate_post_sound_plan(ctx)
    assert not any("overlap_high" in e for e in errors)
