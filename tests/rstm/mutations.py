"""Mutation suite M1–M10 for RSTM cells (HEAD identify+execute, mock only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from interview_mux.run_context import RunContext

MutationFn = Callable[[RunContext], None]


def m_none(ctx: RunContext) -> None:
    return None


def m_empty_array(ctx: RunContext) -> None:
    path = ctx.run_dir / "understanding" / "gap_evaluations.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"evaluations": [], "schema_version": 1}))


def m_hollow_object(ctx: RunContext) -> None:
    path = ctx.run_dir / "mastering" / "plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")


def m_stale_ids(ctx: RunContext) -> None:
    path = ctx.run_dir / "segments" / "boundaries.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "boundaries": [
                    {"segment_id": "seg_MISSING", "start_ms": 0, "end_ms": 1000}
                ],
            }
        )
    )


def m_stage_done_without_primary(ctx: RunContext) -> None:
    done = ctx.run_dir / ".stage_done"
    done.mkdir(parents=True, exist_ok=True)
    (done / "edl").write_text("hollow\n")
    edl = ctx.run_dir / "master" / "edl.json"
    if edl.exists():
        edl.unlink()


def m_pending_shadow(ctx: RunContext) -> None:
    pending = ctx.run_dir / ".pending_writes"
    pending.mkdir(parents=True, exist_ok=True)
    (pending / "master__edl.json").write_text(json.dumps({"events": [], "shadow": True}))


def m_thin_plan(ctx: RunContext) -> None:
    path = ctx.run_dir / "mastering" / "plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "narrative_mode": "sparse_source",
                "ordered_segment_ids": [],
                "candidates_picked": 0,
            }
        )
    )


def m_seated_vo_no_wav(ctx: RunContext) -> None:
    path = ctx.run_dir / "mastering" / "plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc: dict[str, Any] = {}
    if path.exists():
        try:
            doc = json.loads(path.read_text())
        except Exception:
            doc = {}
    doc.setdefault("air_script", {})
    doc["air_script"]["vo_seats"] = [
        {"seat_id": "seat_rstm", "line_id": "line_rstm", "wav_path": "vo_pickup/missing.wav"}
    ]
    path.write_text(json.dumps(doc))


def m_uncommitted_master(ctx: RunContext) -> None:
    master = ctx.run_dir / "master"
    master.mkdir(parents=True, exist_ok=True)
    (master / "master.wav").write_bytes(b"RIFF" + b"\x00" * 64)
    commit = master / "master_commitment.json"
    if commit.exists():
        commit.unlink()


def m_id_remap(ctx: RunContext) -> None:
    path = ctx.run_dir / "segments" / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "segments": [
                    {"segment_id": "seg_REMAPPED", "start_ms": 0, "end_ms": 500}
                ],
            }
        )
    )


MUTATIONS: dict[str, MutationFn] = {
    "M1_none": m_none,
    "M2_empty_array": m_empty_array,
    "M3_hollow_object": m_hollow_object,
    "M4_stale_ids": m_stale_ids,
    "M5_stage_done_without_primary": m_stage_done_without_primary,
    "M6_pending_shadow": m_pending_shadow,
    "M7_thin_plan": m_thin_plan,
    "M8_seated_vo_no_wav": m_seated_vo_no_wav,
    "M9_uncommitted_master": m_uncommitted_master,
    "M10_id_remap": m_id_remap,
}

HIGH_YIELD = (
    "M1_none",
    "M5_stage_done_without_primary",
    "M6_pending_shadow",
    "M8_seated_vo_no_wav",
    "M9_uncommitted_master",
    "M3_hollow_object",
)
