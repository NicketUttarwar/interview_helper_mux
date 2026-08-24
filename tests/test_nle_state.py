from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.nle_state import (
    apply_nle_to_selection,
    apply_segments_with_nle,
    incomplete_trim_ends,
    nle_has_operator_edits,
    save_nle,
)
from interview_mux.run_context import RunContext
from run_fixtures import init_run_meta_for_test, patch_executions_root, patch_merged_config


def _segments() -> list[dict]:
    return [
        {
            "segment_id": "seg_a",
            "start_ms": 0,
            "end_ms": 10_000,
            "speaker_id": "spk1",
            "type": "interviewee_answer",
        },
        {
            "segment_id": "seg_b",
            "start_ms": 10_000,
            "end_ms": 20_000,
            "speaker_id": "spk1",
            "type": "interviewee_answer",
        },
        {
            "segment_id": "seg_c",
            "start_ms": 20_000,
            "end_ms": 30_000,
            "speaker_id": "spk1",
            "type": "interviewee_answer",
        },
    ]


def test_nle_has_operator_edits_detects_order_and_exclude() -> None:
    assert not nle_has_operator_edits({"playhead_ms": 0})
    assert nle_has_operator_edits({"sequence_order": ["seg_a"]})
    assert nle_has_operator_edits(
        {"segment_overrides": {"seg_a": {"excluded": True}}}
    )


def test_apply_segments_excludes_and_reorders() -> None:
    nle = {
        "sequence_order": ["seg_c", "seg_a"],
        "segment_overrides": {"seg_b": {"excluded": True}},
    }
    out = apply_segments_with_nle(_segments(), nle)
    ids = [s["segment_id"] for s in out]
    assert ids == ["seg_c", "seg_a"]


def test_apply_segments_split_children() -> None:
    nle = {
        "sequence_order": ["seg_aa", "seg_ab", "seg_c"],
        "segment_overrides": {
            "seg_a": {"excluded": True, "split_into": ["seg_aa", "seg_ab"]},
            "seg_aa": {"start_ms": 0, "end_ms": 5000, "parent_id": "seg_a"},
            "seg_ab": {"start_ms": 5000, "end_ms": 10_000, "parent_id": "seg_a"},
        },
    }
    out = apply_segments_with_nle(_segments(), nle)
    by_id = {s["segment_id"]: s for s in out}
    assert "seg_a" not in by_id
    assert by_id["seg_aa"]["end_ms"] == 5000
    assert by_id["seg_ab"]["start_ms"] == 5000


def test_apply_nle_to_selection_merges_order_and_excludes() -> None:
    selection = {
        "ordered_segment_ids": ["seg_a", "seg_b", "seg_c"],
        "excluded_segment_ids": [],
    }
    nle = {
        "sequence_order": ["seg_c", "seg_a"],
        "segment_overrides": {"seg_b": {"excluded": True}},
    }
    by_id = {
        "seg_a": {"segment_id": "seg_a"},
        "seg_b": {"segment_id": "seg_b"},
        "seg_c": {"segment_id": "seg_c"},
    }
    merged = apply_nle_to_selection(selection, nle, segments_by_id=by_id)
    assert merged["ordered_segment_ids"] == ["seg_c", "seg_a"]
    assert any(
        e["segment_id"] == "seg_b" and e["reason"] == "nle_operator"
        for e in merged["excluded_segment_ids"]
    )
    assert merged.get("nle_applied") is True


def test_apply_nle_inserts_keepable_children_when_parent_unranked() -> None:
    selection = {
        "ordered_segment_ids": ["seg_005"],
        "excluded_segment_ids": [],
    }
    nle = {
        "sequence_order": [],
        "segment_overrides": {
            "seg_003": {"excluded": True, "split_into": ["seg_003a", "seg_003b"]},
            "seg_003a": {"start_ms": 0, "end_ms": 20000, "parent_id": "seg_003"},
            "seg_003b": {
                "start_ms": 20000,
                "end_ms": 40000,
                "parent_id": "seg_003",
                "excluded": True,
            },
        },
    }
    by_id = {
        "seg_003a": {"segment_id": "seg_003a", "start_ms": 0},
        "seg_003b": {"segment_id": "seg_003b", "start_ms": 20000},
        "seg_005": {"segment_id": "seg_005", "start_ms": 40000},
    }
    merged = apply_nle_to_selection(selection, nle, segments_by_id=by_id)
    assert merged["ordered_segment_ids"][0] == "seg_003a"
    assert "seg_003b" not in merged["ordered_segment_ids"]
    assert "seg_003" not in merged["ordered_segment_ids"]
    assert "seg_005" in merged["ordered_segment_ids"]


def test_apply_nle_drops_never_touch_cta(nle_ctx: RunContext) -> None:
    nle_ctx.write_json(
        "mastering/media_ip_cta.json",
        {
            "version": 1,
            "dropped_segment_ids": ["seg_071c", "seg_071f"],
            "never_touch_segment_ids": ["seg_071c", "seg_071f"],
        },
    )
    selection = {
        "ordered_segment_ids": ["seg_a", "seg_b", "seg_c"],
        "excluded_segment_ids": [],
    }
    nle = {
        "sequence_order": ["seg_a", "seg_071c", "seg_b", "seg_071f", "seg_c"],
        "segment_overrides": {},
    }
    by_id = {
        "seg_a": {"segment_id": "seg_a"},
        "seg_b": {"segment_id": "seg_b"},
        "seg_c": {"segment_id": "seg_c"},
        "seg_071c": {"segment_id": "seg_071c"},
        "seg_071f": {"segment_id": "seg_071f"},
    }
    merged = apply_nle_to_selection(selection, nle, segments_by_id=by_id, ctx=nle_ctx)
    assert merged["ordered_segment_ids"] == ["seg_a", "seg_b", "seg_c"]
    assert "seg_071c" not in merged["ordered_segment_ids"]
    assert "seg_071f" not in merged["ordered_segment_ids"]


def test_apply_segments_trim_override() -> None:
    nle = {"segment_overrides": {"seg_a": {"start_ms": 500, "end_ms": 8000}}}
    out = apply_segments_with_nle(_segments(), nle)
    by_id = {s["segment_id"]: s for s in out}
    assert by_id["seg_a"]["start_ms"] == 500
    assert by_id["seg_a"]["end_ms"] == 8000


def _words(*rows: tuple[int, int, str]) -> list[dict]:
    return [{"start_ms": s, "end_ms": e, "text": t} for s, e, t in rows]


@pytest.fixture
def nle_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    patch_executions_root(monkeypatch, tmp_path)
    c = RunContext("exec_nle_incomplete", create=True)
    init_run_meta_for_test(c)
    c.write_json(
        "segments/manifest.json",
        {
            "segments": [
                {
                    "segment_id": "seg_a",
                    "start_ms": 0,
                    "end_ms": 10_000,
                    "speaker_id": "spk_0",
                    "speaker_role": "interviewee",
                    "type": "interviewee_answer",
                    "text": "hello there and we shipped it",
                    "topic_tags": [],
                }
            ]
        },
    )
    c.write_json(
        "transcript/full.json",
        {
            "text": "hello there and we shipped it",
            "words": _words(
                (0, 500, "hello"),
                (500, 900, "there"),
                (900, 1200, "and"),
                (1200, 1500, "we"),
                (1500, 2000, "shipped"),
                (2000, 2300, "it."),
            ),
        },
    )
    c.write_json("segments/nle_edits.json", {"playhead_ms": 0})
    return c


def test_incomplete_trim_ends_flags_mid_clause(nle_ctx: RunContext) -> None:
    nle = {"segment_overrides": {"seg_a": {"start_ms": 0, "end_ms": 1200}}}
    assert incomplete_trim_ends(nle_ctx, nle) == ["seg_a"]


def test_incomplete_trim_ends_allows_terminal_punctuation(nle_ctx: RunContext) -> None:
    nle = {"segment_overrides": {"seg_a": {"start_ms": 0, "end_ms": 2300}}}
    assert incomplete_trim_ends(nle_ctx, nle) == []


def test_incomplete_trim_ends_skips_excluded_and_missing_transcript(
    nle_ctx: RunContext,
) -> None:
    # Excluded overrides are not clause boundaries.
    nle = {"segment_overrides": {"seg_a": {"excluded": True, "end_ms": 1200}}}
    assert incomplete_trim_ends(nle_ctx, nle) == []
    # No transcript at all — best-effort, never raises.
    nle_ctx.path("transcript", "full.json").unlink()
    nle = {"segment_overrides": {"seg_a": {"start_ms": 0, "end_ms": 1200}}}
    assert incomplete_trim_ends(nle_ctx, nle) == []


def test_save_nle_warns_on_incomplete_end_by_default(nle_ctx: RunContext) -> None:
    nle = {"segment_overrides": {"seg_a": {"start_ms": 0, "end_ms": 1200}}}
    save_nle(nle_ctx, nle)  # does not raise (soft warn is the default)
    log_text = nle_ctx.path("gui_log.jsonl").read_text(encoding="utf-8")
    assert "mid-clause" in log_text
    assert "seg_a" in log_text


def test_save_nle_blocks_incomplete_end_when_configured(
    nle_ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from interview_mux.config import merged_config

    patch_merged_config(
        monkeypatch,
        {**merged_config(), "nle_edits": {"strict": True, "block_incomplete_ends": True}},
    )
    nle = {"segment_overrides": {"seg_a": {"start_ms": 0, "end_ms": 1200}}}
    with pytest.raises(ValueError, match="mid-clause"):
        save_nle(nle_ctx, nle)
