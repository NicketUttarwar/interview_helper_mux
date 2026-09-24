"""i7: omit-ledger layup_skip must clear G1 under hard freeze (exec_13177).

Producer: stamp_gap_report_omit_skips used a non-End-A gate reason, so soft/hard
freeze no-op'd the gap skipped_optional stamp while check_g1_vo still demanded
WAVs for ledger-omitted synthesize lines → vo_synthesize no_delta thrash.
"""

from __future__ import annotations

from interview_mux.gates import check_g1_vo, _G1_VO_CACHE
from interview_mux.omit_ledger import (
    OMIT_LEDGER_REL,
    empty_omit_ledger,
    mint_entry,
    stamp_gap_report_omit_skips,
    write_omit_ledger,
)
from interview_mux.run_context import RunContext
from interview_mux.seat_authority import persist_frozen_seat_doc
from run_fixtures import isolated_run_ctx


def _seed_hard_freeze(ctx: RunContext) -> None:
    meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    if not isinstance(meta, dict):
        meta = {}
    epoch = dict(meta.get("delivery_epoch") or {})
    epoch["vo_seats_freeze"] = {
        "soft": True,
        "hard": True,
        "level": "hard",
        "fingerprint": "i7test",
        "hard_at": "2026-09-23T00:00:00Z",
        "hard_reason": "vo_synthesize",
        "generation": 1,
        "rewrite_generations_post_hard": 24,
    }
    meta["delivery_epoch"] = epoch
    ctx.write_json("run_meta.json", meta)


def _gap_line(line_id: str, seg: str) -> dict:
    # Avoid spoken scaffolding tokens ("Host …") — sanitize would skip_optional.
    return {
        "line_id": line_id,
        "targets_segment_id": seg,
        "delivery": "synthesize",
        "severity": "blocking",
        "required": True,
        "gap_type": "nugget_layup",
        "placement": "before",
        "text": f"Precision oncology setup before {seg}.",
        "voice_speaker_id": "spk_1",
        "origin": "nugget_layup",
    }


def test_check_g1_honors_omit_ledger_without_gap_skip_flags(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_i7_g1_ledger")
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                _gap_line("vo_layup_seg_003b", "seg_003b"),
                _gap_line("vo_layup_seg_037", "seg_037"),
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": ["vo_layup_seg_037"],
                    "omitted_line_ids": [],
                }
            }
        },
        skip_handoff=True,
    )
    ledger = empty_omit_ledger()
    ledger["entries"] = [
        mint_entry(
            kind="layup_skip",
            subject_id="vo_layup_seg_003b",
            target_segment_id="seg_003b",
            decision="omit",
            reason_code="self_explanatory_native",
            owner_stage="nugget_layup_compose",
            compensating_path="native answers already orient",
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
    _G1_VO_CACHE.clear()
    missing = check_g1_vo(ctx)
    assert "vo_layup_seg_003b" not in missing
    assert missing == ["vo_layup_seg_037"]


def test_stamp_gap_omit_skips_lands_under_hard_freeze_end_a(tmp_path):
    ctx = isolated_run_ctx(tmp_path, "exec_i7_stamp_freeze")
    # Artifacts first, then freeze — freeze blocks ordinary write_json to gap.
    ctx.write_json(
        "understanding/gap_report.json",
        {
            "interviewer_lines": [
                _gap_line("vo_layup_seg_003b", "seg_003b"),
                _gap_line("vo_layup_seg_010", "seg_010"),
                _gap_line("vo_layup_seg_037", "seg_037"),
            ]
        },
        skip_handoff=True,
    )
    ledger = empty_omit_ledger()
    ledger["entries"] = [
        mint_entry(
            kind="layup_skip",
            subject_id="vo_layup_seg_003b",
            target_segment_id="seg_003b",
            decision="omit",
            reason_code="self_explanatory_native",
            owner_stage="nugget_layup_compose",
            compensating_path="native",
            seq=1,
        ),
        mint_entry(
            kind="layup_skip",
            subject_id="vo_layup_seg_010",
            target_segment_id="seg_010",
            decision="omit",
            reason_code="native_self_orients",
            owner_stage="nugget_layup_compose",
            compensating_path="native",
            seq=2,
        ),
    ]
    ledger["summary"] = {
        "active_count": 2,
        "by_kind": {"layup_skip": 2},
        "compensated_count": 2,
        "unresolved_high_salience": 0,
    }
    write_omit_ledger(ctx, ledger)
    assert ctx.artifact_exists(OMIT_LEDGER_REL)

    _seed_hard_freeze(ctx)

    stamped = stamp_gap_report_omit_skips(ctx)
    assert stamped >= 2

    gap = ctx.read_json("understanding/gap_report.json")
    by = {
        str(r.get("line_id")): r
        for r in (gap.get("interviewer_lines") or [])
        if isinstance(r, dict)
    }
    assert by["vo_layup_seg_003b"].get("skipped_optional") is True
    assert by["vo_layup_seg_010"].get("skipped_optional") is True
    assert not by["vo_layup_seg_037"].get("skipped_optional")

    ctx.write_json(
        "mastering/mastering_plan.json",
        {
            "air_script": {
                "vo_seats": {
                    "seated_line_ids": ["vo_layup_seg_037"],
                    "omitted_line_ids": [],
                }
            }
        },
        skip_handoff=True,
    )
    # Ensure freeze cannot clobber plan seed; persist if needed.
    if not ctx.artifact_exists("mastering/mastering_plan.json"):
        persist_frozen_seat_doc(
            ctx,
            "mastering/mastering_plan.json",
            {
                "air_script": {
                    "vo_seats": {
                        "seated_line_ids": ["vo_layup_seg_037"],
                        "omitted_line_ids": [],
                    }
                }
            },
            reason="stamp_gap_omit_flags",
            skip_handoff=True,
        )
    _G1_VO_CACHE.clear()
    missing = check_g1_vo(ctx)
    assert "vo_layup_seg_003b" not in missing
    assert "vo_layup_seg_010" not in missing
    assert missing == ["vo_layup_seg_037"]
