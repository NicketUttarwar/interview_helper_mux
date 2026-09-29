"""Resume shape of exec_055: assembly on disk, EDL newer, a recut owed (ISSUES 76).

Every gate junction passes at start must open when the ordering authority
seats it ahead of mix. Each gate used to re-decide this privately.
"""

from __future__ import annotations

import pytest

from run_fixtures import isolated_run_ctx


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("MUX_FORENSICS", "0")
    c = isolated_run_ctx(tmp_path, "junction_resume_matrix")
    c.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001"], "air_order_generation": 1},
        skip_handoff=True,
    )
    c.write_json(
        "master/edl.json",
        {
            "version": 1,
            "clips": [],
            "ordered_segment_ids": ["seg_001"],
            "air_order_generation": 2,
            "timeline_duration_ms": 1000,
        },
        skip_handoff=True,
    )
    path = c.path("master", "assembly.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + b"\x00" * 64)
    monkeypatch.setattr("interview_mux.order_hash.order_drift_heal_action", lambda *a, **k: "ok")
    monkeypatch.setattr("interview_mux.homunculus.agenda.assembly_stale_versus_edl", lambda c: True)
    return c


def _owed(monkeypatch, owed: bool) -> None:
    monkeypatch.setattr(
        "interview_mux.ordering_authority.ordering_exempt",
        lambda c, s, p: "junction_recut_precedes_mix" if owed else None,
    )


def test_commitment_check_yields_to_the_ordering_authority(ctx, monkeypatch) -> None:
    from interview_mux.air_order import assert_consumer

    _owed(monkeypatch, True)
    assert_consumer(ctx, "junction_snip_qa")  # no SystemExit
    with pytest.raises(SystemExit, match="assembly_not_rendered_from_current_edl"):
        assert_consumer(ctx, "master_finalize")


def test_commitment_check_still_holds_junction_without_an_owed_recut(ctx, monkeypatch) -> None:
    """A5 unchanged: a stale assembly with nothing owed verifies and refuses."""
    from interview_mux.air_order import assert_consumer

    _owed(monkeypatch, False)
    with pytest.raises(SystemExit, match="assembly_not_rendered_from_current_edl"):
        assert_consumer(ctx, "junction_snip_qa")


def test_stale_blocker_yields_to_the_ordering_authority(ctx, monkeypatch) -> None:
    from interview_mux import delivery_guardrails as dg

    _owed(monkeypatch, True)
    assert dg.upstream_stale_blockers(ctx, "junction_snip_qa") == []
    _owed(monkeypatch, False)
    assert "assembly_stale_versus_edl" in dg.upstream_stale_blockers(ctx, "junction_snip_qa")
