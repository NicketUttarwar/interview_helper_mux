"""EDL build and QC share one completeness test; tape trail-offs warn (ISSUES 59)."""

from __future__ import annotations

from interview_mux.edl_narrative_qc import _hinge_reachable, first_qc_hinge_between


def _w(text, start, end):
    return {"text": text, "start_ms": start, "end_ms": end}


# exec_052 seg_060: trails off into a 22 s silence, never finishing.
TRAIL = [
    _w("this", 3161670, 3161810), _w("is", 3161810, 3161950), _w("going", 3161950, 3162030),
    _w("to", 3162030, 3162100), _w("be", 3162100, 3162250), _w("more", 3163300, 3163670),
    _w("right", 3163700, 3164010), _w("because", 3164050, 3164310), _w("they're", 3164350, 3164510),
    _w("going", 3164520, 3164590), _w("to", 3164600, 3164630), _w("be", 3164640, 3164750),
    _w("any", 3186700, 3186870),
]


def test_trail_off_has_no_reachable_hinge() -> None:
    speech = {"source_start_ms": 3148170, "source_end_ms": 3162250}
    assert _hinge_reachable(speech, TRAIL, 3162250) is False


def test_a_finished_sentence_is_found_by_the_shared_predicate() -> None:
    words = TRAIL[:5] + [
        _w("important.", 3162400, 3162900),
        _w("So", 3165000, 3165200),
        _w("next", 3165250, 3165500),
    ]
    found = first_qc_hinge_between(words, 3162250, 3174250)
    assert found == 3162900
    speech = {"source_start_ms": 3148170, "source_end_ms": 3162250}
    assert _hinge_reachable(speech, words, 3162250) is True
