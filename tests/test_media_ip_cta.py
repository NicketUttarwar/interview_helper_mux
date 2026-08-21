"""Host execution of 0.1.0 flagship media-IP CTA judgments (no live LLM)."""

from __future__ import annotations

from interview_mux.media_ip_cta import (
    REASON,
    SKIP_HOLE,
    apply_cover_policy,
    apply_cta_judgments,
    apply_editorial_omits,
    cta_cover_budget_exempt,
    cta_cover_regenerate_scope,
    extract_judgments,
    is_lets_hear_hinge,
    never_touch_segment_ids,
    strip_never_touch_nuggets,
)
from interview_mux.nugget_layup import (
    apply_clone_voice_adjacency_skips,
    canned_air_violations,
    coverage_exempt_target_ids,
    evaluate_layup_qc,
    heal_layup_analysis_fields,
    is_justified_skip_row,
    stamp_typed_skip,
)
from interview_mux.run_context import RunContext


def _ctx_010() -> RunContext:
    ctx = RunContext(create=True)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
    )
    return ctx


def _ctx_000() -> RunContext:
    ctx = RunContext(create=True)
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.0.0", "homunculus_kind": "original_pipeline"},
    )
    return ctx


def _manifest(*rows: dict) -> dict:
    return {"segments": list(rows)}


def _seg(sid: str, text: str, *, start: int = 0, end: int = 8000, speaker: str = "spk_0") -> dict:
    return {
        "segment_id": sid,
        "speaker_id": speaker,
        "speaker_role": "interviewee",
        "type": "interviewee_answer",
        "topic_tags": [],
        "text": text,
        "start_ms": start,
        "end_ms": end,
    }


def test_extract_keeps_unsure_and_requires_clear() -> None:
    hits = extract_judgments(
        {
            "media_ip_cta": [
                {"segment_id": "seg_cta", "clearly_media_ip_pitch": True},
                {"segment_id": "seg_maybe", "clearly_media_ip_pitch": False},
                {"segment_id": "seg_story", "clearly_media_ip_pitch": True, "mixed_with_story": False},
            ]
        }
    )
    assert {h["segment_id"] for h in hits} == {"seg_cta", "seg_story"}


def test_extract_omits_null_cut_ms() -> None:
    hits = extract_judgments(
        {
            "media_ip_cta": [
                {
                    "segment_id": "seg_cta",
                    "clearly_media_ip_pitch": True,
                    "cut_ms": None,
                }
            ]
        }
    )
    assert hits[0]["segment_id"] == "seg_cta"
    assert "cut_ms" not in hits[0]


def test_000_is_noop_even_with_judgments() -> None:
    ctx = _ctx_000()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(_seg("seg_a", "hello"), _seg("seg_cta", "buy my old podcast")),
    )
    artifacts = {
        "ordered_segment_ids": ["seg_a", "seg_cta"],
        "excluded_segment_ids": [],
        "media_ip_cta": [{"segment_id": "seg_cta", "clearly_media_ip_pitch": True}],
    }
    out = apply_cta_judgments(ctx, artifacts)
    assert out["ordered_segment_ids"] == ["seg_a", "seg_cta"]
    assert never_touch_segment_ids(ctx) == set()


def test_standalone_cta_dropped_any_speaker() -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg("seg_a", "we sold to hospitals", start=0, end=5000),
            _seg("seg_cta", "go subscribe to my old show", start=5000, end=9000, speaker="spk_guest"),
            _seg("seg_b", "then the exit", start=9000, end=13000),
        ),
    )
    out = apply_cta_judgments(
        ctx,
        {
            "ordered_segment_ids": ["seg_a", "seg_cta", "seg_b"],
            "excluded_segment_ids": [],
            "media_ip_cta": [
                {"segment_id": "seg_cta", "clearly_media_ip_pitch": True, "cta_region": "whole"}
            ],
        },
    )
    assert out["ordered_segment_ids"] == ["seg_a", "seg_b"]
    reasons = {e["segment_id"]: e["reason"] for e in out["excluded_segment_ids"] if isinstance(e, dict)}
    assert reasons["seg_cta"] == REASON
    assert "seg_cta" in never_touch_segment_ids(ctx)
    cover = ctx.read_json("mastering/media_ip_cta.json")
    assert "seg_b" in cover["cover_target_ids"]


def test_leftover_ranking_cta_exclude_leaves_air_order() -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg(
                "seg_001",
                "The show is sponsored by Agilisium Labs. Visit labs.agilisium.com.",
                start=0,
                end=5000,
            ),
            _seg("seg_002", "Mohan joins to talk oncology", start=5000, end=9000),
        ),
    )
    out = apply_cta_judgments(
        ctx,
        {
            "ordered_segment_ids": ["seg_001", "seg_002"],
            "excluded_segment_ids": [
                {
                    "segment_id": "seg_001",
                    "reason": "direct_listener_sponsor_promotion; sponsor message",
                }
            ],
            "media_ip_cta": [],
        },
    )
    assert out["ordered_segment_ids"] == ["seg_002"]
    assert "seg_001" not in out["ordered_segment_ids"]


def test_apply_editorial_omits_drops_sponsor_rationale_and_hard_omit() -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg(
                "seg_001",
                "The Life Sciences DNA podcast is sponsored by Agilisium Labs.",
                start=0,
                end=5000,
            ),
            _seg("seg_002", "Who is Mohan Utawar?", start=5000, end=9000),
            _seg(
                "seg_biz",
                "Our two-sided market lets other businesses pay for access.",
                start=9000,
                end=13000,
            ),
        ),
    )
    out = apply_editorial_omits(
        ctx,
        {
            "ordered_segment_ids": ["seg_001", "seg_002", "seg_biz"],
            "excluded_segment_ids": [],
            "exclude_rationales": {
                "seg_001": "direct_listener_sponsor_promotion; the sponsor message does not support the oncology narrative",
            },
        },
    )
    assert "seg_001" not in out["ordered_segment_ids"]
    assert "seg_002" in out["ordered_segment_ids"]
    assert "seg_biz" in out["ordered_segment_ids"]
    assert out["exclude_rationales"]["seg_001"].startswith("direct_listener_sponsor_promotion")
    assert "seg_001" in never_touch_segment_ids(ctx)


def test_two_clear_hits_both_dropped() -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg("seg_1", "pitch one", start=0, end=4000),
            _seg("seg_keep", "revenue from other customers", start=4000, end=8000),
            _seg("seg_2", "pitch two", start=8000, end=12000),
        ),
    )
    out = apply_cta_judgments(
        ctx,
        {
            "ordered_segment_ids": ["seg_1", "seg_keep", "seg_2"],
            "excluded_segment_ids": [],
            "media_ip_cta": [
                {"segment_id": "seg_1", "clearly_media_ip_pitch": True},
                {"segment_id": "seg_2", "clearly_media_ip_pitch": True},
            ],
        },
    )
    assert out["ordered_segment_ids"] == ["seg_keep"]
    dropped = {e["segment_id"] for e in out["excluded_segment_ids"] if isinstance(e, dict)}
    assert dropped == {"seg_1", "seg_2"}


def test_unsure_clip_kept() -> None:
    ctx = _ctx_010()
    ctx.write_json("segments/manifest.json", _manifest(_seg("seg_a", "maybe a pitch?")))
    out = apply_cta_judgments(
        ctx,
        {
            "ordered_segment_ids": ["seg_a"],
            "excluded_segment_ids": [],
            "media_ip_cta": [{"segment_id": "seg_a", "clearly_media_ip_pitch": False}],
        },
    )
    assert out["ordered_segment_ids"] == ["seg_a"]
    assert never_touch_segment_ids(ctx) == set()


def test_keyword_subscribe_in_story_not_host_dropped() -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(_seg("seg_a", "hospitals subscribe to the protein snack model")),
    )
    out = apply_cta_judgments(
        ctx,
        {
            "ordered_segment_ids": ["seg_a"],
            "excluded_segment_ids": [],
        },
    )
    assert out["ordered_segment_ids"] == ["seg_a"]


def test_mixed_recut_drops_only_cta_child(monkeypatch) -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg("seg_mix", "story then pitch my course", start=0, end=12000),
            _seg("seg_b", "after", start=12000, end=16000),
        ),
    )

    def _split(ctx_inner, segment_id, cut_ms):
        ctx_inner.write_json(
            "segments/nle_edits.json",
            {
                "sequence_order": ["seg_mixa", "seg_mixb", "seg_b"],
                "segment_overrides": {
                    "seg_mixa": {"start_ms": 0, "end_ms": 7000, "parent_id": "seg_mix", "label": "story"},
                    "seg_mixb": {"start_ms": 7000, "end_ms": 12000, "parent_id": "seg_mix", "label": "cta"},
                    "seg_mix": {"excluded": True, "split_into": ["seg_mixa", "seg_mixb"]},
                },
            },
        )
        return ctx_inner.read_json("segments/nle_edits.json")

    monkeypatch.setattr("interview_mux.nle_state.split_segment_at_cuts", _split)
    out = apply_cta_judgments(
        ctx,
        {
            "ordered_segment_ids": ["seg_mix", "seg_b"],
            "excluded_segment_ids": [],
            "media_ip_cta": [
                {
                    "segment_id": "seg_mix",
                    "clearly_media_ip_pitch": True,
                    "mixed_with_story": True,
                    "cta_region": "end",
                    "cut_ms": [7000],
                }
            ],
        },
    )
    assert "seg_mixa" in out["ordered_segment_ids"]
    assert "seg_mixb" not in out["ordered_segment_ids"]
    assert "seg_mix" not in out["ordered_segment_ids"]
    assert "seg_b" in out["ordered_segment_ids"]
    assert "seg_mixb" in never_touch_segment_ids(ctx)
    assert "seg_mix" in never_touch_segment_ids(ctx)
    excl = {
        e["segment_id"]
        for e in out["excluded_segment_ids"]
        if isinstance(e, dict)
    }
    assert "seg_mixa" not in excl


def test_recut_too_short_drops_whole() -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(_seg("seg_mix", "tiny mixed", start=0, end=2000), _seg("seg_b", "after", start=2000, end=6000)),
    )
    out = apply_cta_judgments(
        ctx,
        {
            "ordered_segment_ids": ["seg_mix", "seg_b"],
            "excluded_segment_ids": [],
            "media_ip_cta": [
                {
                    "segment_id": "seg_mix",
                    "clearly_media_ip_pitch": True,
                    "mixed_with_story": True,
                    "cta_region": "end",
                }
            ],
        },
    )
    assert "seg_mix" not in out["ordered_segment_ids"]
    assert "seg_b" in out["ordered_segment_ids"]
    state = ctx.read_json("mastering/media_ip_cta.json")
    assert any(r.get("ok") is False for r in state.get("recuts") or [])


def test_strip_never_touch_nuggets() -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "mastering/media_ip_cta.json",
        {
            "version": 1,
            "locked": True,
            "dropped_segment_ids": ["seg_cta"],
            "never_touch_segment_ids": ["seg_cta"],
        },
    )
    corpus = {
        "nuggets": [
            {
                "nugget_id": "nug_bad",
                "text_claim": "subscribe",
                "evidence_quote": "subscribe",
                "source_segment_ids": ["seg_cta"],
                "in_selection": False,
            },
            {
                "nugget_id": "nug_ok",
                "text_claim": "hospitals",
                "evidence_quote": "hospitals",
                "source_segment_ids": ["seg_keep"],
                "in_selection": True,
            },
        ]
    }
    out = strip_never_touch_nuggets(ctx, corpus)
    ids = {n["nugget_id"] for n in out["nuggets"]}
    assert ids == {"nug_ok"}


def test_coverage_exempt_cta_hole() -> None:
    ctx = _ctx_010()
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_a", "seg_b"]})
    row_a = {
        "target_segment_id": "seg_a",
        "text": "Protein-aware buyers were snacking on the bar, which rewrote the market. Why did that demand nearly break supply?",
        "target_beat": "The snack pivot",
        "listener_need_entering_T": "Need the pivot before scale",
        "forward_unlock": "Why did that demand nearly break supply?",
        "skip": False,
    }
    row = {"target_segment_id": "seg_b", "text": "cover"}
    stamp_typed_skip(row, reason_code=SKIP_HOLE, compensating_path="media_ip_cta_omit")
    assert is_justified_skip_row(row)
    plan = {"ordered_segment_ids": ["seg_a", "seg_b"], "layups": [row_a, row]}
    assert "seg_b" in coverage_exempt_target_ids(ctx, plan)
    qc = evaluate_layup_qc(ctx, plan)
    assert not any("layup_coverage" in str(e) for e in qc.get("errors") or [])


def test_lets_hear_hinge_survives_heal_and_canned_air() -> None:
    text = (
        "The founder rebuilt the snack market around protein-aware buyers. "
        "Let's hear our conversation."
    )
    assert is_lets_hear_hinge(text)
    assert canned_air_violations(text) == []
    ctx = _ctx_010()
    ctx.write_json("segments/manifest.json", _manifest(_seg("seg_b", "the exit story")))
    plan = {
        "layups": [
            {
                "target_segment_id": "seg_b",
                "text": text,
                "target_beat": "The exit",
                "listener_need_entering_T": "After the CTA hole the next native is the exit",
                "forward_unlock": "Let's hear our conversation.",
                "skip": False,
            }
        ]
    }
    healed, _ = heal_layup_analysis_fields(ctx, plan)
    air = str(healed["layups"][0]["text"])
    assert "Let's hear our conversation" in air
    assert "Why does" not in air


def test_clone_adjacent_cover_allowed(monkeypatch) -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "mastering/media_ip_cta.json",
        {
            "version": 1,
            "locked": True,
            "dropped_segment_ids": ["seg_cta"],
            "cover_target_ids": ["seg_b"],
        },
    )
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_a", "seg_b"]})
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg("seg_a", "before", speaker="spk_0"),
            _seg("seg_b", "host continues", speaker="spk_0"),
        ),
    )
    monkeypatch.setattr(
        "interview_mux.source_topology.pickup_eligible_speaker_id",
        lambda _ctx: "spk_0",
    )
    plan = {
        "ordered_segment_ids": ["seg_a", "seg_b"],
        "layups": [
            {
                "target_segment_id": "seg_b",
                "text": "Let's hear how our talk went.",
                "target_beat": "Host continues",
                "listener_need_entering_T": "CTA hole",
                "forward_unlock": "Let's hear how our talk went.",
                "skip": False,
            }
        ],
    }
    out, notes = apply_clone_voice_adjacency_skips(ctx, plan)
    row = out["layups"][0]
    assert row.get("cta_cover") is True
    assert row.get("skip") is not True
    assert any(n.get("action") == "cta_cover_allow" for n in notes)


def test_cta_cover_skip_is_quota_exempt() -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "mastering/media_ip_cta.json",
        {
            "version": 1,
            "locked": True,
            "cover_target_ids": ["seg_b"],
        },
    )
    plan = {
        "layups": [
            {"target_segment_id": "seg_b", "skip": True, "text": ""},
        ]
    }
    out, notes = apply_cover_policy(ctx, plan)
    assert out["layups"][0].get("skip_reason_code") == SKIP_HOLE
    assert any(n.get("action") == "cta_hole_skip" for n in notes)


def test_cover_regenerate_does_not_count_budget() -> None:
    ctx = _ctx_010()
    assert cta_cover_budget_exempt(ctx) is False
    with cta_cover_regenerate_scope(ctx):
        assert cta_cover_budget_exempt(ctx) is True
    assert cta_cover_budget_exempt(ctx) is False


def test_locked_rerun_does_not_retarget() -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(_seg("seg_a", "keep"), _seg("seg_cta", "pitch"), _seg("seg_other", "other")),
    )
    first = apply_cta_judgments(
        ctx,
        {
            "ordered_segment_ids": ["seg_a", "seg_cta", "seg_other"],
            "media_ip_cta": [{"segment_id": "seg_cta", "clearly_media_ip_pitch": True}],
        },
    )
    assert "seg_cta" not in first["ordered_segment_ids"]
    second = apply_cta_judgments(
        ctx,
        {
            "ordered_segment_ids": ["seg_a", "seg_cta", "seg_other"],
            "media_ip_cta": [{"segment_id": "seg_other", "clearly_media_ip_pitch": True}],
        },
    )
    dropped = {
        e["segment_id"]
        for e in second["excluded_segment_ids"]
        if isinstance(e, dict) and e.get("reason") == REASON
    }
    assert "seg_cta" in dropped
    assert "seg_other" not in dropped


def test_cta_open_prefers_story_child(monkeypatch) -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(_seg("seg_mix", "story then pitch", start=0, end=12000)),
    )

    def _split(ctx_inner, segment_id, cut_ms):
        ctx_inner.write_json(
            "segments/nle_edits.json",
            {
                "sequence_order": ["seg_mixa", "seg_mixb"],
                "segment_overrides": {
                    "seg_mixa": {"start_ms": 0, "end_ms": 7000, "parent_id": "seg_mix"},
                    "seg_mixb": {"start_ms": 7000, "end_ms": 12000, "parent_id": "seg_mix"},
                    "seg_mix": {"excluded": True, "split_into": ["seg_mixa", "seg_mixb"]},
                },
            },
        )
        return ctx_inner.read_json("segments/nle_edits.json")

    monkeypatch.setattr("interview_mux.nle_state.split_segment_at_cuts", _split)
    out = apply_cta_judgments(
        ctx,
        {
            "ordered_segment_ids": ["seg_mix"],
            "native_cold_open_segment_id": "seg_mix",
            "media_ip_cta": [
                {
                    "segment_id": "seg_mix",
                    "clearly_media_ip_pitch": True,
                    "mixed_with_story": True,
                    "cta_region": "end",
                    "cta_open": True,
                    "open_choice": "story_child_first",
                    "cut_ms": [7000],
                }
            ],
        },
    )
    assert out["ordered_segment_ids"][0] == "seg_mixa"
    assert "seg_mixb" not in out["ordered_segment_ids"]
    assert out.get("native_cold_open_segment_id") == "seg_mixa"
    state = ctx.read_json("mastering/media_ip_cta.json")
    assert state.get("open_choice") == "story_child_first"


def test_locked_rerun_rewrites_recut_parent(monkeypatch) -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg("seg_mix", "story then pitch", start=0, end=12000),
            _seg("seg_b", "after", start=12000, end=16000),
        ),
    )

    def _split(ctx_inner, segment_id, cut_ms):
        ctx_inner.write_json(
            "segments/nle_edits.json",
            {
                "sequence_order": ["seg_mixa", "seg_mixb", "seg_b"],
                "segment_overrides": {
                    "seg_mixa": {"start_ms": 0, "end_ms": 7000, "parent_id": "seg_mix"},
                    "seg_mixb": {"start_ms": 7000, "end_ms": 12000, "parent_id": "seg_mix"},
                    "seg_mix": {"excluded": True, "split_into": ["seg_mixa", "seg_mixb"]},
                },
            },
        )
        return ctx_inner.read_json("segments/nle_edits.json")

    monkeypatch.setattr("interview_mux.nle_state.split_segment_at_cuts", _split)
    apply_cta_judgments(
        ctx,
        {
            "ordered_segment_ids": ["seg_mix", "seg_b"],
            "media_ip_cta": [
                {
                    "segment_id": "seg_mix",
                    "clearly_media_ip_pitch": True,
                    "mixed_with_story": True,
                    "cta_region": "end",
                    "cut_ms": [7000],
                }
            ],
        },
    )
    second = apply_cta_judgments(
        ctx,
        {
            "ordered_segment_ids": ["seg_mix", "seg_b"],
            "media_ip_cta": [{"segment_id": "seg_other", "clearly_media_ip_pitch": True}],
        },
    )
    assert "seg_mixa" in second["ordered_segment_ids"]
    assert "seg_mix" not in second["ordered_segment_ids"]
    assert "seg_mixb" not in second["ordered_segment_ids"]


def test_never_touch_qc_rejects_paraphrase() -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "mastering/media_ip_cta.json",
        {
            "version": 1,
            "locked": True,
            "dropped_segment_ids": ["seg_cta"],
            "never_touch_segment_ids": ["seg_cta"],
            "never_touch_texts": [
                "Go subscribe to my old show and buy the course at the link below"
            ],
        },
    )
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_b"]})
    ctx.write_json("segments/manifest.json", _manifest(_seg("seg_b", "the exit story")))
    plan = {
        "ordered_segment_ids": ["seg_b"],
        "layups": [
            {
                "target_segment_id": "seg_b",
                "text": (
                    "Go subscribe to my old show and buy the course at the link below. "
                    "Why did the exit change the market?"
                ),
                "target_beat": "The exit",
                "listener_need_entering_T": "Need the exit beat",
                "forward_unlock": "Why did the exit change the market?",
                "skip": False,
            }
        ],
    }
    qc = evaluate_layup_qc(ctx, plan)
    assert any("never_touch_cta" in str(e) for e in qc.get("errors") or [])


def test_opener_vo_shape_third_person_on_010_only() -> None:
    from interview_mux.opening_orientation import ensure_episode_orientation

    ctx = _ctx_010()
    ctx.write_json(
        "understanding/content_brief.json",
        {
            "thesis": (
                "Founder Asha explains how Acme changed its model, protected its "
                "team, and found a sustainable path to growth."
            ),
            "topics": [],
        },
    )
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_010"]})
    report, _ = ensure_episode_orientation(ctx, {"interviewer_lines": []}, ["seg_010"])
    assert report["interviewer_lines"][0].get("vo_shape") == "third_person"

    original = _ctx_000()
    original.write_json(
        "understanding/content_brief.json",
        {
            "thesis": (
                "Founder Asha explains how Acme changed its model, protected its "
                "team, and found a sustainable path to growth."
            ),
            "topics": [],
        },
    )
    original.write_json("master/selection.json", {"ordered_segment_ids": ["seg_010"]})
    report_000, _ = ensure_episode_orientation(
        original, {"interviewer_lines": []}, ["seg_010"]
    )
    assert "vo_shape" not in report_000["interviewer_lines"][0]


def test_recut_error_drops_whole(monkeypatch) -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg("seg_mix", "story then pitch", start=0, end=12000),
            _seg("seg_b", "after", start=12000, end=16000),
        ),
    )

    def _boom(*_args, **_kwargs):
        raise RuntimeError("split failed")

    monkeypatch.setattr("interview_mux.nle_state.split_segment_at_cuts", _boom)
    out = apply_cta_judgments(
        ctx,
        {
            "ordered_segment_ids": ["seg_mix", "seg_b"],
            "media_ip_cta": [
                {
                    "segment_id": "seg_mix",
                    "clearly_media_ip_pitch": True,
                    "mixed_with_story": True,
                    "cta_region": "end",
                    "cut_ms": [7000],
                }
            ],
        },
    )
    assert "seg_mix" not in out["ordered_segment_ids"]
    assert "seg_b" in out["ordered_segment_ids"]
    assert "seg_mix" in never_touch_segment_ids(ctx)


def test_sanitized_story_restored_after_ranking_exclude(monkeypatch) -> None:
    """After CTA is cut out, story remainder returns to the master allow-list."""
    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg("seg_a", "hospitals", start=0, end=4000),
            _seg("seg_mix", "story then pitch my course", start=4000, end=16000),
            _seg("seg_b", "exit", start=16000, end=20000),
        ),
    )

    def _split(ctx_inner, segment_id, cut_ms):
        ctx_inner.write_json(
            "segments/nle_edits.json",
            {
                "sequence_order": ["seg_a", "seg_mixa", "seg_mixb", "seg_b"],
                "segment_overrides": {
                    "seg_mixa": {"start_ms": 4000, "end_ms": 11000, "parent_id": "seg_mix"},
                    "seg_mixb": {"start_ms": 11000, "end_ms": 16000, "parent_id": "seg_mix"},
                    "seg_mix": {"excluded": True, "split_into": ["seg_mixa", "seg_mixb"]},
                },
            },
        )
        return ctx_inner.read_json("segments/nle_edits.json")

    monkeypatch.setattr("interview_mux.nle_state.split_segment_at_cuts", _split)
    out = apply_cta_judgments(
        ctx,
        {
            "ordered_segment_ids": ["seg_a", "seg_b"],
            "excluded_segment_ids": [
                {"segment_id": "seg_mix", "reason": "perspective_direct_monetization"}
            ],
            "media_ip_cta": [
                {
                    "segment_id": "seg_mix",
                    "clearly_media_ip_pitch": True,
                    "mixed_with_story": True,
                    "cta_region": "end",
                    "cut_ms": [11000],
                }
            ],
        },
    )
    assert "seg_mixa" in out["ordered_segment_ids"]
    assert "seg_mixb" not in out["ordered_segment_ids"]
    assert "seg_mix" not in out["ordered_segment_ids"]
    excl = {
        e["segment_id"]
        for e in out["excluded_segment_ids"]
        if isinstance(e, dict)
    }
    assert "seg_mixa" not in excl
    assert "seg_mix" in never_touch_segment_ids(ctx)
    assert "seg_mixb" in never_touch_segment_ids(ctx)
    corpus = strip_never_touch_nuggets(
        ctx,
        {
            "nuggets": [
                {
                    "nugget_id": "nug_cta",
                    "text_claim": "pitch my course",
                    "evidence_quote": "pitch my course",
                    "source_segment_ids": ["seg_mix"],
                    "in_selection": False,
                },
                {
                    "nugget_id": "nug_story",
                    "text_claim": "hospitals",
                    "evidence_quote": "hospitals",
                    "source_segment_ids": ["seg_mixa"],
                    "in_selection": True,
                },
            ]
        },
    )
    ids = {n["nugget_id"] for n in corpus["nuggets"]}
    assert ids == {"nug_story"}


def test_ranking_cta_exclude_without_judgment_is_never_touch() -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg("seg_a", "keep"),
            _seg("seg_cta", "go subscribe to my old show"),
        ),
    )
    out = apply_cta_judgments(
        ctx,
        {
            "ordered_segment_ids": ["seg_a"],
            "excluded_segment_ids": [
                {"segment_id": "seg_cta", "reason": "direct_listener_monetization"}
            ],
        },
    )
    assert "seg_cta" not in out["ordered_segment_ids"]
    assert "seg_cta" in never_touch_segment_ids(ctx)
    reasons = {
        e["segment_id"]: e["reason"]
        for e in out["excluded_segment_ids"]
        if isinstance(e, dict)
    }
    assert reasons["seg_cta"] == REASON


def test_010_perspective_attaches_to_compose() -> None:
    from interview_mux.homunculus.prompts import perspective_block_for_stage

    block = perspective_block_for_stage("nugget_layup_compose")
    assert "Let's hear" in block or "let's hear" in block.lower()
    assert "clearly_media_ip_pitch" in block
    assert perspective_block_for_stage("transcribe") == ""


def test_hard_keep_excludes_never_touch_cta() -> None:
    from interview_mux.hard_keep import hard_keep_segment_ids

    ctx = _ctx_010()
    cuts = ctx.path("understanding/ideal_cuts.json")
    cuts.parent.mkdir(parents=True, exist_ok=True)
    cuts.write_text(
        '{"cuts":[{"segment_id":"seg_cta","must_keep":true,"text":"pitch"}],'
        '"must_keep_segment_ids":["seg_cta"]}',
        encoding="utf-8",
    )
    cta = ctx.path("mastering/media_ip_cta.json")
    cta.parent.mkdir(parents=True, exist_ok=True)
    cta.write_text(
        '{"dropped_segment_ids":["seg_cta"],"never_touch_segment_ids":["seg_cta"]}',
        encoding="utf-8",
    )
    assert "seg_cta" not in hard_keep_segment_ids(ctx)


def test_zero_hits_writes_empty_prune_tree() -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(_seg("seg_a", "hospitals buy reagents from other labs")),
    )
    out = apply_cta_judgments(
        ctx,
        {"ordered_segment_ids": ["seg_a"], "excluded_segment_ids": [], "media_ip_cta": []},
    )
    assert out["ordered_segment_ids"] == ["seg_a"]
    state = ctx.read_json("mastering/media_ip_cta.json")
    assert state.get("prune_tree") == []
    assert state.get("seed_count") == 0
    assert "no_clear_media_ip_cta" in (state.get("notes") or [])


def test_seg_003_shaped_mixed_parent_hard_keep(monkeypatch) -> None:
    ctx = _ctx_010()
    intro = "OneCell is a platform that lets oncologists see living tumor biology."
    bumper = (
        "Well, before we begin, please subscribe, hit the like button, "
        "use the comments section, and download the audio-only version of the show."
    )
    welcome = "Let's welcome Mohan to talk about the science."
    text = f"{intro} {bumper} {welcome}"
    ctx.write_json(
        "segments/manifest.json",
        _manifest(_seg("seg_003", text, start=0, end=72000), _seg("seg_004", "after", start=72000, end=80000)),
    )
    cuts = ctx.path("understanding/ideal_cuts.json")
    cuts.parent.mkdir(parents=True, exist_ok=True)
    cuts.write_text(
        '{"cuts":[{"segment_id":"seg_003","must_keep":true}],'
        '"must_keep_segment_ids":["seg_003"]}',
        encoding="utf-8",
    )

    def _split(ctx_inner, segment_id, cut_ms):
        cuts = sorted(cut_ms)
        ctx_inner.write_json(
            "segments/nle_edits.json",
            {
                "sequence_order": ["seg_003a", "seg_003b", "seg_003c", "seg_004"],
                "segment_overrides": {
                    "seg_003a": {"start_ms": 0, "end_ms": cuts[0], "parent_id": "seg_003", "label": intro},
                    "seg_003b": {
                        "start_ms": cuts[0],
                        "end_ms": cuts[1],
                        "parent_id": "seg_003",
                        "label": bumper,
                    },
                    "seg_003c": {
                        "start_ms": cuts[1],
                        "end_ms": 72000,
                        "parent_id": "seg_003",
                        "label": welcome,
                    },
                    "seg_003": {"excluded": True, "split_into": ["seg_003a", "seg_003b", "seg_003c"]},
                },
            },
        )
        return ctx_inner.read_json("segments/nle_edits.json")

    monkeypatch.setattr("interview_mux.nle_state.split_segment_at_cuts", _split)
    out = apply_cta_judgments(
        ctx,
        {
            "ordered_segment_ids": ["seg_003", "seg_004"],
            "media_ip_cta": [
                {
                    "segment_id": "seg_003",
                    "clearly_media_ip_pitch": True,
                    "mixed_with_story": True,
                    "cta_region": "middle",
                    "cut_ms": [20000, 50000],
                }
            ],
        },
    )
    assert "seg_003a" in out["ordered_segment_ids"]
    assert "seg_003c" in out["ordered_segment_ids"]
    assert "seg_003b" not in out["ordered_segment_ids"]
    assert "seg_003" not in out["ordered_segment_ids"]
    assert "seg_003b" in never_touch_segment_ids(ctx)


def test_multi_parent_cta_in_one_apply() -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg("seg_001", "The show is sponsored by Agilisium Labs.", start=0, end=5000),
            _seg("seg_keep", "Mohan rebuilt the assay.", start=5000, end=9000),
            _seg(
                "seg_mid",
                "Please subscribe to my channel before we continue.",
                start=9000,
                end=13000,
            ),
            _seg("seg_story", "Then the trial enrolled.", start=13000, end=18000),
            _seg(
                "seg_076",
                "Thanks again to our sponsor for making this possible.",
                start=18000,
                end=22000,
            ),
        ),
    )
    out = apply_cta_judgments(
        ctx,
        {
            "ordered_segment_ids": ["seg_001", "seg_keep", "seg_mid", "seg_story", "seg_076"],
            "media_ip_cta": [
                {"segment_id": "seg_001", "clearly_media_ip_pitch": True},
                {"segment_id": "seg_076", "clearly_media_ip_pitch": True},
            ],
        },
    )
    assert out["ordered_segment_ids"] == ["seg_keep", "seg_story"]
    never = never_touch_segment_ids(ctx)
    assert {"seg_001", "seg_mid", "seg_076"} <= never
    state = ctx.read_json("mastering/media_ip_cta.json")
    assert int(state.get("seed_count") or 0) >= 3


def test_two_dirty_spans_in_one_parent(monkeypatch) -> None:
    ctx = _ctx_010()
    chunks = [
        ("The assay story continued cleanly.", 0, 5000),
        ("Please subscribe to my show now.", 5000, 10000),
        ("Then the trial enrolled patients.", 10000, 15000),
        ("Thanks to our sponsor for this episode.", 15000, 20000),
    ]
    text = " ".join(c[0] for c in chunks)
    ctx.write_json(
        "segments/manifest.json",
        _manifest(_seg("seg_mix", text, start=0, end=20000)),
    )
    words = []
    for blob, a, b in chunks:
        toks = blob.split()
        step = max(1, (b - a) // max(1, len(toks)))
        t = a
        for tok in toks:
            words.append({"text": tok, "start_ms": t, "end_ms": t + step - 1})
            t += step
    ctx.write_json("transcript/full.json", {"words": words})

    def _split(ctx_inner, segment_id, cut_ms):
        ctx_inner.write_json(
            "segments/nle_edits.json",
            {
                "sequence_order": ["seg_mixa", "seg_mixb", "seg_mixc", "seg_mixd"],
                "segment_overrides": {
                    "seg_mixa": {"start_ms": 0, "end_ms": 5000, "parent_id": "seg_mix", "label": chunks[0][0]},
                    "seg_mixb": {"start_ms": 5000, "end_ms": 10000, "parent_id": "seg_mix", "label": chunks[1][0]},
                    "seg_mixc": {"start_ms": 10000, "end_ms": 15000, "parent_id": "seg_mix", "label": chunks[2][0]},
                    "seg_mixd": {"start_ms": 15000, "end_ms": 20000, "parent_id": "seg_mix", "label": chunks[3][0]},
                    "seg_mix": {
                        "excluded": True,
                        "split_into": ["seg_mixa", "seg_mixb", "seg_mixc", "seg_mixd"],
                    },
                },
            },
        )
        return ctx_inner.read_json("segments/nle_edits.json")

    monkeypatch.setattr("interview_mux.nle_state.split_segment_at_cuts", _split)
    out = apply_cta_judgments(
        ctx,
        {
            "ordered_segment_ids": ["seg_mix"],
            "media_ip_cta": [
                {
                    "segment_id": "seg_mix",
                    "clearly_media_ip_pitch": True,
                    "mixed_with_story": True,
                    "cta_region": "end",
                    "cut_ms": [5000, 10000, 15000],
                }
            ],
        },
    )
    assert "seg_mixa" in out["ordered_segment_ids"]
    assert "seg_mixc" in out["ordered_segment_ids"]
    assert "seg_mixb" not in out["ordered_segment_ids"]
    assert "seg_mixd" not in out["ordered_segment_ids"]


def test_hard_keep_does_not_skip_parent_prune() -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg("seg_003", "Please subscribe to my show before we talk science.", start=0, end=8000),
            _seg("seg_004", "The assay worked.", start=8000, end=12000),
        ),
    )
    cuts = ctx.path("understanding/ideal_cuts.json")
    cuts.parent.mkdir(parents=True, exist_ok=True)
    cuts.write_text(
        '{"must_keep_segment_ids":["seg_003"],'
        '"cuts":[{"segment_id":"seg_003","must_keep":true}]}',
        encoding="utf-8",
    )
    out = apply_editorial_omits(
        ctx,
        {"ordered_segment_ids": ["seg_003", "seg_004"], "excluded_segment_ids": []},
    )
    assert "seg_003" not in out["ordered_segment_ids"]
    assert "seg_004" in out["ordered_segment_ids"]
    assert "seg_003" in never_touch_segment_ids(ctx)


def test_layup_residue_prunes_all_remaining() -> None:
    from interview_mux.media_ip_cta import heal_on_air_cta_residue

    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg("seg_a", "Please subscribe to my channel.", start=0, end=4000),
            _seg("seg_b", "Thanks to our sponsor again.", start=4000, end=8000),
            _seg("seg_c", "The science continued.", start=8000, end=12000),
        ),
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_a", "seg_b", "seg_c"]},
    )
    out = heal_on_air_cta_residue(ctx)
    assert "seg_a" not in out["ordered_segment_ids"]
    assert "seg_b" not in out["ordered_segment_ids"]
    assert "seg_c" in out["ordered_segment_ids"]
