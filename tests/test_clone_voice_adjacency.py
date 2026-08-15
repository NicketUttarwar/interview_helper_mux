from __future__ import annotations

from pathlib import Path

from interview_mux.gap_framing import (
    avoid_clone_voice_adjacency,
    is_cut_recovery_vo,
)
from interview_mux.stages.assembly import build_flow1_edl


SEGMENTS = {
    "host_a": {"segment_id": "host_a", "speaker_id": "spk_host", "start_ms": 0, "end_ms": 1000},
    "guest": {"segment_id": "guest", "speaker_id": "spk_guest", "start_ms": 1000, "end_ms": 2000},
}
ORDER = ["host_a", "guest"]
CORPUS = {
    "nuggets": [
        {
            "nugget_id": "cut_fact",
            "source_segment_ids": ["cut_host"],
            "in_selection": False,
        }
    ]
}


def _line(**overrides: object) -> dict:
    return {
        "line_id": "vo_1",
        "text": "A grounded explanatory setup.",
        "targets_segment_id": "host_a",
        "placement": "before",
        "delivery": "record",
        "voice_speaker_id": "spk_host",
        **overrides,
    }


def test_generic_clone_adjacent_vo_retargets_to_guest() -> None:
    report, notes = avoid_clone_voice_adjacency(
        {"interviewer_lines": [_line()]},
        SEGMENTS,
        ordered_segment_ids=ORDER,
        clone_speaker_id="spk_host",
        nugget_corpus=CORPUS,
    )

    assert report["interviewer_lines"][0]["targets_segment_id"] == "guest"
    assert report["interviewer_lines"][0]["placement"] == "before"
    assert notes[0]["action"] == "retarget_clone_adjacency"


def test_excluded_tape_layup_is_allowed_before_clone_source() -> None:
    line = _line(origin="nugget_layup", nugget_ids=["cut_fact"])

    assert is_cut_recovery_vo(
        line, ordered_segment_ids=ORDER, nugget_corpus=CORPUS
    )
    report, notes = avoid_clone_voice_adjacency(
        {"interviewer_lines": [line]},
        SEGMENTS,
        ordered_segment_ids=ORDER,
        clone_speaker_id="spk_host",
        nugget_corpus=CORPUS,
    )
    kept = report["interviewer_lines"][0]
    assert kept["targets_segment_id"] == "host_a"
    assert kept["clone_adjacency_exempt"] is True
    assert notes == []


def test_empty_layup_is_not_clone_adjacency_exempt() -> None:
    line = _line(origin="nugget_layup", nugget_ids=[])

    assert not is_cut_recovery_vo(
        line, ordered_segment_ids=ORDER, nugget_corpus=CORPUS
    )


def test_edl_suppresses_unmarked_clone_adjacent_vo(tmp_path: Path) -> None:
    path = tmp_path / "vo.wav"
    path.write_bytes(b"x")
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ORDER},
        segments_by_id=SEGMENTS,
        gap_report={"interviewer_lines": [_line()]},
        resolve_vo_path=lambda _line: path,
        vo_duration_ms=lambda _path: 1000,
    )

    assert not [clip for clip in edl["clips"] if clip.get("type") == "vo_pickup"]
    assert edl["warnings"]["suppressed_clone_adjacency"] == ["vo_1"]

