"""i12: seated air-script VO must not be purged by omit-ledger EDL reconcile.

exec_13177: after vo_synthesize wrote vo_layup_seg_003c, reconcile_edl_with_omit_ledger
purged the take because a stale layup_skip omit entry remained — then assembly
failed VO coverage and vo_fail_open_not_success refused flush.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.omit_ledger import (
    empty_omit_ledger,
    mint_entry,
    reconcile_edl_with_omit_ledger,
    write_omit_ledger,
)
from interview_mux.run_context import RunContext
from interview_mux.vo_synthesis_audit import record_synthesis, synthesis_entry_for_line
from run_fixtures import isolated_run_ctx, write_fixture_vo_wav


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunContext:
    monkeypatch.setenv("MUX_FORENSICS", "0")
    return isolated_run_ctx(tmp_path, "i12_seated_omit_purge")


def test_reconcile_keeps_seated_omitted_ledger_vo(ctx: RunContext) -> None:
    ledger = empty_omit_ledger()
    ledger["entries"] = [
        mint_entry(
            kind="layup_skip",
            subject_id="vo_layup_seg_003c",
            target_segment_id="seg_003",
            decision="omit",
            reason_code="spoken_copy_unhealable",
            owner_stage="nugget_layup_compose",
            compensating_path="omit_unsafe_spoken_copy",
            seq=1,
        )
    ]
    ledger["summary"] = {
        "active_count": 1,
        "by_kind": {"layup_skip": 1},
        "compensated_count": 1,
        "unresolved_high_salience": 0,
    }
    write_omit_ledger(ctx, ledger)

    wav = ctx.final_path("vo_pickup", "synthesized", "vo_layup_seg_003c.wav")
    write_fixture_vo_wav(wav)
    record_synthesis(
        ctx,
        {
            "line_id": "vo_layup_seg_003c",
            "text": "Seated hosted layup that must survive omit reconcile.",
            "targets_segment_id": "seg_003",
            "placement": "before",
            "delivery": "synthesize",
        },
        backend="mlx_audio",
        out_wav=wav,
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": ["vo_layup_seg_003c", "vo_layup_seg_037"],
                    "omitted_line_ids": [],
                    "orientation_id": None,
                }
            }
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_003", "seg_037"],
            "timeline_duration_ms": 20_000,
            "clips": [
                {
                    "type": "vo_pickup",
                    "line_id": "vo_layup_seg_003c",
                    "targets_segment_id": "seg_003",
                    "placement": "before",
                    "timeline_start_ms": 0,
                    "duration_ms": 8_000,
                    "source_path": "vo_pickup/synthesized/vo_layup_seg_003c.wav",
                },
                {
                    "type": "speech",
                    "segment_id": "seg_003",
                    "timeline_start_ms": 8_000,
                    "duration_ms": 12_000,
                    "source_start_ms": 0,
                    "source_end_ms": 12_000,
                },
            ],
            "vo_pickup_clip_count": 1,
        },
        skip_handoff=True,
    )

    report = reconcile_edl_with_omit_ledger(ctx)
    assert report["updated"] is False
    assert report["removed"] == []
    edl = ctx.read_json("master/edl.json")
    assert any(c.get("line_id") == "vo_layup_seg_003c" for c in edl["clips"])
    assert wav.is_file()
    assert synthesis_entry_for_line(ctx, "vo_layup_seg_003c") is not None
    from interview_mux.omit_ledger import line_is_omitted, OMIT_LEDGER_REL

    assert line_is_omitted(ctx.read_json(OMIT_LEDGER_REL), "vo_layup_seg_003c") is False


def test_reconcile_keeps_wav_backed_when_seats_empty(ctx: RunContext) -> None:
    """Seat-lag: WAV on disk + active omit, seats not yet written → keep take."""
    ledger = empty_omit_ledger()
    ledger["entries"] = [
        mint_entry(
            kind="layup_skip",
            subject_id="vo_layup_seg_003c",
            target_segment_id="seg_003",
            decision="omit",
            reason_code="spoken_copy_unhealable",
            owner_stage="nugget_layup_compose",
            compensating_path="omit_unsafe_spoken_copy",
            seq=1,
        )
    ]
    write_omit_ledger(ctx, ledger)
    wav = ctx.final_path("vo_pickup", "synthesized", "vo_layup_seg_003c.wav")
    write_fixture_vo_wav(wav)
    # No seated_line_ids — only WAV protect.
    ctx.write_json(
        "mastering/mastering_plan.json",
        {"air_script": {"vo_seats": {"seated_line_ids": [], "omitted_line_ids": []}}},
        skip_handoff=True,
    )
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_003"],
            "timeline_duration_ms": 8_000,
            "clips": [
                {
                    "type": "vo_pickup",
                    "line_id": "vo_layup_seg_003c",
                    "targets_segment_id": "seg_003",
                    "placement": "before",
                    "timeline_start_ms": 0,
                    "duration_ms": 8_000,
                    "source_path": "vo_pickup/synthesized/vo_layup_seg_003c.wav",
                }
            ],
            "vo_pickup_clip_count": 1,
        },
        skip_handoff=True,
    )
    report = reconcile_edl_with_omit_ledger(ctx)
    assert report["removed"] == []
    assert wav.is_file()
    edl = ctx.read_json("master/edl.json")
    assert any(c.get("line_id") == "vo_layup_seg_003c" for c in edl["clips"])


def test_reconcile_skips_purge_when_protect_load_fails(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = empty_omit_ledger()
    ledger["entries"] = [
        mint_entry(
            kind="layup_skip",
            subject_id="vo_layup_seg_003c",
            target_segment_id="seg_003",
            decision="omit",
            reason_code="spoken_copy_unhealable",
            owner_stage="nugget_layup_compose",
            compensating_path="omit_unsafe_spoken_copy",
            seq=1,
        )
    ]
    write_omit_ledger(ctx, ledger)
    wav = ctx.final_path("vo_pickup", "synthesized", "vo_layup_seg_003c.wav")
    write_fixture_vo_wav(wav)
    ctx.write_json(
        "master/edl.json",
        {
            "version": 1,
            "ordered_segment_ids": ["seg_003"],
            "timeline_duration_ms": 8_000,
            "clips": [
                {
                    "type": "vo_pickup",
                    "line_id": "vo_layup_seg_003c",
                    "targets_segment_id": "seg_003",
                    "placement": "before",
                    "timeline_start_ms": 0,
                    "duration_ms": 8_000,
                    "source_path": "vo_pickup/synthesized/vo_layup_seg_003c.wav",
                }
            ],
            "vo_pickup_clip_count": 1,
        },
        skip_handoff=True,
    )

    def _boom(*_a, **_k):
        raise RuntimeError("protect load boom")

    monkeypatch.setattr(
        "interview_mux.air_script.seated_vo_line_ids",
        _boom,
    )
    report = reconcile_edl_with_omit_ledger(ctx)
    assert report.get("protect_load_failed") is True
    assert report["removed"] == []
    assert wav.is_file()
