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


def test_junction_precedes_when_assembly_missing(tmp_path, monkeypatch):
    """Cascade: missing assembly.wav must not gate junction when EDL exists.

    exec_13159: mix⇄junction deadlock on assembly_not_rendered / Missing assembly.wav.
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
        "interview_mux.junction_snip_qa.live_incomplete_cut_critical_findings",
        lambda _ctx: [],
    )
    monkeypatch.setattr(
        "interview_mux.air_order.mix_stale_versus_live",
        lambda _ctx: True,
    )
    assert junction_recut_precedes_mix(ctx) is True
