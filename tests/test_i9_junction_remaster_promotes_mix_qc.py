"""Cascade: junction remaster must promote mix QC side effects (exec_13159).

When remaster_mix_only runs under junction staging, mix writes
``master/music_cue_coverage.json`` (and related QC) into pending. StageInfo for
junction does not claim those paths, so flush would drop them and PMQ fails
``planned_music_preserved`` / ``episode_close_outro_present``.
"""

from __future__ import annotations

import json

from interview_mux.defect_ledger import (
    defect_summary,
    open_ship_bar_defects,
    record_defect,
    reconcile_defects_for_completed_stages,
)
from interview_mux.junction_snip_qa import remaster_mix_only
from interview_mux.post_master_quality import evaluate_post_master_quality
from interview_mux.write_staging import (
    enter_stage_staging,
    exit_stage_staging,
    promote_staged_side_effects,
    staging_root,
)
from run_fixtures import isolated_run_ctx


_MIX_QC_SIDE_EFFECTS = (
    "master/music_cue_coverage.json",
    "master/listen_critic.json",
    "master/bed_presence_qc.json",
    "master/underbed_ab_qc.json",
    "master/listenability_contract.json",
)


def test_remaster_mix_only_requests_mix_qc_side_effect_promote(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "i9_promote_coverage_spy")
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "edl.json").write_text(
        json.dumps(
            {
                "version": 1,
                "ordered_segment_ids": ["seg_001"],
                "clips": [
                    {
                        "type": "speech",
                        "segment_id": "seg_001",
                        "start_ms": 0,
                        "end_ms": 1000,
                    }
                ],
                "order_content_hash": "abc",
            }
        ),
        encoding="utf-8",
    )

    promoted_batches: list[tuple[str, ...]] = []

    def _spy_promote(ctx_, rels, *, stage_id=None):
        promoted_batches.append(tuple(rels))
        return list(rels)

    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.refuse_mix_if_live_incomplete_cuts",
        lambda _ctx: None,
    )
    monkeypatch.setattr(
        "interview_mux.stages.assembly.run_mix",
        lambda _ctx: _ctx.final_path("master", "assembly.wav"),
    )
    monkeypatch.setattr(
        "interview_mux.assembly_ledger.write_assembly_ledger",
        lambda _ctx: {"complete": True, "naked_seam_count": 0},
    )
    monkeypatch.setattr(
        "interview_mux.seam_autopsy.write_render_ledger",
        lambda _ctx: None,
    )
    monkeypatch.setattr(
        "interview_mux.air_order.ensure_assembly_mtime_seats_edl",
        lambda _ctx: None,
    )
    monkeypatch.setattr(
        "interview_mux.write_staging.promote_staged_side_effects",
        _spy_promote,
    )
    # remaster imports promote from write_staging into its module namespace at call time
    monkeypatch.setattr(
        "interview_mux.junction_snip_qa.promote_staged_side_effects",
        _spy_promote,
        raising=False,
    )

    remaster_mix_only(ctx)

    assert promoted_batches, "remaster_mix_only must promote side effects"
    flat = {rel for batch in promoted_batches for rel in batch}
    for rel in _MIX_QC_SIDE_EFFECTS:
        assert rel in flat, f"missing side-effect promote: {rel}"


def test_junction_promote_commits_music_cue_coverage_from_pending(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "i9_promote_coverage_commit")
    enter_stage_staging("junction_snip_qa")
    try:
        root = staging_root(ctx, "junction_snip_qa")
        master = root / "master"
        master.mkdir(parents=True, exist_ok=True)
        (master / "music_cue_coverage.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "preserved": True,
                    "missing_asset_ids": [],
                    "shortened_preserved_asset_ids": [],
                    "realized_cues": [
                        {
                            "asset_id": "show_theme_v1_full_bed_close",
                            "music_role": "theme_outro",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        promoted = promote_staged_side_effects(
            ctx,
            ("master/music_cue_coverage.json", "master/listen_critic.json"),
            stage_id="junction_snip_qa",
        )
    finally:
        exit_stage_staging()

    assert "master/music_cue_coverage.json" in promoted
    assert ctx.artifact_exists("master/music_cue_coverage.json")
    cov = ctx.read_json("master/music_cue_coverage.json")
    assert cov.get("preserved") is True


def test_pmq_reconciles_stale_ship_bar_defects_for_done_stages(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "i9_defect_reconcile")
    (ctx.run_dir / "master").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "master" / "edl.json").write_text(
        json.dumps({"version": 1, "clips": [], "ordered_segment_ids": []}),
        encoding="utf-8",
    )
    (ctx.run_dir / "master" / "master.wav").write_bytes(b"RIFF" + b"\0" * 64)

    record_defect(
        ctx,
        stage="edl",
        blocker="attempt_memo",
        artifact="master/edl.json",
    )
    record_defect(
        ctx,
        stage="mix",
        blocker="max_mix_cycles",
        artifact="master/assembly.wav",
    )
    record_defect(
        ctx,
        stage="listen_delight_audit",
        blocker="missing_hard_input",
        artifact="mastering/listen_delight_audit.json",
    )
    assert open_ship_bar_defects(ctx)

    # Stamp done without mark_done (simulates heal restamp that skipped resolve).
    for sid in (
        "edl",
        "mix",
        "assembly_preview",
        "listen_delight_audit",
        "master_finalize",
    ):
        (ctx.run_dir / ".stage_done" / sid).touch()

    assert open_ship_bar_defects(ctx)

    quality = evaluate_post_master_quality(ctx)
    ship_bar = next(
        c for c in quality["checks"] if c["check_id"] == "no_open_ship_bar_defects"
    )
    assert ship_bar["passed"] is True
    assert defect_summary(ctx)["open_ship_bar"] == 0
