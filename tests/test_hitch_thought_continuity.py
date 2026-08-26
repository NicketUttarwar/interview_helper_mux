"""Hitch thought-complete closes + same-answer continuity (listener seams)."""

from __future__ import annotations

from interview_mux.chapter_close_hitch import (
    compute_recut_windows,
    last_listen_complete_end_ms,
)
from interview_mux.cut_edge_refine import lift_end_for_outgoing_last_word
from interview_mux.gap_vo_prior_context import (
    end_is_hard_hang,
    ends_hanging_setup,
    ends_setup_ignoring_terminal_punct,
    same_answer_continues,
)
from interview_mux.ideal_cuts import resolve_keeper_air_bounds
from interview_mux.stages.assembly import build_flow1_edl


def _tok(start: int, end: int, text: str, spk: str = "spk_0") -> dict:
    return {
        "start_ms": start,
        "end_ms": end,
        "text": text,
        "word": text,
        "speaker_id": spk,
    }


def test_expanded_incomplete_tails_include_modals_and_prepositions() -> None:
    assert ends_hanging_setup("we still need to")
    assert ends_hanging_setup("patients are interested in")
    assert ends_hanging_setup("the therapy will")
    assert ends_hanging_setup("looking at")
    assert not ends_hanging_setup("that is the whole story.")


def test_soft_setup_ignores_terminal_period() -> None:
    assert ends_setup_ignoring_terminal_punct(
        "physicians and patients are always very interested in understanding what is happening."
    )
    assert not ends_setup_ignoring_terminal_punct(
        "I think those are some of the advantages that the payers will take into account."
    )


def test_same_answer_happening_regulators_soft_hang() -> None:
    """Published ~39:08 class: period on setup, payoff continues after short pause."""
    words = [
        _tok(3367370, 3367670, "The"),
        _tok(3367670, 3367810, "way"),
        _tok(3367810, 3367930, "I"),
        _tok(3367930, 3368030, "think"),
        _tok(3368030, 3368210, "was"),
        _tok(3368210, 3368430, "that"),
        _tok(3368430, 3368650, "the"),
        _tok(3368650, 3369090, "physicians"),
        _tok(3369090, 3369350, "and"),
        _tok(3369350, 3369590, "patients"),
        _tok(3369590, 3369770, "are"),
        _tok(3369770, 3370070, "always"),
        _tok(3370070, 3370350, "very"),
        _tok(3370350, 3370730, "interested"),
        _tok(3370730, 3371070, "in"),
        _tok(3371070, 3371510, "understanding"),
        _tok(3371510, 3371810, "what"),
        _tok(3371810, 3372110, "is"),
        _tok(3372110, 3372530, "happening."),
        _tok(3374470, 3374870, "Regulators,", spk="spk_0"),
        _tok(3374870, 3375270, "it's"),
        _tok(3375270, 3375830, "going"),
        _tok(3375830, 3376030, "to"),
        _tok(3376030, 3376250, "be"),
        _tok(3376250, 3376550, "more"),
        _tok(3376550, 3376890, "about,"),
    ]
    left_end = 3372530
    right_start = 3374470
    assert same_answer_continues(words, left_end, right_start)
    # Soft hang must not be chosen as last listen-complete close.
    hinge = last_listen_complete_end_ms(
        words, start_ms=3367370, bound_end_ms=3378000, min_keep_ms=500
    )
    assert hinge is None or hinge > left_end


def test_hard_hang_scan_and_then_radiology() -> None:
    """Published ~2:36 class: cut on 'and' dropping 'then'."""
    words = [
        _tok(0, 200, "You"),
        _tok(200, 400, "do"),
        _tok(400, 600, "the"),
        _tok(600, 1000, "radiologic"),
        _tok(1000, 1300, "scan"),
        _tok(1300, 1600, "and"),
        _tok(1600, 1900, "then"),
        _tok(1900, 2400, "radiology"),
        _tok(2400, 2800, "finds"),
        _tok(2800, 3400, "something."),
        _tok(4000, 4400, "Next"),
        _tok(4400, 5000, "keeper."),
    ]
    assert end_is_hard_hang(words, 1600)
    lifted, used = lift_end_for_outgoing_last_word(
        1500,
        words,
        clip_start_ms=0,
        next_keeper_start_ms=1900,
        proposed_end_ms=1500,
    )
    assert used
    assert lifted >= 3400
    assert not end_is_hard_hang(words, lifted)

    _s, e = resolve_keeper_air_bounds(
        source_start_ms=0,
        source_end_ms=1900,
        words=words,
        min_keep_ms=400,
        next_keeper_start_ms=1900,
    )
    assert e >= 2800
    last = [
        str(w["text"]).lower().rstrip(".,!?")
        for w in words
        if int(w["end_ms"]) <= e
    ][-1]
    assert last != "and"


def test_hitch_recut_does_not_split_happening_regulators_across_chapters() -> None:
    words = [
        _tok(0, 200, "physicians"),
        _tok(200, 400, "and"),
        _tok(400, 700, "patients"),
        _tok(700, 900, "are"),
        _tok(900, 1200, "interested"),
        _tok(1200, 1400, "in"),
        _tok(1400, 1600, "understanding"),
        _tok(1600, 1800, "what"),
        _tok(1800, 2000, "is"),
        _tok(2000, 2400, "happening."),
        _tok(2900, 3400, "Regulators,"),
        _tok(3400, 3800, "it's"),
        _tok(3800, 4200, "about"),
        _tok(4200, 4800, "insurers."),
    ]
    keepers = [
        {
            "segment_id": "seg_050",
            "start_ms": 0,
            "end_ms": 2400,
            "speaker_id": "spk_0",
        },
        {
            "segment_id": "seg_051",
            "start_ms": 2900,
            "end_ms": 4800,
            "speaker_id": "spk_0",
        },
    ]
    plan = {
        "chapters": [
            {"chapter_id": "ch_01", "title": "What is happening", "segment_ids": ["seg_050"]},
            {"chapter_id": "ch_02", "title": "Regulators", "segment_ids": ["seg_051"]},
        ]
    }
    windows = compute_recut_windows(
        keepers=keepers,
        plan=plan,
        words=words,
        min_keep_ms=400,
        extend_hanging_horizon_ms=8_000,
    )
    assert windows[0]["end_ms"] > 2400
    assert windows[0]["end_ms"] >= 3400
    assert int(windows[1]["start_ms"]) >= int(windows[0]["end_ms"])


def test_acoustic_refine_cannot_undo_keep_merge() -> None:
    from interview_mux.chapter_close_hitch import reapply_same_speaker_keep_merge

    words = [
        _tok(0, 2000, "happening."),
        _tok(2500, 4000, "Regulators,"),
        _tok(4000, 4800, "insurers."),
    ]
    windows = [
        {
            "segment_id": "seg_050",
            "start_ms": 0,
            "end_ms": 2000,
            "speaker_id": "spk_0",
            "keep_merge": True,
        },
        {
            "segment_id": "seg_051",
            "start_ms": 2500,
            "end_ms": 4800,
            "speaker_id": "spk_0",
        },
    ]
    out = reapply_same_speaker_keep_merge(windows, words, max_cut_ms=180_000)
    assert out[0]["end_ms"] >= 2500
    assert out[0]["keep_merge"] is True


def test_hitch_recut_extends_through_and_hang() -> None:
    words = [
        _tok(0, 200, "You"),
        _tok(200, 400, "do"),
        _tok(400, 600, "the"),
        _tok(600, 1000, "radiologic"),
        _tok(1000, 1300, "scan"),
        _tok(1300, 1600, "and"),
        _tok(1600, 1900, "then"),
        _tok(1900, 2400, "radiology"),
        _tok(2400, 2800, "finds"),
        _tok(2800, 3400, "something."),
        _tok(4000, 4400, "Next"),
        _tok(4400, 5000, "keeper."),
    ]
    keepers = [
        {"segment_id": "seg_008", "start_ms": 0, "end_ms": 1600},
        {"segment_id": "seg_009", "start_ms": 1900, "end_ms": 5000},
    ]
    plan = {
        "chapters": [
            {
                "chapter_id": "ch_01",
                "title": "Clinical",
                "segment_ids": ["seg_008", "seg_009"],
            }
        ]
    }
    windows = compute_recut_windows(
        keepers=keepers,
        plan=plan,
        words=words,
        min_keep_ms=400,
        extend_hanging_horizon_ms=8_000,
    )
    assert windows[0]["end_ms"] >= 2800
    assert not end_is_hard_hang(words, int(windows[0]["end_ms"]))


def test_assembly_skips_chapter_hinge_for_same_answer_soft_hang() -> None:
    words = [
        _tok(0, 200, "patients"),
        _tok(200, 400, "are"),
        _tok(400, 700, "interested"),
        _tok(700, 900, "in"),
        _tok(900, 1200, "understanding"),
        _tok(1200, 1400, "what"),
        _tok(1400, 1600, "is"),
        _tok(1600, 2000, "happening."),
        _tok(2500, 3000, "Regulators,"),
        _tok(3000, 3400, "it's"),
        _tok(3400, 3800, "about"),
        _tok(3800, 4200, "insurers."),
    ]
    segs = {
        "seg_050": {
            "segment_id": "seg_050",
            "speaker_id": "spk_0",
            "start_ms": 0,
            "end_ms": 2000,
        },
        "seg_051a": {
            "segment_id": "seg_051a",
            "speaker_id": "spk_0",
            "start_ms": 2500,
            "end_ms": 4200,
        },
    }
    edl = build_flow1_edl(
        selection={"ordered_segment_ids": ["seg_050", "seg_051a"]},
        segments_by_id=segs,
        transitions={"transitions": []},
        transcript_words=words,
    )
    hinges = [
        c
        for c in edl["clips"]
        if c.get("type") == "silence"
        and c.get("air_kind") == "chapter_hinge"
        and int(c.get("duration_ms") or 0) > 0
    ]
    assert not hinges


def test_assembly_still_hitches_true_chapter_jump() -> None:
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
        if c.get("air_kind") == "chapter_hinge" and int(c.get("duration_ms") or 0) > 0
    ]
    assert hitch
    assert hitch[0].get("required_seam_hitch") is True
