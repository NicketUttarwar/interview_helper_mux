"""Planned stingers and the closing outro reach the mix (ISSUES 165).

exec_017: (1) the policy's stinger rate 0.4/min was int()-truncated to 0, so
the mix dropped all 10 planned stingers ("stinger cap reached (0/timeline)");
(2) the cold-open cue was anchored after the last segment by the anchor
fallback, and the bookend dedupe treated it and the outro as duplicates, so
the episode had no closing music.
"""

from __future__ import annotations

from interview_mux.music_lane import collapse_duplicate_music_cues


def test_cold_open_and_outro_on_one_anchor_are_not_duplicates() -> None:
    assets = {
        "motif": {"asset_id": "motif", "role": "theme_cold_open"},
        "close": {"asset_id": "close", "role": "theme_outro"},
    }
    cues = [
        {"cue_id": "open", "asset_id": "motif", "role": "theme_cold_open", "placement": "after_segment", "segment_id": "seg_025h"},
        {"cue_id": "close", "asset_id": "close", "role": "theme_outro", "placement": "after_segment", "segment_id": "seg_025h"},
    ]
    out, actions = collapse_duplicate_music_cues(cues, assets)
    assert [c["cue_id"] for c in out] == ["open", "close"]
    assert actions == []


def test_two_outros_on_one_anchor_still_collapse() -> None:
    assets = {"close": {"asset_id": "close", "role": "theme_outro"}}
    cues = [
        {"cue_id": "a", "asset_id": "close", "role": "theme_outro", "placement": "after_segment", "segment_id": "seg_9"},
        {"cue_id": "b", "asset_id": "close", "role": "theme_outro", "placement": "after_segment", "segment_id": "seg_9"},
    ]
    out, _ = collapse_duplicate_music_cues(cues, assets)
    assert [c["cue_id"] for c in out] == ["a"]


def test_fractional_stinger_rate_is_not_truncated_by_the_profile() -> None:
    import inspect

    from interview_mux import acoustic_profile, sound_design

    src = inspect.getsource(sound_design.flow1_overlays_from_sdp)
    assert 'int(contract.get("stinger_max_per_minute"' not in src
    assert 'float(raw["stinger_max_per_minute"])' in inspect.getsource(acoustic_profile)


