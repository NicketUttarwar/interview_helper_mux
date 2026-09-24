"""Cascade: critical incomplete repairs use non-low_gain remaster path."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def test_critical_repair_remaster_path_bypasses_low_gain(monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.junction_snip_qa import _budgeted_remaster_mix

    calls: list[str] = []

    def _fake_gate(ctx, *, intent, detail):
        calls.append(str(detail.get("path") or ""))
        return {"allow": False, "reason": "low_gain"}

    monkeypatch.setattr(
        "interview_mux.timeline_reopen_meta_gate.decide_timeline_reopen",
        _fake_gate,
    )
    class _Ctx:
        def log(self, *a, **k):
            return None

    # Cosmetics path refused by low_gain
    ok, used = _budgeted_remaster_mix(_Ctx(), path="repair")
    assert ok is False and used == 0
    # Critical path skips low_gain and would remaster — mock remaster+budget
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.junction_remaster_budget_ok",
        lambda _c: (True, 0),
    )
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.remaster_mix_only",
        lambda _c: None,
    )
    monkeypatch.setattr(
        "interview_mux.thrash_hardening.note_junction_remaster",
        lambda _c: None,
    )
    ok2, used2 = _budgeted_remaster_mix(_Ctx(), path="repair_incomplete_clause")
    assert ok2 is True and used2 == 1


def test_junction_does_not_precede_when_assembly_missing(tmp_path, monkeypatch):
    """Always-HAU: missing assembly.wav alone must not put junction ahead of mix.

    exec_13159 originally asserted the opposite to break mix⇄junction deadlock.
    Seat constitution flipped: mix mints the first heard assembly; junction
    precedes only for live incomplete cuts, remaster-in-flight, or existing
    stale assembly (see ``mix_junction_seat.junction_precedes_mix``).
    """
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.junction_snip_qa import junction_recut_precedes_mix
    from run_fixtures import isolated_run_ctx

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "jsq_assembly_gate")
    edl = ctx.path("master", "edl.json")
    edl.parent.mkdir(parents=True, exist_ok=True)
    edl.write_text('{"version":1,"timeline_duration_ms":1,"clips":[]}\n')
    preview = ctx.path("master", "assembly_preview.wav")
    preview.write_bytes(b"RIFF....WAVEfmt ")
    monkeypatch.setattr(
        "interview_mux.mix_junction_seat.live_incomplete_cuts",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.mix_junction_seat.assembly_stale",
        lambda _ctx: True,
    )
    # Preview only — no master/assembly.wav. Stale probe must not invent precede.
    assert not ctx.artifact_exists("master/assembly.wav")
    assert junction_recut_precedes_mix(ctx) is False


def test_junction_precedes_when_existing_assembly_is_stale(tmp_path, monkeypatch):
    """Stale seated assembly still requires junction ahead of mix (13159 deadlock class)."""
    import os

    os.environ["MUX_FORENSICS"] = "0"
    from interview_mux.junction_snip_qa import junction_recut_precedes_mix
    from run_fixtures import isolated_run_ctx

    monkeypatch.setenv("MUX_ASSETS_ROOT", str(tmp_path))
    ctx = isolated_run_ctx(tmp_path, "jsq_assembly_stale")
    edl = ctx.path("master", "edl.json")
    edl.parent.mkdir(parents=True, exist_ok=True)
    edl.write_text('{"version":1,"timeline_duration_ms":1,"clips":[]}\n')
    assembly = ctx.path("master", "assembly.wav")
    assembly.write_bytes(b"RIFF....WAVEfmt ")
    monkeypatch.setattr(
        "interview_mux.mix_junction_seat.live_incomplete_cuts",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.mix_junction_seat.remaster_in_flight",
        lambda _ctx: False,
    )
    monkeypatch.setattr(
        "interview_mux.mix_junction_seat.assembly_stale",
        lambda _ctx: True,
    )
    assert junction_recut_precedes_mix(ctx) is True
