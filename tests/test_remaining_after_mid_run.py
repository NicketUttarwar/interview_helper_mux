"""Regression for remaining mid-run heals: glue promote, G1, EDL/gap, ranking, SDP, schema."""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from interview_mux.artifact_completeness import artifact_status
from interview_mux.artifact_repairs import repair_gap_report, repair_sound_design_plan
from interview_mux.deterministic_lint import _lint_optimal_questions
from interview_mux.edl_qc import _validate_vo_line_ids, _gap_vo_line_ids
from interview_mux.gap_vo_prior_context import vo_value_violations
from interview_mux.pipeline import canonical_stage_id
from interview_mux.prompt_validation import validate_artifact_write
from interview_mux.stages.assembly import _commit_edl_gap_report
from interview_mux.write_staging import (
    enter_stage_staging,
    exit_stage_staging,
    promote_glue_then_discard_stale_edl,
    staging_root,
)
from run_fixtures import isolated_run_ctx, minimal_manifest, minimal_manifest_segment, write_fixture_json


@pytest.fixture(autouse=True)
def _isolate_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVIEW_MUX_DATA_ROOT", str(tmp_path))


def _tiny_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(48_000)
        handle.writeframes(b"\x00\x00" * 4800)


def _line(**patch: object) -> dict:
    base = {
        "line_id": "vo_layup_seg_001d",
        "gap_type": "missing_setup",
        "text": "That shift rewrote who they sell to.",
        "targets_segment_id": "seg_001d",
        "placement": "before",
        "delivery": "synthesize",
        "rationale": "Seat the next clip without restating it.",
        "line_category": "context_setup",
    }
    base.update(patch)
    return base


def test_promote_glue_keeps_gap_report_when_discarding_edl(tmp_path: Path) -> None:
    """Owner pending gap_report promotes; foreign edl pending is discarded (0F)."""
    ctx = isolated_run_ctx(tmp_path, "exec_glue_promote")
    ctx.write_json(
        "understanding/gap_report.json",
        {"interviewer_lines": []},
        skip_handoff=True,
    )
    # Stage under an owner co-producer, not edl (foreign flush DENY).
    owner_root = staging_root(ctx, "gap_framing_compose")
    (owner_root / "understanding").mkdir(parents=True, exist_ok=True)
    good = {
        "interviewer_lines": [
            _line(line_id="vo_keep_001", targets_segment_id="seg_001"),
        ]
    }
    (owner_root / "understanding" / "gap_report.json").write_text(
        json.dumps(good), encoding="utf-8"
    )
    edl_root = staging_root(ctx, "edl")
    (edl_root / "understanding").mkdir(parents=True, exist_ok=True)
    (edl_root / "master").mkdir(parents=True, exist_ok=True)
    (edl_root / "understanding" / "gap_report.json").write_text(
        json.dumps({"interviewer_lines": [_line(line_id="vo_foreign_edl")]}),
        encoding="utf-8",
    )
    (edl_root / "master" / "edl.json").write_text(json.dumps({"clips": []}), encoding="utf-8")

    flush = promote_glue_then_discard_stale_edl(ctx)
    promoted = flush.get("promoted") or []
    assert any(
        "gap_framing_compose:understanding/gap_report.json" in p for p in promoted
    ), promoted
    assert not any(p.startswith("edl:understanding/gap_report") for p in promoted), promoted
    assert "edl" in (flush.get("discarded_edl") or [])
    committed = ctx.read_json("understanding/gap_report.json")
    lids = {
        str(ln.get("line_id"))
        for ln in (committed.get("interviewer_lines") or [])
        if isinstance(ln, dict)
    }
    assert "vo_keep_001" in lids
    assert "vo_foreign_edl" not in lids
    assert not (edl_root / "master" / "edl.json").is_file()


def test_edl_vo_clips_subset_of_committed_gap_report(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_edl_gap_contract")
    report = {"interviewer_lines": [_line(line_id="vo_keep_001", targets_segment_id="seg_001")]}
    # EDL is not a gap_report producer under freeze; plant via the owner path.
    write_fixture_json(ctx, "understanding/gap_report.json", report)
    enter_stage_staging("edl")
    try:
        _commit_edl_gap_report(ctx, report)
    finally:
        exit_stage_staging()
    committed = json.loads(
        ctx.final_path("understanding", "gap_report.json").read_text(encoding="utf-8")
    )
    gap_lines = _gap_vo_line_ids(ctx, committed)
    clips = [
        {
            "type": "vo_pickup",
            "line_id": "vo_keep_001",
            "targets_segment_id": "seg_001",
            "timeline_start_ms": 0,
            "duration_ms": 1000,
        }
    ]
    assert _validate_vo_line_ids(clips, gap_lines) == []
    missing = _validate_vo_line_ids(clips, _gap_vo_line_ids(ctx, {"interviewer_lines": []}))
    assert any("not found in gap_report" in e for e in missing)


def test_canonical_stage_id_maps_selection_alias() -> None:
    assert canonical_stage_id("selection") == "selection_order_sanitize"
    assert canonical_stage_id("full_master_ranking") == "full_master_ranking"


def test_sdp_banned_beds_do_not_reseed_after_drop(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_sdp_no_reseed")
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_021", "seg_030", "seg_040"]},
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment("seg_021", start_ms=0, end_ms=9000, text="overlap beat"),
            minimal_manifest_segment("seg_030", start_ms=10000, end_ms=19000, text="ok beat"),
            minimal_manifest_segment("seg_040", start_ms=20000, end_ms=29000, text="later beat"),
        ),
        skip_handoff=True,
    )
    sonic_path = Path(__file__).parent / "fixtures" / "sonic_context" / "fireside.json"
    sonic = json.loads(sonic_path.read_text(encoding="utf-8"))
    flags = sonic.setdefault("segment_flags", {})
    flags["overlap_high"] = ["seg_021"]
    flags.setdefault("trauma_adjacent", [])
    ctx.write_json("understanding/sonic_context.json", sonic, skip_handoff=True)
    sdp = {
        "version": 1,
        "assets": [{"asset_id": "m_bed", "role": "theme_underscore"}],
        "palettes": [{"palette_id": "p1", "segment_ids": ["seg_021", "seg_030", "seg_040"]}],
        "flow_plans": {
            "podcast": {
                "cues": [
                    {
                        "cue_id": "bed_bad",
                        "placement": "under_segment",
                        "segment_id": "seg_021",
                        "asset_id": "m_bed",
                    },
                    {
                        "cue_id": "bed_ok",
                        "placement": "under_segment",
                        "segment_id": "seg_030",
                        "asset_id": "m_bed",
                    },
                ]
            }
        },
    }
    repaired, notes = repair_sound_design_plan(ctx, sdp)
    assert any(isinstance(n, dict) and n.get("action") == "drop_overlap_high_bed" for n in notes)
    banned = ((repaired.get("coherence") or {}).get("banned_bed_segment_ids") or [])
    assert "seg_021" in banned
    # LLM-shaped reseed with beds back on the banned id, flags cleared — _meta must still drop.
    sonic2 = json.loads(sonic_path.read_text(encoding="utf-8"))
    flags2 = sonic2.setdefault("segment_flags", {})
    flags2["overlap_high"] = []
    flags2.setdefault("trauma_adjacent", [])
    ctx.write_json("understanding/sonic_context.json", sonic2, skip_handoff=True)
    reseeds = {
        **repaired,
        "flow_plans": {
            "podcast": {
                "cues": [
                    {
                        "cue_id": "bed_reseed",
                        "placement": "under_segment",
                        "segment_id": "seg_021",
                        "asset_id": "m_bed",
                    },
                    {
                        "cue_id": "bed_ok",
                        "placement": "under_segment",
                        "segment_id": "seg_030",
                        "asset_id": "m_bed",
                    },
                ]
            }
        },
    }
    again, notes2 = repair_sound_design_plan(ctx, reseeds)
    cues = (((again.get("flow_plans") or {}).get("podcast") or {}).get("cues") or [])
    bed_segs = {
        str(c.get("segment_id") or "")
        for c in cues
        if isinstance(c, dict)
        and str(c.get("placement") or "") == "under_segment"
        and not c.get("skip")
    }
    assert "seg_021" not in bed_segs
    assert any(isinstance(n, dict) and n.get("action") == "drop_overlap_high_bed" for n in notes2)


def test_heal_mmaudio_qa_commits_complete_when_assets_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_mmaudio_complete")
    assets = ctx.path("sound_design", "assets")
    _tiny_wav(assets / "theme_ok.wav")
    ctx.write_json(
        "sound_design/mmaudio_qa.json",
        {
            "version": 1,
            "assets": [
                {"asset_id": "theme_ok", "verdict": "pass"},
                {"asset_id": "ghost", "verdict": "pass"},
            ],
        },
        skip_handoff=True,
    )
    from interview_mux.mmaudio_asset_qa import heal_mmaudio_qa_wav_parity

    heal = heal_mmaudio_qa_wav_parity(ctx)
    assert heal["healed"] is True
    assert "ghost" in heal["dropped"]
    assert artifact_status("sound_design/mmaudio_qa.json", ctx) == "complete"


def test_spoken_copy_guard_never_serializes_json_null(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_guard_null")
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment(
                "seg_001",
                start_ms=0,
                end_ms=4000,
                text="Protein buyers rewrote the addressable market.",
            )
        ),
        skip_handoff=True,
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001"]},
        skip_handoff=True,
    )
    dirty = {
        "interviewer_lines": [
            _line(
                line_id="line_1",
                targets_segment_id="seg_001",
                spoken_copy_guard={"action": None, "script_hash": None, "context_hash": None},
            )
        ]
    }
    repaired, notes = repair_gap_report(ctx, dirty)
    assert any(
        isinstance(n, dict)
        and n.get("action") in {"drop_null", "coalesce_spoken_copy_guard_nulls"}
        and "spoken_copy_guard" in str(n.get("path") or n.get("action"))
        for n in notes
    )
    blob = json.dumps(repaired)
    for ln in repaired.get("interviewer_lines") or []:
        if not isinstance(ln, dict):
            continue
        guard = ln.get("spoken_copy_guard")
        assert guard is not None or "spoken_copy_guard" not in ln
        if isinstance(guard, dict):
            assert None not in guard.values()
    assert '"spoken_copy_guard": null' not in blob
    assert validate_artifact_write("understanding/gap_report.json", repaired) == []


def test_high_gap_parent_covered_by_child_preface(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_high_gap_parent")
    ctx.write_json(
        "understanding/gap_evaluations.json",
        {
            "evaluations": [
                {
                    "segment_id": "seg_070",
                    "self_explanatory": False,
                    "severity": "high",
                    "gap_type": "missing_setup",
                    "listener_confusion": "who is speaking",
                }
            ]
        },
        skip_handoff=True,
    )
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment(
                "seg_070",
                start_ms=0,
                end_ms=8000,
                text="Parent beat about the acquisition.",
            ),
            minimal_manifest_segment(
                "seg_070d",
                start_ms=0,
                end_ms=4000,
                text="Child cut of the acquisition beat.",
                parent_segment_id="seg_070",
            ),
        ),
        skip_handoff=True,
    )
    lines = [
        _line(
            line_id="vo_preface_seg_070d",
            targets_segment_id="seg_070d",
            text="Who is on the other side of that deal?",
            line_category="episode_preface",
        )
    ]
    errors = _lint_optimal_questions({"interviewer_lines": lines}, ctx)
    assert not any("has no interviewer line" in e for e in errors)


def test_last_sentence_overlap_is_rewritten_or_skipped(tmp_path: Path) -> None:
    ctx = isolated_run_ctx(tmp_path, "exec_overlap_rewrite")
    target = (
        "Cell biopsy is next-generation liquid biopsy and we scaled it across hospitals."
    )
    ctx.write_json(
        "segments/manifest.json",
        minimal_manifest(
            minimal_manifest_segment(
                "seg_001d",
                start_ms=0,
                end_ms=6000,
                text=target,
            )
        ),
        skip_handoff=True,
    )
    ctx.write_json(
        "master/selection.json",
        {"ordered_segment_ids": ["seg_001d"]},
        skip_handoff=True,
    )
    dirty = {
        "nugget_layup_authority": True,
        "interviewer_lines": [
            _line(
                origin="nugget_layup",
                text=(
                    "That shift rewrote who they sell to. "
                    "Cell biopsy is next-generation liquid biopsy and we scaled it across hospitals."
                ),
            )
        ],
    }
    repaired, notes = repair_gap_report(ctx, dirty)
    assert any(
        isinstance(n, dict)
        and n.get("action") in {"repair_last_sentence_overlap", "skip_last_sentence_overlap", "repair_last_sentence_layup"}
        for n in notes
    )
    lines = [ln for ln in (repaired.get("interviewer_lines") or []) if isinstance(ln, dict)]
    segs = {"seg_001d": {"text": target}}
    errs = vo_value_violations(lines, segments_by_id=segs, ordered_ids=["seg_001d"])
    assert not any("last sentence restates" in e for e in errs)
