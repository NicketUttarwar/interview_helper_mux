from __future__ import annotations

import json

from interview_mux.opening_orientation import (
    SEQUENCE_COLD_OPEN,
    SEQUENCE_STRAIGHT,
    ensure_episode_orientation,
    validate_opening_orientation,
)
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
