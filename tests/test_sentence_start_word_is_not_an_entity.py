"""An ordinary word opening a sentence is not an unsupported entity (ISSUES 155).

exec_014: post-master quality refused the finished master on
"spoken_unsupported_entity:Reaching" for "Reaching routine care raises two
practical tests..." in vo_layup_seg_017.
"""

from __future__ import annotations

from interview_mux.spoken_copy_guard import spoken_copy_violations

EV = {"target_excerpt": "payers and companion diagnostics", "strict_grounding": True}


def _entity(text: str) -> list[str]:
    return [v for v in spoken_copy_violations(text, evidence=EV) if v.startswith("spoken_unsupported_entity")]


def test_common_word_sentence_start_passes() -> None:
    assert _entity("Reaching routine care raises two practical tests. Why does that matter?") == []


def test_invented_names_are_still_refused() -> None:
    assert _entity("Zorblat argues the test is cheap. Why?")
    assert _entity("The test, says Zorblat, is cheap. Why?")
