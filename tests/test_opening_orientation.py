from __future__ import annotations

import json

from interview_mux.opening_orientation import (
    SEQUENCE_COLD_OPEN,
    SEQUENCE_NATIVE_OPEN,
    SEQUENCE_STRAIGHT,
    ensure_episode_orientation,
    validate_opening_orientation,
)
from interview_mux.gap_vo_prior_context import cold_open_layup_ok
from run_fixtures import isolated_run_ctx


def test_orientation_is_minted_and_grounded_from_brief(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_orientation_mint")
    brief_path = ctx.path("understanding", "content_brief.json")
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(
        json.dumps(
            {
                "thesis": (
                    "Founder Asha explains how Acme changed its model, protected its "
                    "team, and found a sustainable path to growth."
                )
            }
        ),
        encoding="utf-8",
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_010", "seg_011"]},
    )

    report, actions = ensure_episode_orientation(
        ctx, {"interviewer_lines": []}, ["seg_010", "seg_011"]
    )

    assert any(a["action"] == "mint_episode_orientation" for a in actions)
    line = report["interviewer_lines"][0]
    assert line["line_category"] == "episode_preface"
    assert line["targets_segment_id"] == "seg_010"
    assert line["placement"] == "before"
    assert line["opening_sequence"] == SEQUENCE_STRAIGHT
    assert "Asha" in line["text"]
    assert line["allow_music_bed_overlap"] is True


def test_orientation_retargets_after_explicit_native_hook_and_dedupes(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_orientation_hook")
    ctx.write_json(
        "master/selection.json",
        {
            "ordered_segment_ids": ["seg_hook", "seg_body"],
            "native_cold_open_segment_id": "seg_hook",
        },
    )
    report = {
        "interviewer_lines": [
            {
                "line_id": "vo_preface_old",
                "line_category": "episode_preface",
                "episode_orientation": True,
                "text": "With Asha, we explore the decision and why it mattered.",
                "targets_segment_id": "seg_removed",
                "placement": "before",
                "delivery": "synthesize",
            },
            {
                "line_id": "vo_preface_duplicate",
                "line_category": "episode_preface",
                "episode_orientation": True,
                "text": "A duplicate.",
                "targets_segment_id": "seg_body",
                "placement": "before",
                "delivery": "synthesize",
            },
        ]
    }

    out, actions = ensure_episode_orientation(
        ctx, report, ["seg_hook", "seg_body"]
    )

    assert len(out["interviewer_lines"]) == 1
    line = out["interviewer_lines"][0]
    assert line["targets_segment_id"] == "seg_hook"
    assert line["placement"] == "after"
    assert line["opening_sequence"] == SEQUENCE_COLD_OPEN
    assert any(a["action"] == "dedupe_episode_orientation" for a in actions)


def test_orientation_repairs_generic_final_handoff_against_first_native(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_orientation_generic_handoff")
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_004"]})
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_004",
                    "type": "interviewee_answer",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "topic_tags": [],
                    "text": (
                        "Mohan contrasts invasive tissue biopsy with a blood-based "
                        "liquid biopsy."
                    ),
                }
            ]
        },
    )
    report, actions = ensure_episode_orientation(
        ctx,
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_preface_episode_orientation",
                    "line_category": "episode_preface",
                    "episode_orientation": True,
                    "text": (
                        "This conversation examines the choices behind modern diagnosis. "
                        "Let's hear how it unfolded."
                    ),
                    "targets_segment_id": "seg_004",
                    "placement": "before",
                    "delivery": "synthesize",
                }
            ]
        },
        ["seg_004"],
    )
    line = report["interviewer_lines"][0]
    assert line["text"].endswith("What does that contrast reveal?")
    assert cold_open_layup_ok(
        line,
        target_text="Mohan contrasts invasive tissue biopsy with a blood-based liquid biopsy.",
        ordered_ids=["seg_004"],
    )
    assert any(a["action"] == "repair_episode_orientation_last_sentence" for a in actions)


def test_orientation_omitted_when_native_hosts_already_intro(tmp_path) -> None:
    """First native is a guest intro — synthetic preface is redundant."""
    ctx = isolated_run_ctx(tmp_path, "run_orientation_intro_handoff")
    first = (
        "Amr, we've got Mohan Uttarwar on the show today. Who is Mohan? "
        "Mohan is a biotech entrepreneur who is the co-founder and CEO of OneCell.ai."
    )
    ctx.write_json("master/selection.json", {"ordered_segment_ids": ["seg_002"]})
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_002",
                    "type": "interviewer_question",
                    "speaker_id": "spk_1",
                    "speaker_role": "interviewer",
                    "topic_tags": [],
                    "text": first,
                }
            ]
        },
    )
    report, actions = ensure_episode_orientation(
        ctx,
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_preface_episode_orientation",
                    "line_category": "episode_preface",
                    "episode_orientation": True,
                    "text": (
                        "In this conversation, oneCell.ai argues that pairing CTC capture "
                        "with ctDNA could make cancer monitoring more actionable. "
                        "Let's hear how it unfolded."
                    ),
                    "targets_segment_id": "seg_002",
                    "placement": "before",
                    "delivery": "synthesize",
                }
            ]
        },
        ["seg_002"],
    )
    assert any(a.get("action") == "omit_episode_orientation" for a in actions)
    assert not any(
        ln.get("episode_orientation") for ln in report.get("interviewer_lines") or []
    )
    meta = report.get("opening_orientation") or {}
    assert meta.get("omitted") is True
    assert meta.get("required") is False
    assert meta.get("sequence") == SEQUENCE_NATIVE_OPEN
    assert validate_opening_orientation(gap_report=report, edl={"clips": []}) == []


def test_opening_contract_accepts_both_sequences() -> None:
    for sequence, clips in (
        (
            SEQUENCE_STRAIGHT,
            [
                {
                    "type": "vo_pickup",
                    "line_id": "vo_preface",
                    "timeline_start_ms": 0,
                    "duration_ms": 4000,
                },
                {
                    "type": "silence",
                    "air_kind": "opening_music",
                    "timeline_start_ms": 4000,
                    "duration_ms": 8000,
                },
                {"type": "speech", "timeline_start_ms": 12000, "duration_ms": 5000},
            ],
        ),
        (
            SEQUENCE_COLD_OPEN,
            [
                {"type": "speech", "timeline_start_ms": 0, "duration_ms": 5000},
                {
                    "type": "silence",
                    "air_kind": "opening_music",
                    "timeline_start_ms": 5000,
                    "duration_ms": 8000,
                },
                {
                    "type": "vo_pickup",
                    "line_id": "vo_preface",
                    "timeline_start_ms": 13000,
                    "duration_ms": 4000,
                },
                {"type": "speech", "timeline_start_ms": 17000, "duration_ms": 5000},
            ],
        ),
    ):
        report = {
            "interviewer_lines": [
                {
                    "line_id": "vo_preface",
                    "line_category": "episode_preface",
                    "episode_orientation": True,
                    "opening_sequence": sequence,
                    "text": "This conversation introduces the guest, subject, and stakes clearly.",
                    "orientation_missions": [
                        "guest_identity",
                        "conversation_topic",
                        "listener_stakes",
                    ],
                }
            ]
        }
        assert validate_opening_orientation(
            gap_report=report, edl={"clips": clips}
        ) == []


def test_fallback_orientation_never_injects_chapter(tmp_path) -> None:
    from interview_mux.opening_orientation import _fallback_orientation_text

    ctx = isolated_run_ctx(tmp_path, "run_orientation_no_chapter")
    brief_path = ctx.path("understanding", "content_brief.json")
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(
        json.dumps(
            {
                "thesis": (
                    "Founder Asha explains the growth stage that unlocked durable scale."
                )
            }
        ),
        encoding="utf-8",
    )
    text, _ = _fallback_orientation_text(ctx)
    assert "chapter" not in text.casefold()
    assert "phase" in text.casefold() or "growth" in text.casefold()


def test_orientation_omitted_when_native_open_self_orients(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_orientation_omit_native")
    brief_path = ctx.path("understanding", "content_brief.json")
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(
        json.dumps({"guest_name": "Mohan", "thesis": "Liquid biopsy changes trials."}),
        encoding="utf-8",
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_010", "seg_011"]},
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_010",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewer",
                    "type": "interviewer_question",
                    "topic_tags": [],
                    "text": (
                        "Welcome Mohan — today we talk about liquid biopsy, "
                        "trial design, and why a blood draw changes diagnostics."
                    ),
                    "start_ms": 0,
                    "end_ms": 8000,
                },
                {
                    "segment_id": "seg_011",
                    "speaker_id": "spk_1",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                    "text": "Tissue biopsy is invasive and expensive.",
                    "start_ms": 8000,
                    "end_ms": 14000,
                },
            ]
        },
    )
    report, actions = ensure_episode_orientation(
        ctx,
        {
            "interviewer_lines": [
                {
                    "line_id": "vo_preface_episode_orientation",
                    "line_category": "episode_preface",
                    "episode_orientation": True,
                    "text": "Before the science, meet the founder.",
                    "targets_segment_id": "seg_010",
                }
            ]
        },
        ["seg_010", "seg_011"],
    )
    assert any(a.get("action") == "omit_episode_orientation" for a in actions)
    assert not any(
        ln.get("episode_orientation") for ln in report.get("interviewer_lines") or []
    )
    meta = report.get("opening_orientation") or {}
    assert meta.get("omitted") is True
    assert meta.get("required") is False
    assert meta.get("sequence") == SEQUENCE_NATIVE_OPEN


def test_orientation_omitted_when_two_hosts_split_the_intro(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "run_orientation_omit_two_hosts")
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_a", "seg_b", "seg_c"]},
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_a",
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewer",
                    "type": "interviewer_question",
                    "topic_tags": [],
                    "text": (
                        "Amr, we've got a special guest on the show today, "
                        "and I want you to take this one."
                    ),
                    "start_ms": 0,
                    "end_ms": 6000,
                },
                {
                    "segment_id": "seg_b",
                    "speaker_id": "spk_1",
                    "speaker_role": "interviewer",
                    "type": "interviewer_question",
                    "topic_tags": [],
                    "text": (
                        "Who is Mohan? Mohan is a biotech entrepreneur and "
                        "the co-founder of OneCell.ai."
                    ),
                    "start_ms": 6000,
                    "end_ms": 12000,
                },
                {
                    "segment_id": "seg_c",
                    "speaker_id": "spk_2",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "topic_tags": [],
                    "text": "Tissue biopsy is invasive and expensive.",
                    "start_ms": 12000,
                    "end_ms": 18000,
                },
            ]
        },
    )
    report, actions = ensure_episode_orientation(
        ctx, {"interviewer_lines": []}, ["seg_a", "seg_b", "seg_c"]
    )
    assert any(a.get("action") == "omit_episode_orientation" for a in actions)
    assert report["interviewer_lines"] == []
    assert (report.get("opening_orientation") or {}).get("omitted") is True


def test_opening_contract_accepts_omitted_native_intro() -> None:
    report = {
        "interviewer_lines": [
            {
                "line_id": "vo_layup_seg_002",
                "origin": "nugget_layup",
                "text": "What should we listen for in the next beat?",
                "targets_segment_id": "seg_002",
                "placement": "before",
            }
        ],
        "opening_orientation": {
            "required": False,
            "omitted": True,
            "omit_reason": "native_open_self_orients",
            "sequence": SEQUENCE_NATIVE_OPEN,
            "target_segment_id": "seg_001",
        },
    }
    edl = {
        "clips": [
            {
                "type": "silence",
                "air_kind": "opening_music",
                "timeline_start_ms": 0,
                "duration_ms": 8000,
            },
            {"type": "speech", "timeline_start_ms": 8000, "duration_ms": 5000},
        ]
    }
    assert validate_opening_orientation(gap_report=report, edl=edl) == []
