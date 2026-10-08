"""Delivery cards are input-only summaries and do not change response schemas."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from interview_mux.config import repo_root
from interview_mux.gap_vo_prior_context import cold_open_layup_ok
from interview_mux.spoken_meta_lint import spoken_structure_hits
from interview_mux.stages.gaps import _trim_prior_contexts_to_ids
from interview_mux.vo_delivery_card import (
    apply_gap_delivery_cards,
    episode_card,
    next_beat_card,
)

_ROOT = repo_root()


def test_next_beat_card_uses_summaries_and_drops_ids() -> None:
    card = next_beat_card(
        chapter_title="Chapter 4: The cell-biopsy tradeoff",
        listener_confusion="Why a blood draw still misses intact cells in seg_012.",
        handoff_need="Why a blood draw still misses intact cells in seg_012.",
        mission="Orient the listener for gap_type=missing_setup before the next native beat.",
    )
    assert card is not None
    assert "seg_" not in card.lower()
    assert "012" not in card
    assert "chapter" not in card.lower()
    assert "gap_type" not in card
    assert "blood draw" in card
    assert len(card) <= 400


def test_next_beat_card_drops_editor_notes() -> None:
    assert (
        next_beat_card(
            listener_confusion="The listener never hears the unheard prompt.",
        )
        is None
    )
    card = next_beat_card(
        chapter_title="The screening gap",
        listener_confusion="The listener never hears the unheard prompt.",
    )
    assert card == "The screening gap"


def test_next_beat_card_omits_when_only_boilerplate() -> None:
    assert next_beat_card(mission="Add conversational value that unlocks the next native clip without restating it.") is None
    assert next_beat_card() is None
    assert next_beat_card(chapter_title="Chapter 3") is None


def test_next_beat_card_caps_length() -> None:
    card = next_beat_card(listener_confusion=("tradeoff " * 200))
    assert card is not None
    assert len(card) <= 400


def test_episode_card_requires_thesis_and_skips_quotes() -> None:
    assert episode_card({"topics": [{"name": "Biopsy"}]}) is None
    card = episode_card(
        {
            "thesis": "A blood test can miss intact tumor cells.",
            "guest_name": "Avery Chen",
            "topics": [{"name": "Cell biopsy"}, {"name": "seg_009 access"}],
        },
        through_line="Access depends on finding whole cells, not fragments.",
    )
    assert card is not None
    assert card.startswith("A blood test")
    assert "Avery Chen" in card
    assert "Cell biopsy" in card
    assert "seg_" not in card.lower()
    assert len(card) <= 400


def test_gap_cards_are_top_level_and_shard_trim_keeps_own_ids() -> None:
    payload = apply_gap_delivery_cards(
        {
            "ordered_segment_ids": ["seg_001", "seg_002"],
            "content_brief": {"thesis": "The assay changes who can be screened."},
            "talking_points": {"through_line": "Screening has to reach the clinic."},
            "target_native_contexts": {
                "seg_001": {"chapter_title": "The screening gap"},
                "seg_002": {"chapter_title": "The clinic handoff"},
            },
            "gap_evaluations": {
                "evaluations": [
                    {
                        "segment_id": "seg_002",
                        "listener_confusion": "Why the clinic still cannot run the assay.",
                    }
                ]
            },
            "vo_missions": {
                "seg_001": {
                    "mission": "Orient the listener for gap_type=missing_setup before the next native beat."
                }
            },
        }
    )
    assert payload["episode_card"].startswith("The assay")
    assert "seg_001" in payload["next_beat_cards"]
    assert "seg_002" in payload["next_beat_cards"]
    assert "transcript" not in payload["next_beat_cards"]["seg_001"].lower()
    trimmed = _trim_prior_contexts_to_ids(payload, ["seg_002"])
    assert list(trimmed["next_beat_cards"]) == ["seg_002"]
    assert trimmed["episode_card"]


def test_card_field_names_are_planner_meta_ordinary_words_are_not() -> None:
    assert "spoken_planner_meta" in spoken_structure_hits("Follow the next_beat_card.")
    assert "spoken_planner_meta" in spoken_structure_hits("Use the episode_card here.")
    assert "spoken_planner_meta" not in spoken_structure_hits(
        "The analytical diction stays plain and careful."
    )


def test_cold_open_still_rejects_a_restatement_of_the_first_native() -> None:
    line = {
        "line_category": "episode_preface",
        "targets_segment_id": "seg_001",
        "text": "Cell biopsy finds circulating tumor cells in blood.",
    }
    assert (
        cold_open_layup_ok(
            line,
            target_text="Cell biopsy finds circulating tumor cells in blood.",
            ordered_ids=["seg_001"],
        )
        is False
    )


def _item_schema(envelope_name: str, array_key: str) -> dict:
    path = (
        Path(_ROOT)
        / "docs/cross-cutting/json-schemas/composed"
        / envelope_name
    )
    schema = json.loads(path.read_text(encoding="utf-8"))
    return schema["properties"]["artifacts"]["properties"][array_key]["items"]


def test_persisted_context_packet_accepts_cards_and_responses_cannot_emit_them() -> None:
    """Cards may live on the saved framing packet. Strict replies cannot grow a new key."""
    from interview_mux.prompt_validation import validate_synthetic_context_packet

    packet = {
        "version": 1,
        "generated_at": "2026-10-08T00:00:00Z",
        "ordered_segment_ids": ["seg_001"],
        "selected_native_segments": [{"segment_id": "seg_001", "text": "native words"}],
        "native_duration_ms": 1000,
        "policy": {"plan_after_native_selection": True},
        "episode_card": "A blood test can miss intact tumor cells.",
        "next_beat_cards": {"seg_001": "Why the clinic still cannot run the assay."},
    }
    assert validate_synthetic_context_packet(packet) == []

    forbidden = {"next_beat_card", "next_beat_cards", "episode_card", "delivery_register", "diction"}
    composed = Path(_ROOT) / "docs/cross-cutting/json-schemas/composed"
    envelopes = [
        "analysis_envelope_gap_framing_compose.openai.json",
        "analysis_envelope_nugget_layup_compose.openai.json",
        "analysis_envelope_nugget_intro_compose.openai.json",
        "analysis_envelope_transitions.openai.json",
        "analysis_envelope_vo_line_adjudicate.openai.json",
        "analysis_envelope_synthetic_framing_plan.openai.json",
    ]
    for name in envelopes:
        schema = json.loads((composed / name).read_text(encoding="utf-8"))
        blob = json.dumps(schema)
        for key in forbidden:
            assert f'"{key}"' not in blob, f"{name} lists {key}"

    layup_schema = _item_schema(
        "analysis_envelope_nugget_layup_compose.openai.json", "layups"
    )
    layup = {key: None for key in layup_schema["required"]}
    layup["target_segment_id"] = "seg_011"
    layup["text"] = "Cell biopsy changes what a blood draw can miss."
    Draft202012Validator(layup_schema).validate(layup)
    layup["next_beat_card"] = "should not be a response field"
    errors = list(Draft202012Validator(layup_schema).iter_errors(layup))
    assert errors

    gap_schema = _item_schema(
        "analysis_envelope_gap_framing_compose.openai.json", "interviewer_lines"
    )
    line = {key: None for key in gap_schema["required"]}
    line.update(
        {
            "line_id": "vo_layup_seg_011",
            "gap_type": "missing_setup",
            "text": "Cell biopsy changes what a blood draw can miss.",
            "targets_segment_id": "seg_011",
            "placement": "before",
            "delivery": "synthesize",
            "line_category": "story_bridge",
            "spoken_copy_guard": {
                "action": None,
                "script_hash": None,
                "context_hash": None,
            },
            "extracted_from": {"artifact": None, "path": None},
        }
    )
    Draft202012Validator(gap_schema).validate(line)
    line["delivery_register"] = "warm_conversational"
    assert list(Draft202012Validator(gap_schema).iter_errors(line))
