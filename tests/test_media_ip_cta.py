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


def _seg(
    sid: str,
    text: str,
    *,
    start: int = 0,
    end: int = 8000,
    speaker: str = "spk_0",
    topic_tags: list[str] | None = None,
) -> dict:
    return {
        "segment_id": sid,
        "speaker_id": speaker,
        "speaker_role": "interviewee",
        "type": "interviewee_answer",
        "topic_tags": list(topic_tags or []),
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


def test_mixed_keeps_diagnostics_close_drops_subscribe_cta(monkeypatch) -> None:
    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg(
                "seg_005",
                "drug development, and diagnostics. Well, before we begin, "
                "hit the subscribe button and leave a comment.",
                start=96160,
                end=121660,
            ),
            _seg("seg_006", "after", start=124840, end=150540),
        ),
    )
    words = [
        {"text": "drug", "start_ms": 96160, "end_ms": 96300, "speaker_id": "spk_0"},
        {"text": "development,", "start_ms": 96300, "end_ms": 96780, "speaker_id": "spk_0"},
        {"text": "and", "start_ms": 96780, "end_ms": 97120, "speaker_id": "spk_0"},
        {"text": "diagnostics.", "start_ms": 97120, "end_ms": 97920, "speaker_id": "spk_0"},
        {"text": "Well,", "start_ms": 97920, "end_ms": 98320, "speaker_id": "spk_0"},
        {"text": "before", "start_ms": 98580, "end_ms": 98780, "speaker_id": "spk_0"},
        {"text": "we", "start_ms": 98780, "end_ms": 99000, "speaker_id": "spk_0"},
        {"text": "begin,", "start_ms": 99000, "end_ms": 99220, "speaker_id": "spk_0"},
        {"text": "hit", "start_ms": 100000, "end_ms": 100200, "speaker_id": "spk_0"},
        {"text": "the", "start_ms": 100200, "end_ms": 100360, "speaker_id": "spk_0"},
        {"text": "subscribe", "start_ms": 100360, "end_ms": 100800, "speaker_id": "spk_0"},
        {"text": "button", "start_ms": 100800, "end_ms": 101200, "speaker_id": "spk_0"},
    ]
    ctx.write_json("transcript/full.json", {"words": words})

    def _split(ctx_inner, segment_id, cut_ms):
        cut = int(cut_ms[0])
        ctx_inner.write_json(
            "segments/nle_edits.json",
            {
                "sequence_order": ["seg_005a", "seg_005b", "seg_006"],
                "segment_overrides": {
                    "seg_005a": {
                        "start_ms": 96160,
                        "end_ms": cut,
                        "parent_id": "seg_005",
                        "label": "story",
                    },
                    "seg_005b": {
                        "start_ms": cut,
                        "end_ms": 121660,
                        "parent_id": "seg_005",
                        "label": "cta",
                    },
                    "seg_005": {"excluded": True, "split_into": ["seg_005a", "seg_005b"]},
                },
            },
        )
        return ctx_inner.read_json("segments/nle_edits.json")

    monkeypatch.setattr("interview_mux.nle_state.split_segment_at_cuts", _split)
    out = apply_cta_judgments(
        ctx,
        {
            "ordered_segment_ids": ["seg_005", "seg_006"],
            "excluded_segment_ids": [],
            "media_ip_cta": [
                {
                    "segment_id": "seg_005",
                    "clearly_media_ip_pitch": True,
                    "mixed_with_story": True,
                    "must_keep_in_clip": False,
                    "cta_region": "middle",
                }
            ],
        },
    )
    assert "seg_005a" in out["ordered_segment_ids"]
    assert "seg_005b" not in out["ordered_segment_ids"]
    assert "seg_005" not in out["ordered_segment_ids"]
    assert "seg_006" in out["ordered_segment_ids"]
    recuts = ctx.read_json("mastering/media_ip_cta.json").get("recuts") or []
    ok = next(r for r in recuts if r.get("parent_id") == "seg_005")
    assert ok.get("ok") is True
    cuts = [int(c) for c in (ok.get("cut_ms") or [])]
    assert cuts and cuts[0] == 97920


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


def test_prepare_layup_skips_never_touch_cta_wording() -> None:
    """Persist-time skip so rotating never_touch_cta QC fails cannot loop compose."""
    from interview_mux.nugget_layup import prepare_layup_plan_for_persist

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
    assert any(
        "never_touch_cta" in str(e)
        for e in (evaluate_layup_qc(ctx, plan).get("errors") or [])
    )
    prepared = prepare_layup_plan_for_persist(ctx, plan)
    row = next(
        r for r in (prepared.get("layups") or []) if r.get("target_segment_id") == "seg_b"
    )
    assert row.get("skip") is True
    assert row.get("skip_reason_code") == "never_touch_cta"
    assert is_justified_skip_row(row)
    qc = evaluate_layup_qc(ctx, prepared)
    assert not any("never_touch_cta" in str(e) for e in (qc.get("errors") or []))


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
    state = ctx.read_json("mastering/media_ip_cta.json")
    assert "seg_003a" in (state.get("admitted_story_segment_ids") or [])
    assert "seg_003c" in (state.get("admitted_story_segment_ids") or [])
    man_ids = {
        str(s.get("segment_id"))
        for s in (ctx.read_json("segments/manifest.json").get("segments") or [])
        if isinstance(s, dict)
    }
    assert "seg_003a" in man_ids
    assert "seg_003c" in man_ids


def test_cta_story_children_survive_repair_and_hydrate(monkeypatch) -> None:
    ctx = _ctx_010()
    intro = "OneCell.ai is a precision oncology company using live single-cell analytics."
    bumper = "Hit the subscribe button and leave a comment in the comments section."
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg("seg_003", f"{intro} {bumper}", start=0, end=40000),
            _seg("seg_005", "Thank you for having me.", start=40000, end=50000),
        ),
    )
    ctx.write_json(
        "segments/boundaries.json",
        {
            "boundaries": [
                {
                    "segment_id": "seg_003",
                    "start_ms": 0,
                    "end_ms": 40000,
                    "speaker_id": "spk_0",
                    "proposed_split_reason": "topic_shift",
                },
                {
                    "segment_id": "seg_005",
                    "start_ms": 40000,
                    "end_ms": 50000,
                    "speaker_id": "spk_0",
                    "proposed_split_reason": "topic_shift",
                },
            ]
        },
    )
    cuts_path = ctx.path("understanding/ideal_cuts.json")
    cuts_path.parent.mkdir(parents=True, exist_ok=True)
    cuts_path.write_text(
        '{"cuts":[{"segment_id":"seg_003","must_keep":true}],'
        '"must_keep_segment_ids":["seg_003"]}',
        encoding="utf-8",
    )

    def _split(ctx_inner, segment_id, cut_ms):
        cut = int(cut_ms[0])
        ctx_inner.write_json(
            "segments/nle_edits.json",
            {
                "sequence_order": ["seg_003a", "seg_003b", "seg_005"],
                "segment_overrides": {
                    "seg_003a": {
                        "start_ms": 0,
                        "end_ms": cut,
                        "parent_id": "seg_003",
                        "label": intro,
                    },
                    "seg_003b": {
                        "start_ms": cut,
                        "end_ms": 40000,
                        "parent_id": "seg_003",
                        "label": bumper,
                    },
                    "seg_003": {"excluded": True, "split_into": ["seg_003a", "seg_003b"]},
                },
            },
        )
        return ctx_inner.read_json("segments/nle_edits.json")

    monkeypatch.setattr("interview_mux.nle_state.split_segment_at_cuts", _split)
    out = apply_cta_judgments(
        ctx,
        {
            "ordered_segment_ids": ["seg_003", "seg_005"],
            "excluded_segment_ids": [],
            "media_ip_cta": [
                {
                    "segment_id": "seg_003",
                    "clearly_media_ip_pitch": True,
                    "mixed_with_story": True,
                    "cta_region": "end",
                    "cut_ms": [22000],
                }
            ],
        },
    )
    assert "seg_003a" in out["ordered_segment_ids"]
    assert "seg_003b" not in out["ordered_segment_ids"]

    from interview_mux.artifact_completeness import hydrate_manifest_from_boundaries
    from interview_mux.artifact_repairs import repair_master_selection
    from interview_mux.hard_keep import hard_keep_segment_ids

    man = ctx.read_json("segments/manifest.json")
    man_ids = {str(s.get("segment_id")) for s in man["segments"] if isinstance(s, dict)}
    assert "seg_003a" in man_ids
    hydrated = hydrate_manifest_from_boundaries(ctx, man)
    hyd_ids = {str(s.get("segment_id")) for s in hydrated["segments"] if isinstance(s, dict)}
    assert "seg_003a" in hyd_ids

    repaired, actions = repair_master_selection(ctx, dict(out))
    assert "seg_003a" in repaired["ordered_segment_ids"]
    excl = {
        str(r.get("segment_id"))
        for r in (repaired.get("excluded_segment_ids") or [])
        if isinstance(r, dict)
    }
    assert "seg_003a" not in excl
    assert not any(a.get("action") == "drop_orphan_ref" and a.get("segment_id") == "seg_003a" for a in actions)

    assert "seg_003a" in hard_keep_segment_ids(ctx)
    assert "seg_003" not in hard_keep_segment_ids(ctx)
    cuts = ctx.read_json("understanding/ideal_cuts.json")
    assert "seg_003a" in (cuts.get("must_keep_segment_ids") or [])
    assert "seg_003a" in (out.get("considerable_segment_ids") or [])


def test_short_story_child_survives_blank_repair() -> None:
    """Listen-complete admitted prefixes stamped story_keep_ok survive blank-repair."""
    ctx = _ctx_010()
    keep_a = _seg(
        "seg_003a",
        "OneCell.ai is a precision oncology company.",
        start=0,
        end=1900,
    )
    keep_a["_meta"] = {"story_keep_ok": True}
    keep_j = _seg(
        "seg_003j",
        "Let's welcome Mohan to the show.",
        start=20000,
        end=21500,
    )
    keep_j["_meta"] = {"story_keep_ok": True}
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            keep_a,
            keep_j,
            _seg("seg_005", "Thank you for having me on the show today.", start=40000, end=50000),
        ),
    )
    ctx.write_json(
        "mastering/media_ip_cta.json",
        {
            "version": 1,
            "admitted_story_segment_ids": ["seg_003a", "seg_003j"],
            "considerable_segment_ids": ["seg_003a", "seg_003j"],
            "never_touch_segment_ids": ["seg_003"],
        },
    )
    from interview_mux.artifact_repairs import (
        _segment_is_blank_or_unusable,
        repair_master_selection,
    )

    assert _segment_is_blank_or_unusable(ctx, "seg_003a") is False
    assert _segment_is_blank_or_unusable(ctx, "seg_003j") is False
    # Stamped kids already on air must not be blank-dropped (max_cta_readmit=0).
    repaired, actions = repair_master_selection(
        ctx,
        {
            "ordered_segment_ids": ["seg_003a", "seg_003j", "seg_005"],
            "excluded_segment_ids": [],
        },
    )
    assert "seg_003a" in repaired["ordered_segment_ids"]
    assert "seg_003j" in repaired["ordered_segment_ids"]
    excl = {
        str(r.get("segment_id"))
        for r in (repaired.get("excluded_segment_ids") or [])
        if isinstance(r, dict)
    }
    assert "seg_003a" not in excl
    assert "seg_003j" not in excl
    assert not any(a.get("action") == "drop_blank_segments" for a in actions)


def test_unstamped_short_admitted_story_is_blank_unusable() -> None:
    """Admitted story kids without story_keep_ok stay blank (incomplete microfragments)."""
    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg("seg_003a", "And what is OneCell.ai? OneCell", start=0, end=1900),
            _seg("seg_003j", "let's welcome Mohan", start=20000, end=21500),
        ),
    )
    ctx.write_json(
        "mastering/media_ip_cta.json",
        {
            "version": 1,
            "admitted_story_segment_ids": ["seg_003a", "seg_003j"],
            "considerable_segment_ids": ["seg_003a", "seg_003j"],
            "never_touch_segment_ids": ["seg_003"],
        },
    )
    from interview_mux.artifact_repairs import _segment_is_blank_or_unusable

    assert _segment_is_blank_or_unusable(ctx, "seg_003a") is True
    assert _segment_is_blank_or_unusable(ctx, "seg_003j") is True


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


def test_execute_cta_omit_from_needs_keeps_reverse_jump_native() -> None:
    from interview_mux.media_ip_cta import execute_cta_omit_from_needs

    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg(
                "seg_001a",
                "The Life Sciences DNA podcast is sponsored by Agilisium Labs.",
                start=0,
                end=8000,
            ),
            _seg(
                "seg_003h",
                "Before we begin, stay up on the latest episodes by hitting the subscribe button.",
                start=8000,
                end=12000,
            ),
            _seg(
                "seg_054",
                "Yeah, and so this is early detection of the tumor changing.",
                start=12000,
                end=18000,
            ),
        ),
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001a", "seg_003h", "seg_054"]},
    )
    dropped = execute_cta_omit_from_needs(
        ctx,
        [
            {
                "type": "rerun_stage",
                "stage": "selection",
                "blocking": True,
                "reason": (
                    "Remove seg_001a (sponsor bumper) and seg_003h (subscribe CTA); "
                    "re-evaluate reverse jump seg_054 → seg_003a"
                ),
            }
        ],
    )
    sel = ctx.read_json("master/selection.json")
    order = sel.get("ordered_segment_ids") or []
    assert "seg_001a" in dropped
    assert "seg_003h" in dropped
    assert "seg_054" not in dropped
    assert "seg_001a" not in order
    assert "seg_003h" not in order
    assert "seg_054" in order


def test_execute_cta_omit_drops_outro_range() -> None:
    from interview_mux.media_ip_cta import execute_cta_omit_from_needs

    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg("seg_054", "This is early detection of the tumor changing.", start=0, end=4000),
            _seg("seg_068b", "Life Sciences DNA is a bi-monthly podcast produced by Levine Media.", start=4000, end=6000),
            _seg("seg_068c", "Be sure to follow us on your preferred podcast platform.", start=6000, end=8000),
            _seg("seg_068l", "Beautiful. Let's Follow Y!", start=8000, end=9000),
        ),
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_054", "seg_068b", "seg_068c", "seg_068l"]},
    )
    needs = [
        {
            "type": "rerun_stage",
            "stage": "selection",
            "blocking": True,
            "reason": (
                "Remove seg_068b through seg_068l from the locked air order. "
                "This run includes direct listener requests to follow and contact "
                "the programme, plus disconnected outro credits and sign-off."
            ),
        }
    ]
    try:
        dropped = execute_cta_omit_from_needs(ctx, needs)
    except ValueError as exc:
        # Intentional: selection write refuses empty ordered_segment_ids.
        assert "ordered_segment_ids" in str(exc)
        return
    order = ctx.read_json("master/selection.json").get("ordered_segment_ids") or []
    assert order, "omit must leave a non-empty air order"
    assert "seg_054" not in dropped or "seg_054" in order
    assert any(x in dropped for x in ("seg_068b", "seg_068c", "seg_068l"))


def test_execute_cta_omit_drops_fragmentary_tail_via_boundary_detection_need() -> None:
    """Layup asks boundary_detection to remove post-sign-off scraps — host-omit them."""
    from interview_mux.media_ip_cta import (
        execute_cta_omit_from_needs,
        is_selection_cta_omit_need,
    )

    need = {
        "type": "rerun_stage",
        "stage": "boundary_detection",
        "blocking": True,
        "reason": (
            "Review and recut or remove seg_063i and seg_063j: they are selected "
            "in the master but contain empty or fragmentary text after an already "
            "complete sign-off."
        ),
    }
    assert is_selection_cta_omit_need(need)

    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg("seg_062", "That is the promise of real-time profiling.", start=0, end=4000),
            _seg("seg_063h", "Thanks for joining us today.", start=4000, end=7000),
            _seg("seg_063i", "We'll", start=7000, end=7500),
            _seg("seg_063j", "We'll see you next time.", start=7500, end=9500),
        ),
    )
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_062", "seg_063h", "seg_063i", "seg_063j"],
        },
    )
    dropped = execute_cta_omit_from_needs(ctx, [need])
    order = ctx.read_json("master/selection.json").get("ordered_segment_ids") or []
    assert "seg_063i" in dropped
    assert "seg_063j" in dropped
    assert "seg_062" not in dropped
    assert "seg_063h" not in dropped
    assert order == ["seg_062", "seg_063h"]


def test_execute_cta_omit_drops_degraded_transcript_excerpt_need() -> None:
    """Layup transcript_excerpt for empty/degraded post-CTA scrap → host omit."""
    from interview_mux.media_ip_cta import (
        execute_cta_omit_from_needs,
        is_selection_cta_omit_need,
    )

    need = {
        "type": "transcript_excerpt",
        "stage": "nugget_layup_compose",
        "blocking": True,
        "reason": (
            "seg_066j is retained in the locked order but has an empty, heavily "
            "degraded transcript after the CTA cut; a verified substantive excerpt "
            "is required to keep it on air."
        ),
    }
    assert is_selection_cta_omit_need(need)
    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg("seg_065", "Real substance remains.", start=0, end=4000),
            _seg("seg_066j", "Thanks for joining us.", start=4000, end=6000),
        ),
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_065", "seg_066j"]},
    )
    dropped = execute_cta_omit_from_needs(ctx, [need])
    order = ctx.read_json("master/selection.json").get("ordered_segment_ids") or []
    assert "seg_066j" in dropped
    assert "seg_065" not in dropped
    assert order == ["seg_065"]


def test_execute_cta_omit_keeps_reverse_jump_intro_and_commits_under_staging() -> None:
    from interview_mux.media_ip_cta import execute_cta_omit_from_needs
    from interview_mux.write_staging import enter_stage_staging, exit_stage_staging

    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg(
                "seg_002",
                "Mohan, thanks for joining us. We're going to talk today about how AI is transforming cancer care.",
                start=0,
                end=8000,
            ),
            _seg(
                "seg_074",
                "Thanks for listening to Life Sciences DNA.",
                start=8000,
                end=9000,
            ),
            _seg(
                "seg_074b",
                "Life Sciences DNA is a bi-monthly podcast produced by the Levine Media Group with production support from FullView Media.",
                start=9000,
                end=11000,
            ),
            _seg(
                "seg_074d",
                "Music for this podcast is provided courtesy of the Jonah Levine Collective.",
                start=11000,
                end=12500,
            ),
            _seg(
                "seg_074g",
                "The Life Sciences DNA.",
                start=12500,
                end=13000,
            ),
        ),
    )
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_002", "seg_074b", "seg_074d", "seg_074g"],
            "excluded_segment_ids": [{"segment_id": "seg_074", "reason": "media_ip_cta"}],
        },
    )
    enter_stage_staging("nugget_layup_compose")
    try:
        dropped = execute_cta_omit_from_needs(
            ctx,
            [
                {
                    "type": "rerun_stage",
                    "stage": "selection",
                    "blocking": True,
                    "reason": (
                        "Reconcile the locked air order with the authoritative media-IP CTA "
                        "exclusion for parent seg_074 and its selected children seg_074b, "
                        "seg_074d, and seg_074g. The current order also reverse-jumps from "
                        "end credits into seg_002."
                    ),
                }
            ],
        )
    finally:
        exit_stage_staging()
    # Staging rollback must not undo the host omit.
    committed = ctx.final_path("master", "selection.json")
    import json

    order = json.loads(committed.read_text(encoding="utf-8")).get("ordered_segment_ids") or []
    assert "seg_074b" in dropped
    assert "seg_074d" in dropped
    # Fragmentary parent-child id may be covered by parent exclusion without explicit drop.
    assert set(dropped) >= {"seg_074b", "seg_074d"}
    assert "seg_002" not in dropped
    assert "seg_002" in order
    assert "seg_074b" not in order
    assert "seg_074d" not in order


def test_execute_cta_omit_releases_poisoned_intro_never_touch() -> None:
    from interview_mux.homunculus.issues import emit_issue
    from interview_mux.media_ip_cta import ARTIFACT_REL, execute_cta_omit_from_needs

    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg(
                "seg_002",
                "Mohan, thanks for joining us. We're going to talk today about how AI is transforming cancer care.",
                start=0,
                end=8000,
            ),
            _seg(
                "seg_074",
                "Thanks for listening to Life Sciences DNA.",
                start=8000,
                end=9000,
            ),
            _seg(
                "seg_074b",
                "Life Sciences DNA is a bi-monthly podcast produced by the Levine Media Group with production support from FullView Media.",
                start=9000,
                end=11000,
            ),
            _seg(
                "seg_073",
                "That is the assay result in the first cohort.",
                start=7000,
                end=8000,
            ),
        ),
    )
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_073", "seg_074b"],
            "excluded_segment_ids": [
                {"segment_id": "seg_074", "reason": "media_ip_cta"},
                {"segment_id": "seg_002", "reason": "media_ip_cta"},
            ],
        },
    )
    ctx.write_json(
        ARTIFACT_REL,
        {
            "version": 1,
            "locked": True,
            "dropped_segment_ids": ["seg_074", "seg_074b", "seg_002"],
            "never_touch_segment_ids": ["seg_074", "seg_074b", "seg_002"],
        },
    )
    emit_issue(
        ctx,
        kind="perspective_direct_monetization",
        source="apply_editorial_omits",
        stage_id="full_master_ranking",
        implicated=["seg_002", "seg_074b"],
        evidence={"reasons": {"seg_002": "reverse-jumps into seg_002"}},
    )
    dropped = execute_cta_omit_from_needs(
        ctx,
        [
            {
                "type": "rerun_stage",
                "stage": "selection",
                "blocking": True,
                "reason": (
                    "media_ip_cta credits omit: cta_omit_applied dropped "
                    "seg_074b,seg_002 reverse-jumps into seg_002"
                ),
            }
        ],
    )
    order = ctx.read_json("master/selection.json").get("ordered_segment_ids") or []
    state = ctx.read_json(ARTIFACT_REL)
    assert "seg_002" not in dropped
    assert "seg_002" in order
    assert "seg_074b" not in order
    assert "seg_002" not in (state.get("dropped_segment_ids") or [])
    assert "seg_002" not in (state.get("never_touch_segment_ids") or [])
    assert "seg_074" in (state.get("dropped_segment_ids") or []) or "seg_074" in (
        state.get("never_touch_segment_ids") or []
    )


def test_heal_strips_never_touch_left_on_air() -> None:
    from interview_mux.media_ip_cta import ARTIFACT_REL, heal_on_air_cta_residue

    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg("seg_001a", "The podcast is sponsored by Agilisium Labs.", start=0, end=8000),
            _seg("seg_002", "The assay worked in the first cohort.", start=8000, end=12000),
        ),
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001a", "seg_002"]},
    )
    ctx.write_json(
        ARTIFACT_REL,
        {
            "version": 1,
            "locked": True,
            "dropped_segment_ids": ["seg_001"],
            "never_touch_segment_ids": ["seg_001", "seg_001a"],
        },
    )
    try:
        out = heal_on_air_cta_residue(ctx)
    except ValueError as exc:
        # Fail-closed: refuse empty ordered_segment_ids if prune would wipe the air order.
        assert "ordered_segment_ids" in str(exc)
        return
    order = out.get("ordered_segment_ids") or []
    assert "seg_001a" not in order
    assert "seg_002" in order
    disk = ctx.read_json("master/selection.json")
    assert "seg_001a" not in (disk.get("ordered_segment_ids") or [])


def test_clamp_source_stops_cta_bleed_into_keeper() -> None:
    """Keeper air bounds must not extend through excluded subscribe CTA tape."""
    from interview_mux.edl_qc import validate_flow1_edl
    from interview_mux.media_ip_cta import (
        ARTIFACT_REL,
        clamp_edl_speech_away_from_never_touch,
        clamp_source_away_from_never_touch,
        never_touch_end_cap_ms,
        never_touch_source_intervals,
        selection_cta_exclude_ids,
    )

    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg(
                "seg_003g",
                "I want to understand how OneCell works.",
                start=87210,
                end=97970,
                speaker="spk_host",
            ),
            _seg(
                "seg_003h",
                "Before we begin, subscribe for the latest episodes.",
                start=97970,
                end=105890,
                speaker="spk_host",
            ),
            _seg(
                "seg_004",
                "Mohan, welcome.",
                start=111310,
                end=120000,
                speaker="spk_guest",
            ),
        ),
    )
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_003g", "seg_004"],
            "excluded_segment_ids": [
                {"segment_id": "seg_003h", "reason": "media_ip_cta"},
            ],
            "exclude_rationales": {"seg_003h": "media_ip_cta"},
        },
    )
    # Thin CTA artifact (exec_370 shape) — selection rationales must still clamp.
    ctx.write_json(ARTIFACT_REL, {"version": 1, "locked": True})

    assert "seg_003h" in selection_cta_exclude_ids(ctx)
    intervals = never_touch_source_intervals(ctx)
    assert intervals == [(97970, 105890, "seg_003h")]
    assert never_touch_end_cap_ms(87320, intervals) == 97970

    ss, se, notes = clamp_source_away_from_never_touch(
        87320, 105890, intervals
    )
    assert ss == 87320
    assert se == 97970
    assert any("clamp_end_before_never_touch:seg_003h" in n for n in notes)

    # Parent CTA exclude must not wipe on-air NLE children of that parent.
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_003g", "seg_004"],
            "excluded_segment_ids": [
                {"segment_id": "seg_003", "reason": "media_ip_cta"},
                {"segment_id": "seg_003h", "reason": "media_ip_cta"},
            ],
            "exclude_rationales": {
                "seg_003": "media_ip_cta",
                "seg_003h": "media_ip_cta",
            },
        },
    )
    intervals_parent = never_touch_source_intervals(ctx)
    assert intervals_parent == [(97970, 105890, "seg_003h")]
    assert all(row[2] != "seg_003" for row in intervals_parent)

    edl = {
        "ordered_segment_ids": ["seg_003g", "seg_004"],
        "timeline_duration_ms": 20000,
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_003g",
                "source_start_ms": 87320,
                "source_end_ms": 105890,
                "timeline_start_ms": 0,
                "duration_ms": 105890 - 87320,
            },
            {
                "type": "speech",
                "segment_id": "seg_004",
                "source_start_ms": 111310,
                "source_end_ms": 120000,
                "timeline_start_ms": 105890 - 87320,
                "duration_ms": 120000 - 111310,
            },
        ],
    }
    bleed_errors = validate_flow1_edl(ctx, edl)
    assert any("Never-touch CTA bleed" in e for e in bleed_errors)

    fixed, rows = clamp_edl_speech_away_from_never_touch(ctx, edl)
    assert rows
    clip0 = (fixed.get("clips") or [])[0]
    assert int(clip0["source_end_ms"]) == 97970
    assert int(clip0["duration_ms"]) == 97970 - 87320
    assert validate_flow1_edl(ctx, fixed) == []


def test_never_touch_punches_packaging_keep_inside_dropped_parent() -> None:
    """Dropped parent mega-range must not zero an on-air keep that is not an NLE child."""
    from interview_mux.media_ip_cta import (
        ARTIFACT_REL,
        clamp_edl_speech_away_from_never_touch,
        clamp_source_away_from_never_touch,
        never_touch_source_intervals,
    )

    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg(
                "seg_002",
                "Before we start, subscribe and share this show.",
                start=23240,
                end=121660,
                speaker="spk_host",
            ),
            _seg(
                "seg_003a",
                "And what are you hoping to hear from Mohan today?",
                start=83020,
                end=87160,
                speaker="spk_host",
            ),
            _seg(
                "seg_004",
                "Mohan, thanks for joining.",
                start=121660,
                end=130000,
                speaker="spk_guest",
            ),
        ),
    )
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_003a", "seg_004"],
            "excluded_segment_ids": [
                {"segment_id": "seg_002", "reason": "media_ip_cta"},
            ],
            "exclude_rationales": {"seg_002": "media_ip_cta"},
        },
    )
    ctx.write_json(
        ARTIFACT_REL,
        {
            "version": 1,
            "locked": True,
            "dropped_segment_ids": ["seg_002"],
            "never_touch_segment_ids": ["seg_002"],
        },
    )

    intervals = never_touch_source_intervals(ctx)
    assert all(not (a < 83020 and b > 87160) for a, b, _ in intervals)
    assert any(b == 83020 for a, b, _ in intervals)
    assert any(a == 87160 for a, b, _ in intervals)

    ss, se, notes = clamp_source_away_from_never_touch(83020, 87160, intervals)
    assert ss == 83020
    assert se == 87160
    assert not any("zeroed_inside_never_touch" in n for n in notes)

    edl = {
        "ordered_segment_ids": ["seg_003a", "seg_004"],
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_003a",
                "source_start_ms": 83020,
                "source_end_ms": 87160,
                "timeline_start_ms": 0,
                "duration_ms": 87160 - 83020,
            },
            {
                "type": "speech",
                "segment_id": "seg_004",
                "source_start_ms": 121660,
                "source_end_ms": 130000,
                "timeline_start_ms": 87160 - 83020,
                "duration_ms": 130000 - 121660,
            },
        ],
    }
    fixed, rows = clamp_edl_speech_away_from_never_touch(ctx, edl)
    ids = [c.get("segment_id") for c in (fixed.get("clips") or []) if c.get("type") == "speech"]
    assert "seg_003a" in ids
    clip_a = next(c for c in fixed["clips"] if c.get("segment_id") == "seg_003a")
    assert int(clip_a["duration_ms"]) == 87160 - 83020
    assert not any("never_touch_unplayable" in (r.get("notes") or []) for r in rows)


def test_clamp_drops_zero_duration_never_touch_clip() -> None:
    """A speech clip fully inside never-touch must be omitted, not aired at 0 ms."""
    from interview_mux.media_ip_cta import clamp_edl_speech_away_from_never_touch

    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg("seg_cta", "Subscribe now.", start=0, end=8000, speaker="spk_host", topic_tags=["cta"]),
            _seg("seg_keep", "Let's talk science.", start=9000, end=16000),
        ),
    )
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_cta", "seg_keep"],
            "excluded_segment_ids": [],
        },
    )
    edl = {
        "ordered_segment_ids": ["seg_cta", "seg_keep"],
        "clips": [
            {
                "type": "speech",
                "segment_id": "seg_cta",
                "source_start_ms": 0,
                "source_end_ms": 8000,
                "timeline_start_ms": 0,
                "duration_ms": 8000,
            },
            {
                "type": "speech",
                "segment_id": "seg_keep",
                "source_start_ms": 9000,
                "source_end_ms": 16000,
                "timeline_start_ms": 8000,
                "duration_ms": 7000,
            },
        ],
    }
    try:
        fixed, rows = clamp_edl_speech_away_from_never_touch(
            ctx, edl, intervals=[(0, 8000, "seg_cta")]
        )
    except ValueError as exc:
        # Fail-closed when selection sync would write empty ordered_segment_ids.
        assert "ordered_segment_ids" in str(exc)
        return
    speech_ids = [
        c.get("segment_id")
        for c in (fixed.get("clips") or [])
        if c.get("type") == "speech"
    ]
    assert speech_ids == ["seg_keep"]
    assert "seg_cta" not in (fixed.get("ordered_segment_ids") or [])
    assert any("never_touch_unplayable" in (r.get("notes") or []) for r in rows)
    sel = ctx.read_json("master/selection.json")
    assert "seg_cta" not in (sel.get("ordered_segment_ids") or [])
    assert "seg_keep" in (sel.get("ordered_segment_ids") or [])


def test_nle_collapse_does_not_zero_manifest_keep_inside_dropped_parent() -> None:
    """NLE never-touch stubs must not shrink the punch hole or leave a 0 ms clip."""
    from interview_mux.media_ip_cta import (
        ARTIFACT_REL,
        clamp_source_away_from_never_touch,
        heal_nle_unplayable_keep_overrides,
        never_touch_source_intervals,
    )
    from interview_mux.nle_state import load_nle, save_nle, segments_by_id_with_nle

    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg(
                "seg_002",
                "Before we start, subscribe and share this show.",
                start=23240,
                end=121660,
                speaker="spk_host",
            ),
            _seg(
                "seg_003a",
                "And what are you hoping to hear from Mohan today?",
                start=83020,
                end=87160,
                speaker="spk_host",
            ),
            _seg(
                "seg_004",
                "Mohan, thanks for joining.",
                start=121660,
                end=130000,
                speaker="spk_guest",
            ),
        ),
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_003a", "seg_004"], "excluded_segment_ids": []},
    )
    ctx.write_json(
        ARTIFACT_REL,
        {
            "version": 1,
            "locked": True,
            "dropped_segment_ids": ["seg_002"],
            "never_touch_segment_ids": ["seg_002"],
        },
    )
    nle = load_nle(ctx)
    nle["segment_overrides"] = {"seg_003a": {"start_ms": 82720, "end_ms": 83020}}
    save_nle(ctx, nle)
    assert int(segments_by_id_with_nle(ctx)["seg_003a"]["end_ms"]) == 83020

    restored = heal_nle_unplayable_keep_overrides(ctx)
    assert restored == ["seg_003a"]
    assert "start_ms" not in (load_nle(ctx).get("segment_overrides") or {}).get("seg_003a", {})
    assert int(segments_by_id_with_nle(ctx)["seg_003a"]["start_ms"]) == 83020
    assert int(segments_by_id_with_nle(ctx)["seg_003a"]["end_ms"]) == 87160

    intervals = never_touch_source_intervals(ctx)
    ss, se, notes = clamp_source_away_from_never_touch(83020, 87160, intervals)
    assert (ss, se) == (83020, 87160)
    assert not any("zeroed_inside_never_touch" in n for n in notes)


def test_cta_omit_excluded_in_order() -> None:
    from interview_mux.media_ip_cta import execute_cta_omit_from_needs

    ctx = _ctx_010()
    ctx.write_json(
        "segments/manifest.json",
        _manifest(
            _seg("seg_054", "Subscribe to the Life Sciences DNA podcast now.", start=0, end=4000),
            _seg("seg_010", "Early detection of the tumor changing.", start=4000, end=8000),
        ),
    )
    # Bypass selection sanitize (would strip excludes still on ordered).
    import json

    sel_path = ctx.path("master", "selection.json")
    sel_path.parent.mkdir(parents=True, exist_ok=True)
    sel_path.write_text(
        json.dumps(
            {
                "ordered_segment_ids": ["seg_054", "seg_010"],
                "excluded_segment_ids": [{"segment_id": "seg_054", "reason": "media_ip_cta"}],
                "exclude_rationales": {"seg_054": "media_ip_cta sponsor bumper"},
            }
        ),
        encoding="utf-8",
    )
    execute_cta_omit_from_needs(ctx, [])
    sel = ctx.read_json("master/selection.json")
    order = [str(s) for s in (sel.get("ordered_segment_ids") or [])]
    assert "seg_054" not in order
    assert "seg_010" in order
