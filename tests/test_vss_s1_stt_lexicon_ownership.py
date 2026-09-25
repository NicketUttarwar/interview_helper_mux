"""VSS S1: stt_lexicon ALLOW re-homed off vernacular_segment_sanitize.

Operational write_mode still lets any stage persist (telemetry-style), but
catalog producers / heal_pin / authoritative must name the real writers —
not vernacular (ghost ALLOW peeled).
"""

from __future__ import annotations

from interview_mux.artifact_ownership import heal_pin_for, row_for_path, write_permitted

_ISLANDS = "analysis/stt_lexicon_islands.json"
_BOOSTS = "analysis/stt_lexicon_island_boosts.json"
_VSS = "vernacular_segment_sanitize"
_FMR = "full_master_ranking"
_LCI = "low_conf_island_scan"


def test_s1_stt_lexicon_islands_owned_by_fmr() -> None:
    row = row_for_path(_ISLANDS)
    assert row is not None
    assert row.producers == (_FMR,)
    assert row.authoritative == _FMR
    assert row.heal_pin == _FMR
    assert _VSS not in row.producers
    assert heal_pin_for(_ISLANDS) == _FMR

    ok_fmr, reason_fmr = write_permitted(None, _ISLANDS, _FMR, role="producer", verb="persist")
    assert ok_fmr is True, reason_fmr


def test_s1_stt_lexicon_boosts_co_owned_by_low_conf_and_fmr() -> None:
    row = row_for_path(_BOOSTS)
    assert row is not None
    assert row.producers == (_LCI, _FMR)
    assert row.authoritative == _FMR
    assert row.heal_pin == _FMR
    assert _VSS not in row.producers
    assert heal_pin_for(_BOOSTS) == _FMR

    for stage in (_LCI, _FMR):
        ok, reason = write_permitted(None, _BOOSTS, stage, role="producer", verb="persist")
        assert ok is True, f"{stage}: {reason}"
