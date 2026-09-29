"""Mix seat survives an EDL rewrite with unchanged content; one auto-promote per run (ISSUES 52)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from interview_mux.air_order import mix_wav_fresh_versus_edl
from interview_mux.run_context import RunContext
from interview_mux.timeline_optimizer.daemon import auto_promote_allowed


def _ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))
    ctx = RunContext("exec_mix_seat", create=True)
    asm = ctx.final_path("master", "assembly.wav")
    asm.parent.mkdir(parents=True, exist_ok=True)
    asm.write_bytes(b"RIFF")
    edl = ctx.final_path("master", "edl.json")
    edl.write_text("{}", encoding="utf-8")
    old = time.time() - 600
    os.utime(asm, (old, old))
    return ctx


CLIPS = [
    {"type": "speech", "segment_id": "seg_001", "line_id": None},
    {"type": "speech", "segment_id": "seg_006", "line_id": None},
]


def _ledger(ctx: RunContext, clips) -> None:
    ctx.final_path("master", "render_ledger.json").write_text(
        json.dumps({"version": 1, "clips": clips}), encoding="utf-8"
    )


def test_newer_edl_with_committed_render_is_still_fresh(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.final_path("master", "edl.json").write_text(json.dumps({"clips": CLIPS}), encoding="utf-8")
    _ledger(ctx, CLIPS)
    monkeypatch.setattr(
        "interview_mux.seam_autopsy.verify_commitment", lambda c, *a, **k: {"status": "committed"}
    )
    assert mix_wav_fresh_versus_edl(ctx) is True


def test_newer_edl_with_recut_clips_is_stale(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.final_path("master", "edl.json").write_text(json.dumps({"clips": CLIPS[:1]}), encoding="utf-8")
    _ledger(ctx, CLIPS)
    monkeypatch.setattr(
        "interview_mux.seam_autopsy.verify_commitment", lambda c, *a, **k: {"status": "committed"}
    )
    assert mix_wav_fresh_versus_edl(ctx) is False


def test_newer_edl_without_ledger_is_stale(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.final_path("master", "edl.json").write_text(json.dumps({"clips": CLIPS}), encoding="utf-8")
    monkeypatch.setattr(
        "interview_mux.seam_autopsy.verify_commitment", lambda c, *a, **k: {"status": "committed"}
    )
    assert mix_wav_fresh_versus_edl(ctx) is False


def test_newer_edl_with_diverged_render_is_stale(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.final_path("master", "edl.json").write_text(json.dumps({"clips": CLIPS}), encoding="utf-8")
    _ledger(ctx, CLIPS)
    monkeypatch.setattr(
        "interview_mux.seam_autopsy.verify_commitment", lambda c, *a, **k: {"status": "diverged"}
    )
    assert mix_wav_fresh_versus_edl(ctx) is False


def test_mtime_seat_needs_no_commitment_check(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch)
    asm = ctx.final_path("master", "assembly.wav")
    now = time.time() + 5
    os.utime(asm, (now, now))
    monkeypatch.setattr(
        "interview_mux.seam_autopsy.verify_commitment",
        lambda c, *a, **k: (_ for _ in ()).throw(AssertionError("not consulted")),
    )
    assert mix_wav_fresh_versus_edl(ctx) is True


def test_auto_promote_is_attempted_once() -> None:
    assert auto_promote_allowed({}) is True
    assert auto_promote_allowed({"auto_promoted_once": True}) is False
    assert auto_promote_allowed({"auto_promote_attempted": True}) is False
    assert auto_promote_allowed(None) is True
