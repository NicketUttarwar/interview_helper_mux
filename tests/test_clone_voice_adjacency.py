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


def test_clone_adjacent_to_prior_host_retargets_to_later_guest() -> None:
    """Before-guest VO is still clone-adjacent when the previous native is the host."""
    segments = {
        **SEGMENTS,
        "guest2": {
            "segment_id": "guest2",
            "speaker_id": "spk_guest",
            "start_ms": 2000,
            "end_ms": 3000,
        },
    }
    report, notes = avoid_clone_voice_adjacency(
        {"interviewer_lines": [_line(targets_segment_id="guest")]},
        segments,
        ordered_segment_ids=["host_a", "guest", "guest2"],
        clone_speaker_id="spk_host",
        nugget_corpus=CORPUS,
    )

    assert report["interviewer_lines"][0]["targets_segment_id"] == "guest2"
    assert notes[0]["action"] == "retarget_clone_adjacency"


def test_edl_suppresses_clone_adjacent_to_previous_native(tmp_path: Path) -> None:
    path = tmp_path / "vo.wav"
    path.write_bytes(b"x")
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ORDER},
        segments_by_id=SEGMENTS,
        gap_report={"interviewer_lines": [_line(targets_segment_id="guest")]},
        resolve_vo_path=lambda _line: path,
        vo_duration_ms=lambda _path: 1000,
    )

    assert not [clip for clip in edl["clips"] if clip.get("type") == "vo_pickup"]
    assert edl["warnings"]["suppressed_clone_adjacency"] == ["vo_1"]


def test_generic_clone_adjacent_vo_drops_when_next_guest_still_abuts_host() -> None:
    """Retargeting onto the first guest still sits clone VO next to the host native."""
    report, notes = avoid_clone_voice_adjacency(
        {"interviewer_lines": [_line()]},
        SEGMENTS,
        ordered_segment_ids=ORDER,
        clone_speaker_id="spk_host",
        nugget_corpus=CORPUS,
    )

    assert report.get("interviewer_lines") == []
    assert notes[0]["action"] == "drop_clone_adjacency"


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
    assert "vo_host" not in kept_ids
    assert "vo_guest" not in kept_ids
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


def test_edl_suppresses_clone_adjacent_auto_minted_transition() -> None:
    """Synth-stamped host voice next to host native must hitch, not ship a transition clip."""
    segs = {
        "seg_023": {
            "segment_id": "seg_023",
            "speaker_id": "spk_0",
            "start_ms": 0,
            "end_ms": 3000,
            "text": "guest prior",
        },
        "seg_024": {
            "segment_id": "seg_024",
            "speaker_id": "spk_1",
            "start_ms": 4000,
            "end_ms": 7000,
            "text": "host native",
        },
    }
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_023", "seg_024"]},
        segments_by_id=segs,
        transitions={
            "transitions": [
                {
                    "after_segment_id": "seg_023",
                    "before_segment_id": "seg_024",
                    "text": "Moving from tumor cells to the next beat.",
                    "voice_speaker_id": "spk_1",
                    "auto_minted": True,
                    "type": "bridge",
                }
            ]
        },
        verify_pair=lambda _a, _b: None,
    )
    assert not [c for c in edl["clips"] if c.get("type") == "transition"]
    assert "transition:seg_023->seg_024" in edl["warnings"]["suppressed_clone_adjacency"]


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


def test_edl_suppresses_unvoiced_transition_after_clone_source() -> None:
    """Episode lock must be stamped before clone-adjacency decide, not after emit."""
    from interview_mux.run_context import RunContext

    ctx = RunContext("run_edl_unvoiced_tr", create=True)
    ctx.write_json(
        "understanding/speaker_delivery_plan.json",
        {"clone_speaker_id": "spk_host"},
        skip_handoff=True,
    )
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ORDER},
        segments_by_id=SEGMENTS,
        transitions={
            "transitions": [_transition(after="host_a", before="guest", voice="")]
        },
        ctx=ctx,
    )

    assert not [c for c in edl["clips"] if c.get("type") == "transition"]
    assert "transition:host_a->guest" in edl["warnings"]["suppressed_clone_adjacency"]
    hitch = [c for c in edl["clips"] if c.get("clone_adjacency_hitch")]
    assert hitch
    assert hitch[0].get("air_kind") == "chapter_hinge"
    assert int(hitch[0].get("duration_ms") or 0) > 0


def test_edl_chapter_jump_without_transition_gets_hitch() -> None:
    """Reorder/chapter-scale joins still need audible glue when clone speech is absent."""
    from interview_mux.assembly_ledger import HITCH_AIR_KINDS, _seam_index
    from interview_mux.reorder_bridges import build_reorder_bridges

    segs = {
        "host_a": {
            "segment_id": "host_a",
            "speaker_id": "spk_host",
            "start_ms": 0,
            "end_ms": 8_000,
        },
        "guest": {
            "segment_id": "guest",
            "speaker_id": "spk_guest",
            "start_ms": 90_000,
            "end_ms": 100_000,
        },
    }
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["host_a", "guest"]},
        segments_by_id=segs,
        transitions={"transitions": []},
    )
    hitch = [
        c
        for c in edl["clips"]
        if str(c.get("air_kind") or "") in HITCH_AIR_KINDS
        and int(c.get("duration_ms") or 0) > 0
    ]
    assert hitch
    assert hitch[0].get("required_seam_hitch") is True
    seams = _seam_index(
        ["host_a", "guest"],
        segs,
        [c for c in (edl.get("clips") or []) if isinstance(c, dict)],
        build_reorder_bridges(["host_a", "guest"], segs),
    )
    assert not any(s.get("naked") for s in seams)


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


def _seg(sid: str, speaker: str, text: str, *, start_ms: int = 0) -> dict:
    return {
        "segment_id": sid,
        "speaker_id": speaker,
        "speaker_role": "interviewer" if speaker == "spk_host" else "interviewee",
        "type": "interviewer_question" if speaker == "spk_host" else "interviewee_answer",
        "topic_tags": [],
        "text": text,
        "start_ms": start_ms,
        "end_ms": start_ms + 4000,
    }


def test_nugget_clone_adjacent_layup_retargets_to_guest(monkeypatch) -> None:
    from interview_mux.nugget_layup import apply_clone_voice_adjacency_skips
    from interview_mux.run_context import RunContext

    ctx = RunContext("exec_clone_retarget_010", create=True)
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_010", "seg_012"]},
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                _seg("seg_010", "spk_host", "Tell us about cell biopsy."),
                _seg("seg_012", "spk_guest", "Circulating tumour cells are rare.", start_ms=4000),
            ]
        },
    )
    ctx.write_json(
        "understanding/nugget_corpus.json",
        {
            "nuggets": [
                {
                    "nugget_id": "nug_cell",
                    "text_claim": "Mohan calls cell biopsy a next generation of liquid biopsy.",
                    "evidence_quote": "next generation of liquid biopsy",
                    "salience": "high",
                    "in_selection": True,
                }
            ]
        },
    )
    monkeypatch.setattr(
        "interview_mux.source_topology.pickup_eligible_speaker_id",
        lambda _ctx: "spk_host",
    )
    plan = {
        "ordered_segment_ids": ["seg_010", "seg_012"],
        "layups": [
            {
                "target_segment_id": "seg_010",
                "line_id": "vo_layup_seg_010",
                "text": (
                    "Mohan calls cell biopsy a next generation of liquid biopsy. "
                    "What should we listen for next?"
                ),
                "nugget_ids": ["nug_cell"],
                "selected_nugget_ids": ["nug_cell"],
                "skip": False,
                "target_beat": "Cell biopsy definition",
                "listener_need_entering_T": "Need the definition before the guest clip.",
                "forward_unlock": "What should we listen for next?",
                "setup_from_nuggets": "Mohan calls cell biopsy a next generation of liquid biopsy.",
            },
            {
                "target_segment_id": "seg_012",
                "line_id": "vo_layup_seg_012",
                "text": "",
                "skip": True,
                "skip_reason_code": "self_explanatory_native",
                "compensating_path": "native_self_orients",
            },
        ],
    }
    out, notes = apply_clone_voice_adjacency_skips(ctx, plan)
    aired = [
        r
        for r in out["layups"]
        if not r.get("skip") and str(r.get("text") or "").strip()
    ]
    assert len(aired) == 1
    assert aired[0]["target_segment_id"] == "seg_012"
    assert "nug_cell" in (aired[0].get("nugget_ids") or [])
    assert any(n.get("action") == "retarget_clone_voice_adjacency" for n in notes)
    skipped_010 = next(
        r for r in out["layups"] if r.get("target_segment_id") == "seg_010"
    )
    assert skipped_010.get("skip") is True


def test_generic_clone_adjacent_layup_still_skips(monkeypatch) -> None:
    from interview_mux.nugget_layup import apply_clone_voice_adjacency_skips
    from interview_mux.run_context import RunContext

    ctx = RunContext("exec_clone_skip_generic", create=True)
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_010", "seg_012"]},
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                _seg("seg_010", "spk_host", "Host question."),
                _seg("seg_012", "spk_guest", "Guest answer.", start_ms=4000),
            ]
        },
    )
    monkeypatch.setattr(
        "interview_mux.source_topology.pickup_eligible_speaker_id",
        lambda _ctx: "spk_host",
    )
    plan = {
        "ordered_segment_ids": ["seg_010", "seg_012"],
        "layups": [
            {
                "target_segment_id": "seg_010",
                "line_id": "vo_layup_seg_010",
                "text": "What should we listen for next?",
                "nugget_ids": [],
                "skip": False,
                "target_beat": "Host question",
                "listener_need_entering_T": "Need a hinge.",
                "forward_unlock": "What should we listen for next?",
                "setup_from_nuggets": "",
            }
        ],
    }
    out, notes = apply_clone_voice_adjacency_skips(ctx, plan)
    row = next(r for r in out["layups"] if r.get("line_id") == "vo_layup_seg_010")
    assert row.get("skip") is True
    assert row.get("skip_reason_code") == "clone_voice_adjacency"
    assert any(n.get("action") == "skip_clone_voice_adjacency" for n in notes)


def test_nugget_clone_adjacent_merges_into_existing_guest_layup(monkeypatch) -> None:
    from interview_mux.nugget_layup import apply_clone_voice_adjacency_skips
    from interview_mux.run_context import RunContext

    ctx = RunContext("exec_clone_merge_012", create=True)
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_010", "seg_012"]},
    )
    ctx.write_json(
        "segments/manifest.json",
        {
            "segments": [
                _seg("seg_010", "spk_host", "Host question."),
                _seg("seg_012", "spk_guest", "Guest answer.", start_ms=4000),
            ]
        },
    )
    ctx.write_json(
        "understanding/nugget_corpus.json",
        {
            "nuggets": [
                {
                    "nugget_id": "nug_cell",
                    "text_claim": "Cell biopsy is next-generation liquid biopsy.",
                    "evidence_quote": "next-generation liquid biopsy",
                    "salience": "high",
                    "in_selection": True,
                }
            ]
        },
    )
    monkeypatch.setattr(
        "interview_mux.source_topology.pickup_eligible_speaker_id",
        lambda _ctx: "spk_host",
    )
    plan = {
        "ordered_segment_ids": ["seg_010", "seg_012"],
        "layups": [
            {
                "target_segment_id": "seg_010",
                "line_id": "vo_layup_seg_010",
                "text": (
                    "Cell biopsy is next-generation liquid biopsy. "
                    "What should we listen for next?"
                ),
                "nugget_ids": ["nug_cell"],
                "skip": False,
                "setup_from_nuggets": "Cell biopsy is next-generation liquid biopsy.",
                "target_beat": "Host question",
                "listener_need_entering_T": "Need the definition.",
                "forward_unlock": "What should we listen for next?",
            },
            {
                "target_segment_id": "seg_012",
                "line_id": "vo_layup_seg_012",
                "text": (
                    "Circulating tumour cells are vanishingly rare. "
                    "How did that change the diagnostic path?"
                ),
                "nugget_ids": ["nug_ctc"],
                "skip": False,
                "setup_from_nuggets": "Circulating tumour cells are vanishingly rare.",
                "target_beat": "Guest answer",
                "listener_need_entering_T": "Need rarity.",
                "forward_unlock": "How did that change the diagnostic path?",
            },
        ],
    }
    out, notes = apply_clone_voice_adjacency_skips(ctx, plan)
    guest = next(r for r in out["layups"] if r.get("line_id") == "vo_layup_seg_012")
    host = next(r for r in out["layups"] if r.get("target_segment_id") == "seg_010")
    assert host.get("skip") is True
    assert host.get("skip_reason_code") == "merged_clone_adjacency"
    assert "nug_cell" in (guest.get("nugget_ids") or [])
    assert "cell biopsy" in str(guest.get("text") or "").lower()
    assert any(n.get("action") == "merge_clone_voice_adjacency" for n in notes)

