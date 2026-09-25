"""End-B: owner flush/orphan must not clobber sha-bound VO (MUX_FORENSICS=0)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_mux.heal_routing import PLAYBOOK_REGISTRY, classify_heal_error
from interview_mux.run_context import RunContext
from interview_mux.spoken_copy_guard import script_hash
from interview_mux.vo_synthesis_audit import wav_content_sha256
from interview_mux.write_staging import (
    flush_stage_writes,
    promote_owner_vo_pickup,
)
from run_fixtures import isolated_run_ctx, write_fixture_json


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    monkeypatch.setattr(
        "interview_mux.write_staging.write_approval_enabled", lambda: False
    )
    return isolated_run_ctx(tmp_path, "endb_flush_bind")


def _plant_audited_and_stale(ctx: RunContext, *, lid: str = "vo_layup_seg_020") -> Path:
    text = "Why does counting cells leave clinicians uncertain?"
    write_fixture_json(
        ctx,
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                {
                    "line_id": lid,
                    "text": text,
                    "targets_segment_id": "seg_020",
                    "placement": "before",
                    "delivery": "synthesize",
                }
            ]
        },
    )
    syn = ctx.run_dir / "vo_pickup" / "synthesized"
    syn.mkdir(parents=True)
    good = syn / f"{lid}.wav"
    good.write_bytes(b"RIFF" + b"\x00" * 100 + b"GOOD_AUDITED_TAKE")
    want = wav_content_sha256(good)
    report = {
        "version": 1,
        "entries": [
            {
                "line_id": lid,
                "script_hash": script_hash(text),
                "context_hash": "def",
                "wav_sha256": want,
                "backend": "chatterbox",
                "qc_pass": True,
                "out_wav": f"vo_pickup/synthesized/{lid}.wav",
            }
        ],
    }
    (ctx.run_dir / "vo_pickup" / "synthesis_report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    pending = (
        ctx.run_dir
        / ".pending_writes"
        / "vo_synthesize"
        / "vo_pickup"
        / "synthesized"
    )
    pending.mkdir(parents=True)
    stale = pending / f"{lid}.wav"
    stale.write_bytes(b"RIFF" + b"\x00" * 100 + b"STALE_PENDING_BYTES!!")
    assert wav_content_sha256(stale) != want
    return good


def test_endb_flush_bypasses_stale_vo_skip(ctx: RunContext) -> None:
    lid = "vo_layup_seg_020"
    good = _plant_audited_and_stale(ctx, lid=lid)
    want = wav_content_sha256(good)
    rel = f"vo_pickup/synthesized/{lid}.wav"

    # promote_owner skips (existing partial) and discards pending.
    flushed_owner = promote_owner_vo_pickup(ctx)
    assert rel not in flushed_owner
    assert wav_content_sha256(good) == want
    assert good.read_bytes().endswith(b"GOOD_AUDITED_TAKE")
    pending = (
        ctx.run_dir
        / ".pending_writes"
        / "vo_synthesize"
        / "vo_pickup"
        / "synthesized"
        / f"{lid}.wav"
    )
    assert not pending.is_file()

    # Re-plant stale pending and assert flush cannot clobber either.
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_bytes(b"RIFF" + b"\x00" * 100 + b"STALE_PENDING_BYTES!!")
    flushed = flush_stage_writes(ctx, "vo_synthesize")
    assert rel not in flushed
    assert wav_content_sha256(good) == want
    assert good.read_bytes().endswith(b"GOOD_AUDITED_TAKE")
    assert not pending.is_file()


def test_endb_orphan_commit_skips_stale_vo(ctx: RunContext) -> None:
    lid = "vo_layup_seg_021"
    good = _plant_audited_and_stale(ctx, lid=lid)
    want = wav_content_sha256(good)
    rel = f"vo_pickup/synthesized/{lid}.wav"
    # Owner flush shares bind-skip; do not mark_done over pending vo_synthesize.json.
    flushed = flush_stage_writes(ctx, "vo_synthesize")
    assert rel not in flushed
    assert wav_content_sha256(good) == want
    assert good.read_bytes().endswith(b"GOOD_AUDITED_TAKE")


def test_endb_missing_g1_pickup_pins_vo_synthesize_not_edl() -> None:
    assert PLAYBOOK_REGISTRY["missing_g1_pickup"].resume_stage == "vo_synthesize"
    route = classify_heal_error(
        "G1 VO pickup missing for: vo_layup_seg_001",
        stage="edl",
    )
    assert route.from_stage == "vo_synthesize" or route.from_stage == "vo_line_adjudicate"
    assert route.from_stage not in {"edl", "mix", "master_finalize"}
