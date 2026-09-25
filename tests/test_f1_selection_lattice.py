"""F1 selection lattice: drop CTA/orphan from air; stale stamp probe; specialist write-through.

Fixture shape from exec_11165 (CTA parent + ghost seg_069 keep, specialist cache
lost on ranking abort). Does not resume that run.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from interview_mux.artifact_sanitize.reentry import stamp_matches
from interview_mux.artifact_sanitize.selection import selection_sanitary_errors
from interview_mux.llm_specialists import (
    _persist_specialist_output,
    maybe_run_pre_stage_specialists,
)
from interview_mux.selection_constraints import seal_selection_lattice
from interview_mux.write_staging import (
    discard_stage_writes,
    enter_stage_staging,
    exit_stage_staging,
)
from run_fixtures import isolated_run_ctx

_FIX = Path(__file__).resolve().parent / "fixtures" / "f1_selection_lattice"
_SPEC_REL = (
    "understanding/stage_runs/full_master_ranking/"
    "specialist_stt_lexicon_island_verify.json"
)
_PILOT_CFG = {
    "analysis": {
        "specialists": {
            "enabled": True,
            "pilot_stages": ["full_master_ranking"],
        }
    }
}


def _homunculus(ctx) -> None:
    ctx.write_json(
        "run_meta.json",
        {"homunculus_version": "0.1.0", "homunculus_kind": "homunculus"},
        skip_handoff=True,
    )


def _write_raw(ctx, rel: str, data: dict) -> None:
    path = ctx.final_path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _plant_lattice(ctx) -> dict:
    segs = json.loads((_FIX / "segments.json").read_text(encoding="utf-8"))
    cuts = json.loads((_FIX / "ideal_cuts.json").read_text(encoding="utf-8"))
    sel = json.loads((_FIX / "selection_cta_orphan.json").read_text(encoding="utf-8"))
    ctx.write_json("segments/manifest.json", segs, skip_handoff=True)
    _write_raw(ctx, "understanding/ideal_cuts.json", cuts)
    _write_raw(ctx, "master/selection.json", sel)
    return sel


def test_seal_drops_cta_and_orphan_without_raising(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "f1_seal_cta_orphan")
    _homunculus(ctx)
    sel = _plant_lattice(ctx)
    sealed = seal_selection_lattice(ctx, sel, fail_closed=True)
    ordered = [str(s) for s in (sealed.get("ordered_segment_ids") or [])]
    assert "seg_022" in ordered
    assert "seg_001" not in ordered
    assert "seg_069" not in ordered


def test_stale_stamp_cosmetic_ok_without_off_bus_write(tmp_path) -> None:
    """S2: stale stamp + cosmetic-only dry sanitize → sanitary; no disk write."""
    ctx = isolated_run_ctx(tmp_path, "f1_stamp_no_write")
    ctx.write_json(
        "segments/manifest.json",
        json.loads((_FIX / "segments.json").read_text(encoding="utf-8")),
        skip_handoff=True,
    )
    doc = {
        "ordered_segment_ids": ["seg_022"],
        "order_content_hash": "fresh-order",
        "excluded_segment_ids": [],
        "chapters": [],
        "_meta": {
            "sanitize": {
                "ok": True,
                "after_count": 2,
                "hash": "stale-hash-not-matching",
                "source": "artifact_sanitize.selection",
            }
        },
    }
    ctx._one_writer_raw = True
    ctx.write_json("master/selection.json", doc, skip_handoff=True)
    before = ctx.read_json("master/selection.json")
    assert selection_sanitary_errors(ctx) == []
    after = ctx.read_json("master/selection.json")
    # Probe must not restamp off-bus; stage commit owns stamp refresh.
    assert (after.get("_meta") or {}).get("sanitize") == (
        (before.get("_meta") or {}).get("sanitize")
    )
    assert not stamp_matches(
        after, content_keys=["ordered_segment_ids", "order_content_hash"]
    )


def test_specialist_write_through_survives_pending_discard(tmp_path) -> None:
    ctx = isolated_run_ctx(tmp_path, "f1_specialist_write_through")
    env = json.loads((_FIX / "specialist_envelope.json").read_text(encoding="utf-8"))
    enter_stage_staging("full_master_ranking")
    try:
        _persist_specialist_output(
            ctx,
            stage_key="full_master_ranking",
            spec_key="stt_lexicon_island_verify",
            env=env,
        )
        shadow = ctx.path(
            "understanding",
            "stage_runs",
            "full_master_ranking",
            "would_die.json",
        )
        shadow.parent.mkdir(parents=True, exist_ok=True)
        shadow.write_text("{}", encoding="utf-8")
        discard_stage_writes(ctx, "full_master_ranking")
    finally:
        exit_stage_staging()
    assert ctx.artifact_exists(_SPEC_REL)
    assert not shadow.exists()
    with patch("interview_mux.llm_specialists.run_specialist") as mock_run:
        mock_run.side_effect = AssertionError("must reuse committed specialist cache")
        outputs = maybe_run_pre_stage_specialists(
            ctx,
            "full_master_ranking",
            {"segments": {}},
            cfg=_PILOT_CFG,
        )
        mock_run.assert_not_called()
    assert outputs and outputs[0].get("cached") is True
