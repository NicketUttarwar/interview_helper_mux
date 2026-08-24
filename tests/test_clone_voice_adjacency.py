from __future__ import annotations

from pathlib import Path

from interview_mux.clone_adjacency_verify import (
    id_matches_clone,
    should_suppress_clone_adjacency,
    tape_window_ms,
)
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


def test_clone_adjacent_vo_drops_when_replacement_occupied() -> None:
    """When the only non-clone retarget is already owned, drop instead of stacking."""
    report, notes = avoid_clone_voice_adjacency(
        {
            "interviewer_lines": [
                _line(
                    line_id="vo_guest",
                    targets_segment_id="guest",
                    voice_speaker_id="spk_host",
                ),
                _line(line_id="vo_host", targets_segment_id="host_a"),
            ]
        },
        SEGMENTS,
        ordered_segment_ids=ORDER,
        clone_speaker_id="spk_host",
        nugget_corpus=CORPUS,
    )
    kept_ids = {str(ln.get("line_id")) for ln in report["interviewer_lines"]}
    assert "vo_guest" in kept_ids
    assert "vo_host" not in kept_ids
    assert any(n.get("action") == "drop_clone_adjacency" for n in notes)


def test_empty_layup_is_not_clone_adjacency_exempt() -> None:
    line = _line(origin="nugget_layup", nugget_ids=[])

    assert not is_cut_recovery_vo(
        line, ordered_segment_ids=ORDER, nugget_corpus=CORPUS
    )


def test_edl_keeps_episode_orientation_despite_clone_adjacency(tmp_path: Path) -> None:
    path = tmp_path / "vo.wav"
    path.write_bytes(b"x")
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ORDER},
        segments_by_id=SEGMENTS,
        gap_report={
            "interviewer_lines": [
                _line(
                    line_id="vo_preface_opening",
                    episode_orientation=True,
                    line_category="episode_preface",
                    gap_type="missing_orientation",
                    orientation_missions=[
                        "guest_identity",
                        "conversation_topic",
                        "listener_stakes",
                    ],
                    text=(
                        "Mohan of OneCell.ai joins us to examine whether blood-based "
                        "cancer testing can become more adaptive."
                    ),
                )
            ]
        },
        resolve_vo_path=lambda _line: path,
        vo_duration_ms=lambda _path: 1000,
    )
    vo = [clip for clip in edl["clips"] if clip.get("type") == "vo_pickup"]
    assert [clip.get("line_id") for clip in vo] == ["vo_preface_opening"]
    assert "vo_preface_opening" not in edl["warnings"]["suppressed_clone_adjacency"]


def test_orientation_clone_adjacency_is_exempt() -> None:
    report, notes = avoid_clone_voice_adjacency(
        {
            "interviewer_lines": [
                _line(
                    line_id="vo_preface_opening",
                    episode_orientation=True,
                    line_category="episode_preface",
                )
            ]
        },
        SEGMENTS,
        ordered_segment_ids=ORDER,
        clone_speaker_id="spk_host",
        nugget_corpus=CORPUS,
    )
    kept = report["interviewer_lines"][0]
    assert kept["targets_segment_id"] == "host_a"
    assert kept["clone_adjacency_exempt"] is True
    assert notes == []


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


def test_id_matches_clone_requires_both_ids() -> None:
    assert id_matches_clone("spk_1", "spk_1")
    assert not id_matches_clone("spk_0", "spk_1")
    assert not id_matches_clone("", "spk_1")
    assert not id_matches_clone("spk_1", "")


def test_should_suppress_keep_only_when_every_hit_is_no() -> None:
    assert should_suppress_clone_adjacency(
        id_hit_segment_ids=[], verdicts={}, verify_enabled=True
    ) == (False, "no_id_match")
    assert should_suppress_clone_adjacency(
        id_hit_segment_ids=["seg_a"], verdicts=None, verify_enabled=False
    ) == (True, "id_match")
    assert should_suppress_clone_adjacency(
        id_hit_segment_ids=["seg_a"],
        verdicts={"seg_a": "YES"},
        verify_enabled=True,
    ) == (True, "same_person")
    assert should_suppress_clone_adjacency(
        id_hit_segment_ids=["seg_a"],
        verdicts={"seg_a": None},
        verify_enabled=True,
    ) == (True, "verify_unavailable")
    assert should_suppress_clone_adjacency(
        id_hit_segment_ids=["seg_a", "seg_b"],
        verdicts={"seg_a": "NO", "seg_b": "NO"},
        verify_enabled=True,
    ) == (False, "id_mismatch_kept")
    assert should_suppress_clone_adjacency(
        id_hit_segment_ids=["seg_a", "seg_b"],
        verdicts={"seg_a": "NO", "seg_b": None},
        verify_enabled=True,
    ) == (True, "verify_unavailable")


def test_tape_window_uses_end_or_start_edge() -> None:
    seg = {"start_ms": 10_000, "end_ms": 20_000}
    assert tape_window_ms(seg, edge="end", clip_ms=4000) == (16_000, 20_000)
    assert tape_window_ms(seg, edge="start", clip_ms=4000) == (10_000, 14_000)


def _transition(*, after: str, before: str, voice: str = "spk_host") -> dict:
    return {
        "after_segment_id": after,
        "before_segment_id": before,
        "text": "A short host bridge.",
        "type": "light_bridge",
        "voice_speaker_id": voice,
    }


def test_edl_verify_yes_still_suppresses_clone_adjacent_vo(tmp_path: Path) -> None:
    path = tmp_path / "vo.wav"
    path.write_bytes(b"x")
    calls: list[tuple[str, str]] = []

    def verify_pair(a: Path, b: Path) -> str:
        calls.append((a.name, b.name))
        return "YES"

    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ORDER},
        segments_by_id=SEGMENTS,
        gap_report={"interviewer_lines": [_line()]},
        resolve_vo_path=lambda _line: path,
        vo_duration_ms=lambda _path: 1000,
        verify_pair=verify_pair,
    )

    assert not [clip for clip in edl["clips"] if clip.get("type") == "vo_pickup"]
    assert edl["warnings"]["suppressed_clone_adjacency"] == ["vo_1"]
    assert calls == [("spk_host", "host_a")]


def test_edl_verify_no_keeps_clone_adjacent_vo(tmp_path: Path) -> None:
    path = tmp_path / "vo.wav"
    path.write_bytes(b"x")

    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ORDER},
        segments_by_id=SEGMENTS,
        gap_report={"interviewer_lines": [_line()]},
        resolve_vo_path=lambda _line: path,
        vo_duration_ms=lambda _path: 1000,
        verify_pair=lambda _a, _b: "NO",
    )

    vo = [clip for clip in edl["clips"] if clip.get("type") == "vo_pickup"]
    assert [clip.get("line_id") for clip in vo] == ["vo_1"]
    assert edl["warnings"]["suppressed_clone_adjacency"] == []
    assert edl["warnings"]["clone_adjacency_id_mismatch_kept"] == ["vo_1"]


def test_edl_verify_none_still_suppresses(tmp_path: Path) -> None:
    path = tmp_path / "vo.wav"
    path.write_bytes(b"x")

    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ORDER},
        segments_by_id=SEGMENTS,
        gap_report={"interviewer_lines": [_line()]},
        resolve_vo_path=lambda _line: path,
        vo_duration_ms=lambda _path: 1000,
        verify_pair=lambda _a, _b: None,
    )

    assert not [clip for clip in edl["clips"] if clip.get("type") == "vo_pickup"]
    assert edl["warnings"]["suppressed_clone_adjacency"] == ["vo_1"]


def test_edl_guest_guest_transition_does_not_call_verify() -> None:
    segs = {
        "guest_a": {
            "segment_id": "guest_a",
            "speaker_id": "spk_guest",
            "start_ms": 0,
            "end_ms": 1000,
        },
        "guest_b": {
            "segment_id": "guest_b",
            "speaker_id": "spk_guest",
            "start_ms": 1000,
            "end_ms": 2000,
        },
    }
    calls: list[tuple[str, str]] = []

    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["guest_a", "guest_b"]},
        segments_by_id=segs,
        transitions={
            "transitions": [_transition(after="guest_a", before="guest_b")]
        },
        verify_pair=lambda a, b: calls.append((a.name, b.name)) or "YES",
    )

    assert [c.get("type") for c in edl["clips"] if c.get("type") == "transition"]
    assert calls == []
    assert edl["warnings"]["suppressed_clone_adjacency"] == []


def test_edl_verify_no_keeps_id_matching_transition() -> None:
    segs = {
        "guest": {
            "segment_id": "guest",
            "speaker_id": "spk_guest",
            "start_ms": 0,
            "end_ms": 1000,
        },
        "host_b": {
            "segment_id": "host_b",
            "speaker_id": "spk_host",
            "start_ms": 1000,
            "end_ms": 2000,
        },
    }

    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["guest", "host_b"]},
        segments_by_id=segs,
        transitions={"transitions": [_transition(after="guest", before="host_b")]},
        verify_pair=lambda _a, _b: "NO",
    )

    assert any(c.get("type") == "transition" for c in edl["clips"])
    assert edl["warnings"]["suppressed_clone_adjacency"] == []
    assert edl["warnings"]["clone_adjacency_id_mismatch_kept"] == [
        "transition:guest->host_b"
    ]


def test_edl_verify_yes_suppresses_id_matching_transition() -> None:
    segs = {
        "guest": {
            "segment_id": "guest",
            "speaker_id": "spk_guest",
            "start_ms": 0,
            "end_ms": 1000,
        },
        "host_b": {
            "segment_id": "host_b",
            "speaker_id": "spk_host",
            "start_ms": 1000,
            "end_ms": 2000,
        },
    }

    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["guest", "host_b"]},
        segments_by_id=segs,
        transitions={"transitions": [_transition(after="guest", before="host_b")]},
        verify_pair=lambda _a, _b: "YES",
    )

    assert not [c for c in edl["clips"] if c.get("type") == "transition"]
    assert edl["warnings"]["suppressed_clone_adjacency"] == [
        "transition:guest->host_b"
    ]


def test_edl_verify_caches_shared_segment() -> None:
    segs = {
        "guest_a": {
            "segment_id": "guest_a",
            "speaker_id": "spk_guest",
            "start_ms": 0,
            "end_ms": 1000,
        },
        "host_mid": {
            "segment_id": "host_mid",
            "speaker_id": "spk_host",
            "start_ms": 1000,
            "end_ms": 2000,
        },
        "guest_b": {
            "segment_id": "guest_b",
            "speaker_id": "spk_guest",
            "start_ms": 2000,
            "end_ms": 3000,
        },
    }
    calls: list[str] = []

    def verify_pair(a: Path, b: Path) -> str:
        calls.append(b.name)
        return "NO"

    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["guest_a", "host_mid", "guest_b"]},
        segments_by_id=segs,
        transitions={
            "transitions": [
                _transition(after="guest_a", before="host_mid"),
                _transition(after="host_mid", before="guest_b"),
            ]
        },
        verify_pair=verify_pair,
    )

    assert calls == ["host_mid"]
    assert edl["warnings"]["suppressed_clone_adjacency"] == []
    assert set(edl["warnings"]["clone_adjacency_id_mismatch_kept"]) == {
        "transition:guest_a->host_mid",
        "transition:host_mid->guest_b",
    }

