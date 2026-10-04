"""CTA-wording reuse counts only wording that does not also air as story (ISSUES 157)."""

from __future__ import annotations

from interview_mux import media_ip_cta as m

PARENT = (
    "The Life Sciences DNA podcast is sponsored by Agilisium Labs, a collaborative space "
    "where Agilisium works with its clients. Blood tests may reveal molecular changes before "
    "imaging does, and capturing a circulating tumour cell alive changes the analysis."
)
STORY = "Blood tests may reveal molecular changes before imaging does when a circulating tumour cell is captured alive."
LAYUP = "Blood tests may reveal molecular changes before imaging does. What changes when a circulating tumour cell is captured alive?"
SPONSOR_COPY = "This podcast is sponsored by Agilisium Labs, where Agilisium works with its clients."


def _patch(monkeypatch, story_tokens: set[str]) -> None:
    monkeypatch.setattr(m, "never_touch_texts", lambda c: [PARENT])
    monkeypatch.setattr(m, "_on_air_story_tokens", lambda c: story_tokens)


def test_story_line_on_the_parents_topic_is_not_cta_reuse(monkeypatch) -> None:
    _patch(monkeypatch, m._tokens(STORY))
    assert not m.air_overlaps_never_touch(object(), LAYUP)


def test_sponsor_wording_is_still_refused(monkeypatch) -> None:
    _patch(monkeypatch, m._tokens(STORY))
    assert m.air_overlaps_never_touch(object(), SPONSOR_COPY)
