"""The stock seed pool and the spoken-copy guard agree; an unspeakable seat is released (ISSUES 123)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.gap_vo_prior_context import _COURTESY_SEED_POOL, courtesy_seed_text
from interview_mux.spoken_copy_guard import guard_spoken_copy, spoken_copy_violations


def test_every_pool_phrase_passes_the_guard_bare_and_required() -> None:
    for phrase in _COURTESY_SEED_POOL:
        assert spoken_copy_violations(phrase, evidence=None, seen_texts=None) == [], phrase
        decision = guard_spoken_copy(phrase, evidence={}, required=True, purpose="pool")
        assert decision["action"] != "block", (phrase, decision)


def test_the_former_filler_phrases_are_gone_and_still_banned() -> None:
    banned = (
        "What tension carries into what comes next?",
        "How should we hear what follows differently?",
        "How does that landing set up what follows?",
    )
    for phrase in banned:
        assert phrase not in _COURTESY_SEED_POOL
        assert "spoken_generic_filler" in spoken_copy_violations(phrase, evidence=None, seen_texts=None)


def test_a_seed_is_never_the_phrase_the_guard_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    import interview_mux.gap_vo_prior_context as m

    # Force the hash to pick a phrase the guard will refuse in this context.
    monkeypatch.setattr(m, "_COURTESY_SEED_POOL", ("What tension carries into what comes next?",) + tuple(_COURTESY_SEED_POOL))
    monkeypatch.setattr(m.zlib, "crc32", lambda b: 0)
    text = courtesy_seed_text(None, category="story_bridge", target_segment_id="seg_019")
    assert text != "What tension carries into what comes next?"
    assert spoken_copy_violations(text, evidence=None, seen_texts=None) == []


def test_bind_heal_releases_a_seat_whose_copy_the_guard_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from interview_mux import vo_bind_authority as vba

    seen: dict = {}
    monkeypatch.setattr(vba, "_copy_unspeakable", lambda c, row: True)
    monkeypatch.setattr(vba, "_omit_bind_failed_line", lambda c, lid, row: seen.setdefault("lid", lid) or True)
    monkeypatch.setattr(vba, "_line_wav_present", lambda c, row: False)
    monkeypatch.setattr(vba, "_try_resynth_seated_line", lambda c, row: False)
    monkeypatch.setattr(vba, "_gap_lines_by_id", lambda c: {"vo_seed_seg_019": {"line_id": "vo_seed_seg_019", "text": "What tension carries into what comes next?"}})
    monkeypatch.setattr("interview_mux.stage_input_checks.compact_vo_coverage_stale_or_missing", lambda c: ["vo_seed_seg_019"])
    monkeypatch.setattr("interview_mux.write_staging.discard_non_owner_pending_vo_pickup", lambda c: [])
    monkeypatch.setattr("interview_mux.write_staging.promote_owner_vo_pickup", lambda c: [])

    class _Ctx:
        run_dir = tmp_path

        def log(self, *a, **k):
            pass

    out = vba.heal_seated_bind_mismatch(_Ctx(), attempt_synth=True)
    assert out["omitted"] == ["vo_seed_seg_019"]
    assert out["refused"] == []
    assert seen["lid"] == "vo_seed_seg_019"
